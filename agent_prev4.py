# agent.py — KitchenCompanion (LiveKit Agent with PDF Cookbook RAG)
import warnings
warnings.filterwarnings("ignore", message="Field .* protected namespace")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import math
import asyncio
from typing import Optional, Tuple, List

import requests
from dotenv import load_dotenv
from geopy.geocoders import Nominatim

from livekit import agents
from livekit.agents import AgentSession, Agent, JobContext, ChatContext, ChatMessage
from livekit.agents import function_tool, RunContext
from livekit.agents.llm import ToolError
from livekit.plugins import openai

# LangChain RAG
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI  # keep community variant to avoid extra deps

# ---------------------------------------------------------------------
# Environment / globals
# ---------------------------------------------------------------------
warnings.filterwarnings("ignore", message="Field .* protected namespace")
load_dotenv(".env.local")

# Quieter HF/Transformers logging if ever pulled in
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

# LiveKit Cloud url/keys may be injected by Cloud; keep local fallbacks
os.environ["LIVEKIT_URL"] = os.getenv("LIVEKIT_URL", "wss://<your-project>.livekit.cloud")
os.environ["LIVEKIT_API_KEY"] = os.getenv("LIVEKIT_API_KEY", os.environ.get("LIVEKIT_API_KEY"))
os.environ["LIVEKIT_API_SECRET"] = os.getenv("LIVEKIT_API_SECRET", os.environ.get("LIVEKIT_API_SECRET"))

# --- Global RAG Setup ---
# IMPORTANT: in Cloud, we bake the vectorstore to /app/vectorstore inside the image
#VECTORSTORE_PATH = os.getenv("VECTORSTORE_PATH", "/vectorstore")
VECTORSTORE_PATH = os.getenv("VECTORSTORE_PATH") or next(
    (         p for p in (
             "/app/vectorstore",  # inside Docker/LiveKit Cloud
             "/Users/shamikalikhite/Documents/kitchenCompanion/vectorstore",  # your local path
             os.path.join(os.getcwd(), "vectorstore"),  # repo-relative
         )
         if os.path.exists(os.path.join(p, "index.faiss"))
         and os.path.exists(os.path.join(p, "index.pkl"))
     ),
     "/app/vectorstore",  # final fallback (will log a warning if not found)
     )
_vectorstore = None
_qa_chain = None

# Tiny no-op embeddings object—FAISS.load_local requires an embeddings param,
# but we don't need to re-embed when loading a prebuilt index.
class NoopEmbeddings:
    def embed_documents(self, texts: List[str]):
        raise RuntimeError("NoopEmbeddings cannot embed new documents.")
    def embed_query(self, text: str):
        raise RuntimeError("NoopEmbeddings cannot embed queries.")


def initialize_rag() -> bool:
    """Initialize the RAG system by loading the prebuilt FAISS vectorstore from disk."""
    global _vectorstore, _qa_chain

    index_path = os.path.join(VECTORSTORE_PATH, "index.faiss")
    pkl_path = os.path.join(VECTORSTORE_PATH, "index.pkl")

    if not (os.path.exists(index_path) and os.path.exists(pkl_path)):
        print("⚠️  WARNING: Vectorstore not found!")
        print(f"   Expected: {VECTORSTORE_PATH}/index.faiss and index.pkl")
        print("   Tip: add your vectorstore/ folder to the repo and COPY it into the image.")
        return False

    try:
        print(f"🔄 Loading FAISS index from {VECTORSTORE_PATH} ...")
        _vectorstore = FAISS.load_local(
            VECTORSTORE_PATH,
            NoopEmbeddings(),                  # prevents embedding calls during load
            allow_dangerous_deserialization=True,
        )

        retriever = _vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 3},
        )

        _qa_chain = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.7,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
            ),
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
        )

        print("✅ RAG system initialized (prebuilt FAISS)")
        return True
    except Exception as e:
        print(f"❌ Error initializing RAG: {e}")
        return False


