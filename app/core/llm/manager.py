from typing import List, Dict, Any
from .bedrock_llm import BedrockLLM

class LLMManager:
    def __init__(self, model_name: str, model_backend: str):
        self.model_name = model_name
        self.model_backend = model_backend
        if model_backend == "bedrock":
            self.llm = BedrockLLM(model_name=model_name, model_backend=model_backend, region="us-east-1")
        else:
            raise ValueError(f"Unsupported backend: {model_backend}")

    async def generate(self, messages: List[Dict[str, str]]) -> str:
        return await self.llm.generate(messages)