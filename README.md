# AI Code Review Agent

Topcoder challenge submission for automated code review using AI.

## Features
- Analyzes SonarQube JSON, code ZIPs, challenge specs, and scorecard questions.
- Supports AWS Bedrock (Claude, LLaMA) and local Mistral 7B (via Docker).
- Multi-agent architecture: validation, analysis, and NLP agents.
- Web frontend and CLI for easy interaction.

## Installation
1. Clone the repo:
   ```bash
   git clone <repo-url>
   cd ai-code-reviewer