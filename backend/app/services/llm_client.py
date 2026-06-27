"""Provider-agnostic LLM client (OpenAI + Anthropic).

All AI features in the app go through this module so the underlying provider
can be switched with a single .env change:

    LLM_PROVIDER=openai     # or "anthropic", or "auto" (default)
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    OPENAI_MODEL=gpt-4o
    ANTHROPIC_MODEL=claude-sonnet-4-5

Message format (provider neutral)
----------------------------------
    messages = [
        {"role": "user", "content": "plain string"},
        {"role": "user", "content": [
            {"type": "text", "text": "What is in this screenshot?"},
            {"type": "image_b64", "media_type": "image/png", "data": "<base64>"},
        ]},
        {"role": "assistant", "content": "..."},
    ]

The system prompt is passed separately (Anthropic requires that; for OpenAI we
prepend it as a system message).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.automation.utils.logger import log


class LLMNotConfiguredError(RuntimeError):
    """Raised when no usable LLM provider/API key is configured."""


def _extract_json(text: str) -> Dict[str, Any]:
    """Best-effort extraction of a JSON object from an LLM response.

    Tries three strategies in order:
    1. Parse the whole (stripped) text directly.
    2. rfind-based slice (fast; handles most "trailing prose" cases).
    3. Depth-tracking scan from the first '{' (handles cases where post-JSON
       prose itself contains '}' characters, which defeats rfind).
    """
    if not text:
        raise ValueError("Empty LLM response")
    # Strip markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    text = text.strip()

    # Strategy 1: fast path — whole string is valid JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")

    # Strategy 2: first { … last } (works unless post-JSON prose has braces)
    end = text.rfind("}")
    if end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Strategy 3: depth-tracking — walk from first '{' to its matching '}'
    # respecting strings so that braces inside string values are not counted.
    depth = 0
    in_str = False
    escape_next = False
    for i, ch in enumerate(text[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_str:
            escape_next = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break  # outermost {} isn't valid JSON; nothing more to try

    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")


class LLMClient:
    """Unified async chat client over OpenAI and Anthropic."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = (provider or settings.active_llm_provider).lower()
        if self.provider in ("none", ""):
            raise LLMNotConfiguredError(
                "No LLM provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env "
                "(and optionally LLM_PROVIDER=openai|anthropic)."
            )

        if self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise LLMNotConfiguredError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            self.model = model or settings.OPENAI_MODEL
        elif self.provider == "anthropic":
            if not settings.ANTHROPIC_API_KEY:
                raise LLMNotConfiguredError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:  # pragma: no cover
                raise LLMNotConfiguredError(
                    "anthropic package not installed. Run: pip install anthropic"
                ) from exc
            self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            self.model = model or settings.ANTHROPIC_MODEL
        else:
            raise LLMNotConfiguredError(f"Unknown LLM provider: {self.provider}")

        log(f"[LLM] Using provider={self.provider} model={self.model}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        """Send a chat request and return the assistant text."""
        if self.provider == "openai":
            return await self._chat_openai(messages, system, max_tokens, temperature, json_mode)
        return await self._chat_anthropic(messages, system, max_tokens, temperature, json_mode)

    async def chat_json(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Send a chat request and parse the response as a JSON object."""
        text = await self.chat(messages, system, max_tokens, temperature, json_mode=True)
        return _extract_json(text)

    # ------------------------------------------------------------------
    # OpenAI
    # ------------------------------------------------------------------

    @staticmethod
    def _to_openai_messages(messages: List[Dict[str, Any]], system: Optional[str]) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        if system:
            converted.append({"role": "system", "content": system})
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                converted.append({"role": msg["role"], "content": content})
                continue
            parts = []
            for block in content:
                if block.get("type") == "text":
                    parts.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "image_b64":
                    media = block.get("media_type", "image/png")
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media};base64,{block['data']}"},
                    })
            converted.append({"role": msg["role"], "content": parts})
        return converted

    async def _chat_openai(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str],
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_openai_messages(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------

    @staticmethod
    def _to_anthropic_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                converted.append({"role": msg["role"], "content": content})
                continue
            parts = []
            for block in content:
                if block.get("type") == "text":
                    parts.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "image_b64":
                    parts.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": block.get("media_type", "image/png"),
                            "data": block["data"],
                        },
                    })
            converted.append({"role": msg["role"], "content": parts})
        return converted

    async def _chat_anthropic(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str],
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> str:
        sys_prompt = system or ""
        if json_mode:
            sys_prompt = (sys_prompt + "\n\nRespond ONLY with a single valid JSON object. "
                          "No prose, no markdown fences.").strip()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_anthropic_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if sys_prompt:
            kwargs["system"] = sys_prompt
        response = await self._client.messages.create(**kwargs)
        parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        return "".join(parts)


# ----------------------------------------------------------------------
# Singleton helper — most callers just need the default client.
# ----------------------------------------------------------------------

_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return a lazily-created default LLM client (raises if unconfigured)."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def reset_llm_client() -> None:
    """Reset the cached client (used by tests / when settings change)."""
    global _default_client
    _default_client = None
