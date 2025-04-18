import boto3
import json
from typing import List, Dict, Any, Tuple
import asyncio
import backoff
import yaml
import logging
import re

logger = logging.getLogger(__name__)

BEDROCK_SEMAPHORE = asyncio.Semaphore(1)

class BedrockLLM:
    """Interface to AWS Bedrock for generating responses using large language models.

    This class manages interactions with AWS Bedrock's runtime API, supporting multiple
    model backends (e.g., DeepSeek, LLaMA, Claude, Mistral). It handles model initialization,
    configuration loading, prompt formatting, and asynchronous response generation with
    error handling and throttling mitigation.

    Attributes:
        model_name (str): Name of the model (e.g., 'mistral_large', 'claude3_7_sonnet').
        model_backend (str): Backend provider (e.g., 'bedrock').
        region (str): AWS region for Bedrock client (default: 'us-east-1').
        client (boto3.client): Bedrock runtime client.
        model_id (str): Unique identifier for the model in Bedrock.
        model_config (Dict): Configuration parameters for the model from config/models.yaml.
    """

    def __init__(self, model_name: str, model_backend: str, region: str = "us-east-1"):
        """Initialize the BedrockLLM with model and backend details.

        Args:
            model_name (str): Name of the model to use (e.g., 'mistral_large').
            model_backend (str): Backend provider (e.g., 'bedrock').
            region (str, optional): AWS region for Bedrock client. Defaults to 'us-east-1'.

        Raises:
            Exception: If Bedrock client initialization fails (e.g., invalid credentials).
        """
        self.model_name = model_name
        self.model_backend = model_backend
        self.region = region
        try:
            self.client = boto3.client("bedrock-runtime", region_name=self.region)
            logger.debug(f"Initialized Bedrock client: model_name={model_name}, region={region}")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {str(e)}")
            raise
        self.model_id, self.model_config = self._get_model_config()

    def _get_model_config(self) -> Tuple[str, Dict]:
        """Load model configuration from config/models.yaml.

        Retrieves the model ID and configuration parameters (e.g., max_tokens, temperature)
        for the specified model and backend.

        Returns:
            Tuple[str, Dict]: Model ID and configuration dictionary.

        Raises:
            Exception: If the configuration file is missing or invalid.
        """
        logger.debug(f"Loading config for model: {self.model_name}")
        try:
            with open("config/models.yaml", "r") as f:
                config = yaml.safe_load(f)
            model_config = config["backends"][self.model_backend]["models"].get(self.model_name, {})
            model_id = model_config.get("model_id", self.model_name)
            logger.debug(f"Model config for {self.model_name}: {model_config}")
            return model_id, model_config
        except Exception as e:
            logger.error(f"Failed to load model config: {str(e)}")
            return self.model_name, {}

    @backoff.on_exception(backoff.expo, Exception, max_tries=1, max_time=5, jitter=backoff.full_jitter)
    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generate a response from the Bedrock model asynchronously.

        Formats the input messages according to the model's requirements, sends the request
        to AWS Bedrock, and processes the response. Handles different model formats (e.g.,
        DeepSeek, LLaMA, Claude, Mistral) and ensures JSON output for specific tasks (e.g.,
        scorecard, security).

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' (e.g.,
                'system', 'user') and 'content' keys.

        Returns:
            str: JSON-formatted response string, typically a list of dictionaries for tasks
                like scorecard or security, or a single dictionary for others. Returns a
                fallback response on failure.

        Raises:
            Exception: If the Bedrock invocation fails (e.g., throttling, network issues).
        """
        async with BEDROCK_SEMAPHORE:
            logger.debug(f"Generating with model: {self.model_name} (model_id: {self.model_id})")
            try:
                body = {}
                if "deepseek" in self.model_id.lower():
                    body = {
                        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
                        "max_tokens": self.model_config.get("max_tokens", 512),
                        "temperature": self.model_config.get("temperature", 0.4),
                        "top_p": self.model_config.get("top_p", 0.9)
                    }
                elif "llama3" in self.model_id.lower():
                    body = {
                        "prompt": self._format_llama_prompt(messages),
                        "max_gen_len": self.model_config.get("max_gen_len", 512),
                        "temperature": self.model_config.get("temperature", 0.5),
                        "top_p": self.model_config.get("top_p", 0.9)
                    }
                elif "claude" in self.model_id.lower():
                    system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
                    user_messages = [
                        {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
                        for m in messages if m["role"] != "system"
                    ]
                    body = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": self.model_config.get("max_tokens", 200),
                        "top_k": self.model_config.get("top_k", 250),
                        "stop_sequences": self.model_config.get("stop_sequences", []),
                        "temperature": self.model_config.get("temperature", 1),
                        "top_p": self.model_config.get("top_p", 0.999),
                        "system": system_prompt,
                        "messages": user_messages
                    }
                    if "scorecard" in messages[0].get("content", "").lower():
                        body["thinking"] = {"type": "enabled", "budget_tokens": 1024}
                else:
                    body = {
                        "prompt": self._format_mistral_prompt(messages),
                        "max_tokens": self.model_config.get("max_tokens", 512),
                        "temperature": self.model_config.get("temperature", 0.3),
                        "top_p": self.model_config.get("top_p", 0.9),
                        "top_k": self.model_config.get("top_k", 50)
                    }

                start_time = asyncio.get_event_loop().time()
                response = await asyncio.to_thread(
                    self.client.invoke_model,
                    modelId=self.model_id,
                    body=json.dumps(body),
                    contentType="application/json"
                )
                response_time = asyncio.get_event_loop().time() - start_time
                logger.debug(f"Request took {response_time}s")

                response_body = json.loads(response["body"].read())
                logger.debug(f"Raw response for {self.model_name}: {response_body}")
                logger.debug(f"Tokens used: {response_body.get('usage', {})}")
                output = ""
                if "deepseek" in self.model_id.lower():
                    output = response_body.get("choices", [{}])[0].get("message", {}).get("content") or ""
                elif "llama3" in self.model_id.lower():
                    output = response_body.get("generation") or ""
                elif "claude" in self.model_id.lower():
                    output = response_body.get("content", [{}])[0].get("text") or ""
                else:
                    output = response_body.get("outputs", [{}])[0].get("text") or ""

                content = messages[0].get("content", "").lower()
                expected_array = "scorecard" in content or "security" in content or "validation" in content
                logger.debug(f"Raw output before processing: {output[:200]}")

                if output:
                    output = output.strip()
                    if output.startswith("```json"):
                        output = output[7:].rsplit("```", 1)[0].strip()
                    output = output.replace('\n', ' ').replace('\r', '')
                    try:
                        parsed = json.loads(output)
                        if expected_array and not isinstance(parsed, list):
                            logger.warning(f"Expected array, got: {output[:100]}")
                            output = json.dumps([parsed] if isinstance(parsed, dict) else [{"answer": "Evaluation failed", "confidence": 1}])
                    except json.JSONDecodeError:
                        logger.warning(f"Non-JSON output: {output[:100]}")
                        match = re.search(r'(\[.*?\]|\{.*?\})', output, re.DOTALL)
                        if match:
                            output = match.group(0)
                        else:
                            output = json.dumps([{"answer": "Evaluation failed", "confidence": 1}] if expected_array else {})
                    await asyncio.sleep(3)  # Increased delay
                    return output
                logger.warning(f"Empty response for {self.model_name}")
                await asyncio.sleep(8)  # Increased delay
                return json.dumps([{"answer": "Evaluation failed", "confidence": 1}] if expected_array else [])

            except Exception as e:
                if "ThrottlingException" in str(e):
                    logger.error(f"Throttling detected for {self.model_name}: {str(e)}")
                    await asyncio.sleep(8)  # Increased delay
                logger.error(f"Bedrock invocation failed for {self.model_name}: {str(e)}")
                raise
            logger.error(f"All attempts failed for {self.model_name}")
            return json.dumps([{"answer": "Evaluation failed", "confidence": 1}] if "scorecard" in messages[0].get("content", "").lower() else [])

    def _format_mistral_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Format messages into a prompt string for Mistral models.

        Converts a list of message dictionaries into a formatted prompt string with
        [INST] tags for system and user roles, as required by Mistral models.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role'
                and 'content' keys.

        Returns:
            str: Formatted prompt string for Mistral model.
        """
        prompt = "<s>"
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"[INST] {content} [/INST]"
            elif role == "user":
                prompt += f"[INST] {content} [/INST]"
        logger.debug(f"Formatted Mistral prompt: {prompt[:100]}...")
        return prompt

    def _format_llama_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Format messages into a prompt string for LLaMA models.

        Converts a list of message dictionaries into a formatted prompt string with
        'System:' and 'User:' prefixes, as required by LLaMA models.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role'
                and 'content' keys.

        Returns:
            str: Formatted prompt string for LLaMA model.
        """
        prompt = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"System: {content}\n"
            elif role == "user":
                prompt += f"User: {content}\n"
        logger.debug(f"Formatted LLaMA prompt: {prompt[:100]}...")
        return prompt