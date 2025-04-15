from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseLLMAdapter(ABC):
    @abstractmethod
    def invoke(self, prompt: str) -> str:
        pass
    
    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        pass