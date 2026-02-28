LLM_MODEL = "Qwen/Qwen2-0.5B-Instruct"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
WELCOME_MESSAGE = """
╔══════════════════════════════════════════════════════════════════╗
║           Podcast Organizer Chatbot                              ║
║                                                                  ║
║  Ask questions about your podcast using a local LLM.             ║
╚══════════════════════════════════════════════════════════════════╝
"""

# This propt is used to provide the LLM with context from the document and help ensure it only responds using information from the document, not outside knowledge
PROMPT_TEMPLATE = """You are a helpful assistant that answers questions based only on the provided context. If the answer cannot be found in the context, say "I couldn't find information about that in the loaded document."

Context from the document:
---
{context}
---

Question: {question}

Answer based only on the context above:"""

