from chromadb.api import client
import os
import sys
import chromadb
from embedding_service import embed_texts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, 'ai', 'documents')
DB_PATH = os.path.join(BASE_DIR, 'ai', 'vector_db')

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

def get_all_text_files(directory):
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith('.txt'):
                files.append(os.path.join(root, filename))
    return files

def chunk_text(text, chunk_size, overlap):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += (chunk_size - overlap)
    return chunks

def ingest_documents():
    print("[RAG Ingest] Bắt đầu quá trình đọc tài liệu...")
    
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH, exist_ok=True)
        
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # Xóa collection cũ nếu có để ingest lại từ đầu (đơn giản hóa)
    try:
        client.delete_collection(name="sales_documents")
    except chromadb.errors.NotFoundError:
        pass
        
    collection = client.create_collection(name="sales_documents")
    
    files = get_all_text_files(DOCS_DIR)
    
    if not files:
        print(f"[RAG Ingest] Không tìm thấy tài liệu nào trong thư mục {DOCS_DIR}")
        exit()

    total_chunks = 0
    all_chunks = []
    all_metadatas = []
    all_ids = []

    for file_path in files:
        print(f"[RAG Ingest] Đang đọc file: {os.path.relpath(file_path, BASE_DIR)}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            filename = os.path.basename(file_path)
            rel_path = os.path.relpath(file_path, DOCS_DIR)
            
            chunks = chunk_text(content, CHUNK_SIZE, CHUNK_OVERLAP)
            
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadatas.append({
                    "source": rel_path,
                    "filename": filename,
                    "chunk_index": i
                })
                all_ids.append(f"{filename}_chunk_{i}")
                
            print(f"  -> Tạo được {len(chunks)} chunks.")
            total_chunks += len(chunks)
        except Exception as e:
            print(f"  -> Lỗi khi đọc {file_path}: {e}")

    # CHUNGKING
    if all_chunks:
        print(f"[RAG Ingest] Đang tạo embeddings cho {total_chunks} chunks...")
        embeddings = embed_texts(all_chunks)
        
        print("[RAG Ingest] Đang lưu vào ChromaDB...")
        # Lô nhỏ để tránh lỗi memory nếu quá nhiều
        batch_size = 100
        for i in range(0, len(all_chunks), batch_size):
            collection.add(
                documents=all_chunks[i:i+batch_size],
                embeddings=embeddings[i:i+batch_size],
                metadatas=all_metadatas[i:i+batch_size],
                ids=all_ids[i:i+batch_size]
            )
            
        print(f"[RAG Ingest] ✅ Hoàn thành! Tổng chunks đã lưu: {total_chunks}")
    else:
        print("[RAG Ingest] ❌ Không có chunk nào được tạo.")

if __name__ == "__main__":
    ingest_documents()
