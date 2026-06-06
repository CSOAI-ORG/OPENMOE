"""Byzantine-robust aggregation for router-replica score vectors (Empire Layer 2).

The ByzFL absorption (Empire spec PART 1, TIER 1 #9 "ByzFL → add MoE-specific
aggregators"). Cleanroom, stdlib-only implementations of the classic
Byzantine-robust aggregation rules from the published algorithms.

Where :mod:`openmoe_bft.routing` runs a *hash-vote* over discrete expert-key
proposals (each replica names one expert; a ``2f+1`` quorum must name the same
one), this module is the *soft / numeric* complement: each of ``N`` router
replicas emits a real-valued **score vector** (e.g. the per-expert router
logits), and we aggregate those vectors with a rule that is provably robust to
up to ``f`` arbitrary (Byzantine) replicas before taking the argmax.

All functions are pure, take ``list[list[float]]`` (one inner list per replica,
all the same length), validate their inputs, and raise a clear
:class:`ValueError` on malformed input or when the robustness precondition on
``n`` vs ``f`` does not hold.

References
----------
- Krum / Multi-Krum:
  Blanchard, Mhamdi, Guerraoui, Stainer,
  "Machine Learning with Adversaries: Byzantine Tolerant Gradient Descent",
  NeurIPS 2017.
- Coordinate-wise median / trimmed mean:
  Yin, Chen, Kannan, Bartlett,
  "Byzantine-Robust Distributed Learning: Towards Optimal Statistical Rates",
  ICML 2018.
"""

from __future__ import annotations

from typing import Sequence


Vector = Sequence[float]


# ── input validation ────────────────────────────────────────────


def _validate(vectors: Sequence[Vector]) -> tuple[int, int]:
    """Validate a batch of replica vectors. Returns ``(n, dim)``.

    Raises :class:`ValueError` if the batch is empty, contains an empty vector,
    or the vectors are not all the same length.
    """
    if not vectors:
        raise ValueError("need at least one vector to aggregate")
    n = len(vectors)
    dim = len(vectors[0])
    if dim == 0:
        raise ValueError("vectors must be non-empty (dim >= 1)")
    for i, v in enumerate(vectors):
        if len(v) != dim:
            raise ValueError(
                f"all vectors must have the same length; vector {i} has "
                f"length {len(v)}, expected {dim}"
            )
    return n, dim


def _median(values: list[float]) -> float:
    """Median of a list (mean of the two middle values for even counts)."""
    s = sorted(values)
    m = len(s)
    mid = m // 2
    if m % 2 == 1:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def _sq_dist(a: Vector, b: Vector) -> float:
    """Squared Euclidean distance between two equal-length vectors."""
    return sum((x - y) * (x - y) for x, y in zip(a, b))


# ── aggregation rules ────────────────────────────────────────────


def coordinate_wise_median(vectors: Sequence[Vector]) -> list[float]:
    """Per-coordinate median across replica vectors (Yin et al., ICML 2018).

    For each coordinate independently, return the median of that coordinate
    across all ``n`` replicas. Robust to up to ``f < n/2`` Byzantine replicas
    per coordinate.

    Parameters
    ----------
    vectors:
        ``list[list[float]]`` — one score vector per router replica, all the
        same length.

    Returns
    -------
    list[float]
        The coordinate-wise median vector.
    """
    n, dim = _validate(vectors)
    return [_median([vectors[i][c] for i in range(n)]) for c in range(dim)]


def trimmed_mean(vectors: Sequence[Vector], f: int) -> list[float]:
    """Coordinate-wise trimmed mean (Yin et al., ICML 2018).

    For each coordinate, drop the ``f`` highest and ``f`` lowest values, then
    average the remaining ``n - 2f``. This removes the influence of up to ``f``
    Byzantine replicas (which can only push a coordinate to an extreme, and the
    extremes are exactly what is trimmed).

    Requires ``n > 2f`` so at least one value survives the trim per coordinate.

    Parameters
    ----------
    vectors:
        ``list[list[float]]`` — one score vector per router replica.
    f:
        Number of values to trim from each end per coordinate (``f >= 0``).

    Raises
    ------
    ValueError
        If ``f < 0`` or ``n <= 2f`` (nothing would survive the trim).
    """
    n, dim = _validate(vectors)
    if f < 0:
        raise ValueError("f must be >= 0")
    if n <= 2 * f:
        raise ValueError(
            f"trimmed_mean requires n > 2f; got n={n}, f={f} "
            f"(would trim all {2 * f} values, leaving none)"
        )
    out: list[float] = []
    for c in range(dim):
        col = sorted(vectors[i][c] for i in range(n))
        kept = col[f:n - f] if f > 0 else col
        out.append(sum(kept) / len(kept))
    return out


