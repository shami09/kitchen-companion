# agent.py — KitchenCompanion (LiveKit v1.3+ Realtime Agent)
import warnings
warnings.filterwarnings("ignore", message="Field .* protected namespace")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os, asyncio, requests
from dotenv import load_dotenv
from geopy.geocoders import Nominatim

from livekit import agents
from livekit.agents import AgentSession, Agent, JobContext
from livekit.plugins import openai

from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.chains import RetrievalQA

warnings.filterwarnings("ignore", message="Field .* protected namespace")
load_dotenv('.env.local')
import os
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import os
os.environ["LIVEKIT_URL"] = os.getenv("LIVEKIT_URL", "wss://<your-project>.livekit.cloud")
os.environ["LIVEKIT_API_KEY"] = os.getenv("LIVEKIT_API_KEY")
os.environ["LIVEKIT_API_SECRET"] = os.getenv("LIVEKIT_API_SECRET")


# --- RAG Query Function ---
def get_rag_answer(query: str):
    db = FAISS.load_local("vectorstore", OpenAIEmbeddings(), allow_dangerous_deserialization=True)
    retriever = db.as_retriever(search_kwargs={"k": 3})
    qa = RetrievalQA.from_chain_type(
        llm=ChatOpenAI(model="gpt-4o-mini"),
        retriever=retriever
    )
    return qa.run(query)

# --- Function Tools ---
from livekit.agents import function_tool

@function_tool
def convert_units(amount: float, from_unit: str, to_unit: str):
    """Convert between common kitchen units (cup, tbsp, tsp, ml, g)."""
    conversions = {
        ("cup", "tbsp"): 16, ("tbsp", "tsp"): 3, ("cup", "ml"): 240,
        ("tbsp", "ml"): 15, ("tsp", "ml"): 5, ("cup", "g"): 200
    }
    factor = conversions.get((from_unit, to_unit))
    if not factor:
        return f"I’m not sure how to convert {from_unit} to {to_unit} yet."
    return f"{amount * factor:.2f} {to_unit}"

@function_tool
def find_nearby_grocery(city: str):
    """Find grocery stores near a city using OpenStreetMap."""
    geolocator = Nominatim(user_agent="kitchencompanion")
    loc = geolocator.geocode(city)
    if not loc:
        return f"Couldn’t find location for {city}."
    r = requests.get(
        "https://overpass-api.de/api/interpreter",
        params={
            "data": f'[out:json];node["shop"="supermarket"](around:3000,{loc.latitude},{loc.longitude});out;'
        },
    )
    results = r.json().get("elements", [])
    names = [el["tags"].get("name", "Unnamed Market") for el in results[:3]]
    return "Nearby grocery stores: " + ", ".join(names) if names else "No grocery stores found."

@function_tool
def lookup_cooking_tip(topic: str):
    """Retrieve advice from 'Salt, Fat, Acid, Heat' about a given topic."""
    return get_rag_answer(topic)

# --- Main Entrypoint (matches new documentation) ---
# --- Main Entrypoint (matches new documentation) ---
async def entrypoint(ctx: JobContext):
    print("KitchenCompanion joining room...")
    await ctx.connect()

    # 🔧 Create the session
    session = AgentSession(
        # Realtime LLM model (handles both reasoning and speech)
        llm=openai.realtime.RealtimeModel(
            model="gpt-4o-mini-realtime-preview",
            voice="alloy",
           
        )
    )

    # 🔊 Start the agent and join the LiveKit room
    await session.start(
        room=ctx.room,
        agent=Agent(
            instructions=(
                "You are KitchenCompanion — a warm, witty chef inspired by Gordan Ramsay's "
                "'recipes'. Speak like a friendly sous-chef, teaching principles "
                "of cooking, giving ingredient conversions, and sharing tips directly from the book. "
                "Greet the user warmly and offer your cooking assistance."
            )
        )
    )

    # Generate an initial greeting
    await session.generate_reply()

def get_rag_answer(query: str):
    vectorstore_path = "vectorstore"
    if not os.path.exists(os.path.join(vectorstore_path, "index.faiss")):
        return "I can’t recall that right now — please run build_vectorstore.py first!"

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
    return qa.run(query)


# --- Runner (v1.3+ CLI entrypoint) ---
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
