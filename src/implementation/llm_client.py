import logging
import re
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, question: str, system_prompt: Optional[str] = None, max_tokens: int = 1024) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": question})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            # Qwen3 모델의 <think>...</think> 태그 제거
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
            return content.strip()
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            raise LLMError("흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아가볼까?")

    def is_healthy(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False


class LLMError(Exception):
    pass
