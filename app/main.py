"""Main module for AI Code Reviewer FastAPI application.

This module defines the FastAPI app, mounts static files, and provides endpoints for
code analysis, health checks, model listing, and Bedrock connectivity testing. It is
deployed on AWS Elastic Beanstalk and integrates with AWS Bedrock for LLM processing.

Attributes:
    app: FastAPI application instance.
    templates: Jinja2 templates for rendering HTML.
    config: Loaded configuration from models.yaml.
"""

import sys
import os
import logging
import yaml
import json
import tempfile
import time
from fastapi import FastAPI, File, UploadFile, Form, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.core.agents.master_agent import MasterAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Adjust sys.path for module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

app = FastAPI(
    title="AI Code Reviewer",
    description="A FastAPI application for automated code review using AWS Bedrock.",
    version="1.0.0"
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Load configuration
try:
    with open("config/models.yaml", "r") as f:
        config = yaml.safe_load(f) or {"backends": {}}
except FileNotFoundError:
    config = {"backends": {}}
    logger.warning("Model configuration file not found")

@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    """Render the web UI form for code submission.

    Args:
        request: FastAPI request object.

    Returns:
        TemplateResponse: Rendered index.html template.
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health_check():
    """Check application health status.

    Returns:
        dict: JSON response with health status.

    Example:
        {"status": "healthy"}
    """
    return {"status": "healthy"}

@app.get("/api/models")
async def get_models():
    """List available Bedrock models.

    Returns:
        dict: JSON mapping of backends to model names.

    Raises:
        Exception: If config parsing fails, returns default models.

    Example:
        {"bedrock": ["llama3_70b", "mistral_large", "deepseek_r1"]}
    """
    try:
        return {
            backend: [model for model in config["backends"][backend]["models"].keys()]
            for backend in config["backends"]
            if config["backends"][backend].get("enabled", False)
        }
    except Exception as e:
        logger.error(f"Error in get_models: {e}", exc_info=True)
        return {"bedrock": ["llama3_70b", "mistral_large", "deepseek_r1"]}

@app.get("/api/test-bedrock")
async def test_bedrock():
    """Test connectivity to AWS Bedrock.

    Returns:
        dict: JSON with status and available model IDs.

    Raises:
        Exception: If Bedrock API call fails.

    Example:
        {"status": "success", "models": ["mistral.mixtral-8x7b-instruct-v0:1", ...]}
    """
    try:
        import boto3
        client = boto3.client('bedrock', region_name='us-east-1')
        models = client.list_foundation_models()['modelSummaries']
        return {"status": "success", "models": [m['modelId'] for m in models]}
    except Exception as e:
        logger.error(f"Bedrock test failed: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}

@app.post("/api/analyze")
async def analyze(
    sonar_report: UploadFile = File(...),
    code_zip: UploadFile = File(...),
    challenge_spec: str = Form(...),
    tech_stack: str = Form(...),
    scorecard: UploadFile = File(...),
    model_backend: str = Form(default="bedrock"),
    model_name: str = Form(default="parallel")
):
    """Analyze code submission for quality, security, and compliance.

    Args:
        sonar_report: SonarQube JSON report file.
        code_zip: ZIP file containing source code.
        challenge_spec: Text specification of the challenge.
        tech_stack: Comma-separated list of languages (e.g., "Python,JavaScript").
        scorecard: JSON file with review questions.
        model_backend: LLM backend (default: "bedrock").
        model_name: LLM model name (default: "parallel").

    Returns:
        dict: Analysis results including validity, quality, scorecard answers, and runtime.

    Raises:
        HTTPException: If required inputs are missing or invalid.

    Example:
        {
            "screening_result": {"valid": true, "languages": ["Python"]},
            "quality_metrics": {"doc_coverage": 50, ...},
            "runtime": 140.478,
            ...
        }
    """
    try:
        start_time = time.time()
        logger.info(
            f"Received: sonar_report={sonar_report.filename}, "
            f"code_zip={code_zip.filename}, "
            f"challenge_spec={challenge_spec[:50]}..., "
            f"tech_stack={tech_stack}, "
            f"scorecard={scorecard.filename}, "
            f"model_backend={model_backend}, "
            f"model_name={model_name}"
        )

        if not sonar_report.filename:
            raise HTTPException(status_code=400, detail="SonarQube report is required")
        if not code_zip.filename:
            raise HTTPException(status_code=400, detail="Code ZIP is required")
        if not challenge_spec.strip():
            raise HTTPException(status_code=400, detail="Challenge specification is required")
        if not tech_stack.strip():
            raise HTTPException(status_code=400, detail="Tech stack is required")
        if not scorecard.filename:
            raise HTTPException(status_code=400, detail="Scorecard file is required")

        with tempfile.TemporaryDirectory() as tmpdir:
            sonar_path = os.path.join(tmpdir, "sonar.json")
            zip_path = os.path.join(tmpdir, "code.zip")
            spec_path = os.path.join(tmpdir, "spec.txt")
            scorecard_path = os.path.join(tmpdir, "scorecard.json")

            with open(sonar_path, "wb") as f:
                f.write(await sonar_report.read())
            with open(zip_path, "wb") as f:
                f.write(await code_zip.read())
            with open(spec_path, "w") as f:
                f.write(challenge_spec)
            with open(scorecard_path, "wb") as f:
                f.write(await scorecard.read())

            agent = MasterAgent(
                model_name=model_name,
                model_backend=model_backend,
                tech_stack=tech_stack.split(",")
            )

            result = await agent.review_code(
                sonar_file=sonar_path,
                zip_path=zip_path,
                spec_path=spec_path,
                question_file=scorecard_path
            )

            runtime = time.time() - start_time
            result["runtime"] = runtime

            return result

    except Exception as e:
        logger.error(f"Error in analyze: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))