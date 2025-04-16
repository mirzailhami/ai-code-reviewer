# AI Code Reviewer

## Overview

The AI Code Reviewer automates code evaluation by validating submissions against specified tech stacks (e.g., TypeScript, Python) and analyzing SonarQube reports for issues. It leverages AI agents powered by AWS Bedrock to assess code quality, security, and requirement compliance. The system offers a modular backend, a responsive web UI, and a CLI for batch processing.

## Features

1. **Validation Agent**: Verifies submission files (e.g., `submission.zip`) for tech stack compliance.
2. **SonarQube Parser**: Processes reports (e.g., `sonar-report.json`) for issues and metrics.
3. **NLP Question Agent**: Evaluates scorecard questions for completeness and best practices.
4. **Master Agent**: Orchestrates review, integrating validation, SonarQube analysis, and AI insights.
5. **Web UI**: Upload files (`sonar-report.json`, `submission.zip`, `scorecard.json`, `spec.txt`) and view results.
6. **CLI**: Run reviews via command-line with `app/cli.py`.

## Models Used

The system uses AWS Bedrock models, configured for parallel processing:
- **Backend**: AWS Bedrock (`boto3` integration in `app/core/llm/bedrock_llm.py`).
- **Model Name**: `parallel` (default, configurable via `config/models.yaml`).
- **Models**:
  - `mistral_large` (Mistral Large 2402)
  - `llama3_70b` (Meta LLaMA 3 70B Instruct)
  - `deepseek_r1` (DeepSeek R1)
- **Capabilities**: Analyzes code, SonarQube issues, and specifications to generate JSON reports (e.g., `{"valid": true, "code_quality": 50}`).

## Configuration

Model settings are defined in `config/models.yaml`:

