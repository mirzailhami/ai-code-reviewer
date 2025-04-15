import boto3
import json
from typing import List, Dict, Any
import asyncio
import backoff
import yaml
import logging

logger = logging.getLogger(__name__)

class BedrockLLM:
    def __init__(self, model_name: str, model_backend: str, region: str = "us-east-1"):
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

    def _get_model_config(self) -> tuple[str, Dict]:
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
        prompt = "<|BEGIN_OF_TEXT|>"
        for msg in messages:
            role = msg.get("role", "").capitalize()
            content = msg.get("content", "")
            prompt += f"<|START_OF_TURN|>{role}: {content}<|END_OF_TURN|>"
        logger.debug(f"Formatted LLaMA prompt: {prompt[:100]}...")
        return prompt

    def _format_mistral_prompt(self, messages: List[Dict[str, str]]) -> str:
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