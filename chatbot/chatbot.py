#!/usr/bin/env python3

import argparse
import sys
from typing import Optional
from document_store import DocumentStore
from llm_handler import LLMHandler
import config


class Chatbot:
    
    def __init__(self):
        print(config.WELCOME_MESSAGE)
        
        self.document_store = DocumentStore()
        self.llm = LLMHandler()
        
        print("\n" + "=" * 60)
        print("Ready! Type your question or /help for commands.")
        print("=" * 60 + "\n")
    
    def load_document(self, filepath: str) -> bool:
        return self.document_store.load_file(filepath)
    
    def ask(self, question: str) -> str:
        if not self.document_store.is_loaded():
            return ("No document loaded. Please load a document first:\n"
                   "   /load <filepath>")
        
        relevant_chunks = self.document_store.find_relevant_chunks(question)
        
        if not relevant_chunks:
            return "I couldn't find any relevant information in the document."
        
        response = self.llm.generate_response(question, relevant_chunks)
        
        return response
    
    def run(self):
        while True:
            try:
                user_input = input("\nQuestion: ").strip()
                
                if not user_input:
                    continue
                
                print("\nThinking...", end="", flush=True)
                response = self.ask(user_input)
                print("\n Answer: ", response)
                
            except KeyboardInterrupt:
                print("\n\n Goodbye!")
                break
            except EOFError:
                break


def main():
    parser = argparse.ArgumentParser(
        description="Local Document-Based Chatbot",
        epilog="Example: python chatbot.py --file my_document.txt"
    )
    
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to a text file to load at startup"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help=f"Override the LLM model (default: {config.LLM_MODEL})"
    )
    
    args = parser.parse_args()
    
    if args.model:
        config.LLM_MODEL = args.model
        print(f"Using model: {args.model}")
    
    try:
        chatbot = Chatbot()
    except Exception as e:
        print(f"\nFailed to initialize chatbot: {e}")
        print("\nTry using a smaller model:")
        print("  python chatbot.py --model TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        sys.exit(1)
    
    if args.file:
        chatbot.load_document(args.file)
    
    chatbot.run()


if __name__ == "__main__":
    main()
