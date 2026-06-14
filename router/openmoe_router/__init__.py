"""openmoe-router: open-source MoE inference routing core."""

from .router import InferenceRouter, RouteCriteria, RoutingReceipt
from .providers import Provider, ProviderRegistry

__all__ = [
    "InferenceRouter",
    "RouteCriteria",
    "RoutingReceipt",
    "Provider",
    "ProviderRegistry",
]

__version__ = "0.1.0"
