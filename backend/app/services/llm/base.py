"""Provider-agnostic interface for structured LLM extraction.

Everything downstream (resume parsing, JD parsing, and Day 6's explanations)
talks to this interface, not to Groq directly — swapping providers later
(Ollama, Gemini, OpenAI) means writing one new class, not touching callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from app.core.exceptions import AppError


class LLMExtractionError(AppError):
    """Raised when the provider fails or returns something unusable."""

    status_code = 502
    code = "llm_extraction_failed"


class StructuredModel(Protocol):
    """The subset of pydantic.BaseModel this module relies on."""

    @classmethod
    def model_json_schema(cls) -> dict: ...

    @classmethod
    def model_validate_json(cls, data: str | bytes): ...


class LLMProvider(ABC):
    """One method: text in, a validated pydantic model out."""

    @abstractmethod
    async def extract[T: StructuredModel](
        self,
        *,
        system_prompt: str,
        user_content: str,
        response_model: type[T],
        tool_name: str,
        tool_description: str,
    ) -> T:
        """Extract structured data matching `response_model` from `user_content`.

        Raises LLMExtractionError on any failure (network, malformed
        response, schema mismatch) — callers treat that as a parse failure,
        not a crash.
        """
        raise NotImplementedError
