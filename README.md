# Intelligent Code Review AI Agent System

## Overview

The **Intelligent Code Review AI Agent System** is a powerful, enterprise-grade tool designed to automate code quality assessments for software projects. Built with a modular architecture, it integrates AWS Bedrock's advanced language models, SonarQube analytics, and a multi-agent system to evaluate code submissions against technical requirements, security standards, and best practices. The system supports a user-friendly web interface and a command-line interface (CLI) for seamless integration into developer workflows.

Key capabilities include:

- **Tech Stack Validation**: Ensures submissions align with specified languages, supporting a wide range of programming languages (e.g., Python, Java, C++, Go).
- **SonarQube Integration**: Analyzes code for quality, security, and performance issues.
- **AI-Powered Insights**: Leverages large language models (LLMs) to assess code quality, performance, security, functionality, innovation, and documentation.
- **Comprehensive Reporting**: Delivers detailed JSON reports with actionable feedback.
- **Scalable Deployment**: Supports local development and AWS Elastic Beanstalk for production.

This project is ideal for development teams seeking to streamline code reviews, enforce quality standards, and accelerate delivery without compromising on rigor.

## Features

- **Validation Agent**: Confirms submission files match the specified tech stack using file extension, content analysis, and Pygments-based detection.
- **SonarQube Parser**: Extracts metrics (e.g., code smells, doc coverage) from SonarQube reports.
- **NLP Question Agent**: Evaluates project requirements via scorecard questions, powered by AWS Bedrock models.
- **Master Agent**: Orchestrates the review process, integrating validation, analysis, and AI insights.
- **Web UI**: Intuitive interface for uploading files and viewing results, built with FastAPI and Jinja2.
- **CLI**: Batch processing for automated reviews, perfect for CI/CD pipelines.
- **Parallel Processing**: Optimizes performance by running AI model tasks concurrently.

## Architecture

The system is structured for modularity and scalability:

- **Backend**: FastAPI-powered REST API with AWS Bedrock integration.
- **Agents**:
  - `ValidationAgent`: Tech stack verification.
  - `NLPQuestionAgent`: Scorecard evaluation.
  - `MasterAgent`: Workflow orchestration.
- **Processors**:
  - `SonarParser`: SonarQube report parsing.
  - `ZipProcessor`: Submission extraction and language detection.
  - `ChunkSplitter`: Code chunking for LLM input.
- **Frontend**: Responsive UI.
- **Configuration**: Model settings in `config/models.yaml`, language mappings in `config/languages.yaml`.

## AI Models and Configuration

The AI Code Reviewer leverages AWS Bedrock models to power its analysis tasks. Each task is assigned a specific model optimized for its requirements, with the flexibility to change models and configure prompts dynamically via `config/models.yaml`.

### Models Used by Task

| Task | Default Model | Description |
| --- | --- | --- |
| **Validation** | `mistral_large` | Verifies tech stack compliance using file extensions and content analysis. |
| **Security** | `mistral_large` | Identifies vulnerabilities in code and SonarQube reports. |
| **Quality** | `mistral_large` | Assesses maintainability, code smells, and documentation coverage. |
| **Performance** | `claude3_7_sonnet` | Evaluates code efficiency and identifies bottlenecks. |
| **Scorecard** | `claude3_7_sonnet` | Answers requirement-based questions for functionality and innovation. |

### Dynamic Model Configuration

The system supports dynamic model selection and prompt customization, enabling developers to adapt the tool to specific needs:

- **Change Models**: Update the `MODEL_TASK_MAPPING` in `app/core/agents/master_agent.py` or modify `config/models.yaml` to assign different models (e.g., `llama3_70b`, `deepseek_r1`) to tasks. For example, to use `llama3_70b` for security analysis:

  ```yaml
  backends:
    bedrock:
      models:
        llama3_70b:
          model_id: arn:aws:bedrock:us-east-1:324037276468:inference-profile/us.meta.llama3-3-70b-instruct-v1:0
  ```

  Then update `MODEL_TASK_MAPPING`:

  ```python
  MODEL_TASK_MAPPING = {
      "validation": "mistral_large",
      "security": "llama3_70b",  # Updated model
      "quality": "mistral_large",
      "performance": "claude3_7_sonnet",
      "scorecard": "claude3_7_sonnet"
  }
  ```

- **Customize Prompts**: Edit `config/models.yaml` to adjust system and user prompts for each task. For example, to refine the security prompt:

  ```yaml
  prompts:
    security:
      system: |
        You are a security expert. Analyze code and SonarQube data for vulnerabilities.
        Output JSON only: [{"issue": str, "type": str, "severity": str, "confidence": int, "file": str, "recommendation": str}].
      user: |
        Analyze for vulnerabilities:
        - SonarQube: {sonar_data}
        - Code: {code_samples}
        Focus on critical issues like SQL injection and XSS.
  ```

