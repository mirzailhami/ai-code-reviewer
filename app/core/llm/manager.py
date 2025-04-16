from typing import List, Dict, Any
from .bedrock_llm import BedrockLLM

class LLMManager:
    """Coordinates interactions with Bedrock LLM for code review tasks.

    Attributes:
        model_name (str): Name of the Bedrock model.
        model_backend (str): Backend type, must be 'bedrock'.
        llm (BedrockLLM): Instance of the BedrockLLM client.
    """

    def __init__(self, model_name: str, model_backend: str):
        """Initializes the LLMManager with a model and backend.

        Args:
            model_name (str): Name of the Bedrock model to use.
            model_backend (str): Backend type, must be 'bedrock'.

        Raises:
            ValueError: If an unsupported backend is provided.

        Example:
            >>> manager = LLMManager("mistral_large", "bedrock")
        """
        self.model_name = model_name
        self.model_backend = model_backend
        if model_backend == "bedrock":
            self.llm = BedrockLLM(model_name=model_name, model_backend=model_backend, region="us-east-1")
        else:
            raise ValueError(f"Unsupported backend: {model_backend}")

    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generates a response using the Bedrock LLM.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' and 'content' keys.

        Returns:
            str: Generated text output from the LLM.

        Example:
            >>> manager = LLMManager("mistral_large", "bedrock")
            >>> messages = [{"role": "user", "content": "Review code"}]
            >>> asyncio.run(manager.generate(messages))
            'Code review results...'
        """
        return await self.llm.generate(messages)