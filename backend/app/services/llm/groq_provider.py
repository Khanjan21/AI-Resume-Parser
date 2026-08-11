"""Groq implementation of LLMProvider.

Uses forced tool-calling rather than plain "JSON mode": handing the model a
tool whose `parameters` is our Pydantic schema, then forcing `tool_choice` to
that tool, is far more reliable at producing exactly-shaped JSON (including
nested objects via `$defs`) than asking nicely in a prompt.
"""

from __future__ import annotations

import json

from groq import APIError, APITimeoutError, AsyncGroq
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm.base import LLMExtractionError, LLMProvider, StructuredModel

logger = get_logger(__name__)


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or settings.GROQ_API_KEY
        if not key:
            raise LLMExtractionError(
                "GROQ_API_KEY is not configured — set it in .env to enable parsing."
            )
        self._client = AsyncGroq(api_key=key, timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS)
        self._model = model or settings.GROQ_MODEL

    async def extract[T: StructuredModel](
        self,
        *,
        system_prompt: str,
        user_content: str,
        response_model: type[T],
        tool_name: str,
        tool_description: str,
    ) -> T:
        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": response_model.model_json_schema(),
            },
        }

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": tool_name}},
                temperature=0,
            )
        except APITimeoutError as exc:
            raise LLMExtractionError(f"Groq request timed out: {exc}") from exc
        except APIError as exc:
            raise LLMExtractionError(f"Groq API error: {exc}") from exc

        message = response.choices[0].message
        if not message.tool_calls:
            raise LLMExtractionError(
                "Groq did not return a tool call — got plain text instead: "
                f"{(message.content or '')[:200]}"
            )

        raw_arguments = message.tool_calls[0].function.arguments
        try:
            return response_model.model_validate_json(raw_arguments)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning("Groq tool-call arguments failed validation: %s", raw_arguments[:500])
            raise LLMExtractionError(
                f"Groq's response did not match the expected schema: {exc}"
            ) from exc