- **Benefits**:

  - **Flexibility**: Swap models without code changes.
  - **Scalability**: Add new models by updating `config/models.yaml`.
  - **Precision**: Tailor prompts to improve analysis accuracy for specific projects.

## Language Detection

The AI Code Reviewer supports a wide range of programming languages through dynamic language detection in `ZipProcessor` (`app/core/processors/zip_processor.py`). It processes `submission.zip` files containing any programming language using:

- **Extension-Based Detection**: Maps file extensions to languages via `config/languages.yaml`. Supported languages include Python, TypeScript, JavaScript, HTML, Java, C++, C, C#, Go, Ruby, PHP, Rust, Kotlin, Swift, and more.
- **Content-Based Detection**: Identifies languages in ambiguous files (e.g., `.txt`, no-extension) using predefined patterns in `config/languages.yaml`.
- **Pygments Integration**: Uses the `pygments` library as a fallback to guess languages based on code structure, ensuring robust detection for unsupported extensions.

### Configuring Language Support

Languages and detection patterns are defined in `config/languages.yaml`. To add a new language (e.g., Scala):

```yaml
languages:
  extensions:
    .scala: Scala
  patterns:
    Scala: ["object ", "def main("]
```

This dynamic configuration allows the system to adapt to any programming language without code changes, making it ideal for diverse codebases.

## Scoring Methodology

The AI Code Reviewer generates a comprehensive report with scores across four dimensions: **Code Quality**, **Security**, **Performance**, and **Scorecard**. The **Total Score** is a weighted average of these components.

### Score Components

1. **Code Quality (35% weight)**:

   - **Maintainability Score**: 0-100, based on code structure and complexity (from LLM analysis).
   - **Code Smells**: Count of issues from SonarQube (e.g., high complexity, duplication).
   - **Documentation Coverage**: Percentage of documented code (0-100).
   - **Calculation**: `min(maintainability_score, 100)`.

2. **Security (25% weight)**:

   - **Findings**: List of vulnerabilities (e.g., SQL injection, XSS) from LLM and SonarQube.
   - **Calculation**: `100 - (number_of_findings * 15)`, clamped to 0-100.

3. **Performance (20% weight)**:

   - **Rating**: 0-100, based on LLM-identified bottlenecks and efficiency.
   - **Bottlenecks**: Specific performance issues (e.g., high complexity functions).
   - **Suggestions**: Optimization recommendations.
   - **Calculation**: `min(rating, 100)`.

4. **Scorecard (20% weight)**:

   - **Answers**: Responses to predefined questions (e.g., "Is the solution innovative?") with answers (max 500 chars) and confidence (1-5).
   - **Weights**: Each question has a weight (e.g., 50 for functionality, 20 for innovation).
   - **Calculation**:
     - For each answer: `normalized_confidence = confidence / 5 * weight`.
     - Score: `(sum(normalized_confidence) / sum(weights)) * 100`, clamped to 0-100.
     - Example: For confidences \[4, 3, 4, 5\] and weights \[20, 50, 20, 10\]:
       - `sum_conf_weight = (4/5 * 20) + (3/5 * 50) + (4/5 * 20) + (5/5 * 10) = 16 + 30 + 16 + 10 = 72`.
       - `sum_weights = 20 + 50 + 20 + 10 = 100`.
       - `scorecard = (72 / 100) * 100 = 72.0`.

### Total Score

- **Formula**: `total = (code_quality * 0.35) + (security * 0.25) + (performance * 0.2) + (scorecard * 0.2)`.
- **Example**:
  - `code_quality`: 75, `security`: 100, `performance`: 85, `scorecard`: 72.
  - `total = (75 * 0.35) + (100 * 0.25) + (85 * 0.2) + (72 * 0.2) = 26.25 + 25 + 17 + 14.4 = 82.65`.

## Sample Output Response

The system outputs a JSON report (`report.json`) with detailed metrics and insights. Below is a sample response:

