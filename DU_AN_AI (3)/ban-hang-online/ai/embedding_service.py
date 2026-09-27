import os
import json
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

_model = None

def get_embedding_model_name():
    # Priority: 1. config.json, 2. Environment variable
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('embedding_model'):
                    return data['embedding_model'].strip()
        except Exception:
            pass
    return os.environ.get('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2').strip()

def get_model():
    global _model
    if _model is None:
        model_name = get_embedding_model_name()
        print(f"[Embedding Service] Loading model: {model_name} ...")
        # Load the local model (downloads if not already cached)
        _model = SentenceTransformer(model_name)
    return _model

def embed_texts(texts):
    """
    Tạo embeddings cho một danh sách văn bản (chunks).
    Trả về list các list (vector).
    """
    if not texts:
        return []
    model = get_model()
    embeddings = model.encode(texts)
    return embeddings.tolist()

def embed_query(query):
    """
    Tạo embedding cho một câu hỏi.
    Trả về một list (vector).
    """
    if not query:
        return []
    model = get_model()
    embedding = model.encode([query])
    return embedding[0].tolist()
