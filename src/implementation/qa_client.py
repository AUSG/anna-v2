import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class QAClient:
    def __init__(self, qa_server_base_url: str, api_key: str, timeout: int = 120):
        self.qa_server_base_url = qa_server_base_url.rstrip("/")
        self.api_key = api_key
        self.namespace = "default"
        self.timeout = timeout

    def chat(self, question: str, system_prompt: Optional[str] = None) -> Optional[str]:
        payload = {
            "question": question,
            "namespace": self.namespace,
            "top_k": 4,
        }

        if system_prompt:
            payload["system_prompt"] = system_prompt

        headers = {"X-API-Key": self.api_key}

        try:
            response = requests.post(
                f"{self.qa_server_base_url}/api/v1/chat",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data["answer"]
        except requests.exceptions.RequestException as e:
            return None
        except (KeyError, IndexError) as e:
            return None

    def is_healthy(self) -> bool:
        headers = {"X-API-Key": self.api_key}

        try:
            response = requests.get(
                f"{self.qa_server_base_url}/api/v1/chat/health",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("overall") == "healthy"
            return False
        except requests.exceptions.RequestException:
            return False
