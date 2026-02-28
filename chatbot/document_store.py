import os
from typing import Optional
import numpy as np
from sentence_transformers import SentenceTransformer

import config


class DocumentStore:
    def __init__(self):
        print("Loading embedding model (this may take a moment on first run)...")
        
        self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
        
        self.chunks: list[str] = []           
        self.embeddings: Optional[np.ndarray] = None  
        self.current_file: Optional[str] = None       
        
        print("Embedding model ready!")
    
    def load_file(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            print(f"Error: File not found: {filepath}")
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.strip():
                print("Error: File is empty")
                return False
            
            self.chunks = self._create_chunks(content)
            
            print(f"Creating embeddings for {len(self.chunks)} chunks...")
            self.embeddings = self.embedding_model.encode(
                self.chunks,
                show_progress_bar=True,
                convert_to_numpy=True
            )
            
            self.current_file = filepath
            
            print(f"Loaded: {os.path.basename(filepath)} ({len(self.chunks)} chunks)")
            return True
            
        except Exception as e:
            print(f"Error loading file: {e}")
            return False
    
    def _create_chunks(self, text: str) -> list[str]:
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + 500
            chunk = text[start:end]
            
            if chunk.strip():
                chunks.append(chunk.strip())
            
            start = end - 50
        
        return chunks
    
    def find_relevant_chunks(self, query: str) -> list[str]:
        if not self.chunks or self.embeddings is None:
            return []
        
        query_embedding = self.embedding_model.encode(query, convert_to_numpy=True)
        similarities = self._cosine_similarity(query_embedding, self.embeddings)
        top_indices = np.argsort(similarities)[-3:][::-1]
        return [self.chunks[i] for i in top_indices]
    
    def _cosine_similarity(self, query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
        query_norm = query_vec / np.linalg.norm(query_vec)
        doc_norms = doc_vecs / np.linalg.norm(doc_vecs, axis=1, keepdims=True)
        return np.dot(doc_norms, query_norm)
    
    def clear(self):
        self.chunks = []
        self.embeddings = None
        self.current_file = None
        print("Document cleared from memory")
    
    def is_loaded(self) -> bool:
        return self.current_file is not None and len(self.chunks) > 0
