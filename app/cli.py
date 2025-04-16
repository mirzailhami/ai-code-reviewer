"""Command-line interface for AI Code Reviewer.

This module provides a CLI to analyze code submissions against SonarQube reports,
specifications, and scorecard questions. It uses the MasterAgent to generate a
comprehensive report, saved as `report.json`. Supports async processing with AWS Bedrock.

Example:
    ```bash
    python cli.py --sonar-file sonar.json --zip-path code.zip --spec-path spec.txt \\
                  --question-file scorecard.json --tech-stack "Python,JavaScript"
    ```
"""

import sys
import os
import argparse
import json
import logging
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.agents.master_agent import MasterAgent

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cli_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Adjust sys.path for module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def validate_files(sonar_file: str, zip_path: str, spec_path: str, question_file: str) -> bool:
    """Validate existence of input files.

    Args:
        sonar_file: Path to SonarQube JSON report.
        zip_path: Path to code ZIP file.
        spec_path: Path to challenge specification.
        question_file: Path to scorecard JSON (optional).

    Returns:
        bool: True if all files exist, False otherwise.
    """
    logger.debug(f"Validating files: {sonar_file}, {zip_path}, {spec_path}, {question_file}")
    files = [sonar_file, zip_path, spec_path]
    if question_file:
        files.append(question_file)
    for f in files:
        if not os.path.exists(f):
            logger.error(f"File not found: {f}")
            return False
    return True

async def main():
    """Run the CLI with provided arguments.

    Parses command-line arguments, validates input files, and initiates code review
    via MasterAgent. Outputs results to stdout and saves to `report.json`.

    Args:
        None: Arguments are parsed from sys.argv.

    Returns:
        None

    Raises:
        SystemExit: If argument parsing fails or files are invalid.

    Example:
        ```bash
        python cli.py --sonar-file tests/test_data/sonar-report.json \\
                      --zip-path tests/test_data/submission.zip \\
                      --spec-path tests/test_data/spec.txt \\
                      --question-file tests/test_data/scorecard.json
        ```
    """
    logger.debug(f"Running cli.py from: {os.path.abspath(__file__)}")
    logger.debug(f"os module loaded: {os}")
    
    parser = argparse.ArgumentParser(description="AI Code Reviewer CLI")
    parser.add_argument("--sonar-file", required=True, help="Path to SonarQube report")
    parser.add_argument("--zip-path", required=True, help="Path to code zip file")
    parser.add_argument("--spec-path", required=True, help="Path to challenge spec")
    parser.add_argument("--question-file", help="Path to scorecard JSON")
    parser.add_argument("--tech-stack", default="Python,TypeScript", help="Comma-separated tech stack")
    parser.add_argument("--model-backend", default="bedrock", choices=["bedrock"], help="Model backend")
    parser.add_argument("--model-name", default="parallel", choices=["parallel"], help="Model name")
    
    args = parser.parse_args()
    
    if not validate_files(args.sonar_file, args.zip_path, args.spec_path, args.question_file):
        logger.error("File validation failed")
        sys.exit(1)
    
    tech_stack = args.tech_stack.split(",")
    logger.debug(f"Initializing MasterAgent with model_name={args.model_name}, backend={args.model_backend}, tech_stack={tech_stack}")
    
    agent = MasterAgent(model_name=args.model_name, model_backend=args.model_backend, tech_stack=tech_stack)
    
    logger.debug("Calling MasterAgent.review_code")
    result = await agent.review_code(
        sonar_file=args.sonar_file,
        zip_path=args.zip_path,
        spec_path=args.spec_path,
        question_file=args.question_file
    )
    
    logger.debug(f"Review result: {json.dumps(result, indent=2)[:500]}...")
    print(json.dumps(result, indent=2))
    
    with open("report.json", "w") as f:
        json.dump(result, f, indent=2)
    logger.info("Report generated: report.json")

if __name__ == "__main__":
    asyncio.run(main())