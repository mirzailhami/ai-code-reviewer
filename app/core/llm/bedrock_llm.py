import boto3
import json
from typing import List, Dict, Any, Tuple
import asyncio
import backoff
import yaml
import logging

logger = logging.getLogger(__name__)

class BedrockLLM:
    """Manages interactions with AWS Bedrock LLMs for code analysis and NLP tasks.

    Attributes:
        model_name (str): Name of the Bedrock model (e.g., 'mistral_large').
        model_backend (str): Backend type (e.g., 'bedrock').
        region (str): AWS region for Bedrock client.
        client: Boto3 Bedrock runtime client.
        model_id (str): Unique identifier for the Bedrock model.
        model_config (Dict): Configuration settings for the model.
    """

    def __init__(self, model_name: str, model_backend: str, region: str = "us-east-1"):
        """Initializes the BedrockLLM with model and backend settings.

        Args:
            model_name (str): Name of the Bedrock model to use.
            model_backend (str): Backend type, must be 'bedrock'.
            region (str, optional): AWS region for Bedrock client. Defaults to 'us-east-1'.

        Raises:
            Exception: If Bedrock client initialization fails.
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
        """Loads model configuration from YAML file.

        Returns:
            Tuple[str, Dict]: Model ID and configuration dictionary.

        Raises:
            Exception: If loading or parsing the config file fails.

        Example:
            >>> llm = BedrockLLM("mistral_large", "bedrock")
            >>> model_id, config = llm._get_model_config()
            >>> print(model_id)
            'mistral.mistral-large-2402-v1:0'
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

    @backoff.on_exception(backoff.expo, Exception, max_tries=2, max_time=5)
    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generates a response from the Bedrock model based on input messages.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' and 'content' keys.

        Returns:
            str: Generated text output from the model, stripped of whitespace.

        Raises:
            Exception: If Bedrock invocation fails after retries.

        Example:
            >>> llm = BedrockLLM("mistral_large", "bedrock")
            >>> messages = [{"role": "user", "content": "Analyze this code..."}]
            >>> asyncio.run(llm.generate(messages))
            'Code analysis results...'
        """
        logger.debug(f"Generating with model: {self.model_name} (model_id: {self.model_id})")
        try:
            body = {}
            if "deepseek" in self.model_id.lower():
                body = {
                    "inferenceConfig": {
                        "maxTokens": self.model_config.get("max_tokens", 256)
                    },
                    "messages": [
                        {"role": m["role"], "content": m["content"]} for m in messages
                    ]
                }
            elif "llama3" in self.model_id.lower():
                prompt = self._format_llama_prompt(messages)
                body = {
                    "prompt": prompt,
                    "max_gen_len": self.model_config.get("max_tokens", 256),
                    "temperature": self.model_config.get("temperature", 0.5),
                    "top_p": self.model_config.get("top_p", 0.9)
                }
            else:  # Mistral
                prompt = self._format_mistral_prompt(messages)
                body = {
                    "prompt": prompt,
                    "max_tokens": self.model_config.get("max_tokens", 256 if "question" in prompt.lower() else 128),
                    "temperature": self.model_config.get("temperature", 0.5),
                    "top_p": self.model_config.get("top_p", 0.9),
                    "top_k": self.model_config.get("top_k", 50)
                }

            logger.debug(f"Invoking Bedrock model: {self.model_id} (Attempt 1/2)")
            logger.debug(f"Request body: {json.dumps(body)[:200]}...")

            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json"
            )

            logger.debug(f"Bedrock response status: {response['ResponseMetadata']['HTTPStatusCode']}")
            response_body = json.loads(response["body"].read())

            if "deepseek" in self.model_id.lower():
                output = response_body.get("choices", [{}])[0].get("message", {}).get("content", "")
            elif "llama3" in self.model_id.lower():
                output = response_body.get("generation", "")
            else:  # Mistral
                output = response_body.get("outputs", [{}])[0].get("text", "")

            logger.debug(f"Raw response: {json.dumps(response_body)[:500]}...")
            return output.strip() if output else ""

        except Exception as e:
            logger.error(f"Bedrock invocation failed: {str(e)}")
            logger.debug(f"Attempted modelId: {self.model_id}")
            return ""

    def _format_llama_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Formats messages into a prompt for LLaMA models.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' and 'content' keys.

        Returns:
            str: Formatted prompt string for LLaMA.

        Example:
            >>> llm = BedrockLLM("llama3_70b", "bedrock")
            >>> messages = [{"role": "user", "content": "Hello"}]
            >>> llm._format_llama_prompt(messages)
            '<|BEGIN_OF_TEXT|><|START_OF_TURN|>User: Hello<|END_OF_TURN|>'
        """
        prompt = "<|BEGIN_OF_TEXT|>"
        for msg in messages:
            role = msg.get("role", "").capitalize()
            content = msg.get("content", "")
            prompt += f"<|START_OF_TURN|>{role}: {content}<|END_OF_TURN|>"
        logger.debug(f"Formatted LLaMA prompt: {prompt[:100]}...")
        return prompt

    def _format_mistral_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Formats messages into a prompt for Mistral models.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' and 'content' keys.

        Returns:
            str: Formatted prompt string for Mistral.

        Example:
            >>> llm = BedrockLLM("mistral_large", "bedrock")
            >>> messages = [{"role": "user", "content": "Analyze code"}]
            >>> llm._format_mistral_prompt(messages)
            '[INST] Analyze code [/INST]\n'
        """
        prompt = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"[INST] {content} [/INST]\n"
            elif role == "user":
                prompt += f"[INST] {content} [/INST]\n"
        logger.debug(f"Formatted Mistral prompt: {prompt[:100]}...")
        return prompt