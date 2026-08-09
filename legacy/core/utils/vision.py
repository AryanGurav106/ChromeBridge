"""Direct vision-model call used by the Set-of-Mark screenshot tool.

pydantic-ai 0.0.17 has no multimodal message types, so we cannot feed images
through the agent's tool loop. Instead this helper makes a direct call to the
underlying VLM (OpenAI-compatible or Anthropic, chosen from the configured text
model name) and returns plain text — which a normal text tool can hand back to
the agent.
"""

import base64
import os
from typing import Optional

from core.utils.logger import Logger

logger = Logger()

_DEFAULT_MAX_TOKENS = 1024


def _env(key: str) -> Optional[str]:
    v = os.getenv(key)
    return v.strip() if v else None


async def describe_image(image_path: str, prompt: str, max_tokens: int = _DEFAULT_MAX_TOKENS) -> str:
    """Send an image + text prompt to the configured VLM; return its text reply.

    Uses AGENTIC_BROWSER_TEXT_MODEL/API_KEY/BASE_URL. If the model name starts
    with 'claude', uses the Anthropic SDK; otherwise the OpenAI-compatible SDK.
    """
    model = _env("AGENTIC_BROWSER_TEXT_MODEL")
    if not model:
        return "Vision analysis unavailable: AGENTIC_BROWSER_TEXT_MODEL is not set."

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    try:
        if model.lower().startswith("claude"):
            return await _anthropic_vision(model, b64, prompt, max_tokens)
        return await _openai_vision(model, b64, prompt, max_tokens)
    except Exception as e:
        logger.error(f"Vision call failed: {e}")
        return f"Vision analysis failed: {e}"


async def _openai_vision(model: str, b64: str, prompt: str, max_tokens: int) -> str:
    from openai import AsyncOpenAI

    api_key = _env("AGENTIC_BROWSER_TEXT_API_KEY")
    base_url = _env("AGENTIC_BROWSER_TEXT_BASE_URL") or "https://api.openai.com/v1"
    client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"), timeout=120.0)

    resp = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
    )
    return resp.choices[0].message.content or ""


async def _anthropic_vision(model: str, b64: str, prompt: str, max_tokens: int) -> str:
    from anthropic import AsyncAnthropic

    api_key = _env("AGENTIC_BROWSER_TEXT_API_KEY")
    client = AsyncAnthropic(api_key=api_key, timeout=120.0)

    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64},
                    },
                ],
            }
        ],
    )
    # Concatenate any text blocks in the response.
    parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "\n".join(parts)
