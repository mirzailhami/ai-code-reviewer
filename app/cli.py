"""Command-line interface for AI Code Reviewer."""

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
        logging.FileHandler('cli_debug.log', mode='w'),
        logging.StreamHandler()
    ]
)
# Ensure all loggers inherit root config
logging.getLogger('app.core').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

def validate_files(sonar_file: str, zip_path: str, spec_path: str, question_file: str) -> bool:
    """Validate existence of input files."""
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
    """Run the CLI with provided arguments."""
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