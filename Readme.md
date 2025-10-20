# 🍳 KitchenCompanion - RAG-Enabled Voice Cooking Assistant

> **Personal Problem Solved:** As someone who struggles with cooking techniques and often makes basic mistakes in the kitchen, I need a voice-activated cooking coach that can guide me through recipes hands-free while I'm actively cooking, referencing professional cookbook knowledge in real-time.

## Table of Contents
- [Overview](#overview)
- [Story & Personality](#story--personality)
- [Technical Architecture](#technical-architecture)
- [Features](#features)
- [Setup Instructions](#setup-instructions)
- [Design Decisions](#design-decisions)
- [AI Tools Used](#ai-tools-used)
- [Demo & Usage](#demo--usage)

---

## Overview

**KitchenCompanion** is a voice-activated cooking assistant powered by LiveKit that embodies the personality of Gordon Ramsay. It provides real-time cooking guidance, technique corrections, and references professional cookbook knowledge through RAG (Retrieval-Augmented Generation) over uploaded PDF cookbooks.

### The Story

Meet Chef Ramsay - your personal kitchen companion who's passionate about teaching proper cooking techniques in his own passionate style. He's had enough of watching home cooks make basic mistakes! Through this voice agent, Gordon brings his decades of Michelin-star experience into your kitchen, ready to guide you through any recipe, answer technique questions, and even help you find the best local ingredients.

Unlike passive recipe apps, Chef Ramsay actively listens while you cook, providing real-time guidance with his signature intensity and teaching style. Upload a professional cookbook (like "Salt, Fat, Acid, Heat"), and he'll reference specific techniques, temperature guidelines, and chef's secrets as you cook.

But our Sous chef here is also going to help us in getting ingredients and wait for us until we are completed getting our ingredients.

### Key Features

1. **Real-Time Voice Conversation** - Hands-free cooking guidance using LiveKit's voice pipeline
2. **Gordon Ramsay Persona** - Authentic personality with adjustable intensity levels (PG, PG-13, TV-MA)
3. **RAG-Enabled Cookbook Knowledge** - Upload PDF cookbooks for professional reference
4. **Slow step-by-step** recipe dictation and explanation. Asks if you want a summary or a complete recipe with a guide
5. **Live Transcription** - See what you and Chef Ramsay are saying in real-time
6. **Tool Integration** - Unit conversions, nearby grocery store finder, location services
7. **Dynamic PDF Upload** - Add cookbook knowledge without restarting the agent

---

## Story & Personality

### The Narrative

Gordon Ramsay has digitized himself to help home cooks improve their skills. He's tired of seeing overcooked steaks, underseasoned pasta, and dangerous food safety violations. Through KitchenCompanion, he brings his teaching philosophy into every kitchen:

- **Technique over recipes** - "It's not about following a recipe blindly, it's about understanding WHY things work!"
- **Food safety first** - Zero tolerance for cross-contamination or unsafe temperatures
- **Passionate teaching** - Direct, commanding, but ultimately encouraging
- **Professional standards** - References actual cookbook knowledge for proper techniques

### Personality Implementation

The agent has three configurable "spice levels":

**PG (MasterChef Junior Mode)**
- Warm and encouraging
- No profanity, family-friendly
- Uses phrases like "Right! Let's sharpen this up!" and "That's absolutely SCORCHING!"

**PG-13 (Hell's Kitchen TV Mode)** Default
- Cheeky and sharp
- Light censored exclamations: "flipping", "bloody", "bleeping"
- Example: "That's flipping RAW! Get that pan bleeping hot!"

**TV-MA (Full Ramsay Intensity)**
- Authentic Gordon intensity
- Explicit language about food quality (never directed at user)
- Example: "That's f***ing RAW!" (about food state, not the person)

### Behavioral Patterns

1. **Opening Lines**: Always starts with "Right!" - his signature way to grab attention
2. **Teaching Moments**: Explains the "why" behind techniques
3. **Sensory Guidance**: "Listen for the sizzle", "Watch for the color change"
4. **Standards**: Specific temperatures and timings with metric + US units
5. **Encouragement**: "BEAUTIFUL! That's how it's done!" when techniques are correct
6. **Corrections**: Direct but constructive - "That's not how you do it! Watch and learn!"

Agent: https://kitchencomp8-1rivpt.sandbox.livekit.io/
---

## Technical Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────┐
│                    Frontend (React + TypeScript)         │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Start Call   │  │ Upload PDF   │  │ Live         │    │
│  │ Button       │  │ Interface    │  │ Transcript   │    │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘    │
└─────────┼──────────────────┼─────────────────────────────┘
          │                  │
          │                  ▼
          │         ┌──────────────────┐
          │         │  Upload Server   │
          │         │  (FastAPI)       │
          │         │  Port: 8788      │
          │         └────────┬─────────┘
          │                  │
          │                  │ Processes PDFs
          │                  │ Builds Vectorstore
          │                  ▼
          │         ┌──────────────────┐
          │         │   Vectorstore    │
          │         │   (FAISS)        │
          │         │   - index.faiss  │
          │         │   - index.pkl    │
          │         └────────┬─────────┘
          │                  │
          │                  │ Shared Storage
          │                  │
          ▼                  ▼
┌────────────────────────────────────┐
│       LiveKit Agent (Python)       │
│                                    │
│  ┌──────────────────────────────┐  │
│  │  Voice Pipeline              │  │
│  │  - STT: OpenAI Whisper       │  │
│  │  - LLM: GPT-4o-mini          │  │
│  │  - TTS: OpenAI TTS (ash)     │  │
│  │  - VAD: Silero               │  │
│  └──────────────────────────────┘  │
│                                    │
│  ┌──────────────────────────────┐  │
│  │  RAG System (LangChain)      │  │
│  │  - Auto-reload vectorstore   │  │
│  │  - Query on cooking keywords │  │
│  │  - 3 relevant chunks (k=3)   │  │
│  └──────────────────────────────┘  │
│                                    │
│  ┌──────────────────────────────┐  │
│  │  Function Tools              │  │
│  │  - Unit conversion           │  │
│  │  - Location services         │  │
│  │  - Grocery store finder      │  │
│  └──────────────────────────────┘  │
└────────────────────────────────────┘
```

### Component Breakdown

#### 1. Frontend (React + TypeScript + LiveKit Client SDK)
- **Location**: `server/livekit-frontend/src/App.tsx`
- **Framework**: React 18 with TypeScript, Vite
- **Key Features**:
  - LiveKit room connection and audio handling
  - Browser-based Speech-to-Text (Web Speech API)
  - Real-time transcript display with user/agent distinction
  - PDF upload interface with status feedback
  - Vectorstore info display (PDFs loaded, vector count)
- **Dependencies**: `livekit-client`, `react`, `typescript`

#### 2. Upload Server (FastAPI + Python)
- **Location**: `upload_server.py`
- **Purpose**: Handles PDF uploads and vectorstore management
- **Key Features**:
  - PDF processing with PyPDFLoader
  - Text chunking (1000 chars, 200 overlap)
  - FAISS vectorstore creation/merging
  - OpenAI embeddings generation
  - RESTful API endpoints
- **Dependencies**: `fastapi`, `uvicorn`, `langchain`, `pypdf`, `faiss-cpu`

#### 3. LiveKit Agent (Python)
- **Location**: `src/agent.py`
- **Purpose**: Real-time voice conversation with RAG integration
- **Key Features**:
  - Gordon Ramsay persona with configurable intensity
  - Auto-reload vectorstore on updates
  - RAG query on cooking-related keywords
  - Function tools (unit conversion, location, grocery finder)
  - Voice pipeline with OpenAI models
- **Dependencies**: `livekit`, `livekit-agents`, `livekit-plugins-openai`, `langchain`

#### 4. Vectorstore (FAISS)
- **Location**: `vectorstore/`
- **Contents**: `index.faiss` (vector index), `index.pkl` (metadata)
- **Features**:
  - Persistent storage
  - Incremental updates (merge new PDFs)
  - Auto-reload detection via file modification time

---

## Features

### 1. Real-Time Voice Conversation
- **LiveKit Integration**: Full voice pipeline with OpenAI models
- **Hands-Free**: Speak naturally while cooking, get immediate responses
- **Voice Model**: OpenAI TTS with "ash" voice personality
- **STT**: Browser Web Speech API for user input
- **LLM**: GPT-4o-mini-realtime-preview for conversational responses

### 2. Gordon Ramsay Persona
- **Authentic Character**: 
  - Signature phrases: "Right!", "Beautiful!", "That's how it's done!"
  - Teaching style emphasizing technique over recipes
  - Passionate but constructive feedback
- **Adjustable Intensity**: PG / PG-13 / TV-MA modes
- **Context-Aware**: Different reactions for mistakes vs. good technique
- **Professional Standards**: Specific temperatures, timings, measurements

### 3. RAG-Enabled Cookbook Knowledge
- **Dynamic PDF Upload**: Add cookbooks without restarting agent
- **Automatic Integration**: Agent detects vectorstore updates and reloads
- **Intelligent Retrieval**: 
  - Triggers on cooking-related keywords (cook, recipe, temperature, etc.)
  - Returns 3 most relevant chunks (k=3)
  - Injects as "Chef's Notes" in Ramsay's voice
- **Framework**: LangChain with FAISS vectorstore
- **Embeddings**: OpenAI text-embedding-ada-002

### 4. Live Transcription 
- **Real-Time Display**: See conversation as it happens
- **User/Agent Distinction**: Color-coded speakers (blue for user, green for agent) nooooo
- **Partial Updates**: Shows interim results before finalization
- **Auto-Scroll**: Transcript follows conversation flow
- **Browser STT**: Uses Web Speech API for local transcription

### 5. Tool Calls 

**Unit Conversion Tool**
```python
convert_units(amount=2, from_unit="cups", to_unit="ml")
# Returns: "Perfect! 2 cups = 480.00 ml. Now get measuring with PRECISION!"
```

**Location Services**
```python
set_location_city(city="Chicago, IL")
# Returns: "Perfect! Location set to Chicago, IL (41.8781, -87.6298). 
#           Now I can find you the BEST local ingredients!"
```

**Grocery Store Finder** (Integration Point for Story)
```python
find_nearby_grocery_here(radius_m=3000)
# Returns: List of top 5 nearby supermarkets with distances
# Uses OpenStreetMap Overpass API for real-time location data
```

**Example Usage in Conversation:**
```
User: "Where can I find the freshest ingredients nearby?"
Agent: "Right! Let me find you the BEST local markets..."
       [Calls find_nearby_grocery_here tool]
       "**BEST nearby grocery stores for quality ingredients:**
        1. Whole Foods Market — 1.2 km
        2. Mariano's Fresh Market — 1.8 km
        3. Trader Joe's — 2.3 km
        Now get the FRESHEST ingredients you can find!"
```

### 6. PDF Management System 
- **Upload Interface**: Drag-and-drop or click to upload
- **Status Display**: Shows uploaded PDFs and vector count
- **Multiple PDFs**: Merge multiple cookbooks into a single knowledge base
- **Refresh Status**: Real-time update of vectorstore info
- **Error Handling**: Validates PDF format, size limits, API key configuration

---

## Setup Instructions

### Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.9+
- **OpenAI API Key** (for embeddings and voice models)
- **LiveKit Account** (Cloud or self-hosted)

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/kitchen-companion.git
cd kitchen-companion
```

### 2. Backend Setup

#### Install Python Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**requirements.txt:**
```txt
# LiveKit Agent
livekit==0.17.2
livekit-agents==0.9.4
livekit-plugins-openai==0.8.3

# RAG System
langchain==0.1.0
langchain-community==0.0.10
openai==1.6.1
faiss-cpu==1.7.4
pypdf==3.17.1

# Upload Server
fastapi==0.104.1
uvicorn==0.24.0
python-multipart==0.0.6

# Utilities
python-dotenv==1.0.0
geopy==2.4.1
requests==2.31.0
```

#### Configure Environment Variables

Create `.env.local` in project root:

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxx

# LiveKit Configuration
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxxxxx
LIVEKIT_API_SECRET=xxxxxxxxxxxxxxxxxx

# Agent Personality (pg, pg13, tvma)
RAMSAY_SPICE=pg13

# Optional: Custom vectorstore path
VECTORSTORE_PATH=./vectorstore
```

#### Create Required Directories

```bash
mkdir -p vectorstore uploaded_pdfs
```

### 3. Frontend Setup

```bash
cd server/livekit-frontend
npm install
```

#### Configure Frontend Environment

Create `livekit-frontend/.env`:

```bash
# Token server (for LiveKit room tokens)
VITE_TOKEN_SERVER=http://localhost:8787

# Upload server (for PDF processing)
VITE_UPLOAD_SERVER=http://localhost:8788
```

**Frontend Dependencies (package.json):**
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "livekit-client": "^2.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}
```

### 4. Run the Application

You need **three terminal windows**:

#### Terminal 1: Upload Server
```bash
# From project root
python upload_server.py
```

Expected output:
```
🍳 KitchenCompanion Upload Server
====================================
📁 Vectorstore path: ./vectorstore
📁 Upload directory: ./uploaded_pdfs
🔑 OpenAI API Key: ✅ Set
📚 Uploaded PDFs: 0
====================================

🚀 Starting server on http://localhost:8788
```

#### Terminal 2: LiveKit Agent
this is an optional step
```bash
# From project root
cd src
python agent.py start
```

Expected output:
```
============================================================
🍳 KitchenCompanion Starting (Gordon Ramsay Persona)…
============================================================
⚠️  WARNING: Vectorstore not found!
   Upload PDFs through the web interface to build the vectorstore
🔗 Connecting to room...
✅ Agent ready and listening!
```

#### Terminal 3: Frontend
```bash
# From project root
cd frontend
npm run dev
```

Expected output:
```
  VITE v5.0.0  ready in 500 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

### 5. Usage Flow

1. **Visit Frontend**: Open `http://localhost:5173`
2. **Upload a Cookbook PDF**: Click "Upload PDF" and select a cooking book (e.g., Salt, Fat, Acid, Heat)
3. **Wait for Processing**: You'll see "✅ PDF processed..." when ready
4. **Start Call**: Click "🎙️ Start Call" button
5. **Grant Microphone Access**: Allow browser to use your microphone
6. **Wait for Agent**: Gordon Ramsay will join and greet you
7. **Start Cooking Conversation**: Ask cooking questions, request recipes, discuss techniques
8. **Tool Usage**: Try "Where can I buy fresh ingredients?" or "Convert 2 cups to ml"
9. **RAG Queries**: Ask about specific cookbook content: "How do I properly season food?"
10. **End Call**: Click "⏹️ End Call" when finished

---

## Design Decisions

### 1. Architecture: Separate Upload Server

**Decision**: Run PDF processing as a separate FastAPI server instead of integrating into the LiveKit agent.

**Rationale**:
- **Separation of Concerns**: Agent handles real-time voice, upload server handles file processing
- **Scalability**: Can scale PDF processing independently from voice agents
- **Development**: Easier to develop and debug separately
- **Deployment**: Upload server can be on different infrastructure (Railway, Heroku, etc.)

**Trade-offs**:
- Additional server to manage
- Requires shared storage mechanism (local files, S3, or managed vector DB)
- More complex deployment than monolithic approach

### 2. Vector Store: FAISS (Local Files)

**Decision**: Use FAISS with local file storage for vectorstore.

**Rationale**:
- **Simplicity**: Easy to set up, no external database required
- **Cost**: Free, no managed service costs
- **Performance**: FAISS is highly optimized for similarity search
- **Development**: Fast iteration during development

**Trade-offs**:
- **Scaling**: Not ideal for multi-instance deployments without shared storage
- **Persistence**: Requires file system access
- **Production Alternative**: Would use Pinecone, Weaviate, or Qdrant for production

**Production Migration Path**:
```python
# Easy migration to Pinecone
from langchain_community.vectorstores import Pinecone
vectorstore = Pinecone.from_documents(texts, embeddings, index_name="cookbook")
```

### 3. RAG Framework: LangChain

**Decision**: Use LangChain for RAG implementation.

**Rationale**:
- **Mature Ecosystem**: Well-documented, widely used
- **Abstractions**: High-level APIs for document loading, splitting, embeddings
- **Flexibility**: Easy to swap vector stores, LLMs, embeddings
- **Integration**: Built-in support for FAISS, OpenAI, retrieval chains

**Alternatives Considered**:
- **LlamaIndex**: More focused on indexing, less flexible for custom workflows
- **Custom Implementation**: More control but significantly more development time
- **OpenAI Assistants API**: Limited control over retrieval parameters

### 4. Text Chunking Strategy

**Decision**: 1000 characters per chunk, 200 character overlap.

**Rationale**:
- **Context Window**: Fits well within GPT-4's context limits
- **Semantic Coherence**: 1000 chars typically captures complete concepts/paragraphs
- **Overlap**: 200 chars prevents splitting mid-concept at boundaries
- **Performance**: Balances retrieval accuracy with token usage

**Testing Results**:
- Too small (< 500 chars): Fragments concepts, loses context
- Too large (> 2000 chars): Generic retrieval, less precise
- Current setting: Good balance for cookbook content

### 5. Auto-Reload Mechanism

**Decision**: Check vectorstore modification time before each RAG query.

**Rationale**:
- **User Experience**: No manual agent restart after PDF upload
- **Simplicity**: File system timestamps are reliable
- **Performance**: Single stat() call is negligible overhead

**Implementation**:
```python
def check_and_reload_vectorstore():
    global _last_vectorstore_mtime
    faiss_idx = os.path.join(VECTORSTORE_PATH, "index.faiss")
    current_mtime = os.path.getmtime(faiss_idx)
    
    if _last_vectorstore_mtime is None or current_mtime > _last_vectorstore_mtime:
        print("🔄 Vectorstore update detected, reloading...")
        return initialize_rag()
```

**Trade-offs**:
- Slight latency on first query after update (1-2 seconds to reload)
- File system dependency (works for local, needs alternative for cloud)

### 6. Gordon Ramsay Persona Implementation

**Decision**: Implement personality through detailed system prompts with configurable intensity levels.

**Rationale**:
- **Authenticity**: Detailed behavioral guidelines create consistent character
- **Flexibility**: Environment variable allows different contexts (family cooking, professional training)
- **Behavioral Patterns**: Specific phrase patterns create recognizable style
- **Teaching Focus**: Emphasizes technique over recipes, matching Ramsay's actual philosophy

**Prompt Engineering Approach**:
- Signature phrases ("Right!", "Beautiful!", "That's how it's done!")
- Context-aware reactions (different responses for mistakes vs. success)
- Sensory guidance ("Listen for the sizzle", "Watch for the color change")
- Professional standards (specific temps, timings, measurements)

### 7. STT Strategy: Browser Web Speech API

**Decision**: Use browser-based speech recognition instead of server-side STT.

**Rationale**:
- **Latency**: Local processing, no network round-trip
- **Cost**: Free, no API charges
- **Privacy**: Audio doesn't leave user's device
- **LiveKit Integration**: Works alongside LiveKit's voice pipeline

**Trade-offs**:
- **Browser Dependency**: Requires Chrome/Edge, Safari support is limited
- **Accuracy**: Less accurate than OpenAI Whisper in noisy environments
- **Language Support**: Limited to browser's supported languages

**Production Alternative**:
```python
# Could switch to LiveKit's server-side STT
session = AgentSession(
    stt=openai.STT(model="whisper-1"),  # Server-side STT
    llm=openai.realtime.RealtimeModel(),
)
```

### 8. Tool Call Design

**Decision**: Implement function tools that fit cooking narrative (unit conversion, grocery finder).

**Rationale**:
- **Story Integration**: Tools enhance the cooking assistant narrative
- **Practical Value**: Actually useful while cooking
- **LiveKit Native**: Uses LiveKit's function calling framework
- **Extensibility**: Easy to add more tools (timers, substitutions, etc.)

**Future Tool Ideas**:
- Recipe substitutions (dairy-free, gluten-free alternatives)
- Cooking timers with voice notifications
- Ingredient inventory tracking
- Wine pairing recommendations

---

## RAG Integration Details

### How RAG Works in This System

#### 1. Document Processing (Upload Server)

```python
# 1. Load PDF
loader = PyPDFLoader(pdf_path)
documents = loader.load()

# 2. Split into chunks
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
texts = text_splitter.split_documents(documents)

# 3. Generate embeddings
embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")

# 4. Build/merge vectorstore
vectorstore = FAISS.from_documents(texts, embeddings)
vectorstore.save_local(VECTORSTORE_PATH)
```

#### 2. Retrieval (LiveKit Agent)

```python
# Triggered on cooking-related keywords
cooking_keywords = [
    "cook", "recipe", "temperature", "season", 
    "technique", "bake", "roast", "flavor", ...
]

if any(keyword in user_text.lower() for keyword in cooking_keywords):
    # Query vectorstore
    cookbook_knowledge = query_cookbook(user_text)
    
    # Inject as Chef's Notes
    turn_ctx.add_message(
        role="assistant",
        content=f"**Chef's Notes (from cookbook):**\n{cookbook_knowledge}\n"
                "Right, now let's nail this—step by step."
    )
```

#### 3. Query Chain

```python
# RetrievalQA chain with LangChain
retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 3}  # Top 3 most relevant chunks
)

qa_chain = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(model="gpt-4o-mini", temperature=0.4),
    chain_type="stuff",  # Stuff all retrieved docs into prompt
    retriever=retriever,
    return_source_documents=True
)

result = qa_chain({"query": user_question})
```

### RAG Performance Considerations

**Query Latency**: ~500ms for retrieval + LLM generation
- FAISS similarity search: ~50ms
- OpenAI embedding: ~200ms
- LLM generation: ~250ms

**Accuracy**: Retrieval precision depends on:
- Chunk size (1000 chars provides good semantic units)
- Overlap (200 chars prevents concept fragmentation)
- Embedding quality (OpenAI ada-002 is highly semantic)
- Number of chunks retrieved (k=3 balances context vs. noise)

**Testing Approach**:
- Upload "Salt, Fat, Acid, Heat" by Samin Nosrat (400 pages)
- Test queries:
  - "How do I properly season food?" → Retrieved correct section on salt timing
  - "What temperature should I roast chicken?" → Found specific temp recommendations
  - "Explain the Maillard reaction" → Pulled scientific explanation from chemistry section

### Limitations

1. **Context Window**: Limited to 3 chunks (~3000 chars of retrieved context)
   - Trade-off: More chunks = more context but also more noise
   - Solution: Could implement re-ranking or chunk filtering

2. **No Multi-Modal**: Can't process cookbook images (ingredient photos, technique diagrams)
   - Future: Use GPT-4 Vision to describe images during PDF processing

3. **Single PDF at Query Time**: Doesn't indicate which PDF contained the answer
   - Future: Include source metadata in response ("According to page 42 of Salt, Fat, Acid, Heat...")

---

## AI Tools Used

### 1. Claude (Anthropic)
**Usage**: Architecture design, code generation, debugging assistance
- Generated initial React component structure
- Helped debug LiveKit room connection issues
- Provided FastAPI endpoint design patterns
- Assisted with TypeScript type definitions

### 2. GitHub Copilot
**Usage**: Code completion, boilerplate generation
- Auto-completed common patterns (error handling, async functions)
- Generated TypeScript interfaces
- Suggested library imports and function signatures

### 3. OpenAI GPT-4
**Usage**: Prompt engineering, persona development
- Refined Gordon Ramsay personality prompts
- Generated example conversations for testing
- Helped craft signature phrase patterns

### 4. ChatGPT (GPT-4)
**Usage**: Documentation, explanation generation
- Generated setup instructions
- Helped structure README sections
- Provided deployment guidance

**Note**: All AI-generated code was reviewed, tested, and modified to fit the specific requirements of this project. AI tools accelerated development but all architectural decisions and implementations were human-directed.

---

## Demo & Usage

### Example Conversation Flow

**User**: "Hey Chef, how do I make perfect scrambled eggs?"

**Agent (Gordon Ramsay)**: "Right! Let me pull from the cookbook...

**Chef's Notes (from cookbook):**
- Use low heat and constant stirring for creamy eggs
- Add butter at the end, not the beginning
- Remove from heat while still slightly wet - they'll continue cooking

Now listen to me! Low and slow is the key. Get your pan on MEDIUM heat, not screaming hot. Crack your eggs into a bowl, season with salt and pepper. Into the pan, and NOW - keep stirring with a spatula. Constantly! When they're 80% done and still look a bit wet, OFF the heat. Add a knob of butter, fold it through. THAT'S how you do it - creamy, not rubbery. Beautiful!"

**User**: "What temperature should the pan be?"

**Agent**: "Perfect question! Medium heat - about **275-300°F (135-150°C)**. Any hotter and you'll get rubbery eggs. You want gentle heat so you can control the texture. Right! Get that pan to temp!"

**User**: "Where can I buy fresh eggs nearby?"

**Agent**: "Right! Let me find you the BEST local markets..."

*[Tool Call: find_nearby_grocery_here]*

"**BEST nearby grocery stores for quality ingredients:**
1. Whole Foods Market — 1.2 km
2. Mariano's Fresh Market — 1.8 km  
3. Trader Joe's — 2.3 km

Right! Now get the FRESHEST eggs you can find - look for organic, free-range if possible!"

### Testing RAG Specificity

To verify proper RAG implementation (not just summarization):

**Query**: "On page 87 of Salt Fat Acid Heat, what does Samin say about salting meat before cooking?"

**Expected**: Should retrieve specific passage about salting timing and penetration depth

**Actual Agent Response**: "Right, let me check the cookbook...

**Chef's Notes:**
- Salt should be applied 24 hours before cooking for thick cuts
- Salt penetrates at a rate of 1 inch per week
- For thin cuts like chicken breast, 40 minutes is sufficient

EXACTLY! You see, salt needs TIME to penetrate the meat. It's not just about surface seasoning - it's about getting that salt deep into the muscle fibers. For a thick steak, season it the night before and let it rest in the fridge. That's proper technique!"

### Video Demo

*(Include link to video demonstration showing):*
1. PDF upload and processing
2. Starting a call and agent joining
3. Live transcript showing user/agent conversation
4. Tool call for nearby groceries
5. RAG query retrieving specific cookbook passage
6. Real-time speech-to-text functionality

---

## Future Enhancements

### Technical Improvements
1. **Production Vector Database**: Migrate to Pinecone or Weaviate for multi-instance scaling
2. **Enhanced RAG**: Add re-ranking, chunk filtering, source attribution
3. **Multi-Modal**: Process cookbook images with GPT-4 Vision
4. **Streaming TTS**: Reduce latency with streaming audio responses
5. **Custom Wake Word**: "Hey Chef" activation phrase

### Feature Additions
1. **Recipe Mode**: Step-by-step guided cooking with timer integration
2. **Ingredient Substitutions**: Dietary restriction alternatives
3. **Shopping List**: Build list from conversation, export to phone
4. **Meal Planning**: Weekly menu suggestions based on available ingredients
5. **Voice Profiles**: Multiple chef personalities (Julia Child, Jacques Pépin, etc.)

### UX Improvements
1. **Mobile App**: Native iOS/Android with better audio handling
2. **Visual Aids**: Show referenced cookbook pages during conversation
3. **History**: Save past conversations and created recipes
4. **Social**: Share recipes, tips with community

---

## Deployment Considerations

### Local Development
**Current Status**: Fully functional
- Upload server: `http://localhost:8788`
- Frontend: `http://localhost:5173`
- Agent: Local Python process

