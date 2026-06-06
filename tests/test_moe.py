"""Cleanroom sparse MoE router (Empire Layer 1). Hermetic, stdlib-only.

From-the-paper reimplementation (Switch/GShard/Shazeer noisy gating + Switch
aux loss); no upstream OpenMoE code. Run with:

    HOME=$(mktemp -d) /tmp/openmoe-bft-venv/bin/pytest tests/test_moe.py -v
"""

import math

import pytest

from openmoe_bft.moe import (
    softmax,
    top_k_gating,
    noisy_top_k_gating,
    load_balancing_loss,
    SparseMoERouter,
    RoutingResult,
)


# --------------------------------------------------------------------------- #
# softmax                                                                      #
# --------------------------------------------------------------------------- #
def test_softmax_sums_to_one():
    p = softmax([1.0, 2.0, 3.0])
    assert abs(sum(p) - 1.0) < 1e-12
    # Monotonic: larger logit -> larger probability.
    assert p[0] < p[1] < p[2]


def test_softmax_stable_on_large_logits():
    # Without max-subtraction this overflows math.exp; stable version must not.
    p = softmax([1000.0, 1001.0, 1002.0])
    assert abs(sum(p) - 1.0) < 1e-12
    assert all(0.0 <= x <= 1.0 for x in p)


def test_softmax_uniform():
    p = softmax([5.0, 5.0, 5.0, 5.0])
    assert all(abs(x - 0.25) < 1e-12 for x in p)


def test_softmax_empty_raises():
    with pytest.raises(ValueError):
        softmax([])


# --------------------------------------------------------------------------- #
# top_k_gating                                                                 #
# --------------------------------------------------------------------------- #
def test_top_k_picks_right_experts():
    # Experts 2 and 0 have the largest logits.
    assignment = top_k_gating([3.0, 0.0, 5.0, 1.0], k=2)
    indices = [i for i, _ in assignment]
    assert indices == [2, 0]  # ordered by descending weight


def test_top_k_renormalizes_to_one():
    assignment = top_k_gating([3.0, 0.0, 5.0, 1.0], k=2)
    assert abs(sum(w for _, w in assignment) - 1.0) < 1e-12


def test_top_1_weight_is_one():
    assignment = top_k_gating([1.0, 2.0, 0.5], k=1)
    assert assignment[0][0] == 1
    assert abs(assignment[0][1] - 1.0) < 1e-12


def test_top_k_equals_full_softmax_when_k_is_all():
    logits = [1.0, 2.0, 3.0]
    probs = softmax(logits)
    assignment = top_k_gating(logits, k=3)
    by_index = {i: w for i, w in assignment}
    # k == num_experts -> renormalization is a no-op (softmax already sums to 1).
    for i, p in enumerate(probs):
        assert abs(by_index[i] - p) < 1e-12


def test_top_k_tie_breaks_on_lower_index():
    assignment = top_k_gating([2.0, 2.0, 1.0], k=1)
    assert assignment[0][0] == 0  # tie between 0 and 1 -> lower index wins


def test_top_k_validation():
    with pytest.raises(ValueError):
        top_k_gating([1.0, 2.0], k=0)
    with pytest.raises(ValueError):
        top_k_gating([1.0, 2.0], k=3)  # k > num_experts
    with pytest.raises(ValueError):
        top_k_gating([], k=1)


# --------------------------------------------------------------------------- #
# noisy_top_k_gating                                                           #
# --------------------------------------------------------------------------- #
def test_noisy_zero_noise_equals_top_k():
    logits = [3.0, 0.0, 5.0, 1.0]
    noisy = noisy_top_k_gating(logits, k=2, noise=[0.0, 0.0, 0.0, 0.0])
    plain = top_k_gating(logits, k=2)
    assert noisy == plain


def test_noisy_flips_selection():
    # Expert 0 leads on raw logits; inject noise that pushes expert 1 above it.
    logits = [5.0, 4.0, 0.0]
    plain = top_k_gating(logits, k=1)
    assert plain[0][0] == 0
    noisy = noisy_top_k_gating(logits, k=1, noise=[0.0, 2.0, 0.0])
    assert noisy[0][0] == 1  # noise flipped the winner to expert 1


