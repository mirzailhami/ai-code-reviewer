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

    async def _llm_validate(self, detected_languages: List[str], files: List[Dict[str, str]]) -> List[str]:
        """Use LLM to validate languages with file content."""
        system_prompt = self.prompts.get("validation", {}).get("system", "You are a code analysis expert. Output JSON only: [\"language\", ...]. Identify languages in the provided files based on file extensions and content. Do not include explanations or non-language terms.")
        user_prompt = self.prompts.get("validation", {}).get("user", "Files: {file_list}.\nDetected: {detected_languages}.\nReturn a JSON array of confirmed languages (e.g., [\"Python\", \"TypeScript\"]).").format(
            file_list=json.dumps([{f["path"]: f["content"][:100]} for f in files[:5]], indent=2),
            detected_languages=json.dumps(list(detected_languages))
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        try:
            logger.debug(f"Validation prompt: {json.dumps(messages)[:500]}...")
            response = await self.llm.generate(messages)
            logger.debug(f"Validation response raw: {response[:200]}")
            llm_languages = json.loads(response) if response else detected_languages
            if not isinstance(llm_languages, list):
                logger.warning(f"Expected array for validation, got: {response[:100]}")
                return detected_languages
            normalized_languages = [self._normalize_language(lang) for lang in llm_languages if self._normalize_language(lang)]
            # Merge LLM languages with initially detected languages
            final_languages = list(set(detected_languages + normalized_languages))
            logger.debug(f"LLM-validated languages: {normalized_languages}, Final merged languages: {final_languages}")
            return final_languages
        except Exception as e:
            logger.error(f"LLM validation failed with {self.llm.model_name}: {str(e)}")
            if self.llm.model_name == "mistral_large":
                logger.info("Retrying validation with claude3_7_sonnet")
                claude_llm = LLMManager(model_name="claude3_7_sonnet", model_backend=self.llm.model_backend)
                try:
                    response = await claude_llm.generate(messages)
                    logger.debug(f"Claude validation response: {response[:200]}")
                    llm_languages = json.loads(response) if response else detected_languages
                    if not isinstance(llm_languages, list):
                        logger.warning(f"Claude expected array, got: {response[:100]}")
                        return detected_languages
                    normalized_languages = [self._normalize_language(lang) for lang in llm_languages if self._normalize_language(lang)]
                    final_languages = list(set(detected_languages + normalized_languages))
                    logger.debug(f"Claude-validated languages: {normalized_languages}, Final merged languages: {final_languages}")
                    return final_languages
                except Exception as claude_e:
                    logger.error(f"Claude validation failed: {str(claude_e)}")
            return list(detected_languages)  # Ensure list output

    async def validate_submission(self, zip_path: str) -> Dict:
        """Validate code submission."""
        try:
            logger.debug(f"Validating zip: {zip_path}")
            zip_processor = ZipProcessor(zip_path)
            detected_languages = list(zip_processor.extract_languages())  # Convert set to list
            logger.debug(f"ZipProcessor detected languages: {detected_languages}")
            with zipfile.ZipFile(zip_path) as z:
                files = [
                    {"path": name, "content": z.read(name).decode('utf-8', errors='ignore')}
                    for name in z.namelist()
                    if name.endswith(('.py', '.ts', '.js', '.tsx', '.jsx', '.html', '.txt'))
                ]
            logger.debug(f"Files in {zip_path}: {[f['path'] for f in files]}")
            logger.debug(f"File contents (first 100 chars): {[{f['path']: f['content'][:100]} for f in files[:2]]}")
            logger.debug(f"Expected tech stack (any match): {self.tech_stack}")

            if not files:
                logger.error("No relevant files found in submission")
                return {
                    "valid": False,
                    "reason": "No relevant files found in submission",
                    "languages": []
                }

            detected_languages = await self._llm_validate(detected_languages, files)
            logger.debug(f"Final detected languages after LLM: {detected_languages}")

            if not self.tech_stack:
                logger.warning("No valid tech stack provided; assuming validation passes")
                return {
                    "valid": True,
                    "reason": "",
                    "languages": detected_languages
                }

            matching_languages = set(self.tech_stack).intersection(set(detected_languages))
            if not matching_languages and detected_languages:
                logger.warning(f"No exact match, allowing partial: {detected_languages}")
                matching_languages = set(detected_languages)
            logger.debug(f"Matching languages: {list(matching_languages)}")

            if not matching_languages:
                missing = set(self.tech_stack)
                logger.error(f"No matching languages found. Expected: {', '.join(missing)}, Detected: {', '.join(detected_languages) or 'none'}")
                return {
                    "valid": False,
                    "reason": f"No matching languages found in code: {', '.join(missing)}",
                    "languages": detected_languages
                }

            logger.info(f"Validation passed with matching languages: {', '.join(matching_languages)}")
            return {
                "valid": True,
                "reason": "",
                "languages": detected_languages
            }
        except Exception as e:
            logger.error(f"Validation error for {zip_path}: {str(e)}")
            return {
                "valid": False,
                "reason": f"Validation failed: {str(e)}",
                "languages": []
            }