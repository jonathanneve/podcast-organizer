import warnings

# Suppress the torch.tensor copy warning from transformers
warnings.filterwarnings(
    "ignore", 
    message="To copy construct from a tensor",
    category=UserWarning
)

import torch
from typing import cast
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

import config


class LLMHandler:
    def __init__(self):
        self.model_name = config.LLM_MODEL
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
        
        prompt = config.PROMPT_TEMPLATE.format(
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
    