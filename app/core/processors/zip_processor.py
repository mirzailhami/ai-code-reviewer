import zipfile
import os
import shutil
from typing import Dict, List, Set
import logging

logger = logging.getLogger(__name__)

class ZipProcessor:
    """Processes ZIP archives to extract source code files and detect programming languages."""

    def __init__(self, zip_path: str):
        """Initializes the ZipProcessor with a ZIP file path."""
        self.zip_path = zip_path

    def extract(self, zip_path: str) -> Dict:
        """Extracts source code files from a ZIP archive."""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                temp_dir = "temp_extracted"
                os.makedirs(temp_dir, exist_ok=True)
                zip_ref.extractall(temp_dir)

                files = []
                for root, _, filenames in os.walk(temp_dir):
                    for filename in filenames:
                        if filename.endswith(('.py', '.ts', '.js', '.tsx', '.jsx', '.html', '.txt')):
                            file_path = os.path.join(root, filename)
                            try:
                                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read()
                                files.append({
                                    "path": os.path.relpath(file_path, temp_dir),
                                    "content": content
                                })
                            except Exception as e:
                                logger.debug(f"Failed to read {file_path}: {str(e)}")

                shutil.rmtree(temp_dir)
                logger.debug(f"Extracted files: {[f['path'] for f in files]}")
                return {"files": files}
        except Exception as e:
            logger.error(f"Failed to process ZIP: {str(e)}")
            raise ValueError(f"Failed to process ZIP: {str(e)}")

    def extract_languages(self) -> Set[str]:
        """Detects programming languages used in the ZIP archive."""
        languages = set()
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                logger.debug(f"Files in zip: {file_list}")
                for file_name in file_list:
                    # Extension-based detection
                    if file_name.endswith('.py'):
                        languages.add('Python')
                    elif file_name.endswith(('.ts', '.tsx')):
                        languages.add('TypeScript')
                    elif file_name.endswith(('.js', '.jsx')):
                        languages.add('JavaScript')
                    elif file_name.endswith('.html'):
                        languages.add('HTML')
                    # Content-based detection
                    elif file_name.endswith('.txt') or '.' not in file_name.split('/')[-1]:
                        try:
                            content = zip_ref.read(file_name).decode('utf-8', errors='ignore')
                            if 'def ' in content or 'import ' in content:
                                languages.add('Python')
                            if 'function ' in content and ': string' in content:
                                languages.add('TypeScript')
                            if 'function ' in content and 'var ' in content:
                                languages.add('JavaScript')
                            logger.debug(f"Content-based detection for {file_name}: {content[:100]}")
                        except Exception as e:
                            logger.debug(f"Failed to read {file_name}: {str(e)}")
                logger.debug(f"Detected languages: {list(languages)}")
        except Exception as e:
            logger.error(f"Error processing ZIP: {str(e)}")
            raise ValueError(f"Error processing ZIP: {str(e)}")
        return languages