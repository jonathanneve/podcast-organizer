import warnings
from typing import Optional, cast
import numpy as np
from sentence_transformers import SentenceTransformer
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

# Suppress the torch.tensor copy warning from transformers
warnings.filterwarnings(
    "ignore",
    message="To copy construct from a tensor",
    category=UserWarning
)

LLM_MODEL = "Qwen/Qwen2-0.5B-Instruct"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# This prompt is used to provide the LLM with context from the document and help ensure it only responds using information from the document, not outside knowledge
PROMPT_TEMPLATE = """You are a helpful assistant that answers questions based only on the provided context. If the answer cannot be found in the context, say "I couldn't find information about that in the loaded document."

Context from the document:
---
{context}
---

Question: {question}

Answer based only on the context above:"""

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

class DocumentStore:
    def __init__(self):
        print("Loading embedding model (this may take a moment on first run)...")
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        self.chunks: list[str] = []
        self.embeddings: Optional[np.ndarray] = None
        print("Embedding model ready!")

    def compute_embeddings(self, text: str) -> tuple[list[str], np.ndarray]:
        """Chunks text and creates embeddings."""
        chunks = self._create_chunks(text)
        embeddings = self.embedding_model.encode(
            chunks,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return chunks, embeddings

    def load_precomputed(self, chunks: list[str], embeddings: np.ndarray):
        """Loads pre-computed chunks and embeddings"""
        self.chunks = chunks
        self.embeddings = embeddings

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

    def _create_chunks(self, text: str) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - CHUNK_OVERLAP
        return chunks

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
    