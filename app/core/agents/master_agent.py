from typing import Dict, Any, List
from app.core.agents.validation_agent import ValidationAgent
from app.core.agents.nlp_question_agent import NLPQuestionAgent
from app.core.processors.sonar_parser import SonarParser
from app.core.processors.zip_processor import ZipProcessor
from app.core.processors.chunk_splitter import ChunkSplitter
from app.core.llm.manager import LLMManager
from datetime import datetime
import json
import yaml
import asyncio
import logging
import hashlib

logger = logging.getLogger(__name__)

class MasterAgent:
    """Orchestrates code review using multiple agents."""

    MODEL_TASK_MAPPING = {
        "validation": "mistral_large",
        "security": "mistral_large",
        "quality": "mistral_large",
        "performance": "claude3_7_sonnet",
        "scorecard": "claude3_7_sonnet"
    }

    def __init__(self, model_name: str, model_backend: str, tech_stack: List[str] = None):
        """Initialize with model and tech stack."""
        self.model_name = model_name
        self.model_backend = model_backend
        self.tech_stack = tech_stack or []
        self.is_parallel = model_name.lower() == "parallel"
        self.task_cache = {}  # Cache task results

        available_models = self._get_available_models()
        if self.is_parallel:
            for task, model in self.MODEL_TASK_MAPPING.items():
                if model not in available_models:
                    logger.error(f"Model {model} for {task} not in config/models.yaml")
                    raise ValueError(f"Invalid model {model} for {task}")
        elif model_name not in available_models:
            logger.error(f"Model {model_name} not in config/models.yaml")
            raise ValueError(f"Invalid model {model_name}")

        try:
            with open("config/models.yaml", "r") as f:
                self.prompts = yaml.safe_load(f).get("prompts", {})
        except Exception as e:
            logger.error(f"Failed to load prompts: {str(e)}")
            self.prompts = {}

        validation_model = self.MODEL_TASK_MAPPING["validation"] if self.is_parallel else model_name
        scorecard_model = self.MODEL_TASK_MAPPING["scorecard"] if self.is_parallel else model_name
        self.validation_agent = ValidationAgent(
            tech_stack=self.tech_stack,
            model_name=validation_model,
            model_backend=model_backend
        )
        self.nlp_agent = NLPQuestionAgent(
            model_name=scorecard_model,
            model_backend=model_backend
        )
        self.parser = SonarParser()
        self.zip_processor = ZipProcessor(None)
        self.splitter = ChunkSplitter(chunk_size=200)

        if self.is_parallel:
            self.llms = {}
            for task, model_name in self.MODEL_TASK_MAPPING.items():
                if task in ["security", "quality", "performance"]:
                    try:
                        self.llms[task] = LLMManager(model_name, self.model_backend)
                    except Exception as e:
                        logger.warning(f"Failed to initialize {model_name} for {task}: {e}, falling back to mistral_large")
                        self.llms[task] = LLMManager("mistral_large", self.model_backend)
        else:
            self.llms = {
                task: LLMManager(self.model_name, self.model_backend)
                for task in ["security", "quality", "performance"]
            }

        logger.info(f"Initialized MasterAgent: mode={'parallel' if self.is_parallel else 'single'}, model_name={model_name}")

    def _get_available_models(self) -> List[str]:
        """Load available model names."""
        try:
            with open("config/models.yaml", "r") as f:
                config = yaml.safe_load(f)
            return list(config["backends"][self.model_backend]["models"].keys())
        except Exception as e:
            logger.error(f"Failed to load models: {str(e)}")
            return []

    def _get_cache_key(self, task: str, data: Any) -> str:
        """Generate cache key for task."""
        return hashlib.md5(f"{task}:{json.dumps(data)}".encode()).hexdigest()

    async def review_code(self, sonar_file: str, zip_path: str, spec_path: str, question_file: str = None) -> Dict[str, Any]:
        """Generate code review report."""
        try:
            logger.debug(f"Starting review: zip_path={zip_path}")
            validation_result = await self.validation_agent.validate_submission(zip_path)
            if not validation_result["valid"]:
                logger.error(f"Validation failed: {validation_result['reason']}")
                return {
                    "screening_result": validation_result,
                    "security_findings": [],
                    "quality_metrics": {"maintainability_score": 0, "code_smells": 0, "doc_coverage": 0},
                    "performance_metrics": {"rating": 0, "bottlenecks": [], "optimization_suggestions": []},
                    "scorecard": [],
                    "summary": {"code_quality": 0, "security": 0, "performance": 0, "scorecard": 0, "total": 0.0},
                    "timestamp": datetime.now().isoformat()
                }

            sonar_data = self.parser.parse(sonar_file)
            doc_coverage = self.parser.get_doc_coverage()
            logger.debug(f"Sonar data: {len(sonar_data['issues'])} issues, doc_coverage: {doc_coverage}")

            self.zip_processor.zip_path = zip_path
            code_data = self.zip_processor.extract(zip_path)
            code_chunks = []
            for file in code_data["files"]:
                chunks = self.splitter.split(file["content"])
                code_chunks.extend([{"path": file["path"], "content": chunk} for chunk in chunks])
            code_chunks = code_chunks[:3]

            # Serialize tasks to avoid throttling
            security = []
            quality = {"maintainability_score": 50, "code_smells": len(sonar_data["issues"]), "doc_coverage": doc_coverage}
            performance = {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}

            # Security
            cache_key = self._get_cache_key("security", {"sonar_data": sonar_data, "code_chunks": code_chunks})
            if cache_key in self.task_cache:
                logger.debug("Cache hit for security")
                security = self.task_cache[cache_key]
            else:
                security = await self.analyze_security(sonar_data, code_chunks, self.llms["security"])
                self.task_cache[cache_key] = security

            # Quality
            cache_key = self._get_cache_key("quality", {"sonar_data": sonar_data, "code_chunks": code_chunks})
            if cache_key in self.task_cache:
                logger.debug("Cache hit for quality")
                quality = self.task_cache[cache_key]
            else:
                quality = await self.analyze_quality(sonar_data, code_chunks, self.llms["quality"])
                self.task_cache[cache_key] = quality

            # Performance
            cache_key = self._get_cache_key("performance", {"sonar_data": sonar_data, "code_chunks": code_chunks})
            if cache_key in self.task_cache:
                logger.debug("Cache hit for performance")
                performance = self.task_cache[cache_key]
            else:
                performance = await self.analyze_performance(sonar_data, code_chunks, self.llms["performance"])
                self.task_cache[cache_key] = performance

            results = {
                "screening_result": validation_result,
                "security_findings": security if isinstance(security, list) else [],
                "quality_metrics": quality if isinstance(quality, dict) else {"maintainability_score": 50, "code_smells": len(sonar_data["issues"]), "doc_coverage": doc_coverage},
                "performance_metrics": performance if isinstance(performance, dict) else {"rating": 60, "bottlenecks": [], "optimization_suggestions": []},
                "scorecard": [],
                "summary": {"code_quality": 50, "security": 100, "performance": 60, "scorecard": 0, "total": 0.0},
                "timestamp": datetime.now().isoformat()
            }

            # Use LLM's doc_coverage if valid, else fall back to SonarParser
            results["quality_metrics"]["doc_coverage"] = round(quality.get("doc_coverage", doc_coverage), 1)
            results["quality_metrics"]["code_smells"] = len(sonar_data["issues"])

            if question_file:
                try:
                    with open(spec_path, "r", encoding="utf-8") as f:
                        spec = f.read()
                    results["scorecard"] = await self.nlp_agent.process_questions(question_file, sonar_data, code_chunks, spec)
                    logger.info(f"Processed {len(results['scorecard'])} scorecard answers")
                    if not any(a.get("answer") not in ["Evaluation not available", "No valid answers generated", "Evaluation failed"] for a in results["scorecard"]):
                        logger.warning("No valid scorecard answers with claude3_7_sonnet, retrying with mistral_large after 8s delay")
                        await asyncio.sleep(8)
                        self.nlp_agent = NLPQuestionAgent(model_name="mistral_large", model_backend=self.model_backend)
                        results["scorecard"] = await self.nlp_agent.process_questions(question_file, sonar_data, code_chunks, spec)
                except Exception as e:
                    logger.error(f"Scorecard failed: {str(e)}")
                    results["scorecard"] = [
                        {
                            "question": "Unknown",
                            "category": "",
                            "answer": f"Scorecard failed: {str(e)}",
                            "confidence": 1,
                            "weight": 0
                        }
                    ]

            security_score = 100 - (len(results["security_findings"]) * 15)
            scorecard_answers = [
                a for a in results["scorecard"]
                if a.get("answer") not in ["Evaluation not available", "No valid answers generated", "Evaluation failed"]
            ]
            # Normalize scorecard score to 0-100
            if scorecard_answers:
                sum_conf_weight = sum(a["confidence"] * a["weight"] for a in scorecard_answers if "confidence" in a and "weight" in a)
                sum_weight = sum(a["weight"] for a in scorecard_answers if "weight" in a)
                # Scale confidence (1-5) to 0-100: (confidence/5) * weight
                scorecard_score = (sum_conf_weight / sum_weight) * (100 / 5) if sum_weight > 0 else 0
            else:
                scorecard_score = 0

            # Ensure all components are 0-100
            quality_score = min(results["quality_metrics"].get("maintainability_score", 50), 100)
            security_score = max(min(security_score, 100), 0)
            performance_score = min(results["performance_metrics"].get("rating", 60), 100)
            scorecard_score = max(min(scorecard_score, 100), 0)

            results["summary"] = {
                "code_quality": quality_score,
                "security": security_score,
                "performance": performance_score,
                "scorecard": round(scorecard_score, 1),
                "total": round(
                    quality_score * 0.35 +
                    security_score * 0.25 +
                    performance_score * 0.2 +
                    scorecard_score * 0.2, 1
                )
            }

            logger.info(f"Review completed: total_score={results['summary']['total']}, scorecard_score={results['summary']['scorecard']}, answered_questions={len(scorecard_answers)}")
            with open("report.json", "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            return results
        except Exception as e:
            logger.error(f"Review failed: {str(e)}")
            results = {
                "screening_result": {"valid": False, "reason": str(e), "languages": []},
                "security_findings": [],
                "quality_metrics": {"maintainability_score": 0, "code_smells": 0, "doc_coverage": 0},
                "performance_metrics": {"rating": 0, "bottlenecks": [], "optimization_suggestions": []},
                "scorecard": [],
                "summary": {"code_quality": 0, "security": 0, "performance": 0, "scorecard": 0, "total": 0.0},
                "timestamp": datetime.now().isoformat()
            }
            with open("report.json", "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            return results

    async def analyze_security(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> List[Dict]:
        """Analyze security issues."""
        messages = [
            {
                "role": "system",
                "content": self.prompts.get("security", {}).get("system", "") + "\nReturn a JSON array of issues: [{'issue': str, 'type': str, 'severity': str, 'confidence': int, 'file': str, 'recommendation': str}]. No extra text or markdown. Ensure valid JSON syntax."
            },
            {"role": "user", "content": self.prompts.get("security", {}).get("user", "").format(
                sonar_data=json.dumps(sonar_data, indent=2)[:300],
                code_samples=json.dumps(code_chunks, indent=2)[:500]
            )}
        ]
        try:
            logger.debug(f"Using model {llm.model_name} for security: prompt={json.dumps(messages)[:200]}...")
            response = await llm.generate(messages)
            logger.debug(f"Using model {llm.model_name} for security: response={response[:200]}...")
            parsed = json.loads(response) if response else []
            if not isinstance(parsed, list):
                logger.warning(f"Expected array for security, got: {response[:100]}")
                return []
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Security JSON parsing failed: {str(e)}, response={response[:200]}")
            return []
        except Exception as e:
            logger.error(f"Security analysis failed: {str(e)}")
            return []

    async def analyze_quality(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> Dict:
        """Analyze code quality."""
        messages = [
            {
                "role": "system",
                "content": self.prompts.get("quality", {}).get("system", "") + "\nReturn a JSON object: {'maintainability_score': int, 'code_smells': int, 'doc_coverage': float}. No extra text or markdown. Assign maintainability_score 80-100 for well-structured code unless clear issues exist. Ensure valid JSON syntax."
            },
            {"role": "user", "content": self.prompts.get("quality", {}).get("user", "").format(
                sonar_data=json.dumps(sonar_data, indent=2)[:300],
                code_samples=json.dumps(code_chunks, indent=2)[:500]
            )}
        ]
        try:
            logger.debug(f"Using model {llm.model_name} for quality: prompt={json.dumps(messages)[:200]}...")
            response = await llm.generate(messages)
            logger.debug(f"Using model {llm.model_name} for quality: response={response[:200]}...")
            parsed = json.loads(response) if response else {}
            if not isinstance(parsed, dict):
                logger.warning(f"Expected object for quality, got: {response[:100]}")
                return {"maintainability_score": 50, "code_smells": len(sonar_data["issues"]), "doc_coverage": 0}
            return {
                "maintainability_score": parsed.get("maintainability_score", 50),
                "code_smells": parsed.get("code_smells", len(sonar_data["issues"])),
                "doc_coverage": parsed.get("doc_coverage", 0)
            }
        except json.JSONDecodeError as e:
            logger.error(f"Quality JSON parsing failed: {str(e)}, response={response[:200]}")
            return {"maintainability_score": 50, "code_smells": len(sonar_data["issues"]), "doc_coverage": 0}
        except Exception as e:
            logger.error(f"Quality analysis failed: {str(e)}")
            return {"maintainability_score": 50, "code_smells": len(sonar_data["issues"]), "doc_coverage": 0}

    async def analyze_performance(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> Dict:
        """Analyze performance."""
        messages = [
            {
                "role": "system",
                "content": self.prompts.get("performance", {}).get("system", "") + "\nReturn a JSON object: {'rating': int, 'bottlenecks': [str], 'optimization_suggestions': [str]}. No extra text or markdown. Assign rating 80-100 for efficient code unless clear bottlenecks exist. Ensure valid JSON syntax."
            },
            {"role": "user", "content": self.prompts.get("performance", {}).get("user", "").format(
                sonar_data=json.dumps(sonar_data, indent=2)[:300],
                code_samples=json.dumps(code_chunks, indent=2)[:500]
            )}
        ]
        try:
            logger.debug(f"Using model {llm.model_name} for performance: prompt={json.dumps(messages)[:200]}...")
            response = await llm.generate(messages)
            logger.debug(f"Using model {llm.model_name} for performance: response={response[:200]}...")
            parsed = json.loads(response) if response else {}
            if not isinstance(parsed, dict):
                logger.warning(f"Expected object for performance, got: {response[:100]}")
                return {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}
            return {
                "rating": parsed.get("rating", 60),
                "bottlenecks": parsed.get("bottlenecks", []),
                "optimization_suggestions": parsed.get("optimization_suggestions", [])
            }
        except json.JSONDecodeError as e:
            logger.error(f"Performance JSON parsing failed: {str(e)}, response={response[:200]}")
            return {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}
        except Exception as e:
            logger.error(f"Performance analysis failed: {str(e)}")
            return {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}