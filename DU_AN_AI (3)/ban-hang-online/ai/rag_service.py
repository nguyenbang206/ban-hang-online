import os
import chromadb
from ai.embedding_service import embed_query

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'ai', 'vector_db')

_chroma_client = None
_collection = None

def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        if not os.path.exists(DB_PATH):
            os.makedirs(DB_PATH, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=DB_PATH)
    return _chroma_client

def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        # Lấy collection nếu đã có, tạo mới nếu chưa có
        try:
            _collection = client.get_collection(name="sales_documents")
        except ValueError:
            # Collection does not exist
            _collection = None
    return _collection

def check_rag_status():
    """Kiểm tra xem vector DB đã được khởi tạo và có dữ liệu chưa."""
    col = get_collection()
    if col is None:
        return False
    try:
        return col.count() > 0
    except Exception:
        return False

def retrieve_relevant_documents(question, top_k=5):
    """
    Tìm kiếm các chunk liên quan nhất đến câu hỏi.
    Trả về list of dict: [{'content': '...', 'source': '...'}, ...]
    """
    col = get_collection()
    if col is None:
        return []

    # Tạo embedding cho câu hỏi
    query_embedding = embed_query(question)
    
    # Tìm kiếm
    try:
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
    except Exception as e:
        print(f"[RAG Service] Lỗi truy vấn ChromaDB: {e}")
        return []
        
    docs = []
    if results['documents'] and results['documents'][0]:
        for i, doc in enumerate(results['documents'][0]):
            meta = results['metadatas'][0][i] if results['metadatas'] and results['metadatas'][0] else {}
            docs.append({
                "content": doc,
                "source": meta.get('source', 'Unknown'),
                "filename": meta.get('filename', 'Unknown')
            })
            
    return docs
