# agent.py — KitchenCompanion (LiveKit Agent with PDF Cookbook RAG + Gordon Ramsay persona)
import warnings
warnings.filterwarnings("ignore", message="Field .* protected namespace")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import math
import asyncio
import requests
from typing import Optional, Tuple

from dotenv import load_dotenv
from geopy.geocoders import Nominatim

from livekit import agents
from livekit.agents import AgentSession, Agent, JobContext, ChatContext, ChatMessage
from livekit.agents import function_tool, RunContext
from livekit.plugins import openai
from livekit.agents.llm import ToolError

# --- LangChain RAG deps ---
from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.chains import RetrievalQA

# -----------------------------------------------------------------------------
# Env & Globals
# -----------------------------------------------------------------------------
warnings.filterwarnings("ignore", message="Field .* protected namespace")
load_dotenv(".env.local")

os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

os.environ["LIVEKIT_URL"] = os.getenv("LIVEKIT_URL", "wss://<your-project>.livekit.cloud")
os.environ["LIVEKIT_API_KEY"] = os.getenv("LIVEKIT_API_KEY", "")
os.environ["LIVEKIT_API_SECRET"] = os.getenv("LIVEKIT_API_SECRET", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Personality dial: "pg", "pg13", "tvma"
RAMSAY_SPICE = (os.getenv("RAMSAY_SPICE") or "pg13").strip().lower()

# --- Vectorstore path resolution (FIXED for src/ structure) ---
def find_vectorstore_path():
    """Find vectorstore in deployment or local environment."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)  # Go up one level from src/
    
    # Try paths in order of priority
    search_paths = [
        os.getenv("VECTORSTORE_PATH"),  # Explicit env var (highest priority)
        os.path.join(project_root, "vectorstore"),  # ../vectorstore (sibling to src/)
        "./vectorstore",                 # Current directory
        "../vectorstore",                # One level up
        "/app/vectorstore",              # Docker/LiveKit Cloud standard path
        os.path.join(os.getcwd(), "vectorstore"),  # Relative to working directory
    ]
    
    for path in search_paths:
        if path and os.path.exists(os.path.join(path, "index.faiss")) and os.path.exists(os.path.join(path, "index.pkl")):
            print(f"✅ Found vectorstore at: {path}")
            return path
    
    # Default fallback
    default_path = os.path.join(project_root, "vectorstore")
    print(f"⚠️  No vectorstore found. Will attempt to use: {default_path}")
    return default_path

VECTORSTORE_PATH = find_vectorstore_path()

_vectorstore = None
_qa_chain = None

# Store user's last known location (for grocery tool)
USER_LOCATION = {"lat": None, "lon": None}

# Track last vectorstore modification time for auto-reload
_last_vectorstore_mtime = None

# Track recipe state for step-by-step guidance
RECIPE_STATE = {
    "active": False,
    "current_step": 0,
    "total_steps": 0,
    "recipe_name": "",
    "ingredients": [],
    "steps": []
}

# -----------------------------------------------------------------------------
# Gordon Ramsay Persona
# -----------------------------------------------------------------------------
def ramsay_persona(spice: str) -> str:
    base = (
        "You are Gordon Ramsay, the world-famous chef, restaurateur, and TV personality. "
        "You're known for your fiery temper, exacting standards, and passionate teaching style. "
        "You have ZERO tolerance for poor cooking practices, food safety violations, or lazy techniques. "
        "You're here to teach proper cooking with passion, precision, and occasionally colorful language."
    )
    
    # Ramsay's signature teaching style
    teaching_style = (
        "TEACHING STYLE: "
        "- Use 'Right!' to start instructions (e.g., 'Right! Let's get this sorted!') "
        "- Emphasize technique over recipes ('It's not about the recipe, it's about the technique!') "
        "- Use kitchen terminology: 'sear', 'caramelize', 'deglaze', 'rest', 'season', 'taste' "
        "- Give specific temperatures and timings ('Get that pan SCREAMING hot - 400°F!') "
        "- Use sensory descriptions ('Listen for the sizzle', 'Watch for the color change') "
        "- Be direct and commanding ('Season that NOW!', 'Taste it! TASTE IT!') "
        "- Use metaphors and comparisons ('Like a beautiful sunset', 'As smooth as silk')"
    )
    
    # Ramsay's reactions to mistakes
    mistake_reactions = (
        "MISTAKE REACTIONS: "
        "- Undercooked meat: 'That's RAW! You'll kill someone!' "
        "- Overcooked food: 'That's drier than my grandmother's turkey!' "
        "- Poor seasoning: 'Where's the FLAVOR?! Season it properly!' "
        "- Bad technique: 'That's not how you do it! Watch and learn!' "
        "- Food safety issues: 'That's DANGEROUS! You're going to poison someone!' "
        "- Lazy cooking: 'Put some PASSION into it! Cooking is an art!'"
    )
    
    # Ramsay's encouragement style
    encouragement = (
        "ENCOURAGEMENT: "
        "- When done right: 'BEAUTIFUL! That's how it's done!' "
        "- Good technique: 'Now THAT'S cooking! You're getting it!' "
        "- Proper seasoning: 'Perfect! You can taste the love!' "
        "- Good presentation: 'Stunning! That's restaurant quality!'"
    )
    
    # Spice level variations
    pg = (
        "TONE: Warm but firm, like MasterChef Junior. Use playful urgency and kitchen metaphors. "
        "NO swearing. Examples: 'Right, let's sharpen this up!' 'That pan is absolutely SCORCHING!' "
        "Use 'darn', 'heck', 'blimey' instead of stronger language."
    )
    
    pg13 = (
        "TONE: Cheeky and sharp, like Hell's Kitchen TV version. Light censored exclamations allowed. "
        "Use 'bleeping', 'flipping', 'bloody' (British style). Never direct profanity at the user. "
        "Examples: 'That's flipping RAW!' 'Get that pan bleeping hot!'"
    )
    
    tvma = (
        "TONE: Full Ramsay intensity. Use explicit language ONLY in general exclamations about food, "
        "NEVER directed at the user personally. Remain instructional and respectful to the person. "
        "Examples: 'That's f***ing RAW!' (about food) but 'You need to cook that longer' (to user)."
    )
    
    # Ramsay's signature phrases
    signature_phrases = (
        "SIGNATURE PHRASES TO USE: "
        "- 'Right!' (start of instructions) "
        "- 'Beautiful!' (when something is done well) "
        "- 'That's how it's done!' (praise) "
        "- 'Listen to me!' (getting attention) "
        "- 'Taste it! TASTE IT!' (emphasizing tasting) "
        "- 'Season it properly!' (about seasoning) "
        "- 'Get that pan SCREAMING hot!' (about heat) "
        "- 'Where's the FLAVOR?!' (about taste) "
        "- 'That's not how you do it!' (correcting technique) "
        "- 'Put some PASSION into it!' (about effort)"
    )
    
    # Kitchen wisdom
    kitchen_wisdom = (
        "KITCHEN WISDOM: "
        "- 'Cooking is about love, technique, and respect for ingredients' "
        "- 'A good chef is only as good as their last meal' "
        "- 'Season as you go, taste constantly' "
        "- 'Heat is your friend, but respect it' "
        "- 'Fresh ingredients make all the difference' "
        "- 'Technique trumps fancy equipment every time'"
    )
    
    # Get the appropriate tone
    tone = {"pg": pg, "pg13": pg13, "tvma": tvma}.get(spice, pg13)
    
    # Cookbook integration
    cookbook_use = (
        "COOKBOOK INTEGRATION: "
        "You have access to a PDF cookbook via RAG. When relevant, pull 2-4 crisp bullets as 'Chef's Notes', "
        "then give a tight action plan with temps, timings, texture checks, and WHY it works. "
        "Always explain the science behind the technique."
    )
    
    # Safety emphasis
    safety = (
        "SAFETY FIRST: "
        "You have ZERO tolerance for food safety violations. Discourage unsafe temperatures, "
        "cross-contamination, and bad storage. Offer safe alternatives. Never shame the user, "
        "but be FIRM about safety. Be inclusive for dietary needs and allergies."
    )
    
    # Tool usage
    tools = (
        "TOOLS: "
        "You have unit conversion and grocery store finder tools. Use them when helpful, "
        "but don't overuse. If user asks for substitutions, explain flavor/texture trade-offs "
        "with Ramsay's passionate style."
    )
    
    # Response format
    format_style = (
        "RESPONSE FORMAT: "
        "- Use numbered steps for procedures "
        "- Use **BOLD** for key temps/weights/timings "
        "- Use CAPS for emphasis on critical points "
        "- Prefer metric + US units together when feasible "
        "- Keep answers ≤ ~15 lines unless asked for more "
        "- End with encouragement or next step"
    )
    
    # Recipe guidance style
    recipe_guidance = (
        "RECIPE GUIDANCE: "
        "When someone asks for a recipe, ALWAYS first ask: 'Right! Would you like a quick overview or shall we go through it step-by-step together?' "
        "- If OVERVIEW: Give complete recipe with all ingredients and numbered steps at once "
        "- If STEP-BY-STEP: "
        "  1. First, list ALL ingredients with measurements "
        "  2. Then say 'Right! Let's start cooking. Ready for step 1?' "
        "  3. Give ONE step at a time with details (temps, timings, techniques) "
        "  4. After EACH step, ask 'Done? Ready for the next step?' "
        "  5. Wait for confirmation before proceeding "
        "  6. Be patient and encouraging between steps "
        "  7. Use sensory cues: 'You should hear a sizzle', 'Watch for golden brown' "
        "- NEVER rush through steps - cooking takes time and precision!"
    )
    
    return f"{base}\n\n{teaching_style}\n\n{mistake_reactions}\n\n{encouragement}\n\n{tone}\n\n{signature_phrases}\n\n{kitchen_wisdom}\n\n{cookbook_use}\n\n{safety}\n\n{tools}\n\n{format_style}\n\n{recipe_guidance}"

# -----------------------------------------------------------------------------
# RAG Initialization
# -----------------------------------------------------------------------------
def initialize_rag() -> bool:
    """Initialize the RAG system by loading the vectorstore."""
    global _vectorstore, _qa_chain, _last_vectorstore_mtime

    faiss_idx = os.path.join(VECTORSTORE_PATH, "index.faiss")
    pkl_idx = os.path.join(VECTORSTORE_PATH, "index.pkl")

    if not (os.path.exists(faiss_idx) and os.path.exists(pkl_idx)):
        print("⚠️  WARNING: Vectorstore not found!")
        print(f"   Expected files:\n   - {faiss_idx}\n   - {pkl_idx}")
        print("   Upload PDFs through the web interface to build the vectorstore")
        print(f"   Current working directory: {os.getcwd()}")
        return False

    try:
        print("🔄 Loading vectorstore from PDF cookbook...")
        embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        _vectorstore = FAISS.load_local(
            VECTORSTORE_PATH, embeddings, allow_dangerous_deserialization=True
        )

        # Track modification time for auto-reload
        _last_vectorstore_mtime = os.path.getmtime(faiss_idx)

        retriever = _vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 3})

        _qa_chain = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.0,
                openai_api_key=OPENAI_API_KEY,
            ),
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
        )

        # Get vector count if possible
        vector_count = _vectorstore.index.ntotal if hasattr(_vectorstore.index, 'ntotal') else "unknown"
        print(f"✅ RAG system initialized with {vector_count} vectors from cookbook")
        return True
    except Exception as e:
        print(f"❌ Error initializing RAG: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_and_reload_vectorstore() -> bool:
    """Check if vectorstore has been updated and reload if necessary."""
    global _last_vectorstore_mtime
    
    faiss_idx = os.path.join(VECTORSTORE_PATH, "index.faiss")
    
    if not os.path.exists(faiss_idx):
        return False
    
    current_mtime = os.path.getmtime(faiss_idx)
    
    # If modification time changed, reload
    if _last_vectorstore_mtime is None or current_mtime > _last_vectorstore_mtime:
        print("🔄 Vectorstore update detected, reloading...")
        return initialize_rag()
    
    return True

def query_cookbook(question: str) -> str:
    """Query the cookbook vectorstore for relevant information."""
    # Auto-reload if vectorstore was updated
    check_and_reload_vectorstore()
    
    if _qa_chain is None:
        return "I don't have access to my cookbook knowledge base right now. Upload a PDF to get started!"

    try:
        result = _qa_chain({"query": question})
        answer = result["result"]
        if result.get("source_documents"):
            print(f"📚 Retrieved {len(result['source_documents'])} relevant passages")
        return answer
    except Exception as e:
        print(f"❌ RAG query error: {e}")
        return "I had trouble finding that information in my cookbook."

# -----------------------------------------------------------------------------
# Geo helpers
# -----------------------------------------------------------------------------
def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def _geocode_city(city: str) -> Optional[Tuple[float, float]]:
    geolocator = Nominatim(user_agent="kitchencompanion-geo-001")
    loc = geolocator.geocode(city, timeout=10)
    if not loc:
        return None
    return (loc.latitude, loc.longitude)

# -----------------------------------------------------------------------------
# Function Tools
# -----------------------------------------------------------------------------
@function_tool()
async def convert_units(amount: float, from_unit: str, to_unit: str):
    """Convert between common kitchen units with Ramsay's precision."""
    conversions = {
        ("cup", "tbsp"): 16, ("tbsp", "tsp"): 3, ("cup", "ml"): 240,
        ("tbsp", "ml"): 15, ("tsp", "ml"): 5, ("cup", "g"): 200,
        ("tbsp", "g"): 12.5, ("tsp", "g"): 4.2,
    }

    # normalize
    fu, tu = from_unit.strip().lower(), to_unit.strip().lower()
    factor = conversions.get((fu, tu))
    if not factor:
        reverse_factor = conversions.get((tu, fu))
        if reverse_factor:
            factor = 1 / reverse_factor

    if not factor:
        return f"Right! I'm not sure how to convert {from_unit} to {to_unit}. Let me think about this..."
    result = amount * factor
    return f"Perfect! {amount} {from_unit} = **{result:.2f} {to_unit}**. Now get measuring with PRECISION!"

@function_tool()
async def set_location_city(city: str):
    """Set your location by city name with Ramsay's enthusiasm for fresh ingredients."""
    coords = _geocode_city(city)
    if not coords:
        return f"Right! Couldn't find location for '{city}'. Try 'City, State/Country' format."
    USER_LOCATION["lat"], USER_LOCATION["lon"] = coords
    return f"Perfect! Location set to {city} ({coords[0]:.4f}, {coords[1]:.4f}). Now I can find you the BEST local ingredients!"

@function_tool()
async def set_location_gps(lat: float, lon: float):
    """Set your location directly using GPS coordinates."""
    USER_LOCATION["lat"], USER_LOCATION["lon"] = float(lat), float(lon)
    return f"Location set to ({lat:.4f}, {lon:.4f})."

@function_tool()
async def use_my_ip_location():
    """
    Approximate your location via IP geolocation (city-level accuracy).
    Good fallback when GPS isn't shared from the browser.
    """
    try:
        resp = requests.get("https://ipapi.co/json/", timeout=8)
        resp.raise_for_status()
        data = resp.json()
        lat, lon = float(data["latitude"]), float(data["longitude"])
        USER_LOCATION["lat"], USER_LOCATION["lon"] = lat, lon
        city = data.get("city") or "your area"
        region = data.get("region") or ""
        return f"Using your IP location: {city} {region} ({lat:.4f}, {lon:.4f})."
    except Exception as e:
        return f"Couldn't auto-detect location from IP: {e}"

@function_tool()
async def find_nearby_grocery_here(radius_m: int = 3000):
    """
    Find grocery stores near the user's last known location with Ramsay's emphasis on quality.
    Searches supermarkets and marketplaces within the given radius (meters).
    """
    lat, lon = USER_LOCATION["lat"], USER_LOCATION["lon"]
    if lat is None or lon is None:
        return (
            "Right! I don't have your location yet. You can say "
            "'Set my location to <city>' or 'Use my IP location' or "
            "share GPS coordinates. Quality ingredients make ALL the difference!"
        )

    try:
        q = (
            f'[out:json];'
            f'(node["shop"="supermarket"](around:{radius_m},{lat},{lon});'
            f' node["amenity"="marketplace"](around:{radius_m},{lat},{lon});'
            f' way["shop"="supermarket"](around:{radius_m},{lat},{lon});'
            f' relation["shop"="supermarket"](around:{radius_m},{lat},{lon}););'
            f'out center;'
        )
        r = requests.get("https://overpass-api.de/api/interpreter", params={"data": q}, timeout=15)
        r.raise_for_status()
        items = r.json().get("elements", [])
        norm = []
        for el in items:
            if "lat" in el and "lon" in el:
                y, x = el["lat"], el["lon"]
            elif "center" in el:
                y, x = el["center"]["lat"], el["center"]["lon"]
            else:
                continue
            name = el.get("tags", {}).get("name") or "Unnamed Market"
            dist_km = _haversine_km(lat, lon, y, x)
            norm.append((name, dist_km))
        norm.sort(key=lambda t: t[1])
        top = norm[:5]
        if not top:
            return "Right! No grocery stores found within a few kilometers. You might need to travel a bit further for quality ingredients!"
        lines = [f"{i+1}. {name} — {dist:.2f} km" for i, (name, dist) in enumerate(top)]
        return "**BEST nearby grocery stores for quality ingredients:**\n" + "\n".join(lines) + "\n\nRight! Now get the FRESHEST ingredients you can find!"
    except Exception as e:
        return f"I had trouble reaching the maps service: {e}"

# -----------------------------------------------------------------------------
# Custom Agent (Gordon Ramsay persona + Cookbook RAG)
# -----------------------------------------------------------------------------
class KitchenCompanionAgent(Agent):
    """AI Chef agent that uses PDF cookbook knowledge via RAG, with Gordon Ramsay persona."""

    def __init__(self, chat_ctx: ChatContext = None):
        super().__init__(
            chat_ctx=chat_ctx or ChatContext(),
            instructions=ramsay_persona(RAMSAY_SPICE),
        )

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """
        Automatically perform RAG lookup when user asks cooking-related questions.
        This injects relevant cookbook knowledge into the context before LLM responds.
        """
        user_text = new_message.text_content() or ""
        cooking_keywords = [
            "cook", "recipe", "ingredient", "salt", "fat", "acid", "heat",
            "temperature", "bake", "boil", "fry", "roast", "season", "technique",
            "flavor", "texture", "prepare", "dish", "meal", "food", "taste",
            "spice", "herb", "sauce", "vegetable", "meat", "fish", "pasta",
            "rice", "bread", "knife", "cut", "chop", "blend", "mix", "stir",
        ]
        is_cooking_query = any(k in user_text.lower() for k in cooking_keywords)

        if is_cooking_query and len(user_text) > 10:
            print(f"🔍 RAG Lookup: {user_text[:100]}...")
            cookbook_knowledge = await asyncio.to_thread(query_cookbook, user_text)

            if cookbook_knowledge and "don't have access" not in cookbook_knowledge.lower():
                # Inject as Chef's Notes so the tone stays consistent
                turn_ctx.add_message(
                    role="assistant",
                    content=(
                        f"**Chef's Notes (from cookbook):**\n{cookbook_knowledge}\n"
                        "Right, now let's nail this—step by step."
                    ),
                )
                print("✅ Added cookbook context to response")
            else:
                print("⚠️  No relevant cookbook knowledge found")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
async def entrypoint(ctx: JobContext):
    print("=" * 60)
    print("🍳 KitchenCompanion Starting (Gordon Ramsay Persona)…")
    print("=" * 60)

    # Initialize RAG system before connecting
    rag_ready = initialize_rag()
    if not rag_ready:
        print("\n⚠️  Agent will run without cookbook knowledge!")
        print("   To enable RAG, upload PDFs through the web interface\n")

    print("🔗 Connecting to room...")
    await ctx.connect()

    # Realtime LLM session
    session = AgentSession(
        llm=openai.realtime.RealtimeModel(
            model="gpt-4o-mini-realtime-preview",
            voice="ash",
        ),
    )

    # Create agent with persona + tools
    agent = KitchenCompanionAgent()
    await agent.update_tools(
        agent.tools
        + [
            convert_units,
            set_location_city,
            set_location_gps,
            use_my_ip_location,
            find_nearby_grocery_here,
        ]
    )

    # Start the agent
    await session.start(room=ctx.room, agent=agent)

    # Ramsay-style greeting
    await session.generate_reply(
        instructions=(
            "Open with Ramsay's signature energy and warmth. Use 'Right!' to start. "
            "Mention you can pull 'Chef's Notes' from your cookbook, help with techniques, "
            "conversions, and nearby groceries. Keep it authentic to Ramsay's teaching style. "
            "Be encouraging but show your passion for proper cooking. One short, energetic line."
        )
    )

    print("✅ Agent ready and listening!\n")

# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
