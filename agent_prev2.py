# agent.py — KitchenCompanion (LiveKit v1.3+ Realtime Agent with RAG)
import warnings
warnings.filterwarnings("ignore", message="Field .* protected namespace")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os, asyncio, requests
from dotenv import load_dotenv
from geopy.geocoders import Nominatim

from livekit import agents
from livekit.agents import AgentSession, Agent, JobContext, ChatContext, ChatMessage, RunContext
from livekit.plugins import openai

from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.chains import RetrievalQA

warnings.filterwarnings("ignore", message="Field .* protected namespace")
load_dotenv('.env.local')
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

os.environ["LIVEKIT_URL"] = os.getenv("LIVEKIT_URL", "wss://<your-project>.livekit.cloud")
os.environ["LIVEKIT_API_KEY"] = os.getenv("LIVEKIT_API_KEY")
os.environ["LIVEKIT_API_SECRET"] = os.getenv("LIVEKIT_API_SECRET")


# --- RAG Query Function ---
def get_rag_answer(query: str) -> str:
    """Query the vectorstore for cooking knowledge."""
    vectorstore_path = "vectorstore"
    if not os.path.exists(os.path.join(vectorstore_path, "index.faiss")):
        return "I don't have access to my knowledge base right now."

    try:
        db = FAISS.load_local(
            vectorstore_path,
            OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY")),
            allow_dangerous_deserialization=True
        )
        retriever = db.as_retriever(search_kwargs={"k": 3})
        qa = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(model="gpt-4o-mini"),
            retriever=retriever
        )
        result = qa.run(query)
        return result
    except Exception as e:
        print(f"RAG error: {e}")
        return "I had trouble accessing my knowledge base."


# --- Function Tools ---
from livekit.agents import function_tool

@function_tool
async def convert_units(amount: float, from_unit: str, to_unit: str):
    """Convert between common kitchen units (cup, tbsp, tsp, ml, g)."""
    conversions = {
        ("cup", "tbsp"): 16, ("tbsp", "tsp"): 3, ("cup", "ml"): 240,
        ("tbsp", "ml"): 15, ("tsp", "ml"): 5, ("cup", "g"): 200
    }
    factor = conversions.get((from_unit, to_unit))
    if not factor:
        return f"I'm not sure how to convert {from_unit} to {to_unit} yet."
    return f"{amount * factor:.2f} {to_unit}"

@function_tool
async def find_nearby_grocery(city: str):
    """Find grocery stores near a city using OpenStreetMap."""
    try:
        geolocator = Nominatim(user_agent="kitchencompanion")
        loc = geolocator.geocode(city)
        if not loc:
            return f"Couldn't find location for {city}."
        
        r = requests.get(
            "https://overpass-api.de/api/interpreter",
            params={
                "data": f'[out:json];node["shop"="supermarket"](around:3000,{loc.latitude},{loc.longitude});out;'
            },
            timeout=10
        )
        results = r.json().get("elements", [])
        names = [el["tags"].get("name", "Unnamed Market") for el in results[:3]]
        return "Nearby grocery stores: " + ", ".join(names) if names else "No grocery stores found."
    except Exception as e:
        return f"I had trouble finding grocery stores: {str(e)}"


# --- Custom Agent with RAG ---
class KitchenCompanionAgent(Agent):
    """Custom agent that performs RAG lookup on user queries."""
    
    def __init__(self, chat_ctx: ChatContext = None):
        super().__init__(
            chat_ctx=chat_ctx or ChatContext(),
            instructions=(
                "You are KitchenCompanion — a warm, witty chef inspired by Gordon Ramsay. "
                "Speak like a friendly but demanding sous-chef, teaching principles of cooking, "
                "giving ingredient conversions, and sharing expert tips. "
                "When you receive additional cooking knowledge context, use it to provide "
                "accurate and detailed answers. Be concise but informative."
            )
        )
    
    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """Perform RAG lookup when user completes their turn."""
        user_text = new_message.text_content()
        
        # Only do RAG lookup for cooking-related queries
        cooking_keywords = ['cook', 'recipe', 'ingredient', 'salt', 'fat', 'acid', 'heat', 
                           'temperature', 'bake', 'boil', 'fry', 'season', 'technique']
        
        if any(keyword in user_text.lower() for keyword in cooking_keywords):
            print(f"🔍 Performing RAG lookup for: {user_text}")
            
            # Query the vectorstore
            rag_result = await asyncio.to_thread(get_rag_answer, user_text)
            
            if rag_result and "trouble accessing" not in rag_result.lower():
                # Inject RAG results into context
                turn_ctx.add_message(
                    role="assistant",
                    content=f"[Knowledge base context]: {rag_result}"
                )
                print(f"✅ RAG context added")


# --- Main Entrypoint ---
async def entrypoint(ctx: JobContext):
    print("🍳 KitchenCompanion joining room...")
    await ctx.connect()

    # Create the session
    session = AgentSession(
        llm=openai.realtime.RealtimeModel(
            model="gpt-4o-mini-realtime-preview",
            voice="alloy",
        )
    )

    # Create custom agent with RAG capability
    agent = KitchenCompanionAgent()

    # Start the agent
    await session.start(
        room=ctx.room,
        agent=agent
    )

    # Generate initial greeting
    await session.generate_reply(
        instructions="Greet the user warmly in Gordon Ramsay style and offer your cooking assistance."
    )


# --- Runner ---
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))