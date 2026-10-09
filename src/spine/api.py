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
    max_tokens: int = 512,
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

    import time as _time

    t0 = _time.time()
    result: ProviderResult = provider.complete(
        prompt=prompt,
        context=context,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    latency_ms = int((_time.time() - t0) * 1000)

    # The authoritative error signal is computed here, by the caller-side
    # gates (spine.gates) — never trusted from the adapter, whose own
    # error_signal is only a transport hint.
    from spine.gates import evaluate_result

    report = evaluate_result(result)
    error_signal = report.error_signal
    output = result.output or ""

    if error_signal == 0.0 and output:
        verdict = "commit"
        committed = True
    elif 0.0 < error_signal < 1.0:
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
        "gates": report.to_dict(),
        "latency_ms": latency_ms,
        "provider_result": result,
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

        # Scope names arrive as API input ("SESSION"); enum values are
        # lowercase. Normalize, and reject unknown scopes with a 400 —
        # previously the default itself raised an uncaught ValueError.
        try:
            scope_enum = ContextScope(scope.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown scope '{scope}'. "
                f"Valid: {[s.value for s in ContextScope]}",
            ) from None

        # Assemble in-scope context facts
        context_facts = store.visible_to(scope_enum)

        # Token-efficiency engine (ENGINE-SPEC-v1, as live in MyMilo):
        # two-tier, cache-stable assembly under a budget derived from the
        # route registry — never an unbounded context dump — and a
        # planned output cap instead of a hardcoded max_tokens.
        from spine.assembly import assemble_context
        from spine.tokenplan import (
            ContextOverflowError,
            estimate_tokens,
            plan_max_tokens,
            route_spec,
        )

        spec = route_spec(provider)
        summary_fact = next(
            (f for f in context_facts if f.key.startswith("session-summary:")),
            None,
        )
        summary_text: str | None = None
        summary_covers = 0
        assembly_facts = context_facts
        if summary_fact is not None:
            summary_text = str(summary_fact.value)
            assembly_facts = [f for f in context_facts if f is not summary_fact]
            origin = summary_fact.origin or ""
            if origin.startswith("compacted:"):
                try:
                    summary_covers = int(origin.split(":")[1])
                except (IndexError, ValueError):
                    summary_covers = 0

        budget = max(
            512,
            spec.context_window - spec.margin - spec.default_max_tokens,
        )
        assembly = assemble_context(
            assembly_facts,
            query=intent,
            summary=summary_text,
            summary_covers=summary_covers,
            budget_tokens=budget,
        )
        prompt = "\n\n".join(
            part for part in (assembly.text, f"Transform intent: {intent}") if part
        )
        estimated_input = assembly.estimated_tokens + estimate_tokens(intent) + 16
        try:
            planned_max = plan_max_tokens(spec, estimated_input)
        except ContextOverflowError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        # Run one gated cycle with the planned output cap
        result = _run_gated_cycle(
            provider, prompt, context_facts, max_tokens=planned_max
        )
        token_plan = {
            "route": spec.name,
            "context_window": spec.context_window,
            "estimated_input_tokens": estimated_input,
            "planned_max_tokens": planned_max,
            "facts_used": assembly.facts_used,
            "facts_dropped": assembly.facts_dropped,
        }

        # Record EVERY cycle in the CTST ledger — the ledger is the record
        # of transformation *attempts* (committed and rejected alike), with
        # the verdict, gate evidence, and telemetry attached. Before this,
        # only committed cycles were written, and they were written with
        # committed=False and no telemetry, so the ledger and the
        # /telemetry endpoint could never show what actually happened.
        if ctst_ledger:
            provider_result: ProviderResult = result["provider_result"]
            record = CTSTRecord(
                intent={"summary": intent, "provider": provider},
                context={f.key: f.value for f in context_facts},
                mechanism=provider,
                outcome={"output": result["output"]},
                assessment={
                    "verdict": result["verdict"],
                    "gates": result["gates"],
                },
                error_signal=result["error_signal"],
                committed=bool(result["committed"]),
                telemetry={
                    **provider_result.telemetry,
                    "latency_ms": result["latency_ms"],
                    "error_signal": result["error_signal"],
                    "estimated_input_tokens": token_plan["estimated_input_tokens"],
                    "planned_max_tokens": token_plan["planned_max_tokens"],
                    "context_window": token_plan["context_window"],
                },
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
            "gates": result["gates"],
            "token_plan": token_plan,
            "context_rendered": _render_context(scope_enum),
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
                # The authoritative error signal is the record's own field,
                # set by the gated cycle — not a copy inside telemetry.
                telemetry_by_provider[p]["error_signals"].append(r.error_signal)
                telemetry_by_provider[p]["count"] += 1

        # Compute aggregates
        agg: dict[str, Any] = {
            "providers": {},
            "total_ledger_entries": 0,
        }
        for provider, metrics in telemetry_by_provider.items():
            cs = metrics["count"]
            agg["providers"][provider] = {
                "prompt_tokens_avg": sum(metrics["prompt_tokens"])
                / len(metrics["prompt_tokens"])
                if metrics["prompt_tokens"]
                else 0,
                "completion_tokens_avg": sum(metrics["completion_tokens"])
                / len(metrics["completion_tokens"])
                if metrics["completion_tokens"]
                else 0,
                "total_tokens_avg": sum(metrics["total_tokens"])
                / len(metrics["total_tokens"])
                if metrics["total_tokens"]
                else 0,
                "avg_error_signal": sum(metrics["error_signals"])
                / len(metrics["error_signals"])
                if metrics["error_signals"]
                else 0,
                "runs": cs,
            }
            agg["total_ledger_entries"] += cs

        return agg

    return app


# Module-level FastAPI app (created at import time for convenience)
app = create_app()
