"""Master agent for orchestrating code review in AI Code Reviewer.

This module defines the MasterAgent class, which coordinates validation, SonarQube parsing,
code extraction, and LLM-based analysis to produce a comprehensive code review report.
It integrates with AWS Bedrock for quality, security, and performance evaluations.
"""

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
import re
import logging

logger = logging.getLogger(__name__)

class MasterAgent:
    """Orchestrates code review using validation, SonarQube, and NLP agents.

    Attributes:
        model_name: Name of the LLM model (e.g., 'parallel').
        model_backend: Backend for LLM (e.g., 'bedrock').
        tech_stack: List of supported languages.
        validation_agent: Agent for tech stack validation.
        nlp_agent: Agent for processing scorecard questions.
        parser: Parser for SonarQube reports.
        zip_processor: Processor for code ZIP files.
        splitter: Splits code into chunks for LLM.
        prompts: Loaded prompt templates from models.yaml.
    """
    def __init__(self, model_name: str, model_backend: str, tech_stack: List[str] = None):
        """Initialize MasterAgent with model and tech stack configurations.

        Args:
            model_name: Name of the LLM model.
            model_backend: Backend for LLM (e.g., 'bedrock').
            tech_stack: List of supported languages (default: None).

        Raises:
            FileNotFoundError: If models.yaml is missing.
            yaml.YAMLError: If models.yaml is invalid.
        """
        self.model_name = model_name
        self.model_backend = model_backend
        self.tech_stack = tech_stack if tech_stack is not None else []
        self.validation_agent = ValidationAgent(tech_stack=self.tech_stack, model_name="mistral_large", model_backend=model_backend)
        self.nlp_agent = NLPQuestionAgent("mistral_large", model_backend)
        self.parser = SonarParser()
        self.zip_processor = ZipProcessor(None)
        self.splitter = ChunkSplitter(chunk_size=200)
        
        try:
            with open("config/models.yaml", "r") as f:
                self.prompts = yaml.safe_load(f).get("prompts", {})
            logger.debug(f"Loaded prompts: {self.prompts.keys()}")
        except Exception as e:
            logger.error(f"Failed to load prompts: {str(e)}")
            self.prompts = {}

    async def review_code(self, sonar_file: str, zip_path: str, spec_path: str, question_file: str = None) -> Dict[str, Any]:
        """Review code submission and generate a comprehensive report.

        Args:
            sonar_file: Path to SonarQube JSON report.
            zip_path: Path to code ZIP file.
            spec_path: Path to challenge specification.
            question_file: Path to scorecard JSON (optional).

        Returns:
            dict: Review results including validation, security, quality, performance, and scorecard.

        Raises:
            Exception: If any analysis step fails.

        Example:
            {
                "screening_result": {"valid": true, "languages": ["Python"]},
                "security_findings": [],
                "quality_metrics": {"maintainability_score": 50, "doc_coverage": 0},
                ...
            }
        """
        try:
            logger.debug(f"Starting review_code with model_name={self.model_name}, zip_path={zip_path}")
            validation_result = self.validation_agent.validate_submission(zip_path)
            if not validation_result["valid"]:
                logger.error(f"Validation failed: {validation_result['reason']}")
                return {
                    "error": validation_result["reason"],
                    "screening_result": validation_result,
                    "security_findings": [],
                    "quality_metrics": {"maintainability_score": 0, "code_smells": 0, "doc_coverage": 0},
                    "performance_metrics": {"rating": 0, "bottlenecks": [], "optimization_suggestions": []},
                    "scorecard": [],
                    "summary": {"code_quality": 0, "security": 0, "performance": 0, "total": 0.0},
                    "timestamp": datetime.now().isoformat()
                }

            sonar_data = self.parser.parse(sonar_file)
            sonar_data = {
                "issues": sonar_data.get("issues", [])[:2],
                "metrics": sonar_data.get("metrics", {})
            }
            logger.debug(f"Parsed sonar_data: {json.dumps(sonar_data)[:200]}...")

            self.zip_processor.zip_path = zip_path
            code_data = self.zip_processor.extract(zip_path)
            code_chunks = []
            for file in code_data["files"]:
                chunks = self.splitter.split(file["content"])
                code_chunks.extend([{"path": file["path"], "content": chunk} for chunk in chunks[:2]])
            code_chunks = code_chunks[:2]
            logger.debug(f"Extracted {len(code_chunks)} code chunks")

            results = {
                "screening_result": validation_result,
                "security_findings": [],
                "quality_metrics": {"maintainability_score": 50, "code_smells": 2, "doc_coverage": 0},
                "performance_metrics": {"rating": 60, "bottlenecks": [], "optimization_suggestions": []},
                "scorecard": [],
                "summary": {
                    "code_quality": 0,
                    "security": 0,
                    "performance": 0,
                    "total": 0
                },
                "timestamp": datetime.now().isoformat()
            }

            mistral_llm = LLMManager("mistral_large", self.model_backend)
            llama_llm = LLMManager("llama3_70b", self.model_backend)
            tasks = [
                self.analyze_security(sonar_data, code_chunks, mistral_llm),
                self.analyze_quality(sonar_data, code_chunks, llama_llm),
                self.analyze_performance(sonar_data, code_chunks, mistral_llm),
            ]
            security, quality, performance = await asyncio.gather(*tasks, return_exceptions=True)

            results["security_findings"] = security if isinstance(security, list) else []
            results["quality_metrics"] = quality if isinstance(quality, dict) else {"maintainability_score": 50, "code_smells": 2, "doc_coverage": 0}
            results["performance_metrics"] = performance if isinstance(performance, dict) else {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}
            logger.debug(f"Analysis results - security: {len(results['security_findings'])}, quality: {results['quality_metrics']}, performance: {results['performance_metrics']}")

            # Scale metrics
            quality_metrics = results["quality_metrics"]
            quality_metrics["maintainability_score"] = int(quality_metrics.get("maintainability_score", 50) * 100 if quality_metrics.get("maintainability_score", 50) <= 1 else quality_metrics.get("maintainability_score", 50))
            quality_metrics["doc_coverage"] = int(quality_metrics.get("doc_coverage", 0) * 100 if quality_metrics.get("doc_coverage", 0) <= 1 else quality_metrics.get("doc_coverage", 0))
            performance_metrics = results["performance_metrics"]
            performance_metrics["rating"] = int(performance_metrics.get("rating", 60) * 100 if performance_metrics.get("rating", 60) <= 1 else performance_metrics.get("rating", 60))

            security_score = 100 - (len(results["security_findings"]) * 20)
            results["summary"] = {
                "code_quality": results["quality_metrics"].get("maintainability_score", 50),
                "security": max(security_score, 0),
                "performance": results["performance_metrics"].get("rating", 60),
                "total": round(sum([
                    results["quality_metrics"].get("maintainability_score", 50) * 0.4,
                    max(security_score, 0) * 0.3,
                    results["performance_metrics"].get("rating", 60) * 0.3
                ]) / 10, 2)
            }
            logger.debug(f"Summary updated: {results['summary']}")

            if question_file:
                try:
                    with open(spec_path, "r") as f:
                        spec = f.read()[:500]
                    logger.debug(f"Loaded spec: {spec[:100]}...")
                    nlp_results = await self.nlp_agent.process_questions(question_file, sonar_data, code_chunks, spec)
                    if not nlp_results or not isinstance(nlp_results, list) or not any(nlp_results):
                        logger.warning("No valid NLP results returned")
                        nlp_results = [
                            {
                                "question": "None",
                                "category": "",
                                "answer": "No valid answers generated",
                                "confidence": 1,
                                "weight": 0
                            }
                        ]
                    results["scorecard"] = nlp_results
                    logger.debug(f"Scorecard set: {len([r for r in nlp_results if r.get('answer') != 'No valid answers generated'])} valid answers")
                except Exception as e:
                    logger.error(f"NLP processing failed: {str(e)}")
                    results["scorecard"] = [
                        {
                            "question": "Unknown",
                            "category": "",
                            "answer": f"NLP processing failed: {str(e)}",
                            "confidence": 1,
                            "weight": 0
                        }
                    ]

            logger.info(f"Review completed: {json.dumps(results, indent=2)[:500]}...")
            return results

        except Exception as e:
            logger.error(f"Review failed: {str(e)}")
            return {
                "error": str(e),
                "screening_result": {"valid": False, "reason": str(e), "languages": []},
                "security_findings": [],
                "quality_metrics": {"maintainability_score": 0, "code_smells": 0, "doc_coverage": 0},
                "performance_metrics": {"rating": 0, "bottlenecks": [], "optimization_suggestions": []},
                "scorecard": [],
                "summary": {"code_quality": 0, "security": 0, "performance": 0, "total": 0.0},
                "timestamp": datetime.now().isoformat()
            }

    async def analyze_security(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> List[Dict]:
        """Analyze code for security issues using LLM.

        Args:
            sonar_data: Parsed SonarQube data.
            code_chunks: List of code file chunks.
            llm: LLMManager instance for generation.

        Returns:
            list: List of security findings in JSON format.

        Example:
            [
                {
                    "issue": "Hardcoded credentials",
                    "type": "Security",
                    "severity": "CRITICAL",
                    "confidence": 4,
                    "file": "app/main.py",
                    "recommendation": "Use environment variables."
                }
            ]
        """
        logger.debug(f"Analyzing security with model_name={llm.model_name}")
        messages = [
            {
                "role": "system",
                "content": self.prompts.get("security", {}).get("system", "You are a security expert. Return JSON only.")
            },
            {
                "role": "user",
                "content": self.prompts.get("security", {}).get("user", "").format(
                    sonar_data=json.dumps(sonar_data, indent=2)[:300],
                    code_samples=json.dumps(code_chunks, indent=2)[:500]
                ) + "\nReturn JSON only: [] or [{\"issue\": \"string\", \"type\": \"string\", \"severity\": \"string\", \"confidence\": number, \"file\": \"string\", \"recommendation\": \"string\"}]."
            }
        ]
        try:
            response = await llm.generate(messages)
            logger.debug(f"Security raw response: {response[:200]}...")
            json_match = re.search(r'\[\s*\{.*?\}\s*\]', response, re.DOTALL)
            clean_response = json_match.group(0) if json_match else response.strip()
            if not clean_response.startswith('['):
                clean_response = f'[{clean_response}]'
            
            try:
                findings = json.loads(clean_response)
                logger.debug(f"Security findings: {findings}")
                return findings if isinstance(findings, list) else []
            except json.JSONDecodeError:
                logger.error(f"Security analysis response not JSON: {response[:100]}...")
                return []
        except Exception as e:
            logger.error(f"Security analysis failed: {str(e)}")
            return []

    async def analyze_quality(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> Dict:
        """Analyze code quality using LLM.

        Args:
            sonar_data: Parsed SonarQube data.
            code_chunks: List of code file chunks.
            llm: LLMManager instance for generation.

        Returns:
            dict: Quality metrics including maintainability and doc coverage.

        Example:
            {
                "maintainability_score": 50,
                "code_smells": 2,
                "doc_coverage": 0
            }
        """
        logger.debug(f"Analyzing quality with model_name={llm.model_name}")
        messages = [
            {
                "role": "system",
                "content": self.prompts.get("quality", {}).get("system", "You are a quality expert. Return scores as integers (0-100).")
            },
            {
                "role": "user",
                "content": self.prompts.get("quality", {}).get("user", "").format(
                    sonar_data=json.dumps(sonar_data, indent=2)[:300],
                    code_samples=json.dumps(code_chunks, indent=2)[:500]
                ) + "\nReturn JSON only: {\"maintainability_score\": number, \"code_smells\": number, \"doc_coverage\": number}."
            }
        ]
        try:
            response = await llm.generate(messages)
            logger.debug(f"Quality raw response: {response[:200]}...")
            json_match = re.search(r'\{\s*\"maintainability_score\".*?\}', response, re.DOTALL)
            clean_response = json_match.group(0) if json_match else response.strip()
            
            try:
                metrics = json.loads(clean_response)
                logger.debug(f"Quality metrics: {metrics}")
                return metrics if isinstance(metrics, dict) else {"maintainability_score": 50, "code_smells": 2, "doc_coverage": 0}
            except json.JSONDecodeError:
                logger.error(f"Quality analysis response not JSON: {response[:100]}...")
                return {"maintainability_score": 50, "code_smells": 2, "doc_coverage": 0}
        except Exception as e:
            logger.error(f"Quality analysis failed: {str(e)}")
            return {"maintainability_score": 50, "code_smells": 2, "doc_coverage": 0}

    async def analyze_performance(self, sonar_data: Dict, code_chunks: List[Dict], llm) -> Dict:
        """Analyze code performance using LLM.

        Args:
            sonar_data: Parsed SonarQube data.
            code_chunks: List of code file chunks.
            llm: LLMManager instance for generation.

        Returns:
            dict: Performance metrics including rating and suggestions.

        Example:
            {
                "rating": 60,
                "bottlenecks": [],
                "optimization_suggestions": []
            }
        """
        logger.debug(f"Analyzing performance with model_name={llm.model_name}")
        messages = [
            {
                "role": "system",
                "content": self.prompts.get("performance", {}).get("system", "You are a performance expert. Return scores as integers (0-100).")
            },
            {
                "role": "user",
                "content": self.prompts.get("performance", {}).get("user", "").format(
                    sonar_data=json.dumps(sonar_data, indent=2)[:300],
                    code_samples=json.dumps(code_chunks, indent=2)[:500]
                ) + "\nReturn JSON only: {\"rating\": number, \"bottlenecks\": [], \"optimization_suggestions\": []}."
            }
        ]
        try:
            response = await llm.generate(messages)
            logger.debug(f"Performance raw response: {response[:200]}...")
            json_match = re.search(r'\{\s*\"rating\".*?\}', response, re.DOTALL)
            clean_response = json_match.group(0) if json_match else response.strip()
            
            try:
                metrics = json.loads(clean_response)
                logger.debug(f"Performance metrics: {metrics}")
                return metrics if isinstance(metrics, dict) else {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}
            except json.JSONDecodeError:
                logger.error(f"Performance analysis response not JSON: {response[:100]}...")
                return {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}
        except Exception as e:
            logger.error(f"Performance analysis failed: {str(e)}")
            return {"rating": 60, "bottlenecks": [], "optimization_suggestions": []}