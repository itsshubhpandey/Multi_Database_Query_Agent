from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

try:
    from langchain_mistralai import ChatMistralAI
except ImportError:  # pragma: no cover
    ChatMistralAI = None

from backend.app.config import get_settings


class AiService:
    def __init__(self) -> None:
        self._llm: Runnable | None = None

    def llm(self) -> Runnable:
        if self._llm is not None:
            return self._llm

        settings = get_settings()
        provider = settings.llm_provider.lower()
        if provider == "mistral" and settings.mistral_api_key:
            if ChatMistralAI is None:
                raise RuntimeError("langchain-mistralai is not installed.")
            self._llm = ChatMistralAI(
                model=settings.mistral_model,
                api_key=settings.mistral_api_key,
                temperature=0,
            )
            return self._llm

        if settings.openai_api_key:
            self._llm = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
            )
            return self._llm

        raise RuntimeError("Set MISTRAL_API_KEY or OPENAI_API_KEY in backend/.env.")

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        response = self.llm().invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        return str(response.content)

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        async for chunk in self.llm().astream([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]):
            content = getattr(chunk, "content", "")
            if content:
                yield str(content)
