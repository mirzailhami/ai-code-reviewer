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

logger = logging.getLogger(__name__)

class MasterAgent:
    """Orchestrates code review using multiple agents."""

    MODEL_TASK_MAPPING = {
        "validation": "mistral_large",
        "security": "mistral_large",
        "quality": "deepseek_r1",
        "performance": "llama3_70b",
        "scorecard": "llama3_70b"
    }

    def __init__(self, model_name: str, model_backend: str, tech_stack: List[str] = None):
        """Initialize with model and tech stack."""
        self.model_name = model_name
        self.model_backend = model_backend
        self.tech_stack = tech_stack or []
        self.is_parallel = model_name.lower() == "parallel"

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
            code_chunks = code_chunks[:5]

            tasks = [
                self.analyze_security(sonar_data, code_chunks, self.llms["security"]),
                self.analyze_quality(sonar_data, code_chunks, self.llms["quality"]),
                self.analyze_performance(sonar_data, code_chunks, self.llms["performance"]),
            ]
            security, quality, performance = await asyncio.gather(*tasks, return_exceptions=True)

            results = {
                "screening_result": validation_result,
                "security_findings": security if isinstance(security, list) else [],
                "quality_metrics": quality if isinstance(quality, dict) else {"maintainability_score": 50, "code_smells": len(sonar_data["issues"]), "doc_coverage": doc_coverage},
                "performance_metrics": performance if isinstance(performance, dict) else {"rating": 60, "bottlenecks": [], "optimization_suggestions": []},
                "scorecard": [],
                "summary": {"code_quality": 50, "security": 100, "performance": 60, "scorecard": 0, "total": 0.0},
                "timestamp": datetime.now().isoformat()
            }

            results["quality_metrics"]["doc_coverage"] = round(doc_coverage, 1)
            results["quality_metrics"]["code_smells"] = len(sonar_data["issues"])

            if question_file:
                try:
                    with open(spec_path, "r", encoding="utf-8") as f:
                        spec = f.read()
                    results["scorecard"] = await self.nlp_agent.process_questions(question_file, sonar_data, code_chunks, spec)
                    logger.info(f"Processed {len(results['scorecard'])} scorecard answers")
                    # Fallback to mistral_large if no valid answers
                    if not any(a.get("answer") not in ["Evaluation not available", "No valid answers generated"] for a in results["scorecard"]):
                        logger.warning("No valid scorecard answers with llama3_70b, retrying with mistral_large")
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

            security_score = 100 - (len(results["security_findings"]) * 20)
            scorecard_answers = [
                a for a in results["scorecard"]
                if a.get("answer") not in ["Evaluation not available", "No valid answers generated"]
            ]
            scorecard_score = (
                sum(a["confidence"] * a["weight"] for a in scorecard_answers if "confidence" in a and "weight" in a)
                / max(1, sum(a["weight"] for a in scorecard_answers if "weight" in a))
                * 20  # Normalize to 0-100
            ) if scorecard_answers else 0
            results["summary"] = {
                "code_quality": max(100 - len(sonar_data["issues"]) * 10, 50),
                "security": max(security_score, 0),
                "performance": results["performance_metrics"].get("rating", 60),
                "scorecard": round(scorecard_score, 1),
                "total": round(
                    results["quality_metrics"].get("maintainability_score", 50) * 0.4 +
                    max(security_score, 0) * 0.2 +
                    results["performance_metrics"].get("rating", 60) * 0.2 +
                    scorecard_score * 0.2, 1
                )
            }

            logger.info(f"Review completed: total_score={results['summary']['total']}, scorecard_score={results['summary']['scorecard']}, answered_questions={len(scorecard_answers)}")
            return results
        except Exception as e:
            logger.error(f"Review failed: {str(e)}")
            return {
                "screening_result": {"valid": False, "reason": str(e), "languages": []},
                "security_findings": [],
                "quality_metrics": {"maintainability_score": 0, "code_smells": 0, "doc_coverage": 0},
                "performance_metrics": {"rating": 0, "bottlenecks": [], "optimization_suggestions": []},
                "scorecard": [],
                "summary": {"code_quality": 0, "security": 0, "performance": 0, "scorecard": 0, "total": 0.0},
                "timestamp": datetime.now().isoformat()
            }

    async def analyze_security(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> List[Dict]:
        """Analyze security issues."""
        messages = [
            {"role": "system", "content": self.prompts.get("security", {}).get("system", "")},
            {"role": "user", "content": self.prompts.get("security", {}).get("user", "").format(
                sonar_data=json.dumps(sonar_data, indent=2)[:500],
                code_samples=json.dumps(code_chunks, indent=2)[:1000]
            )}
        ]
        try:
            logger.debug(f"Using model {llm.model_name} for security: prompt={json.dumps(messages)[:200]}...")
            response = await llm.generate(messages)
            logger.debug(f"Using model {llm.model_name} for security: response={response[:200]}...")
            return json.loads(response) if response else []
        except json.JSONDecodeError as e:
            logger.error(f"Security JSON parsing failed: {str(e)}, response={response[:200]}")
            return []
        except Exception as e:
            logger.error(f"Security analysis failed: {str(e)}")
            return []

    async def analyze_quality(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> Dict:
        """Analyze code quality."""
        messages = [
            {"role": "system", "content": self.prompts.get("quality", {}).get("system", "")},
            {"role": "user", "content": self.prompts.get("quality", {}).get("user", "").format(
                sonar_data=json.dumps(sonar_data, indent=2)[:500],
                code_samples=json.dumps(code_chunks, indent=2)[:1000]
            )}
        ]
        try:
            logger.debug(f"Using model {llm.model_name} for quality: prompt={json.dumps(messages)[:200]}...")
            response = await llm.generate(messages)
            logger.debug(f"Using model {llm.model_name} for quality: response={response[:200]}...")
            metrics = json.loads(response) if response else {}
            return {
                "maintainability_score": metrics.get("maintainability_score", 50),
                "code_smells": metrics.get("code_smells", len(sonar_data["issues"])),
                "doc_coverage": metrics.get("doc_coverage", 0)
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
            {"role": "system", "content": self.prompts.get("performance", {}).get("system", "")},
            {"role": "user", "content": self.prompts.get("performance", {}).get("user", "").format(
                sonar_data=json.dumps(sonar_data, indent=2)[:500],
                code_samples=json.dumps(code_chunks, indent=2)[:1000]
            )}
        ]
        try:
            logger.debug(f"Using model {llm.model_name} for performance: prompt={json.dumps(messages)[:200]}...")
            response = await llm.generate(messages)
            logger.debug(f"Using model {llm.model_name} for performance: response={response[:200]}...")
            return json.loads(response) if response else {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}
        except json.JSONDecodeError as e:
            logger.error(f"Performance JSON parsing failed: {str(e)}, response={response[:200]}")
            return {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}
        except Exception as e:
            logger.error(f"Performance analysis failed: {str(e)}")
            return {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}