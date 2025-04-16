import json
import os
from typing import List, Dict, Any
import yaml
import logging
from asyncio import Semaphore
import asyncio
from app.core.llm.manager import LLMManager

logger = logging.getLogger(__name__)

class NLPQuestionAgent:
    """Processes scorecard questions with NLP."""

    def __init__(self, model_name: str, model_backend: str):
        """Initialize with model configuration."""
        self.model_name = model_name
        self.model_backend = model_backend
        self.llm = LLMManager(model_name=model_name, model_backend=model_backend)
        self.semaphore = Semaphore(1)
        try:
            with open("config/models.yaml", "r") as f:
                self.prompts = yaml.safe_load(f).get("prompts", {})
            if "scorecard" not in self.prompts:
                raise ValueError("scorecard prompt missing in config/models.yaml")
        except Exception as e:
            logger.error(f"Failed to load prompts: {str(e)}")
            self.prompts = {}

    async def process_question(self, q: Dict, sonar_data: Dict, code_chunks: List[Dict], spec: str, docs: str) -> Dict:
        """Process a single scorecard question."""
        async with self.semaphore:
            question_text = q.get("question", "Unknown")
            category = q.get("category", "")
            weight = q.get("weight", 0)

            default_result = {
                "question": question_text,
                "category": category,
                "answer": "Evaluation not available",
                "confidence": 1,
                "weight": weight
            }

            try:
                user_prompt_template = self.prompts.get("scorecard", {}).get("user", "")
                if not user_prompt_template:
                    logger.error("scorecard user prompt not found")
                    return default_result

                format_args = {
                    "sonar_data": json.dumps(sonar_data, indent=2)[:500],
                    "code_samples": json.dumps(code_chunks[:2], indent=2)[:1000],
                    "spec": spec[:500],
                    "docs": docs[:1000],
                    "question": question_text,
                    "category": category,
                    "weight": weight
                }
                user_content = user_prompt_template.format(**format_args)

                prompt = [
                    {"role": "system", "content": self.prompts.get("scorecard", {}).get("system", "")},
                    {"role": "user", "content": user_content}
                ]

                logger.debug(f"Using model {self.model_name} for scorecard question '{question_text[:50]}': prompt={json.dumps(prompt)[:200]}...")
                response = await self.llm.generate(prompt)
                logger.debug(f"Using model {self.model_name} for scorecard question '{question_text[:50]}': response={response[:200]}...")

                if not response:
                    logger.warning(f"Empty response for question: {question_text}")
                    return default_result

                try:
                    json_str = response.strip()
                    if json_str.startswith("```json"):
                        json_str = json_str[7:].rsplit("```", 1)[0].strip()
                    result = json.loads(json_str)
                    if not isinstance(result, list) or not result:
                        logger.warning(f"Invalid response format: {json_str[:100]}")
                        return default_result

                    answer_data = result[0]
                    answer = str(answer_data.get("answer", ""))[:200]
                    confidence = answer_data.get("confidence", 1)
                    confidence = min(max(int(confidence), 1), 5)

                    return {
                        "question": question_text,
                        "category": category,
                        "answer": answer or "No answer provided",
                        "confidence": confidence,
                        "weight": weight
                    }
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON: {json_str[:100]}... Error: {str(e)}")
                    return default_result
                except Exception as e:
                    logger.error(f"Response processing error: {str(e)}")
                    return default_result

            except Exception as e:
                logger.error(f"Question processing error: {str(e)}")
                return default_result

    async def process_questions(self, question_file: str, sonar_data: Dict, code_chunks: List[Dict], spec: str) -> List[Dict]:
        """Process multiple scorecard questions."""
        logger.debug(f"Processing questions: {question_file}")
        try:
            with open(question_file, "r", encoding="utf-8") as f:
                questions = json.load(f)
            questions = questions if isinstance(questions, list) else questions.get("questions", [])
            logger.debug(f"Loaded {len(questions)} questions")
        except Exception as e:
            logger.error(f"Failed to load questions: {str(e)}")
            return [
                {
                    "question": "Unknown",
                    "category": "",
                    "answer": f"Failed to load questions: {str(e)}",
                    "confidence": 1,
                    "weight": 0
                }
            ]

        docs = ""
        try:
            if os.path.exists("README.md"):
                with open("README.md", "r", encoding="utf-8") as f:
                    docs += f"README:\n{f.read()}\n\n"
            for chunk in code_chunks[:2]:
                docs += f"File: {chunk.get('path', 'unknown')}\n{chunk.get('content', '')[:500]}\n\n"
        except Exception as e:
            logger.warning(f"Failed to load docs: {str(e)}")

        tasks = [self.process_question(q, sonar_data, code_chunks, spec, docs) for q in questions]
        answers = await asyncio.gather(*tasks, return_exceptions=True)

        valid_answers = [
            answer for answer in answers
            if isinstance(answer, dict)
            and answer.get("answer") not in ["Evaluation not available", "Failed to load questions"]
        ]
        return valid_answers or [
            {
                "question": "None",
                "category": "",
                "answer": "No valid answers generated",
                "confidence": 1,
                "weight": 0
            }
        ]