\`\`\`yaml
backends:
  bedrock:
    enabled: true
    models:
      mistral_large:
        model_id: mistral.mistral-large-2402-v1:0
        max_tokens: 256
        temperature: 0.3
        top_p: 0.9
        top_k: 50
      llama3_70b:
        model_id: meta.llama3-70b-instruct-v1:0
        max_tokens: 256
        temperature: 0.5
        top_p: 0.9
      deepseek_r1:
        model_id: deepseek.deepseek-r1
        max_tokens: 256
prompts:
  nlp_questions:
    system: "You are a code evaluation expert. Return JSON only: [{\"answer\": \"string\", \"confidence\": number}]."
    user: |
      Evaluate the code submission based on the following:
      - SonarQube data: {sonar_data}
      - Code samples: {code_samples}
      - Specification: {spec}
      - Questions: {questions}
      Return JSON only: [{\"answer\": \"string\", \"confidence\": 1-5}].
      Do not include prose, explanations, markdown, or code blocks.
  security:
    system: "You are a security expert. Return JSON only."
    user: |
      Analyze for security issues:
      - SonarQube data: {sonar_data}
      - Code samples: {code_samples}
      Return JSON only: [] or [{\"issue\": \"string\", \"type\": \"string\", \"severity\": \"string\", \"confidence\": number, \"file\": \"string\", \"recommendation\": \"string\"}].
  quality:
    system: "You are a quality expert. Return scores as integers (0-100)."
    user: |
      Evaluate code quality:
      - SonarQube data: {sonar_data}
      - Code samples: {code_samples}
      Return JSON only: {\"maintainability_score\": number, \"code_smells\": number, \"doc_coverage\": number}.
  performance:
    system: "You are a performance expert. Return scores as integers (0-100)."
    user: |
      Evaluate performance:
      - SonarQube data: {sonar_data}
      - Code samples: {code_samples}
      Return JSON only: {\"rating\": number, \"bottlenecks\": [], \"optimization_suggestions\": []}.
\`\`\`

- **backends**: Configures Bedrock models and parameters.
- **prompts**: Defines AI prompts for evaluation tasks.
- **Updates**: Edit `models.yaml` to adjust models or prompt templates.

## REST API Endpoints

| Endpoint           | Method | Description                    | Request Body (Form/Multipart) Example                                                                 | Response (HTML/JSON) Example                             |
|--------------------|--------|--------------------------------|----------------------------------------------------------------------------------------------|---------------------------------------------------------|
| `/`                | GET    | Serves web UI                  | N/A                                                                                          | HTML (`index.html`)                                     |
| `/api/health`      | GET    | Checks app health              | N/A                                                                                          | `{"status": "healthy"}`                                 |
| `/api/models`      | GET    | Lists available models         | N/A                                                                                          | `{"bedrock": ["mistral_large", "llama3_70b", "deepseek_r1"]}` |
| `/api/analyze`     | POST   | Analyzes uploaded files        | `sonar_report`, `code_zip`, `challenge_spec`, `tech_stack: "Python,TypeScript"`, `scorecard`, `model_backend: "bedrock"`, `model_name: "parallel"` | `{"valid": true, "code_quality": 50}`                   |
| `/api/test-bedrock`| GET    | Tests Bedrock connectivity     | N/A                                                                                          | `{"status": "success", "models": [...]}`                |

## Input File Structures

The system processes the following inputs:

1. **SonarQube Report** (`sonar-report.json`):
   \`\`\`json
   {
     "total": 2,
     "issues": [
       {
         "key": "mock-001",
         "rule": "python:S1192",
         "severity": "MINOR",
         "component": "ai-code-reviewer:app/cli.py",
         "line": 10,
         "message": "Define a constant instead of duplicating this literal 'DEBUG' 3 times.",
         "type": "CODE_SMELL"
       },
       {
         "key": "mock-002",
         "rule": "python:S3776",
         "severity": "MAJOR",
         "component": "ai-code-reviewer:app/core/agents/validation_agent.py",
         "line": 45,
         "message": "Cognitive Complexity of functions should not be too high.",
         "type": "CODE_SMELL"
       }
     ],
     "components": []
   }
   \`\`\`
   - Stored in `tests/test_data/sonar-report.json`.
   - Parsed by `app/core/processors/sonar_parser.py`.

2. **Scorecard** (`scorecard.json`):
   \`\`\`json
   [
     {
       "question": "Requirements are implemented completely...",
       "category": "Functionality & Completeness",
       "weight": 50.0
     },
     {
       "question": "The technical solution is modern...",
       "category": "Technical Implementation",
       "weight": 20.0
     },
     {
       "question": "Complete and easy-to-follow documentation...",
       "category": "Presentation (Docs & Demo)",
       "weight": 10.0
     }
   ]
   \`\`\`
   - Stored in `tests/test_data/scorecard.json`.
   - Used by `nlp_question_agent.py`.

3. **Tech Stack**:
   - Input as a comma-separated string (e.g., `TypeScript, Python`).
   - Validated by `validation_agent.py` against `submission.zip`.

4. **Specification** (`spec.txt`):
   \`\`\`text
   The solution must validate code submissions against a specified tech stack and provide a detailed report based on SonarQube analysis. It should support Python and TypeScript, with a web UI and CLI.
   \`\`\`
   - Stored in `tests/test_data/spec.txt`.
   - Guides AI evaluation.

5. **Submission** (`submission.zip`):
   - ZIP file with source code (e.g., `.py`, `.ts`, `README.md`).
   - Processed by `zip_processor.py`.
   - Example: `tests/test_data/submission.zip` with `sample.ts`, `README.md`.
   - **Tip for doc_coverage: 0**: Include a detailed `README.md` and code comments in `.ts` or `.py` files.

## Setup & Execution (Local)

1. **Prerequisites**:
   - Python 3.13+ (`python --version`)
   - AWS CLI configured (`aws configure`) with Bedrock access
   - Project structure:
     \`\`\`
     /ai-code-reviewer
      ├── app/
      │   ├── cli.py
      │   ├── main.py
      │   ├── core/
      │   │   ├── agents/
      │   │   ├── llm/
      │   │   ├── processors/
      │   ├── static/
      │   │   ├── favicon.ico
      │   │   ├── css/styles.css
      │   │   ├── js/app.js
      │   ├── templates/
      │   │   ├── index.html
      ├── config/
      │   ├── models.yaml
      ├── tests/
      │   ├── test_data/
      │   │   ├── sonar-report.json
      │   │   ├── submission.zip
      │   │   ├── spec.txt
      │   │   ├── scorecard.json
      ├── requirements.txt
      ├── .ebextensions/
      ├── .platform/
     \`\`\`

2. **Installation**:
   \`\`\`bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   \`\`\`

3. **Run CLI**:
   \`\`\`bash
   python app/cli.py \\
     --sonar-file tests/test_data/sonar-report.json \\
     --zip-path tests/test_data/submission.zip \\
     --spec-path tests/test_data/spec.txt \\
     --question-file tests/test_data/scorecard.json \\
     --tech-stack "TypeScript, Python"
   \`\`\`

4. **Run Web**:
   \`\`\`bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   \`\`\`
   Open `http://localhost:8000`.

