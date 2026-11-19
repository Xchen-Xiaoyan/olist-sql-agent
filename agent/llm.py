"""Tool-calling chat backends. Select with env LLM_PROVIDER = gemini | ollama.

Messages use one neutral format so the agent loop does not care which backend runs:
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "args"}], "raw": backend-specific}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


class ChatLLM:
    name = "base"

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        """Return {"content": str, "tool_calls": [...], "raw": ..., "elapsed": seconds spent in the model call}."""
        raise NotImplementedError


class GeminiChat(ChatLLM):
    """Google Gemini (free-tier key from https://aistudio.google.com/apikey) with function calling."""

    def __init__(self, model: str | None = None, fallbacks: list[str] | None = None, retries: int = 5):
        from google import genai
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        # Free-tier quotas are per model, so a fallback chain multiplies the daily budget.
        self.fallbacks = fallbacks if fallbacks is not None else [m.strip() for m in os.getenv(
            "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3.5-flash-lite").split(",") if m.strip()]
        self.retries = retries
        self.name = f"gemini/{self.model}"
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=genai.types.HttpOptions(
            timeout=int(os.getenv("GEMINI_TIMEOUT_MS", "60000")),
            retry_options=genai.types.HttpRetryOptions(attempts=1)))

    def _contents(self, messages):
        from google.genai import types
        out = []
        for m in messages:
            if m["role"] == "user":
                out.append(types.Content(role="user", parts=[types.Part(text=m["content"])]))
            elif m["role"] == "assistant":
                # Replay the model's own turn verbatim: Gemini 3 needs its thought signatures back.
                out.append(types.Content.model_validate(m["raw"]) if m.get("raw") else
                           types.Content(role="model", parts=[types.Part(text=m["content"] or " ")]))
            elif m["role"] == "tool":
                part = types.Part.from_function_response(name=m["name"], response={"result": m["content"]})
                if out and out[-1].role == "user" and out[-1].parts and out[-1].parts[0].function_response:
                    out[-1].parts.append(part)  # parallel calls: all responses go in one turn
                else:
                    out.append(types.Content(role="user", parts=[part]))
        return out

    _sent: dict = {}
    _pace_lock = threading.Lock()

    def _pace(self, model):
        """Stay under the free tier's requests-per-minute limit (GEMINI_RPM, default 14) for each model."""
        rpm = int(os.getenv("GEMINI_RPM", "14"))
        with self._pace_lock:
            sent = [t for t in self._sent.get(model, []) if time.time() - t < 60]
            if len(sent) >= rpm:
                time.sleep(60 - (time.time() - sent[0]) + 0.5)
                sent = sent[1:]
            self._sent[model] = sent + [time.time()]

    def _call(self, model, system, messages, tools):
        from google.genai import types
        self._pace(model)
        t0 = time.time()
        decl = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                          parameters_json_schema=t["parameters"]) for t in tools]
        r = self.client.models.generate_content(
            model=model, contents=self._contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=0.0, tools=[types.Tool(function_declarations=decl)],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
        content = r.candidates[0].content if r.candidates and r.candidates[0].content else None
        calls = [{"id": fc.id or uuid.uuid4().hex[:8], "name": fc.name, "args": dict(fc.args or {})}
                 for fc in (r.function_calls or [])]
        text = "".join(p.text for p in (content.parts or []) if p.text and not p.thought) if content else ""
        return {"content": text, "tool_calls": calls,
                "raw": content.model_dump(mode="json", exclude_none=True) if content else None, "model": model,
                "elapsed": time.time() - t0}

    def chat(self, system, messages, tools):
        from google.genai import errors
        last = None
        for model in [self.model, *self.fallbacks]:
            for attempt in range(self.retries):
                try:
                    return self._call(model, system, messages, tools)
                except errors.APIError as e:
                    last = e
                    if e.code not in (429, 500, 503, 504):
                        raise
                    if e.code == 504 or (e.code == 429 and "PerDay" in str(e)):
                        break  # this model's daily quota is gone or it timed out: try the next model
                    # Per-minute limits say how long to wait ("retryDelay"); otherwise back off.
                    delay = re.search(r"retry in ([\d.]+)s", str(e))
                    time.sleep(float(delay.group(1)) + 1 if delay else 2 ** attempt * 2)
                except Exception as e:  # noqa: BLE001 - client-side timeouts surface as httpx errors
                    last = e
                    if "timeout" not in type(e).__name__.lower():
                        raise
                    break
        raise RuntimeError(f"Gemini unavailable on all models: {last}")


class OllamaChat(ChatLLM):
    """Local model served by Ollama with native tool calling, e.g. `ollama pull qwen2.5:7b`."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.name = f"ollama/{self.model}"

    def chat(self, system, messages, tools):
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                msgs.append({"role": "assistant", "content": m["content"] or "",
                             "tool_calls": [{"function": {"name": c["name"], "arguments": c["args"]}}
                                            for c in m.get("tool_calls", [])]})
            elif m["role"] == "tool":
                msgs.append({"role": "tool", "tool_name": m["name"], "content": m["content"]})
            else:
                msgs.append({"role": "user", "content": m["content"]})
        payload = {"model": self.model, "stream": False, "messages": msgs,
                   "tools": [{"type": "function", "function": t} for t in tools],
                   "options": {"temperature": 0, "num_ctx": 16384, "seed": 0}}
        t0 = time.time()
        req = urllib.request.Request(f"{self.host}/api/chat", json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            msg = json.loads(r.read())["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            args = c["function"].get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append({"id": uuid.uuid4().hex[:8], "name": c["function"]["name"], "args": args})
        return {"content": msg.get("content", ""), "tool_calls": calls, "raw": None, "model": self.model,
                "elapsed": time.time() - t0}


class CachedChat(ChatLLM):
    """SQLite response cache keyed on the full conversation: eval reruns are free and resumable."""

    def __init__(self, inner: ChatLLM, path: Path):
        self.inner, self.name = inner, inner.name
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, response TEXT)")
        self.lock = threading.Lock()

    def chat(self, system, messages, tools):
        # Tool-call ids are random, so leave them (and raw replays) out of the key.
        stable = [{k: v for k, v in m.items() if k not in ("raw", "tool_call_id")} |
                  ({"tool_calls": [{"name": c["name"], "args": c["args"]} for c in m["tool_calls"]]}
                   if m.get("tool_calls") else {}) for m in messages]
        key = hashlib.sha256(json.dumps([self.name, system, stable, tools], ensure_ascii=False,
                                        sort_keys=True, default=str).encode()).hexdigest()
        with self.lock:
            row = self.db.execute("SELECT response FROM cache WHERE key = ?", (key,)).fetchone()
        if row:
            return json.loads(row[0]) | {"cached": True}
        out = self.inner.chat(system, messages, tools)
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?)", (key, json.dumps(out, default=str)))
            self.db.commit()
        return out


def get_llm(provider: str | None = None, cache: Path | None = None, **kw) -> ChatLLM:
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()
    llm = GeminiChat(**kw) if provider == "gemini" else OllamaChat(**kw)
    return CachedChat(llm, cache) if cache else llm
