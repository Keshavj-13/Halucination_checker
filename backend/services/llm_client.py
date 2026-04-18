import os
import httpx
import json
import logging
import re
import asyncio
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("audit-api.llm")

class LLMClient:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1" if self.provider == "ollama" else "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "qwen3.5:0.8b" if self.provider == "ollama" else "gpt-3.5-turbo")

    def parse_json(self, text: str) -> Any:
        """Defensively extract JSON from model output."""
        # Try to find JSON block
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1)
        else:
            # Try to find anything that looks like a JSON array or object
            match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
            if match:
                text = match.group(1)
        
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from: {text[:100]}...")
            raise ValueError("Invalid JSON format in model response")

    async def chat(self, prompt: str, system_prompt: str = "You are a helpful assistant.", retries: int = 2) -> str:
        logger.info(f"Calling LLM ({self.provider}/{self.model})")
        
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
        }

        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
            except Exception as e:
                if attempt < retries:
                    logger.warning(f"LLM attempt {attempt + 1} failed: {str(e)}. Retrying...")
                    await asyncio.sleep(1)
                    continue
                logger.error(f"LLM Error after {retries + 1} attempts: {str(e)}")
                raise Exception(f"Failed to communicate with LLM: {str(e)}")

llm = LLMClient()
