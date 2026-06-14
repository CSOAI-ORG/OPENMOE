# openmoe-router

**Open-source Mixture-of-Experts inference router for the charcoal era.**

`openmoe-router` is the flagship routing core of the OpenMoE stack. It sits
between agents / applications and a growing fleet of model providers,
routing each request to the cheapest, fastest, or highest-quality expert
that satisfies the caller's constraints. It is designed to be:

- **Provider-agnostic** — plug in OpenRouter, DeepSeek, Kimi, MiniMax, Qwen,
  local vLLM / SGLang, or any OpenAI-compatible endpoint.
- **Cost-first** — optimize for token cost while holding quality and latency
  guards.
- **MCP-native** — expose routing, benchmarks, and provider health as MCP
  tools so agents can negotiate inference contracts.
- **BFT-safe** — optionally wrap routing decisions in `openmoe-bft` consensus
  so no single router bug can misroute a high-stakes request.

## Quickstart

```bash
cd router
pip install -e ".[dev]"
python -m openmoe_router --help
```

Run a local routing server:

```bash
python -m openmoe_router.server --port 8100
```

Route a chat completion:

```bash
curl -s http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openmoe/auto",
    "messages": [{"role": "user", "content": "Hello"}],
    "criteria": {"optimize": "cost"}
  }'
```

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────────────┐
│  Agent /    │────▶│  openmoe-router  │────▶│  Provider fleet             │
│  App        │     │  (rank + route)  │     │  DeepSeek · Kimi · MiniMax  │
└─────────────┘     └──────────────────┘     │  Qwen · OpenRouter · Local  │
                                             └─────────────────────────────┘
```

The router maintains a live provider registry. For each request it:

1. Filters providers by model availability, capability tags, and SLA.
2. Scores the remainder by the requested criterion (`cost`, `latency`, `quality`).
3. Optionally runs a BFT consensus round across router replicas.
4. Proxies the request and returns the response with a routing receipt.

## Provider registry

Providers are declared in `openmoe_router/providers.yaml` or via environment
variables. Each entry specifies base URL, model list URL, default model, and
cost tier.

## License

Apache-2.0 — same as `openmoe-bft`.
