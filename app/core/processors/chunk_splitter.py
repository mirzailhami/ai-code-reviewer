from typing import List

class ChunkSplitter:
    """Splits text into fixed-size chunks for processing."""

    def __init__(self, chunk_size: int):
        """Initializes the ChunkSplitter with a specified chunk size.

        Args:
            chunk_size (int): Size of each text chunk.
        """
        self.chunk_size = chunk_size

    def split(self, text: str) -> List[str]:
        """Splits the input text into chunks of specified size.

        Args:
            text (str): Text to be split.

        Returns:
            List[str]: List of text chunks.

        Examples:
            >>> splitter = ChunkSplitter(3)
            >>> splitter.split("abcdef")
            ['abc', 'def']
        """
        if not text:
            return []
        return [text[i:i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]