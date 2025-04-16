import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi import FastAPI, File, UploadFile, Form, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.core.agents.master_agent import MasterAgent
import yaml
import json
import tempfile

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

try:
    with open("config/models.yaml", "r") as f:
        config = yaml.safe_load(f) or {"backends": {}}
except FileNotFoundError:
    config = {"backends": {}}
    print("Warning: Model configuration file not found")

@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/models")
async def get_models():
    try:
        return {
            backend: [model for model in config["backends"][backend]["models"].keys()]
            for backend in config["backends"]
            if config["backends"][backend].get("enabled", False)
        }
    except Exception as e:
        print(f"Error in get_models: {str(e)}")
        return {"bedrock": ["llama3_70b", "mistral_large", "deepseek_r1"]}

@app.get("/api/test-bedrock")
async def test_bedrock():
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
    try:
        print(f"Received: sonar_report={sonar_report.filename}, code_zip={code_zip.filename}, "
              f"challenge_spec={challenge_spec[:50]}..., tech_stack={tech_stack}, "
              f"scorecard={scorecard.filename}, "
              f"model_backend={model_backend}, model_name={model_name}")

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

            return result

    except Exception as e:
        print(f"Error in analyze: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))