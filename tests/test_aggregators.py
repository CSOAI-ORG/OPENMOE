"""Byzantine-robust aggregators: correctness, robustness, validation. Hermetic."""

import pytest

from openmoe_bft import (
    coordinate_wise_median,
    trimmed_mean,
    krum,
    multi_krum,
    robust_route,
)


# ── coordinate_wise_median ───────────────────────────────────────

def test_median_odd_count_hand_computed():
    vecs = [
        [1.0, 10.0],
        [2.0, 20.0],
        [3.0, 30.0],
    ]
    # per-coordinate medians: [median(1,2,3), median(10,20,30)] = [2, 20]
    assert coordinate_wise_median(vecs) == [2.0, 20.0]


def test_median_even_count_averages_middle_two():
    vecs = [[1.0], [2.0], [3.0], [100.0]]
    # sorted [1,2,3,100] -> mean of middle two (2,3) = 2.5
    assert coordinate_wise_median(vecs) == [2.5]


def test_median_byzantine_resistant():
    # 5 honest near 5.0, 2 byzantine at ±1e6 -> median unmoved.
    vecs = [[5.0], [5.1], [4.9], [5.0], [5.05], [1e6], [-1e6]]
    out = coordinate_wise_median(vecs)
    assert abs(out[0] - 5.0) < 0.2


# ── trimmed_mean ─────────────────────────────────────────────────

def test_trimmed_mean_hand_computed():
    vecs = [[1.0], [2.0], [3.0], [4.0], [100.0]]
    # f=1: drop 1 low (1) and 1 high (100) -> mean(2,3,4) = 3.0
    assert trimmed_mean(vecs, f=1) == [3.0]


def test_trimmed_mean_f_zero_is_plain_mean():
    vecs = [[2.0, 4.0], [4.0, 8.0]]
    assert trimmed_mean(vecs, f=0) == [3.0, 6.0]


def test_trimmed_mean_byzantine_resistant():
    # 5 honest near 10, 2 byzantine extremes. f=2 trims both extremes per coord.
    vecs = [[10.0], [10.0], [9.0], [11.0], [10.0], [1e9], [-1e9]]
    out = trimmed_mean(vecs, f=2)
    assert abs(out[0] - 10.0) < 1.0


def test_trimmed_mean_validation_n_must_exceed_2f():
    with pytest.raises(ValueError):
        trimmed_mean([[1.0], [2.0]], f=1)  # n=2, 2f=2, not n>2f
    with pytest.raises(ValueError):
        trimmed_mean([[1.0], [2.0], [3.0]], f=-1)


# ── krum / multi_krum ────────────────────────────────────────────

def test_krum_selects_central_vector():
    # n=5, f=1 -> needs n>=2f+3=5. One clear outlier; krum returns a clustered one.
    vecs = [
        [0.0, 0.0],
        [0.1, 0.1],
        [0.0, 0.1],
        [0.1, 0.0],
        [100.0, 100.0],   # byzantine outlier
    ]
    out = krum(vecs, f=1)
    assert out != [100.0, 100.0]
    assert out in [list(v) for v in vecs[:4]]


def test_krum_byzantine_far_vectors_ignored():
    # 5 honest tightly clustered at ~(1,1), 2 byzantine far away. n=7,f=2 ok.
    vecs = [
        [1.0, 1.0],
        [1.1, 0.9],
        [0.9, 1.1],
        [1.0, 1.05],
        [1.05, 1.0],
        [500.0, -500.0],
        [-500.0, 500.0],
    ]
    out = krum(vecs, f=2)
    # selected vector must be from the honest cluster (near (1,1)).
    assert abs(out[0] - 1.0) < 0.5 and abs(out[1] - 1.0) < 0.5


def test_multi_krum_m1_equals_krum():
    vecs = [
        [0.0, 0.0],
        [0.1, 0.1],
        [0.0, 0.1],
        [0.1, 0.0],
        [50.0, 50.0],
    ]
    assert multi_krum(vecs, f=1, m=1) == krum(vecs, f=1)


def test_multi_krum_averages_central_vectors():
    vecs = [
        [0.0, 0.0],
        [2.0, 2.0],
        [1.0, 1.0],
        [1.0, 1.0],
        [100.0, 100.0],  # outlier, excluded
    ]
    out = multi_krum(vecs, f=1, m=4)
    # mean of the 4 central vectors (excluding outlier) = (0+2+1+1)/4 = 1.0
    assert out == [1.0, 1.0]


def test_krum_validation_n_too_small():
    # n=4, f=1 -> needs >=5
    with pytest.raises(ValueError):
        krum([[1.0], [2.0], [3.0], [4.0]], f=1)
    with pytest.raises(ValueError):
        krum([[1.0], [2.0], [3.0], [4.0], [5.0]], f=-1)


def test_multi_krum_validation_m_out_of_range():
    vecs = [[float(i)] for i in range(5)]
    with pytest.raises(ValueError):
        multi_krum(vecs, f=1, m=0)
    with pytest.raises(ValueError):
        multi_krum(vecs, f=1, m=6)
    with pytest.raises(ValueError):
        multi_krum([[1.0]] * 4, f=1, m=2)  # n too small
    # m=3 is valid for n=5,f=1 -> no raise.
    assert len(multi_krum(vecs, f=1, m=3)) == 1


# ── shared validation ────────────────────────────────────────────

def test_empty_and_ragged_inputs_raise():
    with pytest.raises(ValueError):
        coordinate_wise_median([])
    with pytest.raises(ValueError):
        coordinate_wise_median([[]])
    with pytest.raises(ValueError):
        coordinate_wise_median([[1.0, 2.0], [3.0]])  # ragged
    with pytest.raises(ValueError):
        trimmed_mean([[1.0, 2.0], [3.0]], f=0)


# ── robust_route ─────────────────────────────────────────────────

def test_robust_route_picks_expert_median():
    # 3 experts; replicas mostly favour expert 2 (index 2 highest).
    vecs = [
        [0.1, 0.2, 0.9],
        [0.0, 0.3, 0.8],
        [0.2, 0.1, 0.95],
    ]
    assert robust_route(vecs, f=0, method="median") == 2


def test_robust_route_byzantine_cannot_flip_winner():
    # Honest replicas favour expert 0; byzantine replicas scream for expert 2.
    honest = [[10.0, 0.0, 0.0]] * 5
    byz = [[-1e6, 0.0, 1e6], [-1e6, 0.0, 1e6]]
    vecs = honest + byz  # n=7, f=2
    # median ignores the 2 byzantine extremes -> expert 0 still wins.
    assert robust_route(vecs, f=2, method="median") == 0
    # krum picks an honest central vector -> argmax is expert 0.
    assert robust_route(vecs, f=2, method="krum") == 0
    # trimmed_mean trims extremes -> expert 0.
    assert robust_route(vecs, f=2, method="trimmed_mean") == 0


def test_robust_route_multi_krum_default_m():
    vecs = [[1.0, 0.0]] * 5 + [[0.0, 1e6], [0.0, 1e6]]  # n=7, f=2
    # default m = n - f = 5 central vectors averaged; expert 0 wins.
    assert robust_route(vecs, f=2, method="multi_krum") == 0


def test_robust_route_unknown_method_raises():
    with pytest.raises(ValueError):
        robust_route([[1.0]], f=0, method="bogus")


def test_robust_route_argmax_tie_breaks_low_index():
    vecs = [[5.0, 5.0, 1.0]]
    assert robust_route(vecs, f=0, method="median") == 0
