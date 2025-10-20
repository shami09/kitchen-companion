"""
Build vector embeddings from a PDF cookbook for RAG.
Usage: python build_vectorstore.py <path_to_cookbook.pdf>
"""

import os
import sys
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter

load_dotenv('.env.local')

def build_vectorstore(pdf_path: str, output_dir: str = "vectorstore"):
    """
    Load a PDF cookbook, split it into chunks, create embeddings, and save to FAISS.
    
    Args:
        pdf_path: Path to the PDF cookbook file
        output_dir: Directory to save the vectorstore (default: "vectorstore")
    """
    
    if not os.path.exists(pdf_path):
        print(f"❌ Error: PDF file not found at {pdf_path}")
        sys.exit(1)
    
    print(f"📖 Loading PDF from: {pdf_path}")
    
    # Load the PDF
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    
    print(f"✅ Loaded {len(documents)} pages from PDF")
    
    # Split documents into chunks
    # Adjust chunk_size and overlap based on your cookbook's structure
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,        # Size of each chunk in characters
        chunk_overlap=200,      # Overlap between chunks to maintain context
        length_function=len,
        separators=["\n\n", "\n", " ", ""]  # Split on paragraphs first, then sentences
    )
    
    chunks = text_splitter.split_documents(documents)
    print(f"✅ Split into {len(chunks)} text chunks")
    
    # Create embeddings
    print("🔄 Creating embeddings (this may take a few minutes)...")
    embeddings = OpenAIEmbeddings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        model="text-embedding-3-small"  # or "text-embedding-ada-002"
    )
    
    # Create FAISS vectorstore
    vectorstore = FAISS.from_documents(chunks, embeddings)
    
    # Save vectorstore locally
    os.makedirs(output_dir, exist_ok=True)
    vectorstore.save_local(output_dir)
    
    print(f"✅ Vector store saved to: {output_dir}")
    print(f"📊 Total chunks indexed: {len(chunks)}")
    print("\n🎉 Ready to use! Run your agent with: python agent.py dev")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_vectorstore.py <path_to_cookbook.pdf>")
        print("\nExample:")
        print("  python build_vectorstore.py cookbooks/salt_fat_acid_heat.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    build_vectorstore(pdf_path)