```json
{
  "screening_result": {
    "valid": true,
    "reason": "",
    "languages": ["Python", "JavaScript", "HTML"]
  },
  "security_findings": [],
  "quality_metrics": {
    "maintainability_score": 75,
    "code_smells": 3,
    "doc_coverage": 50
  },
  "performance_metrics": {
    "rating": 85,
    "bottlenecks": ["High cognitive complexity in master_agent.py"],
    "optimization_suggestions": [
      "Refactor master_agent.py to reduce complexity",
      "Break down complex logic into smaller functions"
    ]
  },
  "scorecard": [
    {
      "question": "The solution provides a unique approach to solving the given problem(s).",
      "category": "Innovation & Creativity",
      "answer": "The solution uses a multi-model approach with AWS Bedrock, employing Mistral Large and Claude for analysis. The multi-agent design is innovative but complex.",
      "confidence": 4,
      "weight": 20.0
    },
    {
      "question": "Requirements are implemented completely according to the requirements without major use cases or experiences missing.",
      "category": "Functionality & Completeness",
      "answer": "The code meets main requirements but has complexity issues. JSON output and validation are implemented, but maintainability needs improvement.",
      "confidence": 3,
      "weight": 50.0
    },
    {
      "question": "The technical solution is modern and designed with best practices to complement the requirements.",
      "category": "Technical Implementation",
      "answer": "Uses FastAPI and modular design, but SonarQube flags complexity issues in key files, indicating maintainability concerns.",
      "confidence": 4,
      "weight": 20.0
    },
    {
      "question": "Complete and easy-to-follow documentation is included with the solution.",
      "category": "Presentation (Docs & Demo)",
      "answer": "Documentation covers system overview and features but lacks complete setup instructions and a demo video.",
      "confidence": 5,
      "weight": 10.0
    }
  ],
  "summary": {
    "code_quality": 75,
    "security": 100,
    "performance": 85,
    "scorecard": 72.0,
    "total": 82.7
  },
  "timestamp": "2025-04-19T00:15:45.603479",
  "runtime": 72.568
}
```

## Prerequisites

- **Python**: 3.13+ (`python --version`)
- **AWS CLI**: Configured with Bedrock access (`aws configure`)
- **SonarQube**: Local server (`http://localhost:9000`) or remote instance
- **Docker**: Optional, for containerized deployment

## Installation

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/mirzailhami/ai-code-reviewer.git
   cd ai-code-reviewer
   ```

2. **Set Up Virtual Environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure AWS Credentials**:

   - Run `aws configure` or edit your `~/.aws/credentials`:

     ```ini
     [default]
     aws_access_key_id = YOUR_ACCESS_KEY
     aws_secret_access_key = YOUR_SECRET_KEY
     region = us-east-1
     ```

5. **Start SonarQube (Local)**:

   ```bash
   docker run -d -p 9000:9000 sonarqube
   ```

   - Access at `http://localhost:9000`, default login: `admin/admin`.

6. **Generate SonarQube Report**:

   ```bash
   sonar-scanner \
     -Dsonar.projectKey=ai-code-reviewer \
     -Dsonar.sources=. \
     -Dsonar.exclusions="tests/*,venv/*,*.git*,*__pycache__*" \
     -Dsonar.python.version=3.13 \
     -Dsonar.report.export.path=sonar-report.json \
     -Dsonar.token=YOUR_SONAR_TOKEN
   mv sonar-report.json tests/test_data/sonar-report.json
   ```

## Running the Application

### Local Web Server

1. **Start FastAPI**:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Access UI**:

   - Open `http://localhost:8000`.
   - Upload:
     - **SonarQube Report**: `tests/test_data/sonar-report.json`
     - **Submission**: `tests/test_data/submission.zip`
     - **Scorecard**: `tests/test_data/scorecard.json`
     - **Specification**: `tests/test_data/spec.txt`
     - **Tech Stack**: `Python,TypeScript,Java` (or any supported languages)

### CLI

1. **Run Analysis**:

   ```bash
   time python app/cli.py \
     --sonar-file tests/test_data/sonar-report.json \
     --zip-path tests/test_data/submission.zip \
     --spec-path tests/test_data/spec.txt \
     --question-file tests/test_data/scorecard.json \
     --tech-stack "TypeScript,Python,Java"
   ```

2. **Output**:

   - Report saved to `report.json`.
   - Runtime logged (target: ≤60s).

## Deployment (AWS Elastic Beanstalk)

Deploy the application to AWS for a production-ready environment.

1. **Initialize EB CLI**:

   ```bash
   eb init -p python-3.9 ai-code-reviewer --region us-east-1
   ```

2. **Create Environment**:

   ```bash
   eb create ai-code-reviewer-env --single
   ```

3. **Configure IAM Role**:

   - Create `aws-elasticbeanstalk-ec2-role` with `AmazonBedrockFullAccess`.
   - Update environment:

     ```bash
     aws elasticbeanstalk update-environment \
       --environment-name ai-code-reviewer-env \
       --option-settings Namespace=aws:autoscaling:launchconfiguration,OptionName=IamInstanceProfile,Value=aws-elasticbeanstalk-ec2-role
     ```

