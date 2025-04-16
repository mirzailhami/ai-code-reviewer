import boto3
import json
from typing import List, Dict, Any, Tuple
import asyncio
import backoff
import yaml
import logging

logger = logging.getLogger(__name__)

class BedrockLLM:
    """Manages interactions with AWS Bedrock LLMs."""

    def __init__(self, model_name: str, model_backend: str, region: str = "us-east-1"):
        """Initializes the BedrockLLM."""
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
        """Loads model configuration."""
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

    @backoff.on_exception(backoff.expo, Exception, max_tries=6, max_time=120, jitter=backoff.full_jitter)
    async def generate(self, messages: List[Dict[str, str]]) -> str:
        """Generates a response from the Bedrock model."""
        logger.debug(f"Generating with model: {self.model_name} (model_id: {self.model_id})")
        for attempt in range(3):
            try:
                body = {}
                if "deepseek" in self.model_id.lower():
                    body = {
                        "messages": [
                            {"role": m["role"], "content": m["content"]} for m in messages
                        ],
                        "max_tokens": self.model_config.get("max_tokens", 512),
                        "temperature": self.model_config.get("temperature", 0.4),
                        "top_p": self.model_config.get("top_p", 0.9)
                    }
                elif "llama3" in self.model_id.lower():
                    prompt = self._format_llama_prompt(messages)
                    body = {
                        "prompt": prompt,
                        "max_gen_len": self.model_config.get("max_gen_len", 512),
                        "temperature": self.model_config.get("temperature", 0.5),
                        "top_p": self.model_config.get("top_p", 0.9)
                    }
                else:  # Mistral
                    prompt = self._format_mistral_prompt(messages)
                    body = {
                        "prompt": prompt,
                        "max_tokens": self.model_config.get("max_tokens", 512),
                        "temperature": self.model_config.get("temperature", 0.3),
                        "top_p": self.model_config.get("top_p", 0.9),
                        "top_k": self.model_config.get("top_k", 50)
                    }

                response = await asyncio.to_thread(
                    self.client.invoke_model,
                    modelId=self.model_id,
                    body=json.dumps(body),
                    contentType="application/json"
                )

                response_body = json.loads(response["body"].read())
                logger.debug(f"Raw response for {self.model_name}: {response_body}")
                output = ""
                if "deepseek" in self.model_id.lower():
                    output = response_body.get("choices", [{}])[0].get("message", {}).get("content") or ""
                elif "llama3" in self.model_id.lower():
                    output = response_body.get("generation") or ""
                else:  # Mistral
                    output = response_body.get("outputs", [{}])[0].get("text") or ""
                    if "security" in messages[0].get("content", "").lower():
                        try:
                            json.loads(output)
                        except json.JSONDecodeError:
                            logger.warning(f"Mistral non-JSON output: {output[:100]}")
                            output = json.dumps([])

                if output.strip():
                    await asyncio.sleep(2)  # Increased delay
                    return output.strip()
                logger.warning(f"Empty response on attempt {attempt + 1} for {self.model_name}")
                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"Bedrock invocation failed for {self.model_name}: {str(e)}")
                raise
        logger.error(f"All attempts failed for {self.model_name}")
        return ""

    def _format_mistral_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Formats messages for Mistral models."""
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
        """Formats messages for LLaMA models."""
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