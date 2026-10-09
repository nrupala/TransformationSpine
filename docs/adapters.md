# Adapters

Provider adapters live in `src/spine/adapters.py`. Every adapter
implements the `Provider` protocol (`src/spine/provider.py`):
`list_models()`, `complete(...) -> ProviderResult`, `embed(...)`.

| Adapter | Name | Transport | Notes |
|---|---|---|---|
| `LlamaCppProvider` | `llama.cpp` | OpenAI-compatible HTTP (`/v1`) | Default local route. Client built with `trust_env=False` so proxy env vars can never reroute localhost inference. |
| `OllamaProvider` | `ollama` | OpenAI-compatible HTTP (`/v1`) | Local models via Ollama. Also `trust_env=False`. |
| `OpenAIProvider` | `openai` | OpenAI API | Also used as the shim for Anthropic's endpoint. Key from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. |
| `HuggingFaceProvider` | `huggingface` | HF Inference API | Bearer auth from `HF_API_KEY`. |
| `HuggingFaceLocalProvider` | `huggingface_local` | transformers pipeline (local) | Needs the `local` extra. `embed()` refuses to fabricate vectors: with no embedding backend it raises unless `allow_hash_fallback=True` is passed explicitly (the fallback is a deterministic SHA-256 vector, not a semantic embedding). |

## Rules

- Adapters report `usage` (token counts) on every result; telemetry is
  derived from it centrally (`ProviderResult.__post_init__`).
- An adapter's own `error_signal` is a transport hint only. The
  authoritative signal is computed by the caller-side gates
  (`spine.gates.evaluate_result`) — never by the model.
- Tool definitions are passed through in OpenAI function format;
  returned `tool_calls` are executed by `spine.tools`, not adapters.

## Creating providers

Don't instantiate adapters by hand in application code. Use
`spine.factory.build_provider_map(profile, providers_yaml_data)`,
which honors profiles, credentials, and canonical provider names.
