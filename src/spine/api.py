"""TransformationSpine FastAPI application.

The spine API orchestrates the closed-loop control cycle:

  PLANNED → DISPATCHED → PROVISIONAL → COMMITTED
  (or → REJECTED → RETRY/ROLLBACK)

Core loop (per spec 01):
1. Assembles in-scope context from the ContextStore
2. Routes to a provider via RouterRule
3. Executes the provider's complete() method
4. Runs gated verification (compile, test, lint, schema, smoke)
5. Computes error signal
6. Commits or rolls back, writes CTST entry, updates current state

Endpoints:
  POST /api/v1/transform    — submit a transformation intent
  GET  /api/v1/context      — render in-scope context for a prompt
  GET  /api/v1/ledger       — read CTST journal
  GET  /api/v1/status       — system health
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from spine import ContextScope
from spine.adapters import LlamaCppProvider
from spine.ctst import CTSTRecord
from spine.oplog import get_logger
from spine.oplog import log as oplog
from spine.result import ProviderResult

# ── Runtime state ──────────────────────────────────────────────────────

store: Any = None  # ContextStore — initialized in lifespan
ctst_ledger: Any = None  # CTSTLedger — initialized in lifespan
provider_map: dict[str, Any] = {}  # name → Provider instance


# ── Helper functions ─────────────────────────────────────────────────


def _render_context(scope: Any = None) -> str:
    """Render in-scope context as a prompt block (deterministic ordering)."""
    if store is None:
        return "# No context assembled"
    # Use the store's visible_to which already filters by scope
    facts = store.visible_to(scope or __import__("spine").ContextScope.SESSION)
    return "\n\n".join(
        f"#{f.key} [{f.scope}] (origin: {f.origin or 'unknown'})"
        f"\n{f.value}"
        for f in facts
    )


def _run_gated_cycle(
    provider_name: str,
    prompt: str,
    context: Any,
) -> dict[str, Any]:
    """Run one gated transformation cycle against a registered provider.

    Returns dict with: output, error_signal, verdict, committed, reason.
    """
    provider = provider_map.get(provider_name)
    if provider is None:
        return {
            "output": "",
            "error_signal": 1.0,
            "verdict": "error",
            "committed": False,
            "reason": f"Provider '{provider_name}' not registered",
        }

    result: ProviderResult = provider.complete(
        prompt=prompt,
        context=context,
        max_tokens=512,
        temperature=0.0,
    )

    error_signal = result.error_signal
    output = result.output or ""

    # Simple gate: error_signal must be 0.0 (converged) and output non-empty
    # to count as committed. In production this would call pytest/ruff/etc.
    if error_signal == 0.0 and output:
        verdict = "commit"
        committed = True
    elif error_signal > 0.0 and error_signal < 1.0:
        verdict = "retry"
        committed = False
    else:
        verdict = "rollback"
        committed = False

    return {
        "output": output,
        "error_signal": error_signal,
        "verdict": verdict,
        "committed": committed,
        "reason": f"error_signal={error_signal:.3f}, provider={provider_name}",
    }


# ── Lifespan ─────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: Any) -> Any:
    global store, ctst_ledger, provider_map

    # Import the package modules after app starts to avoid circular deps
    from spine.ctst import CTSTLedger  # noqa: F811
    from spine.store import ContextStore  # noqa: F811

    # Initialize context store (durable backing: PROJECT/PERSISTENT facts
    # survive restarts; path overridable via SPINE_CONTEXT_PATH) and ledger.
    store = ContextStore(
        path=os.environ.get("SPINE_CONTEXT_PATH", "spine-context.json")
    )
    ctst_ledger = CTSTLedger()

    # Register LlamaCppProvider (connects to :8830 OpenAI-compatible router)
    op_logger = get_logger("spine")
    oplog(op_logger, "spine starting")
    try:
        # Default: Qwen3.5-9B-Q8_0 — verified tool-capable (structured
        # tool_calls, finish_reason=tool_calls) per the 2026-09-13 local
        # tool-call smoke test. Qwen2.5-Coder models emit pseudo-XML tool
        # calls as plain content on this route and are NOT tool-compatible.
        llm_provider = LlamaCppProvider(
            endpoint=os.environ.get("SPINE_LLAMA_ENDPOINT", "http://127.0.0.1:8830"),
            model=os.environ.get("SPINE_LLAMA_MODEL", "Qwen3.5-9B-Q8_0"),
        )
        models = llm_provider.list_models()
        if models:
            provider_map["llama.cpp"] = llm_provider
            oplog(op_logger, "provider registered",
                  provider="llama.cpp", models=len(models))
        else:
            oplog(op_logger, "llama.cpp handshake: no models returned", level=30,
                  provider="llama.cpp")
    except Exception as e:
        oplog(op_logger, "could not connect to llama.cpp", level=40,
              provider="llama.cpp", error=str(e))

    # Register OpenAIProvider only if OPENAI_API_KEY is set
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            from spine.adapters import OpenAIProvider  # noqa: F811
            oa_provider = OpenAIProvider(api_key=api_key)
            provider_map["openai"] = oa_provider
            print("[spine] Registered OpenAIProvider")
        except Exception as e:
            print(f"[spine] Could not register OpenAIProvider: {e}")

    yield  # app runs

    # Cleanup
    store = None
    ctst_ledger = None
    provider_map.clear()


# ── FastAPI application factory ──────────────────────────────────────


def create_app() -> FastAPI:
    """Factory for the spine FastAPI application."""
    app = FastAPI(
        title="Transformation Spine API",
        version="0.1.0",
        description="Provider-neutral orchestration spine with outcome convergence",
        lifespan=lifespan,
    )

    op_logger = get_logger("spine")
    oplog(op_logger, "spine api created")

    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next: Any) -> Any:
        import time as _time
        import uuid as _uuid

        rid = _uuid.uuid4().hex[:12]
        t0 = _time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            oplog(op_logger, "unhandled exception", level=40, request_id=rid,
                  method=request.method, path=request.url.path, error=str(e))
            raise
        dur_ms = int((_time.time() - t0) * 1000)
        response.headers["X-Request-Id"] = rid
        oplog(op_logger, "access", request_id=rid, method=request.method,
              path=request.url.path, status=response.status_code, duration_ms=dur_ms)
        return response

    @app.get("/api/v1/status")
    async def status() -> dict[str, Any]:
        """Health+status endpoint."""
        providers = list(provider_map.keys()) if provider_map else []
        return {
            "status": "ok",
            "providers": providers,
            "context_size": len(store.visible_to(ContextScope.SESSION)) if store else 0,
            "ledger_entries": len(ctst_ledger.read()) if ctst_ledger else 0,
        }

    @app.get("/api/v1/context")  # noqa: F821
    async def context_endpoint() -> JSONResponse:
        """Render the in-scope context as a prompt block."""
        if store is None:
            raise HTTPException(status_code=503, detail="Spine not initialized")
        return JSONResponse(content={"context": _render_context(ContextScope.SESSION)})

    @app.post("/api/v1/transform")
    async def transform(
        intent: str,
        provider: str = "llama.cpp",
        scope: str = "SESSION",
    ) -> dict[str, Any]:
        """Submit a transformation intent and execute the gated cycle.

        Args:
            intent: What to accomplish (user description).
            provider: Which Provider adapter to use (registered in lifespan).
            scope: Context scope to assemble for the prompt.

        Returns:
            Dict with output, error_signal, verdict, committed flag, and
            the rendered context.
        """
        if provider not in provider_map:
            available = list(provider_map.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider}' not available. "
                f"Available: {available}",
            )

        if store is None:
            raise HTTPException(status_code=503, detail="Spine not initialized")

        # Assemble in-scope context facts
        context_facts = store.visible_to(ContextScope(scope))

        # Build a prompt from those facts + the user's intent
        prompt_parts = [
            "\n".join(f"- {f.key}: {f.value}" for f in context_facts),
            "",
            f"Transform intent: {intent}",
        ]
        prompt = "\n".join(part for part in prompt_parts if part)

        # Run one gated cycle
        result = _run_gated_cycle(provider, prompt, context_facts)

        # If the cycle committed, record a CTST entry
        if ctst_ledger and result["committed"]:
            record = CTSTRecord(
                intent={"summary": intent, "provider": provider},
                context={f.key: f.value for f in context_facts},
                mechanism=provider,
                error_signal=result["error_signal"],
            )
            ctst_ledger.append(record)

        return {
            "intent": intent,
            "provider": provider,
            "scope": scope,
            "output": result["output"],
            "error_signal": result["error_signal"],
            "verdict": result["verdict"],
            "committed": result["committed"],
            "context_rendered": _render_context(ContextScope(scope)),
        }

    @app.get("/api/v1/ledger")
    async def ledger() -> dict[str, Any]:
        """Read all CTST journal entries (append-only)."""
        if ctst_ledger is None:
            raise HTTPException(status_code=503, detail="Spine not initialized")
        records = ctst_ledger.read()
        return {"records": [r.to_dict() for r in records]}

    @app.get("/api/v1/ledger/verify")
    async def ledger_verify() -> dict[str, Any]:
        """Verify the CTST hash chain from what is stored on disk."""
        if ctst_ledger is None:
            raise HTTPException(status_code=503, detail="Spine not initialized")
        return {
            "valid": ctst_ledger.verify_chain(),
            "head_hash": ctst_ledger.head_hash,
            "records": len(ctst_ledger.query()),
        }

    @app.get("/api/v1/telemetry")
    async def telemetry_endpoint() -> dict[str, Any]:
        """Aggregated telemetry: provider latency, usage, convergence metrics."""
        telemetry_by_provider: dict[str, dict[str, Any]] = {}
        if ctst_ledger is not None:
            records = ctst_ledger.read()
            for r in records:
                # We store ProviderResult dict via r.to_dict(); parse telemetry
                data = r.to_dict()
                t = data.get("telemetry", {})
                p = data.get("mechanism", "unknown")
                if p not in telemetry_by_provider:
                    telemetry_by_provider[p] = {
                        "prompt_tokens": [],
                        "completion_tokens": [],
                        "total_tokens": [],
                        "error_signals": [],
                        "count": 0,
                    }
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    if k in t and t[k] is not None:
                        telemetry_by_provider[p][k].append(t[k])
                if "error_signal" in t:
                    telemetry_by_provider[p]["error_signals"].append(t["error_signal"])
                telemetry_by_provider[p]["count"] += 1

        # Compute aggregates
        agg: dict[str, Any] = {
            "providers": {},
            "total_ledger_entries": 0,
        }
        for provider, metrics in telemetry_by_provider.items():
            cs = metrics["count"]
            agg["providers"][provider] = {
                "prompt_tokens_avg": sum(metrics["prompt_tokens"]) / cs
                if metrics["prompt_tokens"]
                else 0,
                "completion_tokens_avg": sum(metrics["completion_tokens"]) / cs
                if metrics["completion_tokens"]
                else 0,
                "total_tokens_avg": sum(metrics["total_tokens"]) / cs
                if metrics["total_tokens"]
                else 0,
                "avg_error_signal": sum(metrics["error_signals"]) / cs
                if metrics["error_signals"]
                else 0,
                "runs": cs,
            }
            agg["total_ledger_entries"] += cs

        return agg

    return app


# Module-level FastAPI app (created at import time for convenience)
app = create_app()
