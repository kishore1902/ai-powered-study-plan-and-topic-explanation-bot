"""Groq client (generation only). The API key comes from the browser with each request
and is never stored on the server."""
import json
import re
import time
from dataclasses import dataclass

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class LLMError(Exception):
    def __init__(self, msg: str, missing_key: bool = False):
        super().__init__(msg)
        self.missing_key = missing_key


@dataclass
class Ctx:
    key: str
    model: str = DEFAULT_MODEL


def chat(ctx: Ctx, messages: list, *, json_mode=False, temperature=0.2, max_tokens=2048) -> str:
    if not ctx.key:
        raise LLMError("Add your Groq API key in Settings first.", missing_key=True)
    body = {"model": ctx.model or DEFAULT_MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {ctx.key}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = httpx.post(GROQ_URL, json=body, headers=headers, timeout=40)
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach Groq: {e}")
        if r.status_code == 429 and attempt < 2:
            try:
                wait = float(r.headers.get("retry-after", 4))
            except ValueError:
                wait = 4
            time.sleep(min(wait, 8))
            continue
        if r.status_code >= 400:
            try:
                msg = r.json()["error"]["message"]
            except Exception:
                msg = r.text[:200]
            raise LLMError(f"Groq {r.status_code}: {msg}")
        return r.json()["choices"][0]["message"]["content"]
    raise LLMError("Groq is rate limiting this key. Wait a minute and try again.")


def chat_json(ctx: Ctx, messages: list, **kw) -> dict:
    text = chat(ctx, messages, json_mode=True, **kw)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    raise LLMError("The model returned invalid JSON. Try again.")
