import os
import warnings
from typing import Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import torch
from typing import cast
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

# Suppress the torch.tensor copy warning from transformers
warnings.filterwarnings(
    "ignore", 
    message="To copy construct from a tensor",
    category=UserWarning
)

LLM_MODEL = "Qwen/Qwen2-0.5B-Instruct"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# This propt is used to provide the LLM with context from the document and help ensure it only responds using information from the document, not outside knowledge
PROMPT_TEMPLATE = """You are a helpful assistant that answers questions based only on the provided context. If the answer cannot be found in the context, say "I couldn't find information about that in the loaded document."

Context from the document:
---
{context}
---

Question: {question}

Answer based only on the context above:"""

class DocumentStore:
    def __init__(self):
        print("Loading embedding model (this may take a moment on first run)...")
        
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        
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

            self._index_content(content)
            self.current_file = filepath

            print(f"Loaded: {os.path.basename(filepath)} ({len(self.chunks)} chunks)")
            return True

        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def load_text(self, text: str):
        """Loads text content directly and creates embeddings."""
        self._index_content(text)
        self.current_file = "<text>"

    def _index_content(self, content: str):
        """Chunks text and creates embeddings."""
        self.chunks = self._create_chunks(content)
        self.embeddings = self.embedding_model.encode(
            self.chunks,
            show_progress_bar=False,
            convert_to_numpy=True
        )
    
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

class LLMHandler:
    def __init__(self):
        self.model_name = LLM_MODEL
        self.tokenizer = None
        self.model = None
        self.pipe = None
        self._load_model()
    
    def _load_model(self):
        print(f"Loading language model: {self.model_name}")
        print("   (This may take a few minutes on first run...)")
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float32,
                trust_remote_code=True,
                low_cpu_mem_usage=True
            )
            self.model = self.model.to("cpu")
            self.pipe = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer
            )
            
            print("Language model ready!")
            
        except Exception as e:
            print(f"Error loading model: {e}")
            raise
    
    def generate_response(self, question: str, context_chunks: list[str]) -> str:
        if not context_chunks:
            return ("I don't have any document loaded to answer from.")
        
        if not self.pipe or not self.tokenizer:
            raise Exception('LLM pipeline not initialized correctly!')

        context = "\n\n".join(context_chunks)
        
        prompt = PROMPT_TEMPLATE.format(
            context=context,
            question=question
        )
        
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        try:
            outputs = self.pipe(
                messages,
                max_new_tokens=512,
                temperature=0.7,
                top_p=0.9,
                do_sample=True, 
                pad_token_id=self.tokenizer.eos_token_id, 
                return_full_text=False
            )
            
            raw = outputs[0] if isinstance(outputs, list) else outputs
            output = cast(dict, raw)
            response = output["generated_text"]

            if isinstance(response, list):
                response = response[-1].get("content", str(response))
            
            return response.strip()
            
        except Exception as e:
            return f"Error generating response: {e}"
    