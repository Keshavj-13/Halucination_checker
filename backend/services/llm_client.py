import os
import httpx
import json
import logging
import re
import asyncio
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from services.config import LLM_TIMEOUT_SECONDS

load_dotenv()

logger = logging.getLogger("audit-api.llm")

class LLMClient:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("LLM_MODEL", "gemini-2.5-flash" if self.provider == "gemini" else "gpt-3.5-turbo")
        
        if not self.api_key:
            logger.error(f"No API key found for provider: {self.provider}")
            
        if self.provider == "gemini":
            self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        else:
            self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions")

    def parse_json(self, text: str) -> Any:
        """Defensively extract JSON from model output."""
        # Strip potential thinking tags
        text = re.sub(r"<(thought|thinking)>[\s\S]*?<\/\1>", "", text, flags=re.IGNORECASE)
        
        # Try to find JSON block
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1)
        else:
            # Find the first '[' or '{' and the last ']' or '}'
            start_idx = text.find("[")
            start_idx_obj = text.find("{")
            if start_idx == -1 or (start_idx_obj != -1 and start_idx_obj < start_idx):
                start_idx = start_idx_obj
            
            end_idx = text.rfind("]")
            end_idx_obj = text.rfind("}")
            if end_idx == -1 or (end_idx_obj != -1 and end_idx_obj > end_idx):
                end_idx = end_idx_obj
            
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx+1]
        
        text = text.strip()
        # Clean trailing commas
        text = re.sub(r",\s*([\]\}])", r"\1", text)
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from: {text[:200]}...")
            raise ValueError("Invalid JSON format in model response")

    def _sanitize_error(self, error: Exception) -> str:
        msg = str(error)
        msg = re.sub(r"([?&]key=)[^&\s]+", r"\1<redacted>", msg)
        msg = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1<redacted>", msg)
        return msg

    async def chat(self, prompt: str, system_prompt: str = "You are a helpful assistant.", retries: int = 2) -> str:
        logger.info(f"Calling LLM ({self.provider}/{self.model})")
        
        if self.provider == "gemini":
            payload = {
                "contents": [{
                    "parts": [{"text": f"{system_prompt}\n\nUser: {prompt}"}]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json" if "JSON" in system_prompt else "text/plain"
                }
            }
        else:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
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
                async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
                    if self.provider == "gemini":
                        response = await client.post(self.base_url, json=payload)
                    else:
                        response = await client.post(self.base_url, headers=headers, json=payload)
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    if self.provider == "gemini":
                        content = data["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        content = data["choices"][0]["message"]["content"]
                        
                    logger.debug(f"Raw LLM Output: {content}")
                    return content
            except Exception as e:
                safe_error = self._sanitize_error(e)
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code in {400, 401, 403, 404, 429}:
                    logger.error(f"LLM non-retriable status {status_code}: {safe_error}")
                    raise Exception(f"Failed to communicate with LLM: {safe_error}")

                if attempt < retries:
                    logger.warning(f"LLM attempt {attempt + 1} failed: {safe_error}. Retrying...")
                    await asyncio.sleep(1)
                    continue
                logger.error(f"LLM Error after {retries + 1} attempts: {safe_error}")
                raise Exception(f"Failed to communicate with LLM: {safe_error}")

llm = LLMClient()