def test_noisy_length_mismatch_raises():
    with pytest.raises(ValueError):
        noisy_top_k_gating([1.0, 2.0, 3.0], k=1, noise=[0.0, 0.0])


# --------------------------------------------------------------------------- #
# load_balancing_loss                                                          #
# --------------------------------------------------------------------------- #
def test_balanced_loss_is_one():
    # 4 experts, each gets exactly one top-1 token with weight 1.0.
    num_experts = 4
    assignments = [[(i, 1.0)] for i in range(num_experts)]
    loss = load_balancing_loss(assignments, num_experts)
    assert abs(loss - 1.0) < 1e-12  # perfect balance -> ideal loss N*(1/N)*(1/N)*N


def test_skewed_loss_is_higher():
    num_experts = 4
    balanced = [[(i, 1.0)] for i in range(num_experts)]
    # Everything piled on expert 0.
    skewed = [[(0, 1.0)] for _ in range(num_experts)]
    assert load_balancing_loss(skewed, num_experts) > load_balancing_loss(
        balanced, num_experts
    )


def test_fully_skewed_loss_equals_num_experts():
    # All tokens to one expert: f_0 = 1, P_0 = 1 -> L = N.
    num_experts = 4
    skewed = [[(0, 1.0)] for _ in range(8)]
    assert abs(load_balancing_loss(skewed, num_experts) - num_experts) < 1e-12


def test_loss_empty_is_zero():
    assert load_balancing_loss([], 4) == 0.0


def test_loss_bad_expert_index_raises():
    with pytest.raises(ValueError):
        load_balancing_loss([[(9, 1.0)]], num_experts=4)


# --------------------------------------------------------------------------- #
# SparseMoERouter                                                              #
# --------------------------------------------------------------------------- #
def test_router_basic_route_no_capacity():
    router = SparseMoERouter(num_experts=3, k=1)
    result = router.route([[5.0, 0.0, 0.0], [0.0, 0.0, 5.0]])
    assert isinstance(result, RoutingResult)
    assert result.assignments[0][0][0] == 0
    assert result.assignments[1][0][0] == 2
    assert result.dropped == []


def test_router_route_empty():
    router = SparseMoERouter(num_experts=3, k=1)
    result = router.route([])
    assert result.assignments == []
    assert result.load_balancing_loss == 0.0


def test_router_capacity_reroutes_overflow():
    # 2 tokens both want expert 0 first; capacity 1 forces the 2nd to expert 1.
    router = SparseMoERouter(num_experts=2, k=2, capacity_factor=1.0)
    # capacity = ceil(1.0 * 2 / 2) = 1.
    result = router.route([[5.0, 4.0], [6.0, 3.0]])
    primaries = [a[0][0] for a in result.assignments]
    assert primaries[0] == 0      # first token keeps expert 0
    assert primaries[1] == 1      # second token rerouted to its next-best
    assert result.dropped == []


def test_router_capacity_drops_when_no_slot():
    # k=1 so a token has only one candidate; capacity 1 on expert 0 drops the 2nd.
    router = SparseMoERouter(num_experts=2, k=1, capacity_factor=0.5)
    # capacity = ceil(0.5 * 2 / 2) = 1; both tokens want expert 0 only.
    result = router.route([[5.0, 0.0], [6.0, 0.0]])
    assert result.assignments[0] == [(0, 1.0)]
    assert result.assignments[1] == []   # dropped, empty assignment
    assert result.dropped == [1]


def test_router_ragged_logits_raises():
    router = SparseMoERouter(num_experts=3, k=1)
    with pytest.raises(ValueError):
        router.route([[1.0, 2.0, 3.0], [1.0, 2.0]])  # ragged


def test_router_validation():
    with pytest.raises(ValueError):
        SparseMoERouter(num_experts=0, k=1)
    with pytest.raises(ValueError):
        SparseMoERouter(num_experts=3, k=5)  # k > num_experts
    with pytest.raises(ValueError):
        SparseMoERouter(num_experts=3, k=1, capacity_factor=0.0)


def test_router_capacity_assignments_renormalize():
    router = SparseMoERouter(num_experts=2, k=2, capacity_factor=1.0)
    result = router.route([[5.0, 4.0], [6.0, 3.0]])
    for a in result.assignments:
        if a:
            assert abs(sum(w for _, w in a) - 1.0) < 1e-12
