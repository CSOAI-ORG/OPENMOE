"""Provider registry and model metadata for openmoe-router."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class Provider:
    """A model-provider endpoint that the router can dispatch to."""

    id: str
    name: str
    base_url: str
    models: tuple[str, ...]
    default_model: str | None = None
    cost_tier: str = "standard"  # budget | standard | premium
    capabilities: frozenset[str] = field(default_factory=frozenset)
    health_url: str | None = None
    api_key_env: str | None = None

    def supports(self, model: str) -> bool:
        return model in self.models or model == f"{self.id}/{self.default_model}"


class ProviderRegistry:
    """Live registry of inference providers."""

    def __init__(self, providers: Sequence[Provider] | None = None):
        self._providers: dict[str, Provider] = {
            p.id: p for p in (providers or _DEFAULT_PROVIDERS)
        }

    def add(self, provider: Provider) -> None:
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def list(self) -> list[Provider]:
        return list(self._providers.values())

    def providers_for_model(self, model: str) -> list[Provider]:
        matches: list[Provider] = []
        for p in self._providers.values():
            if p.supports(model):
                matches.append(p)
            elif model == "openmoe/auto":
                matches.append(p)
        return matches


# Stubs for well-known providers. Real keys are pulled from environment at runtime.
_DEFAULT_PROVIDERS = [
    Provider(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        models=("openai/gpt-4o", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat"),
        default_model="deepseek/deepseek-chat",
        cost_tier="standard",
        capabilities=frozenset({"chat", "tools", "vision"}),
        api_key_env="OPENROUTER_API_KEY",
    ),
    Provider(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        models=("deepseek-chat", "deepseek-reasoner"),
        default_model="deepseek-chat",
        cost_tier="budget",
        capabilities=frozenset({"chat", "reasoning"}),
        api_key_env="DEEPSEEK_API_KEY",
    ),
    Provider(
        id="kimi",
        name="Kimi (Moonshot)",
        base_url="https://api.moonshot.cn/v1",
        models=("kimi-k2-0711-preview", "kimi-k2-7", "kimi-latest"),
        default_model="kimi-k2-7",
        cost_tier="standard",
        capabilities=frozenset({"chat", "long-context", "tools"}),
        api_key_env="KIMI_API_KEY",
    ),
    Provider(
        id="minimax",
        name="MiniMax",
        base_url="https://api.minimax.chat/v1",
        models=("MiniMax-M3", "MiniMax-M2.7", "minimax-text-01"),
        default_model="MiniMax-M3",
        cost_tier="standard",
        capabilities=frozenset({"chat", "multimodal"}),
        api_key_env="MINIMAX_API_KEY",
    ),
    Provider(
        id="qwen",
        name="Qwen (Alibaba Cloud)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=("qwen3-235b-a22b", "qwen3-coder", "qwen2.5-72b-instruct"),
        default_model="qwen3-235b-a22b",
        cost_tier="budget",
        capabilities=frozenset({"chat", "coding", "tools"}),
        api_key_env="DASHSCOPE_API_KEY",
    ),
    Provider(
        id="local",
        name="Local vLLM/SGLang",
        base_url="http://localhost:8000/v1",
        models=("local/default",),
        default_model="local/default",
        cost_tier="budget",
        capabilities=frozenset({"chat", "sovereign"}),
    ),
]
