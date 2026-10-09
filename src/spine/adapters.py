# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
"""Provider adapters — concrete Provider protocol implementations.

Every adapter is stateless: it receives explicit context, makes the call,
and returns a ProviderResult. The spine owns context; providers are workers.

Adapters:
  * LlamaCppProvider  — llama.cpp router (OpenAI-compatible) on :8830
  * OllamaProvider    — Ollama endpoint (OpenAI-compatible) — NOT tested live
  * OpenAIProvider    — Any OpenAI-compatible endpoint (Azure, etc.)
  * HuggingFaceProvider — HuggingFace Inference API (cloud)
  * HuggingFaceLocalProvider — Local transformers pipeline (offline)

Testing: llama.cpp adapter tested against live :8830.
         mock server for Ollama/OpenAI/HuggingFace (no live testing in this env).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .context import ContextFact
from .result import ProviderResult


def _context_to_messages(
    context: list[ContextFact], system: str = ""
) -> list[dict[str, str]]:
    """Flatten scoped context into OpenAI-style messages."""
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    for fact in sorted(context, key=lambda f: f.key):
        messages.append(
            {
                "role": "user",
                "content": f"[{fact.key}] {fact.value}",
            }
        )
    return messages


class LlamaCppProvider:
    """Adapter for llama.cpp's OpenAI-compatible router (:8830).

    Tested against the live instance on this machine.
    """

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8830",
        model: str = "Qwen3.5-9B-Q8_0",
    ) -> None:
        self.name = "llama.cpp"
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=120.0, trust_env=False)

    def list_models(self) -> list[str]:
        """Query the router's /v1/models."""
        resp = self.client.get(f"{self.endpoint}/v1/models")
        if resp.status_code != 200:
            return [self.model]
        data = resp.json()
        return [m["id"] for m in data.get("data", [])]

    def complete(
        self,
        prompt: str,
        context: list[ContextFact] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        context = context or []
        msgs = _context_to_messages(context)
        msgs.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        # Add tools if provided (OpenAI function calling format)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = self.client.post(
            f"{self.endpoint}/v1/chat/completions",
            json=payload,
        )

        if resp.status_code != 200:
            return ProviderResult(
                success=False,
                output="",
                provider=self.name,
                model=model or self.model,
                error_signal=1.0,
                finished_reason="error",
                metadata={"status_code": resp.status_code, "body": resp.text[:500]},
            )

        data = resp.json()
        output = ""
        tool_calls = []
        for choice in data.get("choices", []):
            delta = choice.get("delta", {})
            if "content" in delta:
                output += delta["content"]
            elif "reasoning_content" in delta:
                output += delta.get("reasoning_content", "")
            # Handle tool calls
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    tool_calls.append(tc)
            elif "message" in choice:
                # Handle message object (non-streaming)
                msg = choice["message"]
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        tool_calls.append(tc)
                if not output and "content" in msg:
                    output = msg["content"]
                elif not output and "reasoning_content" in msg:
                    output = msg.get("reasoning_content", "")

        if not output:
            output = data["choices"][0].get("message", {}).get("content", "")

        usage = data.get("usage", {})
        return ProviderResult(
            success=True,
            output=output,
            provider=self.name,
            model=model or self.model,
            error_signal=0.0,
            finished_reason=data["choices"][0].get("finish_reason", "completed"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            metadata={"raw": data},
            tool_calls=tool_calls,
        )

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """Request an embedding from the llama.cpp embeddings server (:8831)."""
        resp = self.client.post(
            "http://127.0.0.1:8831/v1/embeddings",
            json={"model": model, "input": text},
        )
        if resp.status_code == 200:
            embedding = resp.json().get("data", [{}])[0].get("embedding", [])
            return [float(x) for x in embedding]
        return []


class OllamaProvider:
    """Adapter for Ollama's OpenAI-compatible endpoint.

    BUILT per design. NOT tested live — Ollama is disabled on this machine
    (see standing rule: llama.cpp is the primary engine; :11434 stays free).
    Tested against a mock HTTP server.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:11434/v1",
        model: str = "qwen2.5-coder:32b",
    ) -> None:
        self.name = "ollama"
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=120.0, trust_env=False)

    def list_models(self) -> list[str]:
        resp = self.client.get(f"{self.endpoint}/models")
        if resp.status_code != 200:
            return [self.model]
        return [m["name"] for m in resp.json().get("models", [])]

    def complete(
        self,
        prompt: str,
        context: list[ContextFact] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        context = context or []
        msgs = _context_to_messages(context, system="You are a helpful assistant.")
        msgs.append({"role": "user", "content": prompt})

        payload = {
            "model": model or self.model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = self.client.post(
            f"{self.endpoint}/chat/completions",
            json=payload,
        )

        if resp.status_code != 200:
            return ProviderResult(
                success=False,
                output="",
                provider=self.name,
                model=model or self.model,
                error_signal=1.0,
                finished_reason="error",
                metadata={"status_code": resp.status_code},
            )

        data = resp.json()
        # Ollama returns either "message" (OpenAI-compatible) or "choices"
        msg = data.get("message", {})
        if not msg and data.get("choices"):
            msg = data["choices"][0].get("message", {})
        output = msg.get("content", "") or msg.get("reasoning_content", "")
        tool_calls = msg.get("tool_calls", [])
        usage = data.get("usage", {})
        return ProviderResult(
            success=True,
            output=output,
            provider=self.name,
            model=model or self.model,
            error_signal=0.0,
            finished_reason=data.get("done_reason", "completed"),
            usage={
                "prompt_tokens": usage.get("prompt_eval_count", 0),
                "completion_tokens": usage.get("eval_count", 0),
            },
            tool_calls=tool_calls,
        )

    def embed(self, text: str, model: str | None = None) -> list[float]:
        resp = self.client.post(
            f"{self.endpoint}/embed",
            json={"model": model or self.model, "input": text},
        )
        if resp.status_code == 200:
            embedding = resp.json().get("embedding", [])
            return [float(x) for x in embedding]
        return []


class OpenAIProvider:
    """Generic OpenAI-compatible provider (OpenAI, Azure, local, etc.)."""

    def __init__(
        self,
        endpoint: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "gpt-4o",
    ) -> None:
        self.name = "openai"
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.client = httpx.Client(
            timeout=120.0,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
        )

    def list_models(self) -> list[str]:
        resp = self.client.get(f"{self.endpoint}/models")
        if resp.status_code != 200:
            return [self.model]
        return [m["id"] for m in resp.json().get("data", [])]

    def complete(
        self,
        prompt: str,
        context: list[ContextFact] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        context = context or []
        msgs = _context_to_messages(context)
        msgs.append({"role": "user", "content": prompt})

        payload = {
            "model": model or self.model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = self.client.post(
            f"{self.endpoint}/chat/completions",
            json=payload,
        )

        if resp.status_code != 200:
            return ProviderResult(
                success=False,
                output="",
                provider=self.name,
                model=model or self.model,
                error_signal=1.0,
                finished_reason="error",
                metadata={"status_code": resp.status_code},
            )

        data = resp.json()
        message = data["choices"][0].get("message", {})
        output = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        usage = data.get("usage", {})
        return ProviderResult(
            success=True,
            output=output,
            provider=self.name,
            model=model or self.model,
            error_signal=0.0,
            finished_reason=data["choices"][0].get("finish_reason", "completed"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            tool_calls=tool_calls,
        )

    def embed(self, text: str, model: str | None = None) -> list[float]:
        resp = self.client.post(
            f"{self.endpoint}/embeddings",
            json={"model": model or self.model, "input": text},
        )
        if resp.status_code == 200:
            embedding = resp.json().get("data", [{}])[0].get("embedding", [])
            return [float(x) for x in embedding]
        return []


class HuggingFaceProvider:
    """Adapter for HuggingFace Inference API (OpenAI-compatible).

    Cloud endpoint: https://api-inference.huggingface.co/v1/chat/completions
    Supports any model served by HF Inference API.

    Tested against mock HTTP server.
    """

    def __init__(
        self,
        endpoint: str = "https://api-inference.huggingface.co/v1/chat/completions",
        model: str = "google/gemma-2b-it",
        api_key: str | None = None,
    ) -> None:
        self.name = "huggingface"
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("HF_API_KEY", "")
        self.client = httpx.Client(
            timeout=120.0,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
        )

    def list_models(self) -> list[str]:
        """HuggingFace Inference API does not list models via /v1/models endpoint.

        Returns the configured model name for compatibility.
        """
        return [self.model]

    def complete(
        self,
        prompt: str,
        context: list[ContextFact] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        context = context or []
        msgs = _context_to_messages(context)
        msgs.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = self.client.post(
            self.endpoint,
            json=payload,
            headers=headers if headers else None,
        )

        if resp.status_code != 200:
            return ProviderResult(
                success=False,
                output="",
                provider=self.name,
                model=model or self.model,
                error_signal=1.0,
                finished_reason="error",
                metadata={"status_code": resp.status_code, "body": resp.text[:500]},
            )

        data = resp.json()
        output = ""
        tool_calls = []
        for choice in data.get("choices", []):
            delta = choice.get("delta", {})
            if "content" in delta:
                output += delta["content"]
            elif "reasoning_content" in delta:
                output += delta.get("reasoning_content", "")
            # Handle tool calls
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    tool_calls.append(tc)
            elif "message" in choice:
                # Handle message object (non-streaming)
                msg = choice["message"]
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        tool_calls.append(tc)
                if not output and "content" in msg:
                    output = msg["content"]
                elif not output and "reasoning_content" in msg:
                    output = msg.get("reasoning_content", "")

        if not output:
            output = data["choices"][0].get("message", {}).get("content", "")

        usage = data.get("usage", {})
        return ProviderResult(
            success=True,
            output=output,
            provider=self.name,
            model=model or self.model,
            error_signal=0.0,
            finished_reason=data["choices"][0].get("finish_reason", "completed"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            metadata={"raw": data},
            tool_calls=tool_calls,
        )

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """Request an embedding from HF Inference API."""
        embed_endpoint = self.endpoint.replace("/chat/completions", "/embeddings")
        resp = self.client.post(
            embed_endpoint,
            json={"model": model or self.model, "input": text},
        )
        if resp.status_code == 200:
            embedding = resp.json().get("data", [{}])[0].get("embedding", [])
            return [float(x) for x in embedding]
        return []


class HuggingFaceLocalProvider:
    """Adapter for local HuggingFace transformers pipeline (offline).

    Uses transformers library locally — no network call.
    Requires transformers to be installed (pip install transformers).

    Tested against mock during development; end-to-end requires transformers.
    """

    def __init__(
        self,
        model: str = "google/gemma-2b-it",
        device: str = "auto",
    ) -> None:
        import transformers

        self.name = "huggingface_local"
        self.model_id = model
        self.device = device

        # Load pipeline — model name can be any HF model ID
        try:
            self.pipe = transformers.pipeline(
                "text-generation",
                model=model,
                device_map=device,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load transformers model '{model}': {e}"
            ) from e

    def list_models(self) -> list[str]:
        return [self.model_id]

    def complete(
        self,
        prompt: str,
        context: list[ContextFact] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        msgs = _context_to_messages(context or [])
        msgs.append({"role": "user", "content": prompt})

        outputs = self.pipe(
            msgs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            return_full_text=False,
        )

        output = str(outputs[0]["generated_text"])

        # Approximate token counts (simple char-based for local usage)
        prompt_text = msgs[-1]["content"] if msgs else prompt
        prompt_tokens = len(prompt_text) // 4  # rough approximation
        completion_tokens = len(output) // 4
        total_tokens = prompt_tokens + completion_tokens

        return ProviderResult(
            success=True,
            output=output.strip(),
            provider=self.name,
            model=model or self.model_id,
            error_signal=0.0,
            finished_reason="completed",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            metadata={"model_id": self.model_id},
            tool_calls=[],
        )

    def embed(
        self,
        text: str,
        model: str | None = None,
        *,
        allow_hash_fallback: bool = False,
    ) -> list[float]:
        import torch

        model_name = model or self.model_id
        # Use sentence-transformers if available, otherwise simple fallback
        try:
            from sentence_transformers import SentenceTransformer

            model_obj = SentenceTransformer(model_name)
            emb = model_obj.encode(text)
            return [float(x) for x in emb]
        except Exception:
            # Fallback: simple embedding via HF model if transformers available
            try:
                import transformers

                tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
                model_obj = transformers.AutoModel.from_pretrained(model_name)
                model_obj.eval()
                inputs = tokenizer(text, return_tensors="pt", truncation=True)
                with torch.no_grad():
                    outputs = model_obj(**inputs)
                    last_hidden = outputs.last_hidden_state
                    # Mean pooling over sequence dimension
                    emb = last_hidden.mean(dim=1).squeeze()
                    return [float(x) for x in emb.tolist()]
            except Exception:
                # No real embedding backend is available. The previous
                # fallback silently returned a pseudo-embedding built from
                # Python's salted hash() — not a semantic vector, and not
                # even deterministic across processes. Refuse loudly
                # unless the caller explicitly opted into the hash vector.
                if not allow_hash_fallback:
                    raise RuntimeError(
                        "No embedding backend available (sentence-transformers "
                        "and transformers both failed to load). Refusing to "
                        "return a pseudo-embedding; pass "
                        "allow_hash_fallback=True if a deterministic "
                        "non-semantic hash vector is really what you want."
                    ) from None
                import hashlib

                digest = hashlib.sha256(text.encode()).digest()
                return [b / 255.0 for b in digest] + [0.0] * 32
