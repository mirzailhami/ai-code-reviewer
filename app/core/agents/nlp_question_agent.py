import json
import os
from typing import List, Dict, Any
import yaml
import logging
import asyncio
import backoff
import hashlib
from app.core.llm.manager import LLMManager

logger = logging.getLogger(__name__)

class NLPQuestionAgent:
    """Agent for processing scorecard questions using an LLM."""
    
    def __init__(self, model_name: str, model_backend: str):
        """Initialize NLPQuestionAgent with LLM and prompts.
        
        Args:
            model_name (str): Name of the LLM model (e.g., claude3_7_sonnet).
            model_backend (str): Backend for the LLM (e.g., bedrock).
        """
        self.model_name = model_name
        self.model_backend = model_backend
        self.llm = LLMManager(model_name=model_name, model_backend=model_backend)
        self.response_cache = {}  # Cache for LLM responses
        try:
            with open("config/models.yaml", "r") as f:
                self.prompts = yaml.safe_load(f).get("prompts", {})
            if "scorecard" not in self.prompts:
                raise ValueError("scorecard prompt missing in config/models.yaml")
        except Exception as e:
            logger.error(f"Failed to load prompts: {str(e)}")
            self.prompts = {}

    @backoff.on_exception(backoff.expo, Exception, max_tries=3, max_time=10)
    async def process_question(self, q: Dict, sonar_data: Dict, code_chunks: List[Dict], spec: str, docs: str) -> Dict:
        """Process a single scorecard question using the LLM.
        
        Args:
            q (dict): Question details (question, category, weight).
            sonar_data (dict): SonarQube report data.
            code_chunks (list): List of code samples.
            spec (str): Challenge specification.
            docs (str): Documentation content.
            
        Returns:
            dict: Result with question, category, answer, confidence, and weight.
        """
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

        # Check cache
        cache_key = hashlib.md5(json.dumps([q, sonar_data, code_chunks, spec, docs]).encode()).hexdigest()
        if cache_key in self.response_cache:
            logger.debug(f"Cache hit for question: {question_text[:50]}")
            return self.response_cache[cache_key]

        try:
            user_prompt_template = self.prompts.get("scorecard", {}).get("user", "")
            if not user_prompt_template:
                logger.error("scorecard user prompt not found")
                return default_result

            format_args = {
                "sonar_data": json.dumps(sonar_data, indent=2)[:2000],  # Increased from 1500
                "code_samples": json.dumps(code_chunks[:5], indent=2)[:4000],  # Increased from 2, 3000
                "spec": spec[:2000],  # Increased from 1500
                "docs": docs[:2000],  # Increased from 1500
                "question": question_text,
                "category": category,
                "weight": weight
            }
            user_content = user_prompt_template.format(**format_args)

            prompt = [
                {"role": "system", "content": self.prompts.get("scorecard", {}).get("system", "")},
                {"role": "user", "content": user_content}
            ]

            logger.debug(f"Processing '{question_text[:50]}': prompt={json.dumps(prompt)[:500]}...")
            response = await self.llm.generate(prompt)
            logger.debug(f"Full LLM response for '{question_text[:50]}': {response}")

            if not response or "Evaluation failed" in response:
                logger.warning(f"Empty or failed response for: {question_text}")
                return default_result

            try:
                json_str = response.strip()
                if json_str.startswith("```json"):
                    json_str = json_str[7:].rsplit("```", 1)[0].strip()
                result = json.loads(json_str)
                if isinstance(result, list) and result and isinstance(result[0], dict):
                    answer_data = result[0]
                elif isinstance(result, dict):
                    answer_data = result
                else:
                    logger.warning(f"Invalid format: {json_str[:100]}")
                    return default_result

                answer = str(answer_data.get("answer", ""))
                confidence = min(max(int(answer_data.get("confidence", 1)), 1), 5)

                result = {
                    "question": question_text,
                    "category": category,
                    "answer": answer or "No answer provided",
                    "confidence": confidence,
                    "weight": weight
                }
                self.response_cache[cache_key] = result  # Cache result
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed: {json_str[:100]}... Error: {e}")
                return default_result
            except Exception as e:
                logger.error(f"Response processing error: {e}")
                return default_result

        except Exception as e:
            logger.error(f"Question processing error: {e}")
            return default_result

    async def process_questions(self, question_file: str, sonar_data: Dict, code_chunks: List[Dict], spec: str) -> List[Dict]:
        """Process multiple scorecard questions from a file.
        
        Args:
            question_file (str): Path to JSON file with questions.
            sonar_data (dict): SonarQube report data.
            code_chunks (list): List of code samples.
            spec (str): Challenge specification.
            
        Returns:
            list: List of results for each question.
        """
        logger.debug(f"Processing questions: {question_file}")
        try:
            with open(question_file, "r", encoding="utf-8") as f:
                questions = json.load(f)
            questions = questions if isinstance(questions, list) else questions.get("questions", [])
            logger.info(f"Loaded {len(questions)} questions")
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
            for chunk in code_chunks[:5]:  # Increased from 2
                docs += f"File: {chunk.get('path', 'unknown')}\n{chunk.get('content', '')[:500]}\n\n"  # Increased from 300
        except Exception as e:
            logger.warning(f"Failed to load docs: {str(e)}")

        answers = []
        for q in questions:
            answer = await self.process_question(q, sonar_data, code_chunks, spec, docs)
            answers.append(answer)
        logger.info(f"Generated {len(answers)} answers")
        return answers