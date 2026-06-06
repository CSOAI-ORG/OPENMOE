"""Cleanroom sparse Mixture-of-Experts router (OpenMoE-BFT Empire, Layer 1).

This module is a **from-the-paper reimplementation** of the OpenMoE sparse
router and the standard Switch / GShard top-k gating it builds on. It contains
**no code** copied from the upstream ``XueFuzhao/OpenMoE`` repository (that
repository ships no license file, so all rights are reserved); everything here
is written directly from the published equations.

References
----------
- Lepikhin et al., 2020, *GShard* — top-2 token-choice gating with capacity.
- Fedus, Zoph & Shazeer, 2022, *Switch Transformers* — top-1 gating and the
  auxiliary load-balancing loss ``L = N * sum_i f_i * P_i``.
- Shazeer et al., 2017, *Outrageously Large Neural Networks* — the original
  sparsely-gated MoE layer and **noisy** top-k gating.
- Xue et al., 2024, *OpenMoE* (arXiv:2402.01739) — the open MoE LLM whose router
  this layer reconstructs.

Empire context
--------------
This is **Layer 1 (base-model routing)** of the 12-layer OpenMoE-BFT Empire: the
ordinary sparse gate that an MoE language model uses to pick experts per token.
The **BFT layer** (:mod:`openmoe_bft.bft` / :mod:`openmoe_bft.routing`) sits
*above* this layer to make the routing decision Byzantine-robust — instead of
trusting one router, N router replicas each run this gate and a ``2f+1`` quorum
must agree. :mod:`openmoe_bft.aggregators` provides the robust numeric fusion of
multiple routers' logit vectors before this gate is even applied. In short:
OpenMoE built the brain (this module); the Empire adds the conscience.

Stdlib only — no numpy, no torch. The :mod:`math` module is the only import.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# A per-token routing assignment: list of (expert_index, gate_weight) pairs.
Assignment = list[tuple[int, float]]


def softmax(logits: Sequence[float]) -> list[float]:
    """Numerically stable softmax of ``logits``.

    Subtracts ``max(logits)`` before exponentiating so that large logits do not
    overflow ``math.exp`` (the standard stable-softmax trick). The returned list
    sums to 1.0 (up to floating-point rounding).
    """
    if not logits:
        raise ValueError("softmax requires at least one logit")
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    total = sum(exps)
    return [e / total for e in exps]


def _validate_k(logits: Sequence[float], k: int) -> None:
    if not logits:
        raise ValueError("logits must be non-empty")
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if k > len(logits):
        raise ValueError(
            f"k ({k}) cannot exceed the number of experts ({len(logits)})"
        )


def top_k_gating(logits: Sequence[float], k: int) -> Assignment:
    """Standard Switch / GShard top-k gate.

    Softmaxes ``logits`` into gate probabilities, selects the ``k`` experts with
    the largest probability, and **renormalizes** those ``k`` gate weights so
    they sum to 1.0 — the conventional Switch Transformers behaviour where the
    dropped experts' mass is redistributed over the kept ones.

    Returns a list of ``(expert_index, gate_weight)`` ordered from highest to
    lowest weight. Ties are broken by lowest expert index (deterministic).

    References: Fedus et al. 2022 (Switch); Lepikhin et al. 2020 (GShard).
    """
    _validate_k(logits, k)
    probs = softmax(logits)
    # Sort by (-prob, index) so ties resolve deterministically to lower index.
    ranked = sorted(range(len(probs)), key=lambda i: (-probs[i], i))
    chosen = ranked[:k]
    mass = sum(probs[i] for i in chosen)
    # mass > 0 always: softmax outputs are strictly positive.
    return [(i, probs[i] / mass) for i in chosen]


def noisy_top_k_gating(
    logits: Sequence[float],
    k: int,
    noise: Sequence[float],
) -> Assignment:
    """Noisy top-k gate (Shazeer et al. 2017), with noise added *before* top-k.

    Per-expert ``noise`` is added to ``logits`` and the top-k gate is then run on
    the perturbed logits. In production the noise is *sampled* (e.g. Gaussian,
    optionally scaled by a learned per-expert std) to encourage load balancing
    and exploration; here it is **injected by the caller** so the function stays
    deterministic and hermetically testable — there is deliberately no RNG call.

    Passing all-zero ``noise`` makes this identical to :func:`top_k_gating`.

    References: Shazeer et al. 2017 (*Outrageously Large Neural Networks*).
    """
    if len(noise) != len(logits):
        raise ValueError(
            f"noise length ({len(noise)}) must match logits length "
            f"({len(logits)})"
        )
    noisy = [l + n for l, n in zip(logits, noise)]
    return top_k_gating(noisy, k)


def load_balancing_loss(
    gate_assignments: Sequence[Assignment],
    num_experts: int,
) -> float:
    """Switch Transformers auxiliary load-balancing loss.

    ``L = N * sum_i f_i * P_i`` where ``N = num_experts``,
    ``f_i`` = fraction of (token, selection) routings sent to expert ``i``, and
    ``P_i`` = mean gate weight (probability mass) assigned to expert ``i`` across
    all tokens. The loss is minimized at ``1.0`` when load is perfectly uniform
    (``f_i = P_i = 1/N`` for every expert) and grows as routing skews toward a
    few experts. Used as an additive regularizer to keep experts balanced.

    ``gate_assignments`` is a list of per-token assignments, each a list of
    ``(expert_index, weight)`` as returned by the gating functions above.

    References: Fedus et al. 2022 (Switch); Shazeer et al. 2017 (original aux
    loss formulation).
    """
    if num_experts < 1:
        raise ValueError("num_experts must be >= 1")
    if not gate_assignments:
        return 0.0

    counts = [0.0] * num_experts          # routings per expert -> f_i
    prob_mass = [0.0] * num_experts       # summed gate weights -> P_i
    total_routings = 0

    for assignment in gate_assignments:
        for expert_index, weight in assignment:
            if not 0 <= expert_index < num_experts:
                raise ValueError(
                    f"expert_index {expert_index} out of range "
                    f"[0, {num_experts})"
                )
            counts[expert_index] += 1.0
            prob_mass[expert_index] += weight
            total_routings += 1

    if total_routings == 0:
        return 0.0

    f = [c / total_routings for c in counts]
    p = [m / total_routings for m in prob_mass]
    return num_experts * sum(fi * pi for fi, pi in zip(f, p))


@dataclass
class SparseMoERouter:
    """Sparse top-k MoE router tying the gate, capacity and aux loss together.

    Parameters
    ----------
    num_experts:
        Total number of experts ``N``.
    k:
        Experts selected per token (1 = Switch-style, 2 = GShard-style, ...).
    capacity_factor:
        If set, each expert may accept at most
        ``capacity = ceil(capacity_factor * num_tokens / num_experts)`` of its
        *primary* (top-1) routings. Overflow tokens are **rerouted** to their
        next-best expert with available capacity; if no such expert exists the
        token is marked **dropped** (its assignment becomes empty). This mirrors
        the expert-capacity / token-dropping behaviour of GShard and Switch,
        where overflowed tokens skip the MoE layer. ``None`` disables capacity.

    Modeling decision (capacity overflow)
    -------------------------------------
    Capacity is enforced **greedily on the primary (highest-weight) expert** in
    token order: a token first tries its top expert, and on overflow walks down
    its own remaining ranked experts to the next one with free capacity. This is
    deterministic and explainable; only the top-1 slot is capacity-limited, the
    remaining ``k-1`` selections of a routed token are kept as-is.
    """

    num_experts: int
    k: int = 1
    capacity_factor: float | None = None

    def __post_init__(self) -> None:
        if self.num_experts < 1:
            raise ValueError("num_experts must be >= 1")
        if self.k < 1:
            raise ValueError("k must be >= 1")
        if self.k > self.num_experts:
            raise ValueError("k cannot exceed num_experts")
        if self.capacity_factor is not None and self.capacity_factor <= 0:
            raise ValueError("capacity_factor must be > 0 when set")

    def _ranked_experts(self, logits: Sequence[float]) -> list[tuple[int, float]]:
        """Full ranked (expert, renormalized weight) list, top-k truncated."""
        return top_k_gating(logits, self.k)

    def route(
        self,
        token_logits: Sequence[Sequence[float]],
    ) -> "RoutingResult":
        """Route a batch of tokens and report the aggregate aux loss.

        ``token_logits`` is one logit vector (length ``num_experts``) per token.
        Returns a :class:`RoutingResult` with per-token assignments (after any
        capacity rerouting/dropping) and the load-balancing loss computed over
        the *final* assignments.
        """
        if not token_logits:
            return RoutingResult(assignments=[], load_balancing_loss=0.0, dropped=[])

        num_tokens = len(token_logits)
        for row in token_logits:
            if len(row) != self.num_experts:
                raise ValueError(
                    f"each token must have {self.num_experts} logits, "
                    f"got a row of length {len(row)}"
                )

        # Per-token ranked top-k assignments (pre-capacity).
        ranked: list[Assignment] = [self._ranked_experts(r) for r in token_logits]

        if self.capacity_factor is None:
            assignments = ranked
            dropped: list[int] = []
        else:
            capacity = math.ceil(
                self.capacity_factor * num_tokens / self.num_experts
            )
            assignments, dropped = self._apply_capacity(ranked, capacity)

        loss = load_balancing_loss(assignments, self.num_experts)
        return RoutingResult(
            assignments=assignments,
            load_balancing_loss=loss,
            dropped=dropped,
        )

    def _apply_capacity(
        self,
        ranked: list[Assignment],
        capacity: int,
    ) -> tuple[list[Assignment], list[int]]:
        """Greedy primary-slot capacity enforcement; see class docstring."""
        used = [0] * self.num_experts
        assignments: list[Assignment] = []
        dropped: list[int] = []

        for token_idx, assignment in enumerate(ranked):
            # The token's own ranked experts (highest weight first).
            placed_primary = -1
            for slot, (expert_index, _weight) in enumerate(assignment):
                if used[expert_index] < capacity:
                    used[expert_index] += 1
                    placed_primary = slot
                    break
            if placed_primary < 0:
                # No ranked expert had free capacity -> drop the token.
                assignments.append([])
                dropped.append(token_idx)
                continue
            # Keep the token's assignments, but reorder so the expert that
            # actually accepted it (after rerouting) is the primary slot.
            chosen = assignment[placed_primary]
            rest = [a for i, a in enumerate(assignment) if i != placed_primary]
            # Renormalize weights over the surviving selections so they sum to 1.
            kept = [chosen] + rest
            total_w = sum(w for _, w in kept)
            assignments.append([(e, w / total_w) for e, w in kept])

        return assignments, dropped


@dataclass
class RoutingResult:
    """Output of :meth:`SparseMoERouter.route`."""

    assignments: list[Assignment]      # per-token [(expert_index, weight), ...]
    load_balancing_loss: float
    dropped: list[int] = field(default_factory=list)  # indices of dropped tokens
