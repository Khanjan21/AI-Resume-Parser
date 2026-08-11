"""LLM provider package — import `get_llm_provider` rather than a concrete class.

Swapping providers later (Ollama, Gemini, ...) means changing this one factory
function; nothing else in the codebase names `GroqProvider` directly.
"""

from __future__ import annotations

from functools import lru_cache

from app.services.llm.base import LLMExtractionError, LLMProvider
from app.services.llm.groq_provider import GroqProvider

__all__ = ["LLMExtractionError", "LLMProvider", "GroqProvider", "get_llm_provider"]


@lru_cache
def get_llm_provider() -> LLMProvider:
    return GroqProvider()
