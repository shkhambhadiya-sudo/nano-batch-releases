"""Local model gateway. Two tiers (spec §10): `large` for judgment, `small` for
classification and log scanning. Backends:

- ollama: local Ollama server (default on the Mac). Data never leaves the machine.
- mock:   deterministic rule-based answers so the whole system runs without a
          model server (tests, cloud scaffold). Every mock answer is tagged so it is
          never mistaken for a real model's output.

All calls return `LLMResult(text, model, tokens)`. `complete_json` asks for JSON and
parses it, falling back to `{}` when the model does not comply."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from ..config import settings

Tier = Literal["large", "small"]


@dataclass
class LLMResult:
    text: str
    model: str
    tokens: int


class OllamaBackend:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")

    async def complete(self, model: str, system: str, prompt: str, json_mode: bool) -> LLMResult:
        body: dict[str, Any] = {
            "model": model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0.2},
        }
        if json_mode:
            body["format"] = "json"
        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.post(f"{self.url}/api/chat", json=body)
            r.raise_for_status()
            data = r.json()
        tokens = int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0))
        return LLMResult(text=data["message"]["content"], model=model, tokens=tokens)

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.url}/api/tags")
                r.raise_for_status()
                names = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "models": names}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "models": []}


class MockBackend:
    """Rule-based stand-in. Understands the prompt *kinds* the agents send (each
    prompt starts with a `TASK:` line) and returns plausible structured output."""

    async def complete(self, model: str, system: str, prompt: str, json_mode: bool) -> LLMResult:
        task = _task_kind(prompt)
        text = _mock_answer(task, prompt) if json_mode else _mock_prose(task, prompt)
        return LLMResult(text=text, model="mock", tokens=len(prompt) // 4)

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "models": ["mock"], "note": "mock backend - no real model"}


def _task_kind(prompt: str) -> str:
    m = re.match(r"\s*TASK:\s*([a-z_\-]+)", prompt)
    return m.group(1) if m else "unknown"


def _mock_answer(task: str, prompt: str) -> str:
    # Classify on the owner's input only, never on the instruction text around it.
    text = prompt.split("INPUT:", 1)[-1].lower() if "INPUT:" in prompt else prompt.lower()
    if task == "classify_capture":
        kind = "task"
        if any(w in text for w in ("what if", "idea", "maybe we", "could we", "should we")):
            kind = "idea"
        elif any(w in text for w in ("goal", "target", "by end of", "reach ")):
            kind = "goal"
        elif any(w in text for w in ("blocked", "waiting on", "stuck", "can't proceed")):
            kind = "blocker"
        missing = []
        if "done" not in text and kind in ("task", "goal"):
            missing.append("What does done look like?")
        if not re.search(r"\b(by|before|deadline|due)\b", text) and kind in ("task", "goal"):
            missing.append("Is there a deadline?")
        if kind == "blocker" and "waiting on" not in text:
            missing.append("Who is this waiting on?")
        hint = None
        for m in re.finditer(r"([^,:\n]+?) \(id (proj_[a-z0-9]+)\)", prompt.split("INPUT:", 1)[0]):
            first_word = m.group(1).strip().split()[0].lower()
            if len(first_word) > 3 and first_word in text:
                hint = m.group(2)
                break
        return json.dumps({
            "kind": kind,
            "title": _title_from(prompt),
            "project_hint": hint,
            "questions": missing[:2],
            "confidence": 0.6,
        })
    if task == "link_tasks":
        return json.dumps({"links": []})
    if task == "assess_flag":
        return json.dumps({"flag": False, "reason": "mock: insufficient evidence"})
    return "{}"


def _mock_prose(task: str, prompt: str) -> str:
    return f"[mock {task}] " + prompt.split("\n", 1)[-1][:400].strip()


def _title_from(prompt: str) -> str:
    body = prompt.split("INPUT:", 1)[-1].strip()
    first = body.splitlines()[0] if body else "Untitled"
    return first[:80].rstrip(".")


class Gateway:
    def __init__(self) -> None:
        self.backend = OllamaBackend(settings.ollama_url) if settings.llm_backend == "ollama" else MockBackend()
        self.models = {"large": settings.model_large, "small": settings.model_small}

    async def complete(self, tier: Tier, system: str, prompt: str) -> LLMResult:
        return await self.backend.complete(self.models[tier], system, prompt, json_mode=False)

    async def complete_json(self, tier: Tier, system: str, prompt: str) -> tuple[dict[str, Any], LLMResult]:
        res = await self.backend.complete(self.models[tier], system, prompt, json_mode=True)
        return _parse_json(res.text), res

    async def health(self) -> dict[str, Any]:
        h = await self.backend.health()
        h["backend"] = settings.llm_backend
        h["tiers"] = self.models
        return h


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    return {}


gateway = Gateway()