def krum(vectors: Sequence[Vector], f: int) -> list[float]:
    """Krum aggregation: select the single most-central vector.

    Blanchard et al., NeurIPS 2017. For each candidate vector, compute the sum
    of squared distances to its ``n - f - 2`` nearest neighbours (excluding
    itself); the candidate with the *smallest* such score is returned
    unchanged. By construction this vector is close to a majority of honest
    replicas and far from up to ``f`` Byzantine outliers.

    Requires ``n >= 2f + 3`` so that ``n - f - 2 >= f + 1`` honest neighbours
    are guaranteed to exist for the selected vector.

    Parameters
    ----------
    vectors:
        ``list[list[float]]`` — one score vector per router replica.
    f:
        Assumed number of Byzantine replicas (``f >= 0``).

    Returns
    -------
    list[float]
        The selected (most-central) replica vector, as a new list.

    Raises
    ------
    ValueError
        If ``f < 0`` or ``n < 2f + 3``.
    """
    n, _dim = _validate(vectors)
    if f < 0:
        raise ValueError("f must be >= 0")
    if n < 2 * f + 3:
        raise ValueError(
            f"krum requires n >= 2f + 3; got n={n}, f={f} "
            f"(need at least {2 * f + 3} replicas)"
        )
    idx = _krum_select(vectors, f, n)
    return list(vectors[idx])


def multi_krum(vectors: Sequence[Vector], f: int, m: int) -> list[float]:
    """Multi-Krum: average the ``m`` lowest-scoring (most-central) vectors.

    Blanchard et al., NeurIPS 2017 (the "Multi-Krum" variant). Computes the
    Krum selection score for every candidate, picks the ``m`` best, and returns
    their coordinate-wise mean. ``m = 1`` reduces to plain :func:`krum`; larger
    ``m`` reduces variance while keeping the same robustness guarantee.

    Requires ``n >= 2f + 3`` and ``1 <= m <= n``.

    Parameters
    ----------
    vectors:
        ``list[list[float]]`` — one score vector per router replica.
    f:
        Assumed number of Byzantine replicas (``f >= 0``).
    m:
        Number of most-central vectors to average.

    Raises
    ------
    ValueError
        If ``f < 0``, ``n < 2f + 3``, or ``m`` is out of ``[1, n]``.
    """
    n, dim = _validate(vectors)
    if f < 0:
        raise ValueError("f must be >= 0")
    if n < 2 * f + 3:
        raise ValueError(
            f"multi_krum requires n >= 2f + 3; got n={n}, f={f} "
            f"(need at least {2 * f + 3} replicas)"
        )
    if not (1 <= m <= n):
        raise ValueError(f"m must be in [1, {n}]; got m={m}")

    scores = [(_krum_score(vectors, i, f, n), i) for i in range(n)]
    scores.sort(key=lambda t: (t[0], t[1]))
    chosen = [i for _score, i in scores[:m]]
    return [sum(vectors[i][c] for i in chosen) / m for c in range(dim)]


def _krum_score(vectors: Sequence[Vector], i: int, f: int, n: int) -> float:
    """Sum of squared distances from vector ``i`` to its ``n-f-2`` nearest."""
    dists = sorted(
        _sq_dist(vectors[i], vectors[j]) for j in range(n) if j != i
    )
    k = n - f - 2  # number of nearest neighbours to sum over
    return sum(dists[:k])


def _krum_select(vectors: Sequence[Vector], f: int, n: int) -> int:
    """Index of the vector with the smallest Krum score (ties: lowest index)."""
    best_idx = 0
    best_score = _krum_score(vectors, 0, f, n)
    for i in range(1, n):
        s = _krum_score(vectors, i, f, n)
        if s < best_score:
            best_score, best_idx = s, i
    return best_idx


# ── convenience: numeric router ──────────────────────────────────


_METHODS = {"median", "trimmed_mean", "krum", "multi_krum"}


def robust_route(
    score_vectors: Sequence[Vector],
    f: int,
    method: str = "median",
    *,
    m: int | None = None,
) -> int:
    """Aggregate replica score vectors robustly and return the argmax expert.

    The numeric complement to :class:`openmoe_bft.routing.BFTRouter`: instead of
    voting over discrete expert keys, each replica emits a per-expert score
    vector and we fuse them with a Byzantine-robust rule before choosing the
    highest-scoring expert. Up to ``f`` adversarial replicas cannot move the
    winner.

    Parameters
    ----------
    score_vectors:
        ``list[list[float]]`` — one per-expert score vector per replica.
    f:
        Assumed number of Byzantine replicas.
    method:
        One of ``"median"``, ``"trimmed_mean"``, ``"krum"``, ``"multi_krum"``.
    m:
        Only for ``method="multi_krum"`` — how many central vectors to average
        (defaults to ``n - f`` when omitted).

    Returns
    -------
    int
        Index of the winning expert (argmax of the aggregated vector). Ties are
        broken toward the lowest index.

    Raises
    ------
    ValueError
        On unknown ``method`` or any precondition failure of the chosen rule.
    """
    if method not in _METHODS:
        raise ValueError(
            f"unknown method {method!r}; choose one of {sorted(_METHODS)}"
        )
    n, _dim = _validate(score_vectors)

    if method == "median":
        agg = coordinate_wise_median(score_vectors)
    elif method == "trimmed_mean":
        agg = trimmed_mean(score_vectors, f)
    elif method == "krum":
        agg = krum(score_vectors, f)
    else:  # multi_krum
        mm = (n - f) if m is None else m
        agg = multi_krum(score_vectors, f, mm)

    # argmax with lowest-index tie-break.
    best_i = 0
    best_v = agg[0]
    for i in range(1, len(agg)):
        if agg[i] > best_v:
            best_v, best_i = agg[i], i
    return best_i
