"""
upload_server.py - PDF Upload Server for KitchenCompanion
Handles PDF uploads and builds/updates the vectorstore for RAG

Run: python upload_server.py
Runs on: http://localhost:8788
"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv(".env.local")
# Initialize FastAPI app
app = FastAPI(
    title="KitchenCompanion Upload Server",
    description="Handles PDF uploads and vectorstore management for RAG",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️  WARNING: OPENAI_API_KEY not set! Upload will fail.")
    print("   Set it in .env.local: OPENAI_API_KEY=sk-...")

VECTORSTORE_PATH = os.getenv("VECTORSTORE_PATH", "./vectorstore")

# Ensure directories exist
UPLOAD_DIR = Path("./uploaded_pdfs")
UPLOAD_DIR.mkdir(exist_ok=True)

VECTORSTORE_DIR = Path(VECTORSTORE_PATH)
VECTORSTORE_DIR.mkdir(exist_ok=True)

# Track uploaded PDFs
pdf_list_file = UPLOAD_DIR / "pdf_list.txt"


def get_pdf_list():
    """Get list of uploaded PDFs."""
    if not pdf_list_file.exists():
        return []
    with open(pdf_list_file, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def add_to_pdf_list(filename: str):
    """Add a PDF to the list."""
    pdfs = get_pdf_list()
    if filename not in pdfs:
        with open(pdf_list_file, 'a') as f:
            f.write(f"{filename}\n")


def remove_from_pdf_list(filename: str):
    """Remove a PDF from the list."""
    pdfs = get_pdf_list()
    if filename in pdfs:
        pdfs.remove(filename)
        with open(pdf_list_file, 'w') as f:
            for pdf in pdfs:
                f.write(f"{pdf}\n")


def build_vectorstore_from_pdf(pdf_path: str, output_path: str, merge: bool = True) -> bool:
    """
    Build or update vectorstore from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        output_path: Path to save the vectorstore
        merge: If True, merge with existing vectorstore. If False, create new.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"📄 Loading PDF: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        
        if not documents:
            print("❌ No content found in PDF")
            return False
        
        print(f"📝 Loaded {len(documents)} pages from PDF")
        
        # Split into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        texts = text_splitter.split_documents(documents)
        print(f"✂️  Split into {len(texts)} chunks")
        
        if not texts:
            print("❌ No text chunks created from PDF")
            return False
        
        # Create embeddings
        print("🔄 Creating embeddings...")
        embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        
        # Check if vectorstore already exists
        existing_vectorstore_path = Path(output_path)
        faiss_exists = (existing_vectorstore_path / "index.faiss").exists()
        
        if merge and faiss_exists:
            print("🔄 Merging with existing vectorstore...")
            vectorstore = FAISS.load_local(
                output_path, 
                embeddings, 
                allow_dangerous_deserialization=True
            )
            # Add new documents to existing vectorstore
            vectorstore.add_documents(texts)
            print(f"✅ Added {len(texts)} new chunks to existing vectorstore")
        else:
            print("🆕 Creating new vectorstore...")
            vectorstore = FAISS.from_documents(texts, embeddings)
            print(f"✅ Created new vectorstore with {len(texts)} chunks")
        
        # Save vectorstore
        vectorstore.save_local(output_path)
        print(f"💾 Vectorstore saved to {output_path}")
        
        # Get total vector count
        total_vectors = vectorstore.index.ntotal if hasattr(vectorstore.index, 'ntotal') else "unknown"
        print(f"📊 Total vectors in store: {total_vectors}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error building vectorstore: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "running",
        "service": "KitchenCompanion Upload Server",
        "version": "1.0.0",
        "endpoints": {
            "upload": "POST /upload",
            "info": "GET /vectorstore-info",
            "list": "GET /list-pdfs",
            "clear": "POST /clear-vectorstore"
        }
    }


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF and add it to the RAG vectorstore.
    The agent will automatically reload the vectorstore on next query.
    
    Args:
        file: PDF file to upload
    
    Returns:
        JSON with status and details
    """
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Check API key
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500, 
            detail="OPENAI_API_KEY not configured on server"
        )
    
    try:
        # Read file content
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        print(f"\n{'='*60}")
        print(f"📥 Received PDF: {file.filename}")
        print(f"   Size: {file_size_mb:.2f} MB ({len(content):,} bytes)")
        print(f"{'='*60}")
        
        # Validate file size (max 50MB)
        if file_size_mb > 50:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large ({file_size_mb:.1f}MB). Maximum size is 50MB."
            )
        
        # Save to upload directory (for reference/backup)
        upload_path = UPLOAD_DIR / file.filename
        with open(upload_path, 'wb') as f:
            f.write(content)
        print(f"💾 Saved to: {upload_path}")
        
        # Save to temp file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        print(f"🔄 Processing PDF...")
        
        # Build/update vectorstore (merge with existing)
        success = build_vectorstore_from_pdf(tmp_path, VECTORSTORE_PATH, merge=True)
        
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        if success:
            # Add to PDF list
            add_to_pdf_list(file.filename)
            
            print(f"✅ Upload complete!")
            print(f"{'='*60}\n")
            
            return JSONResponse({
                "status": "success",
                "message": f"PDF '{file.filename}' processed and added to knowledge base",
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "vectorstore_path": VECTORSTORE_PATH,
                "total_pdfs": len(get_pdf_list())
            })
        else:
            # Clean up uploaded file if processing failed
            if upload_path.exists():
                upload_path.unlink()
            
            raise HTTPException(
                status_code=500, 
                detail="Failed to process PDF. Check server logs for details."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Upload error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/vectorstore-info")
async def vectorstore_info():
    """
    Get information about the current vectorstore.
    
    Returns:
        JSON with vectorstore status, PDF count, and vector count
    """
    faiss_path = Path(VECTORSTORE_PATH) / "index.faiss"
    pkl_path = Path(VECTORSTORE_PATH) / "index.pkl"
    
    uploaded_pdfs = get_pdf_list()
    
    if not faiss_path.exists() or not pkl_path.exists():
        return JSONResponse({
            "status": "empty",
            "message": "No vectorstore found. Upload a PDF to get started.",
            "uploaded_pdfs": uploaded_pdfs,
            "pdf_count": len(uploaded_pdfs),
            "vectorstore_path": VECTORSTORE_PATH
        })
    
    # Try to load and get info
    try:
        embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        vectorstore = FAISS.load_local(
            VECTORSTORE_PATH, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
        
        vector_count = vectorstore.index.ntotal if hasattr(vectorstore.index, 'ntotal') else "unknown"
        
        return JSONResponse({
            "status": "ready",
            "message": "Vectorstore loaded and ready",
            "path": VECTORSTORE_PATH,
            "uploaded_pdfs": uploaded_pdfs,
            "pdf_count": len(uploaded_pdfs),
            "vector_count": vector_count
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"Error loading vectorstore: {str(e)}",
            "uploaded_pdfs": uploaded_pdfs,
            "pdf_count": len(uploaded_pdfs),
            "vectorstore_path": VECTORSTORE_PATH
        })


@app.get("/list-pdfs")
async def list_pdfs():
    """
    List all uploaded PDFs.
    
    Returns:
        JSON with list of PDF filenames
    """
    pdfs = get_pdf_list()
    return JSONResponse({
        "pdfs": pdfs,
        "count": len(pdfs)
    })


@app.post("/clear-vectorstore")
async def clear_vectorstore():
    """
    Clear the vectorstore and all uploaded PDFs.
    Use this to start fresh.
    
    Returns:
        JSON with status message
    """
    try:
        import shutil
        
        # Clear vectorstore
        if os.path.exists(VECTORSTORE_PATH):
            shutil.rmtree(VECTORSTORE_PATH)
            os.makedirs(VECTORSTORE_PATH)
            print(f"🗑️  Cleared vectorstore at {VECTORSTORE_PATH}")
        
        # Clear uploaded PDFs
        if UPLOAD_DIR.exists():
            for pdf_file in UPLOAD_DIR.glob("*.pdf"):
                pdf_file.unlink()
            print(f"🗑️  Cleared uploaded PDFs from {UPLOAD_DIR}")
        
        # Clear PDF list
        if pdf_list_file.exists():
            pdf_list_file.unlink()
            print(f"🗑️  Cleared PDF list")
        
        return JSONResponse({
            "status": "success",
            "message": "Vectorstore and all PDFs cleared successfully"
        })
    except Exception as e:
        print(f"❌ Error clearing vectorstore: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete-pdf/{filename}")
async def delete_pdf(filename: str):
    """
    Delete a specific PDF and rebuild vectorstore without it.
    Note: This requires rebuilding the entire vectorstore from remaining PDFs.
    
    Args:
        filename: Name of the PDF file to delete
    
    Returns:
        JSON with status message
    """
    try:
        # Check if PDF exists
        pdf_path = UPLOAD_DIR / filename
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail=f"PDF '{filename}' not found")
        
        # Remove from list
        remove_from_pdf_list(filename)
        
        # Delete the file
        pdf_path.unlink()
        print(f"🗑️  Deleted PDF: {filename}")
        
        # Get remaining PDFs
        remaining_pdfs = get_pdf_list()
        
        if remaining_pdfs:
            # Rebuild vectorstore from remaining PDFs
            print(f"🔄 Rebuilding vectorstore from {len(remaining_pdfs)} remaining PDF(s)...")
            
            import shutil
            if os.path.exists(VECTORSTORE_PATH):
                shutil.rmtree(VECTORSTORE_PATH)
                os.makedirs(VECTORSTORE_PATH)
            
            for pdf_name in remaining_pdfs:
                pdf_file = UPLOAD_DIR / pdf_name
                if pdf_file.exists():
                    build_vectorstore_from_pdf(
                        str(pdf_file), 
                        VECTORSTORE_PATH, 
                        merge=True
                    )
            
            return JSONResponse({
                "status": "success",
                "message": f"PDF '{filename}' deleted and vectorstore rebuilt",
                "remaining_pdfs": len(remaining_pdfs)
            })
        else:
            # No PDFs left, clear vectorstore
            import shutil
            if os.path.exists(VECTORSTORE_PATH):
                shutil.rmtree(VECTORSTORE_PATH)
                os.makedirs(VECTORSTORE_PATH)
            
            return JSONResponse({
                "status": "success",
                "message": f"PDF '{filename}' deleted. No PDFs remaining.",
                "remaining_pdfs": 0
            })
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*60)
    print("🍳 KitchenCompanion Upload Server")
    print("="*60)
    print(f"📁 Vectorstore path: {VECTORSTORE_PATH}")
    print(f"📁 Upload directory: {UPLOAD_DIR}")
    print(f"🔑 OpenAI API Key: {'✅ Set' if OPENAI_API_KEY else '❌ Not Set'}")
    print(f"📚 Uploaded PDFs: {len(get_pdf_list())}")
    print("="*60)
    print("\n🚀 Starting server on http://localhost:8788")
    print("   API docs: http://localhost:8788/docs")
    print("   Health check: http://localhost:8788/")
    print("\n   Press Ctrl+C to stop\n")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8788,
        log_level="info"
    )