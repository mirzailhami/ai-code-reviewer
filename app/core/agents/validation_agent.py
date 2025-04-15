from typing import Dict, List
from app.core.processors.zip_processor import ZipProcessor
from app.core.llm.manager import LLMManager
import os
import logging
import zipfile

logger = logging.getLogger(__name__)

class ValidationAgent:
    def __init__(self, tech_stack, model_name, model_backend):
        self.tech_stack = [self._normalize_language(lang.strip()) for lang in tech_stack if self._normalize_language(lang.strip())]
        self.llm = LLMManager(model_name=model_name, model_backend=model_backend)
        logger.debug(f"ValidationAgent initialized with tech_stack={self.tech_stack}, model_name={model_name}, model_backend={model_backend}")

    def _normalize_language(self, lang: str) -> str:
        lang_map = {
            "python": "Python",
            "typescript": "TypeScript",
            "javascript": "JavaScript",
            "node.js": "JavaScript",
            "node.js (typescript)": "TypeScript",
            "html": "HTML",
            "css": "CSS",
            "llm": "",
            "sonarqube": ""
        }
        normalized = lang_map.get(lang.lower(), lang.capitalize() if lang.lower() in ['java', 'c', 'c++', 'ruby'] else "")
        logger.debug(f"Normalized '{lang}' to '{normalized}'")
        return normalized

    def validate_submission(self, zip_path: str) -> Dict:
        try:
            logger.debug(f"Validating zip: {zip_path}")
            zip_processor = ZipProcessor(zip_path)
            detected_languages = zip_processor.extract_languages()
            logger.debug(f"Files in {zip_path}: {[name for name in zipfile.ZipFile(zip_path).namelist() if name.endswith(('.py', '.ts', '.js', '.tsx', '.jsx', '.html'))]}")
            logger.debug(f"Detected languages: {list(detected_languages)}")
            logger.debug(f"Expected tech stack: {self.tech_stack}")
            if not self.tech_stack:
                logger.warning("No valid tech stack provided; assuming validation passes")
                return {
                    "valid": True,
                    "reason": None,
                    "languages": list(detected_languages)
                }
            matching_languages = set(self.tech_stack).intersection(detected_languages)
            logger.debug(f"Matching languages: {list(matching_languages)}")
            if not matching_languages:
                missing = set(self.tech_stack)
                logger.error(f"No matching languages found. Expected: {', '.join(missing)}, Detected: {', '.join(detected_languages) or 'none'}")
                return {
                    "valid": False,
                    "reason": f"No matching languages found in code: {', '.join(missing)}",
                    "languages": list(detected_languages)
                }
            logger.info(f"Validation passed with matching languages: {', '.join(matching_languages)}")
            return {
                "valid": True,
                "reason": None,
                "languages": list(detected_languages)
            }
        except Exception as e:
            logger.error(f"Validation error for {zip_path}: {str(e)}")
            return {
                "valid": False,
                "reason": f"Validation failed: {str(e)}",
                "languages": []
            }