def query_cookbook(question: str) -> str:
    """Query the cookbook vectorstore for relevant information."""
    if _qa_chain is None:
        return "I don't have access to my cookbook knowledge base right now."

    try:
        result = _qa_chain({"query": question})
        answer = result["result"]
        if result.get("source_documents"):
            print(f"📚 Retrieved {len(result['source_documents'])} relevant passages")
        return answer
    except Exception as e:
        print(f"❌ RAG query error: {e}")
        return "I had trouble finding that information in my cookbook."


# ---------------------------------------------------------------------
# Helpers (location)
# ---------------------------------------------------------------------
def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def _geocode_city(city: str) -> Optional[Tuple[float, float]]:
    geolocator = Nominatim(user_agent="kitchencompanion-geo-001")
    loc = geolocator.geocode(city, timeout=10)
    if not loc:
        return None
    return (loc.latitude, loc.longitude)

USER_LOCATION = {"lat": None, "lon": None}


# ---------------------------------------------------------------------
# Function Tools (LiveKit @function_tool — first arg must be RunContext)
# ---------------------------------------------------------------------
@function_tool()
async def convert_units(context: RunContext, amount: float, from_unit: str, to_unit: str):
    """Convert between common kitchen units (cup, tbsp, tsp, ml, g)."""
    conversions = {
        ("cup", "tbsp"): 16, ("tbsp", "tsp"): 3, ("cup", "ml"): 240,
        ("tbsp", "ml"): 15, ("tsp", "ml"): 5, ("cup", "g"): 200,
        ("tbsp", "g"): 12.5, ("tsp", "g"): 4.2,
    }
    key = (from_unit.lower(), to_unit.lower())
    factor = conversions.get(key)
    if not factor:
        rev = conversions.get((to_unit.lower(), from_unit.lower()))
        if rev:
            factor = 1 / rev
    if not factor:
        raise ToolError(f"Unsupported conversion: {from_unit} → {to_unit}")
    return f"{amount * factor:.2f} {to_unit}"


@function_tool()
async def set_location_city(context: RunContext, city: str):
    """Set your location by city name (e.g., 'Evanston, IL')."""
    coords = _geocode_city(city)
    if not coords:
        raise ToolError(f"Couldn't find location for '{city}'. Try 'City, State/Country'.")
    USER_LOCATION["lat"], USER_LOCATION["lon"] = coords
    return f"Location set to {city} ({coords[0]:.4f}, {coords[1]:.4f})."


@function_tool()
async def set_location_gps(context: RunContext, lat: float, lon: float):
    """Set your location directly using GPS coordinates."""
    USER_LOCATION["lat"], USER_LOCATION["lon"] = float(lat), float(lon)
    return f"Location set to ({lat:.4f}, {lon:.4f})."


@function_tool()
async def use_my_ip_location(context: RunContext):
    """
    Approximate your location via IP geolocation (city-level accuracy).
    Good fallback when GPS isn't shared from the browser.
    """
    try:
        resp = requests.get("https://ipapi.co/json/", timeout=8)
        data = resp.json()
        lat, lon = float(data["latitude"]), float(data["longitude"])
        USER_LOCATION["lat"], USER_LOCATION["lon"] = lat, lon
        city = data.get("city") or "your area"
        region = data.get("region") or ""
        return f"Using your IP location: {city} {region} ({lat:.4f}, {lon:.4f})."
    except Exception as e:
        raise ToolError(f"Couldn't auto-detect location from IP: {e}")