## Deployment (AWS Elastic Beanstalk)

Deploy to AWS EB for a live demo:

1. **Prerequisites**:
   - AWS CLI (`pip install awscli`)
   - EB CLI (`pip install awsebcli`)
   - Git initialized

2. **Configuration**:
   - `requirements.txt`:
     \`\`\`
     fastapi==0.115.0
     uvicorn==0.30.6
     python-multipart==0.0.9
     jinja2==3.1.4
     boto3==1.35.29
     pyyaml==6.0.2
     aiohttp==3.10.5
     click==8.1.7
     backoff==2.2.1
     gunicorn==23.0.0
     \`\`\`
   - `.ebextensions/options.config`:
     \`\`\`yaml
     option_settings:
       aws:elasticbeanstalk:container:python:
         WSGIPath: app.main:app
       aws:elasticbeanstalk:environment:process:default:
         Port: 8000
         Protocol: HTTP
     \`\`\`
   - `.ebextensions/healthcheck.config`:
     \`\`\`yaml
     option_settings:
       aws:elasticbeanstalk:application:
         Application Healthcheck URL: /api/health
     \`\`\`
   - `.platform/hooks/predeploy/01_setup_gunicorn.sh`:
     \`\`\`bash
     #!/bin/bash
     source /var/app/venv/*/bin/activate
     pip install uvicorn==0.30.6 gunicorn==23.0.0
     cat << GUNICORN_CONF > /var/app/staging/gunicorn.conf.py
     bind = '0.0.0.0:8000'
     workers = 2
     worker_class = 'uvicorn.workers.UvicornWorker'
     timeout = 60
     keepalive = 2
     GUNICORN_CONF
     \`\`\`
   - `.platform/nginx/conf.d/custom.conf`:
     \`\`\`
     client_max_body_size 50M;
     \`\`\`

3. **Initialize EB**:
   \`\`\`bash
   eb init -p python-3.9 ai-code-reviewer --region us-east-1
   eb create ai-code-reviewer-env --single
   \`\`\`

4. **Set IAM Role**:
   - Create `aws-elasticbeanstalk-ec2-role` with `AmazonBedrockFullAccess`.
   - Attach to EB:
     \`\`\`bash
     aws elasticbeanstalk update-environment \\
       --environment-name ai-code-reviewer-env \\
       --option-settings Namespace=aws:autoscaling:launchconfiguration,OptionName=IamInstanceProfile,Value=aws-elasticbeanstalk-ec2-role
     \`\`\`

5. **Deploy**:
   \`\`\`bash
   git add .
   git commit -m "Deploy to EB"
   eb deploy ai-code-reviewer-env
   eb open
   \`\`\`
   Access at `http://ai-code-reviewer-env.eba-qmwrm295.us-east-1.elasticbeanstalk.com`.

