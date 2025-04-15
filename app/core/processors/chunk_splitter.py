from typing import List

class ChunkSplitter:
    def __init__(self, chunk_size: int):
        self.chunk_size = chunk_size

    def split(self, text: str) -> List[str]:
        if not text:
            return []
        return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size)]