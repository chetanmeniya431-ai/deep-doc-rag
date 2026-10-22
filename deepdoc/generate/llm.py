"""Tiny client for a free local LLM served by Ollama. No API key, no cost."""
from __future__ import annotations

import base64

import httpx

from .. import config


class LLMUnavailable(RuntimeError):
    pass


def available() -> bool:
    if not config.OLLAMA_URL:
        return False
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=4)
        names = [m["name"] for m in r.json().get("models", [])]
        return any(n == config.LLM_MODEL or n.split(":")[0] == config.LLM_MODEL for n in names)
    except Exception:
        return False


def chat(system: str, user: str, model: str | None = None, max_tokens: int = 400) -> str:
    if not config.OLLAMA_URL:
        raise LLMUnavailable("OLLAMA_URL is not set")
    payload = {
        "model": model or config.LLM_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "keep_alive": config.LLM_KEEP_ALIVE,
        "options": {"temperature": 0, "num_ctx": config.LLM_CONTEXT_TOKENS, "num_predict": max_tokens},
    }
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=config.LLM_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:
        raise LLMUnavailable(str(exc)) from exc
    return r.json()["message"]["content"].strip()


def describe_image(png: bytes, caption: str = "") -> str:
    """Optional: ask a free vision model (VLM_MODEL, e.g. moondream) to read a chart."""
    if not (config.OLLAMA_URL and config.VLM_MODEL):
        return ""
    prompt = ("Describe this chart for a search index. List the title, axis labels, every category and its value, "
              "and the main trend. Use plain text only.")
    if caption:
        prompt += f" The caption is: {caption}"
    payload = {"model": config.VLM_MODEL, "prompt": prompt, "images": [base64.b64encode(png).decode()],
               "stream": False, "keep_alive": config.LLM_KEEP_ALIVE, "options": {"temperature": 0}}
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/generate", json=payload, timeout=config.LLM_TIMEOUT)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception:
        return ""