## CI/CD with GitHub Actions

Automate deployment:

1. **Workflow File**: `.github/workflows/deploy.yml`:
   \`\`\`yaml
   name: Deploy to AWS Elastic Beanstalk
   on:
     push:
       branches:
         - main
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - name: Checkout code
           uses: actions/checkout@v4
         - name: Set up Python
           uses: actions/setup-python@v5
           with:
             python-version: '3.9'
         - name: Install dependencies
           run: |
             python -m pip install --upgrade pip
             pip install -r requirements.txt
         - name: Configure AWS credentials
           uses: aws-actions/configure-aws-credentials@v4
           with:
             aws-access-key-id: \${{ secrets.AWS_ACCESS_KEY_ID }}
             aws-secret-access-key: \${{ secrets.AWS_SECRET_ACCESS_KEY }}
             aws-region: us-east-1
         - name: Install EB CLI
           run: pip install awsebcli
         - name: Deploy to Elastic Beanstalk
           run: |
             eb init ai-code-reviewer -p python-3.9 --region us-east-1
             eb use ai-code-reviewer-env
             eb deploy ai-code-reviewer-env
   \`\`\`

2. **Secrets**:
   - Add `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` in GitHub Settings > Secrets.

## Suggestions for Production

To enhance reliability and scalability:
- **Logging**: Add `logging` to `main.py` (e.g., `logging.basicConfig(level=logging.INFO)`) and send logs to AWS CloudWatch.
- **Rate Limiting**: Use `slowapi` to limit `/api/analyze` requests.
- **Caching**: Cache Bedrock responses with Redis for repeated queries.
- **Error Handling**: Already uses `HTTPException` in `/api/analyze`; consider retrying Bedrock calls with `backoff`.
- **Security**:
  - Store credentials in AWS Secrets Manager.
  - Enable AWS WAF on EB for DDoS protection.
- **Scaling**: Configure EB auto-scaling (`aws:autoscaling:asg`).
- **Monitoring**: Use `/api/health` for CloudWatch alarms.
- **File Validation**: Check `submission.zip` size before upload.

## Limitations

- **Large Files**:
  - **Limit**: Nginx set to 50MB (`client_max_body_size 50M`).
  - **Mitigation**: Use S3 pre-signed URLs for larger files.
- **Text Truncation**:
  - **Limit**: Bedrock input ~8k tokens.
  - **Mitigation**: Chunk inputs with `chunk_splitter.py`.
- **Tech Stack Detection**:
  - **Limit**: Relies on file extensions in `zip_processor.py`.
  - **Mitigation**: Add AST parsing.
- **SonarQube Reports**:
  - **Limit**: Assumes `issues` array format.
  - **Mitigation**: Add schema validation in `sonar_parser.py`.
- **Bedrock Latency**:
  - **Limit**: ~1-2s per request.
  - **Mitigation**: Parallel processing enabled (`parallel` model).

## Demo

- **Local**: `http://localhost:8000`
- **Live**: `http://ai-code-reviewer-env.eba-qmwrm295.us-east-1.elasticbeanstalk.com`

## Dependencies

See `requirements.txt`. Key packages:
- `fastapi==0.115.0`: Web framework
- `uvicorn==0.30.6`: ASGI server
- `gunicorn==23.0.0`: WSGI/ASGI server for EB
- `boto3==1.35.29`: AWS SDK for Bedrock
- `jinja2==3.1.4`: Templating
- `pyyaml==6.0.2`: Config parsing

## Notes

- **Python**: Local 3.13+; EB uses 3.9.
- **Security**: IAM role `aws-elasticbeanstalk-ec2-role` with `AmazonBedrockFullAccess`.
- **Improvements**:
  - Add TypeScript/Python files with comments to `submission.zip` for `doc_coverage`.
  - Re-add logging to `main.py` for better debugging.
  - Test `/api/test-bedrock` on EB to confirm Bedrock access.