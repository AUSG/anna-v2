from typing import List, Optional, Protocol, Union

from features.questions.models import ChatFailure, ChatResult, Utterance


class QAGateway(Protocol):
    def chat(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        conversation: Optional[List[Utterance]] = None,
    ) -> Union[ChatResult, ChatFailure]:
        ...

    def generate(
        self,
        content: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        images: Optional[List[str]] = None,
    ) -> Optional[str]:
        """검색 없이 생성한 답변. 실패하면 None."""
        ...

    def daily_digest(self) -> str:
        """어제의 다이제스트. 실패는 예외로 전파한다."""
        ...
