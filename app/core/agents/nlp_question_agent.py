"""NLP question agent for evaluating code submission questions.

This module defines the NLPQuestionAgent class, which processes scorecard questions
using LLM to generate answers based on SonarQube data, code samples, and specifications.
"""

from typing import List, Dict, Any
from app.core.llm.manager import LLMManager
import json
import yaml
import re
import asyncio
from asyncio import Semaphore
import logging

logger = logging.getLogger(__name__)

class NLPQuestionAgent:
    """Processes scorecard questions with NLP for code evaluation.

    Attributes:
        model_name: Name of the LLM model.
        model_backend: Backend for LLM (e.g., 'bedrock').
        llm: LLMManager instance for generation.
        semaphore: Asyncio semaphore to limit concurrent LLM calls.
        prompts: Loaded prompt templates from models.yaml.
    """
    def __init__(self, model_name: str, model_backend: str):
        """Initialize NLPQuestionAgent with model configuration.

        Args:
            model_name: Name of the LLM model.
            model_backend: Backend for LLM (e.g., 'bedrock').

        Raises:
            FileNotFoundError: If models.yaml is missing.
            yaml.YAMLError: If models.yaml is invalid.
        """
        self.model_name = model_name
        self.model_backend = model_backend
        self.llm = LLMManager(model_name="mistral_large", model_backend=model_backend)
        self.semaphore = Semaphore(1)
        try:
            with open("config/models.yaml", "r") as f:
                self.prompts = yaml.safe_load(f).get("prompts", {})
            logger.debug(f"Loaded prompts: {self.prompts.keys()}")
        except Exception as e:
            logger.error(f"Failed to load prompts: {str(e)}")
            self.prompts = {
                "nlp_questions": {
                    "system": "You are a code evaluation expert. Return JSON only: [{\"answer\": \"string\", \"confidence\": number}].",
                    "user": (
                        "Evaluate the code submission based on the following:\n"
                        "- SonarQube data: {sonar_data}\n"
                        "- Code samples: {code_samples}\n"
                        "- Specification: {spec}\n"
                        "- Question: {questions}\n"
                        "Provide a concise answer (up to 200 characters) addressing the question. Use SonarQube issues, code, and spec to justify your response. "
                        "Return JSON only: [{\"answer\": \"string\", \"confidence\": 1-5}]."
                    )
                }
            }

    async def process_question(self, q: Dict, sonar_data: Dict, code_chunks: List[Dict], spec: str) -> Dict:
        """Process a single scorecard question with NLP.

        Args:
            q: Question dictionary with 'question', 'category', and 'weight'.
            sonar_data: Parsed SonarQube data.
            code_chunks: List of code file chunks.
            spec: Challenge specification text.

        Returns:
            dict: Answer with question, category, answer, confidence, and weight.

        Example:
            {
                "question": "Is the code maintainable?",
                "category": "Quality",
                "answer": "Code has issues but is maintainable.",
                "confidence": 4,
                "weight": 20.0
            }
        """
        async with self.semaphore:
            question_text = q.get('question', 'Unknown')
            logger.debug(f"Processing question: {question_text[:50]}...")
            default_result = {
                "question": question_text,
                "category": q.get("category", ""),
                "answer": "Failed to generate answer",
                "confidence": 2,
                "weight": q.get("weight", 0)
            }
            try:
                # Get prompt template
                user_prompt_template = self.prompts.get("nlp_questions", {}).get(
                    "user",
                    (
                        "Evaluate the code submission based on the following:\n"
                        "- SonarQube data: {sonar_data}\n"
                        "- Code samples: {code_samples}\n"
                        "- Specification: {spec}\n"
                        "- Question: {questions}\n"
                        "Provide a concise answer (up to 200 characters) addressing the question. Use SonarQube issues, code, and spec to justify your response. "
                        "Return JSON only: [{\"answer\": \"string\", \"confidence\": 1-5}]."
                    )
                )
                logger.debug(f"User prompt template (raw): {repr(user_prompt_template)[:200]}...")

                # Validate template placeholders
                expected_keys = {"sonar_data", "code_samples", "spec", "questions"}
                found_keys = set(re.findall(r'\{([^{}]+)\}', user_prompt_template))
                invalid_keys = found_keys - expected_keys
                if invalid_keys:
                    logger.warning(f"Invalid prompt keys found: {invalid_keys}. Using fallback template.")
                    user_prompt_template = (
                        "Evaluate the code submission:\n"
                        "SonarQube: {sonar_data}\n"
                        "Code: {code_samples}\n"
                        "Spec: {spec}\n"
                        "Question: {questions}\n"
                        "Provide a concise answer (up to 200 characters) addressing the question. Use SonarQube issues, code, and spec to justify your response. "
                        "Return JSON only: [{\"answer\": \"string\", \"confidence\": 1-5}]."
                    )

                # Ensure no stray 'answer' placeholder
                if 'answer' in user_prompt_template.lower() and not any(k in user_prompt_template for k in expected_keys):
                    logger.warning("'answer' found in template. Using fallback template.")
                    user_prompt_template = (
                        "Evaluate the code submission:\n"
                        "SonarQube: {sonar_data}\n"
                        "Code: {code_samples}\n"
                        "Spec: {spec}\n"
                        "Question: {questions}\n"
                        "Provide a concise answer (up to 200 characters) addressing the question. Use SonarQube issues, code, and spec to justify your response. "
                        "Return JSON only: [{\"answer\": \"string\", \"confidence\": 1-5}]."
                    )
                logger.debug(f"Validated prompt template: {user_prompt_template[:200]}...")

                # Prepare format args
                format_args = {
                    "sonar_data": json.dumps(sonar_data, indent=2)[:300],
                    "code_samples": json.dumps(code_chunks[:2], indent=2)[:500],
                    "spec": spec[:500],
                    "questions": json.dumps([q], indent=2)
                }
                logger.debug(f"Prompt format args: {json.dumps(format_args)[:500]}...")

                # Safe formatting: manual replacement
                user_content = user_prompt_template
                for key, value in format_args.items():
                    placeholder = "{" + key + "}"
                    safe_value = str(value).replace('\\', '\\\\').replace('{', '{{').replace('}', '}}')
                    user_content = user_content.replace(placeholder, safe_value)
                logger.debug(f"Formatted user content: {user_content[:200]}...")

                # Verify no unresolved placeholders
                unresolved = re.findall(r'\{(sonar_data|code_samples|spec|questions)\}', user_content)
                if unresolved:
                    logger.error(f"Unresolved placeholders in user_content: {unresolved}. Using fallback.")
                    user_content = (
                        "Evaluate the code submission:\n"
                        "SonarQube: " + str(format_args['sonar_data']) + "\n"
                        "Code: " + str(format_args['code_samples']) + "\n"
                        "Spec: " + str(format_args['spec']) + "\n"
                        "Question: " + str(format_args['questions']) + "\n"
                        "Provide a concise answer (up to 200 characters) addressing the question. Use SonarQube issues, code, and spec to justify your response. "
                        'Return JSON only: [{"answer": "string", "confidence": 1-5}].'
                    )

                prompt = [
                    {
                        "role": "system",
                        "content": self.prompts.get("nlp_questions", {}).get(
                            "system",
                            "You are a code evaluation expert. Return JSON only: [{\"answer\": \"string\", \"confidence\": number}]."
                        )
                    },
                    {
                        "role": "user",
                        "content": user_content + "\nReturn JSON only: [{\"answer\": \"string\", \"confidence\": 1-5}]. Do not include prose, explanations, markdown, or code blocks."
                    }
                ]
                logger.debug(f"Prompt for '{question_text[:50]}...': {json.dumps(prompt)[:500]}...")

                response = await self.llm.generate(prompt)
                logger.debug(f"NLP raw response for '{question_text[:50]}...': {response[:500]}...")
                if not response:
                    logger.warning(f"Empty response for '{question_text[:50]}...'")
                    return default_result

                # Clean response
                clean_response = response.strip()
                clean_response = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', clean_response, flags=re.DOTALL).strip()
                clean_response = re.sub(r'^\s*[\[\{]?[^\[\{]*?([\[\{].*?[\]\}])\s*$', r'\1', clean_response, flags=re.DOTALL).strip()

                # Try to isolate JSON
                json_match = re.search(r'\[\s*\{.*?\}\s*\]', clean_response, re.DOTALL)
                if json_match:
                    clean_response = json_match.group(0)
                else:
                    json_start = clean_response.find('[{')
                    json_end = clean_response.rfind('}]') + 2
                    if json_start != -1 and json_end > json_start:
                        clean_response = clean_response[json_start:json_end]
                    else:
                        json_match = re.search(r'\{.*?\}', clean_response, re.DOTALL)
                        if json_match:
                            clean_response = f'[{json_match.group(0)}]'
                        else:
                            logger.debug(f"No JSON structure found: {clean_response[:100]}...")

                if not clean_response:
                    logger.warning(f"No valid JSON after cleaning: {response[:100]}...")
                    return default_result

                try:
                    result = json.loads(clean_response)
                    logger.debug(f"Parsed JSON: {result}")
                    if isinstance(result, list) and result and isinstance(result[0], dict):
                        result = result[0]
                    else:
                        logger.warning(f"Invalid JSON structure: {clean_response[:100]}...")
                        return default_result
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse error: {str(e)}, response: {clean_response[:100]}...")
                    answer_match = re.search(r'"answer"\s*:\s*"(.*?)"(?:,\s*"confidence"\s*:\s*(\d+))?', clean_response, re.DOTALL | re.IGNORECASE)
                    if answer_match:
                        answer_text = answer_match.group(1) or "Parsed with issues"
                        conf = int(answer_match.group(2)) if answer_match.group(2) else 2
                        result = {"answer": answer_text, "confidence": conf}
                        logger.debug(f"Manual extraction succeeded: {result}")
                    else:
                        text_match = re.search(r'[^`{[\]}]*?\w+[^`{[\]}]*', clean_response, re.DOTALL)
                        if text_match and text_match.group(0).strip():
                            result = {"answer": text_match.group(0).strip()[:200], "confidence": 2}
                            logger.debug(f"Text fallback used: {result}")
                        else:
                            raw_answer = re.search(r'[^`{[\}]+\w+[^{}[\]]*', response, re.DOTALL)
                            if raw_answer and raw_answer.group(0).strip():
                                result = {"answer": raw_answer.group(0).strip()[:200], "confidence": 2}
                                logger.debug(f"Raw text fallback used: {result}")
                            else:
                                logger.warning(f"All extraction failed: {response[:100]}...")
                                return default_result

                answer = {
                    "question": question_text,
                    "category": q.get("category", ""),
                    "answer": result.get("answer", "Unable to process")[:200],
                    "confidence": min(max(int(result.get("confidence", 2) or 2), 1), 5),
                    "weight": q.get("weight", 0)
                }
                logger.debug(f"Generated answer: {answer}")
                return answer

            except Exception as e:
                logger.error(f"Error processing question '{question_text[:50]}...': {str(e)}")
                return default_result

    async def process_questions(self, question_file: str, sonar_data: Dict, code_chunks: List[Dict], spec: str) -> List[Dict]:
        """Process multiple scorecard questions with NLP.

        Args:
            question_file: Path to scorecard JSON file.
            sonar_data: Parsed SonarQube data.
            code_chunks: List of code file chunks.
            spec: Challenge specification text.

        Returns:
            list: List of answers with question, category, answer, confidence, and weight.

        Example:
            [
                {
                    "question": "Is the code maintainable?",
                    "category": "Quality",
                    "answer": "Code has issues but is maintainable.",
                    "confidence": 4,
                    "weight": 20.0
                },
                ...
            ]
        """
        logger.debug(f"Processing questions with model_name={self.model_name}, question_file={question_file}")
        try:
            with open(question_file, "r") as f:
                questions = json.load(f)
            logger.debug(f"Loaded {len(questions)} questions: {[q.get('question', 'Unknown')[:50] for q in questions]}")
        except Exception as e:
            logger.error(f"Failed to load questions: {str(e)}")
            return [
                {
                    "question": "Unknown",
                    "category": "",
                    "answer": "Failed to load questions",
                    "confidence": 1,
                    "weight": 0
                }
            ]

        if not questions:
            logger.warning("No questions found in scorecard.json")
            return [
                {
                    "question": "None",
                    "category": "",
                    "answer": "No questions provided",
                    "confidence": 1,
                    "weight": 0
                }
            ]

        tasks = [self.process_question(q, sonar_data, code_chunks, spec) for q in questions]
        answers = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_answers = []
        for answer in answers:
            if isinstance(answer, Exception):
                logger.error(f"Task failed with exception: {str(answer)}")
                continue
            if isinstance(answer, dict) and answer.get("answer") and answer["answer"] not in ["Failed to generate answer", "Failed to load questions", "Unable to process"]:
                valid_answers.append(answer)
            else:
                logger.warning(f"Filtered invalid answer: {answer}")
        
        logger.info(f"Processed questions: {len(valid_answers)} answers generated")
        return valid_answers if valid_answers else [
            {
                "question": "None",
                "category": "",
                "answer": "No valid answers generated",
                "confidence": 1,
                "weight": 0
            }
        ]