@function_tool()
async def find_nearby_grocery_here(context: RunContext, radius_m: int = 3000):
    """
    Find grocery stores near the user's last known location.
    Searches supermarkets and marketplaces within the given radius (meters).
    """
    lat, lon = USER_LOCATION["lat"], USER_LOCATION["lon"]
    if lat is None or lon is None:
        raise ToolError(
            "Location unknown. Say “Set my location to <city>”, or “Use my IP location”, "
            "or provide GPS coordinates."
        )

    # Overpass call can take a moment; make it interruption-friendly
    async def _fetch():
        q = (
            f'[out:json];'
            f'(node["shop"="supermarket"](around:{radius_m},{lat},{lon});'
            f' node["amenity"="marketplace"](around:{radius_m},{lat},{lon});'
            f' way["shop"="supermarket"](around:{radius_m},{lat},{lon});'
            f' relation["shop"="supermarket"](around:{radius_m},{lat},{lon}););'
            f'out center;'
        )
        r = requests.get("https://overpass-api.de/api/interpreter",
                         params={"data": q}, timeout=15)
        r.raise_for_status()
        return r.json().get("elements", [])

    task = asyncio.ensure_future(asyncio.to_thread(_fetch))
    await context.speech_handle.wait_if_not_interrupted([task])

    if context.speech_handle.interrupted:
        task.cancel()
        return None

    try:
        items = await task
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
            return "No grocery stores found within a few kilometers."
        lines = [f"{i+1}. {name} — {dist:.2f} km" for i, (name, dist) in enumerate(top)]
        return "Nearby grocery stores:\n" + "\n".join(lines)
    except Exception as e:
        raise ToolError(f"Map lookup failed: {e}")


# ---------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------
class KitchenCompanionAgent(Agent):
    """AI Chef agent that uses PDF cookbook knowledge via RAG."""
    def __init__(self, chat_ctx: ChatContext = None):
        super().__init__(
            chat_ctx=chat_ctx or ChatContext(),
            instructions=(
                "You are KitchenCompanion — a warm, enthusiastic chef inspired by great cookbook authors. "
                "You have access to a cookbook knowledge base through RAG (Retrieval Augmented Generation). "
                "When you receive cookbook context, use it to provide accurate, detailed cooking advice. "
                "Teach cooking principles, techniques, and share tips from your cookbook knowledge. "
                "Be friendly, encouraging, and precise with your guidance. "
                "If users ask about conversions or grocery stores, you have tools for that too!"
            ),
        )

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """Automatically perform RAG lookup for cooking-related questions and inject context."""
        user_text = new_message.text_content()
        cooking_keywords = [
            "cook","recipe","ingredient","salt","fat","acid","heat","temperature","bake","boil","fry",
            "roast","season","technique","flavor","texture","prepare","dish","meal","food","taste",
            "spice","herb","sauce","vegetable","meat","fish","pasta","rice","bread","knife","cut",
            "chop","blend","mix","stir"
        ]
        is_cooking_query = any(k in user_text.lower() for k in cooking_keywords)

        if is_cooking_query and len(user_text) > 10:
            print(f"🔍 RAG Lookup: {user_text[:100]} ...")
            cookbook_knowledge = await asyncio.to_thread(query_cookbook, user_text)
            if cookbook_knowledge and "don't have access" not in cookbook_knowledge.lower():
                turn_ctx.add_message(
                    role="assistant",
                    content=f"[Cookbook Knowledge]: {cookbook_knowledge}",
                )
                print("✅ Added cookbook context to response")
            else:
                print("⚠️  No relevant cookbook knowledge found")


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------
async def entrypoint(ctx: JobContext):
    print("=" * 60)
    print("🍳 KitchenCompanion Starting...")
    print("=" * 60)

    # Initialize RAG system before connecting
    rag_ready = initialize_rag()
    if not rag_ready:
        print("\n⚠️  Agent will run without cookbook knowledge!")
        print("   To enable RAG, bake vectorstore/ into the image or set VECTORSTORE_PATH.\n")

    print("🔗 Connecting to room...")
    await ctx.connect()

    session = AgentSession(
        llm=openai.realtime.RealtimeModel(
            model="gpt-4o-mini-realtime-preview",
            voice="alloy",
            # tools can also be supplied here; we register them on the Agent below
        )
    )

    # Create agent and register tools BEFORE starting the session
    agent = KitchenCompanionAgent()
    await agent.update_tools(agent.tools + [
        convert_units,
        set_location_city,
        set_location_gps,
        use_my_ip_location,
        find_nearby_grocery_here,
    ])

    await session.start(room=ctx.room, agent=agent)

    await session.generate_reply(
        instructions=(
            "Greet the user warmly as their personal AI chef. "
            "Mention that you have cookbook knowledge and can help with recipes, "
            "techniques, unit conversions, and finding grocery stores. Keep it brief and friendly."
        )
    )

    print("✅ Agent ready and listening!\n")


# --- Runner ---
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
