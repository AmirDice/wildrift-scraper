"""LLM observability for the build advisor (Langfuse).

What it records
---------------
One TRACE per advisor request (a build, a counter build, a rune page, a site
agent answer), and inside it one GENERATION per model call. A single build is
several calls -- tournament candidates, the judge, authoring, repairs, now and
then a full regeneration -- and until now the only view of that was a token
tally per request. Each generation carries:

  - the stage (author / judge / repair / regenerate / tournament / runes /
    site_agent), so "which stage is slow or expensive" is a filter, not a
    guess from thinking levels;
  - model, thinking level, temperature;
  - input, output, reasoning and cached tokens (Langfuse prices them);
  - latency, and every failed attempt as an ERROR-level generation, so
    retries and 429 backoff show up instead of hiding inside one slow call.

Langfuse v3 is built on OpenTelemetry, so the trace context is a ContextVar:
the best-of runner's worker threads (started with copy_context().run) land
inside the request's trace without being passed anything.

Inert unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set, and an
optional import, so local runs and tests need nothing new. LANGFUSE_HOST
defaults to the EU region (cloud.langfuse.com). Observability must never
break a generation: every Langfuse call here is wrapped.

Privacy: build prompts are game data. Site agent questions are free text a
visitor typed, so those are recorded truncated, and no visitor identifier
(IP, account, session cookie) is ever sent -- the advisor does not have one.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import sys
from typing import Any, Iterator

_PUBLIC = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
_SECRET = os.environ.get("LANGFUSE_SECRET_KEY", "")
ENABLED = bool(_PUBLIC and _SECRET)

# Prompts run to tens of thousands of characters (the item catalogue is in
# them). Langfuse stores them fine, but there is no reason to ship 60KB per
# call; the head and tail are where the request-specific part is.
MAX_TEXT = int(os.environ.get("LANGFUSE_MAX_TEXT", "20000"))

_STAGE: contextvars.ContextVar[str] = contextvars.ContextVar("advisor_stage", default="")

_client = None
_client_failed = False


def _get():
    """The Langfuse client, created on first use; None when disabled."""
    global _client, _client_failed
    if not ENABLED or _client_failed:
        return None
    if _client is None:
        try:
            from langfuse import Langfuse
            _client = Langfuse(
                public_key=_PUBLIC,
                secret_key=_SECRET,
                host=os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com",
                environment=(os.environ.get("VERCEL_ENV") or "development"),
                release=(os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:12] or None,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[observability] Langfuse disabled: {exc}", file=sys.stderr)
            _client_failed = True
            return None
    return _client


def clip(text: Any, limit: int = 0) -> Any:
    limit = limit or MAX_TEXT
    if isinstance(text, str) and len(text) > limit:
        half = limit // 2
        return f"{text[:half]}\n...[{len(text) - limit} chars clipped]...\n{text[-half:]}"
    return text


@contextlib.contextmanager
def stage(name: str) -> Iterator[None]:
    """Label every model call made inside this block with a stage name."""
    token = _STAGE.set(name)
    try:
        yield
    finally:
        _STAGE.reset(token)


def current_stage(default: str = "author") -> str:
    return _STAGE.get() or default


class _Null:
    """Stands in for a span/generation when tracing is off or failed."""

    def update(self, **_: Any) -> None:
        return None

    def update_trace(self, **_: Any) -> None:
        return None


@contextlib.contextmanager
def request_trace(name: str, *, input: Any = None, tags: list[str] | None = None,
                  metadata: dict | None = None) -> Iterator[Any]:
    """Root span for one advisor request. Does NOT flush: the caller sends
    the response first and then calls flush(), so a slow Langfuse never adds
    latency to a build the player is waiting for."""
    client = _get()
    if client is None:
        yield _Null()
        return
    try:
        cm = client.start_as_current_span(name=name, input=input, metadata=metadata)
        span = cm.__enter__()
        span.update_trace(name=name, tags=tags or [], input=input, metadata=metadata)
    except Exception as exc:  # noqa: BLE001
        print(f"[observability] trace start failed: {exc}", file=sys.stderr)
        yield _Null()
        return
    exc_info = (None, None, None)
    try:
        yield span
    except BaseException:
        exc_info = sys.exc_info()
        with contextlib.suppress(Exception):
            span.update(level="ERROR", status_message=str(exc_info[1])[:500])
        raise
    finally:
        with contextlib.suppress(Exception):
            cm.__exit__(*exc_info)


def flush() -> None:
    """Send buffered traces. Call AFTER the response is written: the
    serverless function can be frozen once it returns, losing anything
    still buffered."""
    client = _get() if ENABLED else None
    if client is not None:
        with contextlib.suppress(Exception):
            client.flush()


@contextlib.contextmanager
def generation(*, model: str, prompt: str, system: str = "", thinking_level: str = "",
               attempt: int = 0, temperature: float | None = None) -> Iterator[Any]:
    """One model call. The caller reports usage and output via record()."""
    client = _get()
    if client is None:
        yield _Null()
        return
    name = current_stage()
    try:
        cm = client.start_as_current_generation(
            name=name,
            model=model,
            input=[
                *([{"role": "system", "content": clip(system, 4000)}] if system else []),
                {"role": "user", "content": clip(prompt)},
            ],
            model_parameters={
                k: v for k, v in {
                    "thinking_level": thinking_level or None,
                    "temperature": temperature,
                }.items() if v is not None
            },
            metadata={"stage": name, "attempt": attempt},
        )
        gen = cm.__enter__()
    except Exception as exc:  # noqa: BLE001
        print(f"[observability] generation start failed: {exc}", file=sys.stderr)
        yield _Null()
        return
    exc_info = (None, None, None)
    try:
        yield gen
    except BaseException:
        exc_info = sys.exc_info()
        with contextlib.suppress(Exception):
            gen.update(level="ERROR", status_message=str(exc_info[1])[:500])
        raise
    finally:
        with contextlib.suppress(Exception):
            cm.__exit__(*exc_info)


def record(gen: Any, response: Any = None, *, output: Any = None) -> None:
    """Attach Gemini usage metadata and the output to a generation."""
    try:
        usage: dict[str, int] | None = None
        breakdown: dict[str, int] = {}
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            def n(attr: str) -> int:
                return int(getattr(meta, attr, 0) or 0)
            prompt, answer, thoughts = n("prompt_token_count"), n("candidates_token_count"), n("thoughts_token_count")
            # Gemini bills thinking tokens at the output rate but reports them
            # apart from the answer. Langfuse prices the "input" and "output"
            # keys and sums every key into the total, so thoughts go INTO
            # output (or the cost is understated) and the split goes to
            # metadata (or the total would count them twice).
            usage = {"input": prompt, "output": answer + thoughts, "total": prompt + answer + thoughts}
            breakdown = {"answer_tokens": answer, "thinking_tokens": thoughts,
                         "cached_tokens": n("cached_content_token_count")}
        gen.update(output=clip(output if output is not None else getattr(response, "text", None)),
                   usage_details=usage,
                   metadata=breakdown or None)
    except Exception:  # noqa: BLE001
        pass
