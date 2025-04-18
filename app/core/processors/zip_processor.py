import zipfile
import os
from typing import Dict, List, Set
import logging
import yaml
from pygments.lexers import guess_lexer_for_filename, TextLexer
from pygments.util import ClassNotFound

logger = logging.getLogger(__name__)

class ZipProcessor:
    """Processes ZIP archives to extract source code and detect programming languages.

    Attributes:
        zip_path (str): Path to the ZIP file.
        extension_map (Dict[str, str]): Mapping of file extensions to languages.
        content_patterns (Dict[str, List[str]]): Patterns for content-based language detection.
    """

    def __init__(self, zip_path: str = None):
        """Initialize ZipProcessor with an optional ZIP file path.

        Args:
            zip_path (str, optional): Path to the ZIP file.
        """
        self.zip_path = zip_path
        self.extension_map, self.content_patterns = self._load_language_config()
        logger.debug(f"Initialized ZipProcessor with zip_path: {zip_path}, languages: {list(self.extension_map.values())}")

    def _load_language_config(self) -> tuple[Dict[str, str], Dict[str, List[str]]]:
        """Load language mappings from config/languages.yaml.

        Returns:
            tuple[Dict[str, str], Dict[str, List[str]]]: Extension map and content patterns.

        Raises:
            ValueError: If config file is missing or invalid.
        """
        try:
            with open("config/languages.yaml", "r") as f:
                config = yaml.safe_load(f)
            return (
                config.get("languages", {}).get("extensions", {}),
                config.get("languages", {}).get("patterns", {})
            )
        except Exception as e:
            logger.error(f"Failed to load languages.yaml: {str(e)}")
            raise ValueError(f"Failed to load language configuration: {str(e)}")

    def extract(self, zip_path: str = None) -> Dict[str, List[Dict]]:
        """Extract source code files from a ZIP archive.

        Args:
            zip_path (str, optional): Path to ZIP file. Defaults to self.zip_path.

        Returns:
            Dict[str, List[Dict]]: Dictionary with list of files, each with path and content.

        Raises:
            ValueError: If ZIP file is invalid or cannot be processed.
        """
        zip_path = zip_path or self.zip_path
        if not zip_path or not os.path.exists(zip_path):
            logger.error(f"Invalid or missing zip path: {zip_path}")
            raise ValueError(f"Invalid zip path: {zip_path}")

        files = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.is_dir() or file_info.filename.startswith('__MACOSX'):
                        continue
                    if self._is_valid_file(file_info.filename):
                        try:
                            content = zip_ref.read(file_info.filename).decode('utf-8', errors='ignore')
                            files.append({
                                "path": file_info.filename,
                                "content": content
                            })
                        except Exception as e:
                            logger.debug(f"Failed to read {file_info.filename}: {str(e)}")
            logger.debug(f"Extracted {len(files)} files from {zip_path}")
            return {"files": files}
        except Exception as e:
            logger.error(f"Failed to process ZIP: {str(e)}")
            raise ValueError(f"Failed to process ZIP: {str(e)}")

    def extract_languages(self, zip_path: str = None) -> Set[str]:
        """Detect programming languages in the ZIP archive.

        Args:
            zip_path (str, optional): Path to ZIP file. Defaults to self.zip_path.

        Returns:
            Set[str]: Set of detected programming languages.

        Raises:
            ValueError: If ZIP file is invalid or cannot be processed.
        """
        zip_path = zip_path or self.zip_path
        if not zip_path or not os.path.exists(zip_path):
            logger.error(f"Invalid or missing zip path: {zip_path}")
            raise ValueError(f"Invalid zip path: {zip_path}")

        languages = set()
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.is_dir() or file_info.filename.startswith('__MACOSX'):
                        continue
                    languages.update(self._detect_languages(file_info, zip_ref))
            logger.debug(f"Detected languages: {list(languages)}")
            return languages
        except Exception as e:
            logger.error(f"Failed to process ZIP: {str(e)}")
            raise ValueError(f"Failed to process ZIP: {str(e)}")

    def _is_valid_file(self, filename: str) -> bool:
        """Check if a file has a valid extension or is text-based.

        Args:
            filename (str): Name of the file.

        Returns:
            bool: True if file is valid for extraction, False otherwise.
        """
        ext = os.path.splitext(filename)[1].lower()
        return ext in self.extension_map or ext == '.txt' or '.' not in filename.split('/')[-1]

    def _detect_languages(self, file_info: zipfile.ZipInfo, zip_ref: zipfile.ZipFile) -> Set[str]:
        """Detect languages for a single file based on extension, content, or Pygments.

        Args:
            file_info (zipfile.ZipInfo): File information from ZIP.
            zip_ref (zipfile.ZipFile): Open ZIP file reference.

        Returns:
            Set[str]: Set of detected languages.
        """
        languages = set()
        filename = file_info.filename
        ext = os.path.splitext(filename)[1].lower()

        # Extension-based detection
        if ext in self.extension_map:
            languages.add(self.extension_map[ext])
            return languages

        # Content-based detection for .txt or no-extension files
        if ext == '.txt' or '.' not in filename.split('/')[-1]:
            try:
                content = zip_ref.read(filename).decode('utf-8', errors='ignore')
                # Pattern-based detection
                for lang, patterns in self.content_patterns.items():
                    if any(pattern in content for pattern in patterns):
                        languages.add(lang)
                # Pygments-based detection as fallback
                if not languages:
                    try:
                        lexer = guess_lexer_for_filename(filename, content, stripnl=False)
                        languages.add(lexer.name)
                    except ClassNotFound:
                        logger.debug(f"Pygments could not detect language for {filename}")
            except Exception as e:
                logger.debug(f"Failed to read {filename} for content analysis: {str(e)}")

        return languages