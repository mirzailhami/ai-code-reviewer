from typing import Dict, List
from app.core.processors.zip_processor import ZipProcessor
from app.core.llm.manager import LLMManager
import logging
import zipfile
import json
import yaml
import asyncio

logger = logging.getLogger(__name__)

class ValidationAgent:
    """Validates code submissions against a specified tech stack."""

    def __init__(self, tech_stack, model_name, model_backend):
        """Initialize ValidationAgent."""
        self.tech_stack = [self._normalize_language(lang.strip()) for lang in tech_stack if self._normalize_language(lang.strip())]
        self.llm = LLMManager(model_name=model_name, model_backend=model_backend)
        try:
            with open("config/models.yaml", "r") as f:
                self.prompts = yaml.safe_load(f).get("prompts", {})
        except Exception as e:
            logger.error(f"Failed to load prompts: {str(e)}")
            self.prompts = {}
        logger.debug(f"ValidationAgent initialized with tech_stack={self.tech_stack}, model_name={model_name}")

    def _normalize_language(self, lang: str) -> str:
        """Normalize language names."""
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

    async def _llm_validate(self, detected_languages: List[str], files: List[str]) -> List[str]:
        """Use LLM to validate languages."""
        system_prompt = self.prompts.get("validation", {}).get("system", "You are a code analysis expert. Return JSON only: [\"language\", ...].")
        user_prompt = self.prompts.get("validation", {}).get("user", "").format(
            file_list=", ".join(files[:5]),
            detected_languages=", ".join(detected_languages)
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        try:
            logger.debug(f"Using model {self.llm.model_name} for validation: prompt={json.dumps(messages)[:200]}...")
            response = await self.llm.generate(messages)
            logger.debug(f"Using model {self.llm.model_name} for validation: response={response[:200]}...")
            return json.loads(response) if response else detected_languages
        except Exception as e:
            logger.error(f"LLM validation failed: {str(e)}")
            return detected_languages

    async def validate_submission(self, zip_path: str) -> Dict:
        """Validate code submission."""
        try:
            logger.debug(f"Validating zip: {zip_path}")
            zip_processor = ZipProcessor(zip_path)
            detected_languages = zip_processor.extract_languages()
            with zipfile.ZipFile(zip_path) as z:
                files = [name for name in z.namelist() if name.endswith(('.py', '.ts', '.js', '.tsx', '.jsx', '.html'))]
            logger.debug(f"Files in {zip_path}: {files}")
            logger.debug(f"Detected languages: {list(detected_languages)}")
            logger.debug(f"Expected tech stack: {self.tech_stack}")

            if len(detected_languages) > len(self.tech_stack):
                detected_languages = await self._llm_validate(detected_languages, files)

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

            # Include all detected languages, not just matches
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