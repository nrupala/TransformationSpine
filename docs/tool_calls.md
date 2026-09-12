# Tool-Call Abstraction

TransformationSpine supports OpenAI-style function calling via the `tool_calls` field on `ProviderResult`. This enables the spine to orchestrate multi-step workflows where the model can request external tool execution.

## Architecture

```
Provider.complete(prompt, tools=[...])
        │
        ▼
  ProviderResult.tool_calls  ← list of tool call dicts
        │
        ▼
  Spine executes tool, passes result back
        │
        ▼
  Provider.complete(prompt, tool_results=...)
```

## ProviderResult Schema

```python
@dataclass
class ProviderResult:
    success: bool
    output: str
    provider: str
    model: str
    error_signal: float = 1.0
    finished_reason: str = "completed"
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = ""
    telemetry: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
```

## Tool Definition Format

Tools follow the OpenAI function calling schema:

```json
{
  "type": "function",
  "function": {
    "name": "search",
    "description": "Search for information",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "Search query"}
      },
      "required": ["query"]
    }
  }
}
```

## Tool Call Response Format

When a provider returns tool calls, they appear in `ProviderResult.tool_calls`:

```json
[
  {
    "id": "call_abc123",
    "name": "search",
    "arguments": {
      "query": "transformation spine"
    }
  }
]
```

## Adapters Supporting Tool Calls

All OpenAI-compatible adapters (LlamaCppProvider, OpenAIProvider, OllamaProvider, HuggingFaceProvider) support tool calls:

```python
provider = LlamaCppProvider()
tools = [{
    "type": "function",
    "function": {
        "name": "compute",
        "description": "Compute a mathematical expression",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            }
        }
    }
}]

result = provider.complete(
    prompt="What is 2+2?",
    context=[],
    tools=tools,
)

if result.tool_calls:
    for call in result.tool_calls:
        # Execute the tool
        tool_result = execute_tool(call["name"], call["arguments"])
        # Pass back to provider
        result = provider.complete(
            prompt="Continue with result",
            context=[],
            tools=tools,
            tool_results=[{"call_id": call["id"], "result": tool_result}],
        )
```

## Backward Compatibility

The `tool_calls` field defaults to an empty list, so existing code that doesn't use tools continues to work without modification.

## Testing

Run the tool-call tests:

```bash
python -m pytest tests/test_tool_calls.py -v
```