4. **Deploy**:

   ```bash
   git add .
   git commit -m "Deploy to Elastic Beanstalk"
   eb deploy ai-code-reviewer-env
   eb open
   ```

5. **Access**:

   - URL: `http://ai-code-reviewer-env.eba-xxxxxxxx.us-east-1.elasticbeanstalk.com`

## CI/CD with GitHub Actions

Automate deployments with GitHub Actions.

1. **Create Workflow**:

   - File: `.github/workflows/deploy.yml`

2. **Add Secrets**:

   - In GitHub: Settings > Secrets and variables > Actions.
   - Add: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

## Input File Formats

1. **SonarQube Report** (`sonar-report.json`):

   ```json
   {
     "total": 2,
     "issues": [
       {
         "key": "mock-001",
         "rule": "python:S1192",
         "severity": "MINOR",
         "component": "app/cli.py",
         "line": 10,
         "message": "Define a constant instead of duplicating this literal 'DEBUG' 3 times.",
         "type": "CODE_SMELL"
       }
     ],
     "components": []
   }
   ```

2. **Scorecard** (`scorecard.json`):

   ```json
   [
     {
       "question": "The solution provides a unique approach to solving the given problem(s).",
       "category": "Innovation & Creativity",
       "weight": 20.0
     },
     {
       "question": "Requirements are implemented completely...",
       "category": "Functionality & Completeness",
       "weight": 50.0
     }
   ]
   ```

3. **Specification** (`spec.txt`):

   - Copy paste the text from Topcoder Challange: `https://www.topcoder.com/challenges/46621f5a-e6a4-4a0d-b86f-32429acafe75`.

4. **Submission** (`submission.zip`):

   - ZIP containing source code in any programming language (e.g., `.py`, `.java`, `.cpp`, `.go`).

## REST API Endpoints

| Endpoint | Method | Description | Request Body (Multipart) | Response (JSON) Example |
| --- | --- | --- | --- | --- |
| `/` | GET | Serves web UI | N/A | HTML (`index.html`) |
| `/api/health` | GET | Checks app health | N/A | `{"status": "healthy"}` |
| `/api/models` | GET | Lists available models | N/A | `{"bedrock": ["mistral_large", "claude3_7_sonnet"]}` |
| `/api/analyze` | POST | Analyzes uploaded files | `sonar_report`, `submission`, `challenge_spec`, `scorecard`, `tech_stack`, `model_backend`, `model_name` | `{"screening_result": {"valid": true}, ...}` |
| `/api/test-bedrock` | GET | Tests Bedrock connectivity | N/A | `{"status": "success", "models": [...]}` |

## Dependencies

Key dependencies:

- `fastapi==0.115.2`: Web framework for REST API.
- `uvicorn==0.30.6`: ASGI server for local development.
- `gunicorn==23.0.0`: WSGI server for Elastic Beanstalk.
- `boto3==1.35.36`: AWS SDK for Bedrock integration.
- `pyyaml==6.0.2`: YAML configuration parsing.
- `jinja2==3.1.4`: Templating for web UI.
- `pygments==2.18.0`: Language detection for diverse codebases.

## Production Recommendations

- **Logging**: Stream logs to AWS CloudWatch for monitoring (`logging` in `app/main.py`).
- **Rate Limiting**: Implement `slowapi` for `/api/analyze` to prevent abuse.
- **Caching**: Use Redis to cache Bedrock responses for repeated queries.
- **Security**:
  - Store credentials in AWS Secrets Manager.
  - Enable AWS WAF on Elastic Beanstalk for DDoS protection.
- **Scaling**: Configure auto-scaling in Elastic Beanstalk (`aws:autoscaling:asg`).
- **Monitoring**: Set up CloudWatch alarms for `/api/health` endpoint.

## Limitations

- **File Size**: Limited to 50MB (`client_max_body_size 50M` in Nginx). Use S3 for larger uploads.
- **LLM Latency**: Bedrock requests take \~1-2s. Parallel processing mitigates this.
- **Language Detection**: Relies on extensions, patterns, and Pygments. Rare languages may require custom patterns in `config/languages.yaml`.
- **SonarQube**: Assumes standard report format. Add schema validation in `sonar_parser.py`.

## Demo

- **Local**: `http://localhost:8000`
- **Live**: `http://ai-code-reviewer-env.eba-qmwrm295.us-east-1.elasticbeanstalk.com`

## License

MIT License. See `LICENSE` for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/xyz`).
3. Commit changes (`git commit -m "Add xyz feature"`).
4. Push to the branch (`git push origin feature/xyz`).
5. Open a pull request.

For issues, file a ticket on the GitHub Issues page.

## Contact

For support or inquiries, contact me.