import zipfile
import os
import shutil
from typing import Dict, List, Set


class ZipProcessor:
    """Processes ZIP archives to extract source code files and detect programming languages."""

    def __init__(self, zip_path: str):
        """Initializes the ZipProcessor with a ZIP file path.

        Args:
            zip_path (str): Path to the ZIP archive to process.
        """
        self.zip_path = zip_path

    def extract(self, zip_path: str) -> Dict:
        """Extracts source code files from a ZIP archive.

        Args:
            zip_path (str): Path to the ZIP archive.

        Returns:
            Dict: Dictionary containing a list of files with their paths and contents.

        Raises:
            ValueError: If the ZIP file cannot be read or extracted.
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                temp_dir = "temp_extracted"
                os.makedirs(temp_dir, exist_ok=True)
                zip_ref.extractall(temp_dir)

                files = []
                for root, _, filenames in os.walk(temp_dir):
                    for filename in filenames:
                        if filename.endswith(('.py', '.ts', '.js', '.tsx', '.jsx', '.html')):
                            file_path = os.path.join(root, filename)
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            files.append({
                                "path": os.path.relpath(file_path, temp_dir),
                                "content": content
                            })

                shutil.rmtree(temp_dir)

                return {"files": files}
        except Exception as e:
            raise ValueError(f"Failed to process ZIP: {str(e)}")

    def extract_languages(self) -> Set[str]:
        """Detects programming languages used in the ZIP archive based on file extensions.

        Returns:
            Set[str]: Set of detected languages (e.g., 'Python', 'JavaScript').

        Raises:
            ValueError: If the ZIP file cannot be read.
        """
        languages = set()
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                for file_name in zip_ref.namelist():
                    if file_name.endswith('.py'):
                        languages.add('Python')
                    elif file_name.endswith(('.ts', '.tsx')):
                        languages.add('TypeScript')
                    elif file_name.endswith(('.js', '.jsx')):
                        languages.add('JavaScript')
                    elif file_name.endswith('.html'):
                        languages.add('HTML')
            return languages
        except Exception as e:
            raise ValueError(f"Error processing ZIP: {str(e)}")