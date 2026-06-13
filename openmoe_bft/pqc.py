"""Post-Quantum Armor — Layer-9 hardening of the audit chain (OpenMoE-BFT Empire).

A *"harvest now, decrypt later"* defense for the tamper-evident receipt layer
(:mod:`openmoe_bft.receipts`). An adversary recording our signed audit trail
today could, once a cryptographically-relevant quantum computer exists, forge
classical (HMAC-keyed / Ed25519) signatures retroactively. The defense is to
sign with **NIST post-quantum** algorithms now:

- **ML-DSA** (FIPS 204, formerly **Dilithium**) — lattice signatures. We use
  ``ML-DSA-65`` (security category 3, the balanced default).
- **ML-KEM** (FIPS 203, formerly **Kyber**) — lattice key-encapsulation. We use
  ``ML-KEM-1024`` (category 5) for the highest-assurance key wrap.

These come from **liboqs** via its Python binding (``oqs`` /
``liboqs-python``) — a heavy, native, *optional* dependency. This module keeps
the package core **stdlib-only and network/dep-free**: ``oqs`` is **lazy-imported
only when a PQC primitive is actually called**, and every wrapper raises a clear

    RuntimeError("install openmoe-bft[pqc] (liboqs) for post-quantum signatures")

when it is absent. Wire the extra into ``pyproject.toml`` (the orchestrator does
this — this module does not edit it)::

    [project.optional-dependencies]
    pqc = ["liboqs-python>=0.10"]

Hybrid is the transition pattern (not PQC-only)
-----------------------------------------------
NIST and **CNSA 2.0** recommend a **hybrid** migration — keep a *classical*
signature (HMAC-SHA256 / Ed25519, already in ``receipts.py``) **and** add an
ML-DSA signature, rather than dropping classical immediately. Rationale: the PQC
schemes are young; a hybrid is no weaker than its strongest leg, so a future
break of *either* family does not forge the receipt. :class:`HybridSignature`
implements exactly this — classical always, ML-DSA when liboqs is available —
and **falls back to classical-only** (still verifying) when it is not. CNSA 2.0
expects software/firmware signing to be PQC by **2030**; hybrid is the bridge.

:func:`quantum_readiness` quantifies *how* harvest-now-decrypt-later-resistant an
existing :class:`~openmoe_bft.receipts.AuditChain` is: the share of its receipts
that carry a PQC signature, plus an advisory.

Hermeticity note: nothing here reads the clock or an RNG of its own. Key
generation inside liboqs uses liboqs's own CSPRNG and is only reached when a
caller explicitly asks for a keypair (and only when the optional dep is
installed) — the pure-Python core and all tests stay deterministic and offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .receipts import AuditChain, sign_hmac, verify_hmac


__all__ = [
    "ML_DSA_ALG",
    "ML_KEM_ALG",
    "PQC_INSTALL_HINT",
    "pqc_available",
    "keypair_ml_dsa",
    "sign_ml_dsa",
    "verify_ml_dsa",
    "keypair_ml_kem",
    "kem_ml_kem_encapsulate",
    "kem_ml_kem_decapsulate",
    "HybridSignature",
    "QuantumReadiness",
    "quantum_readiness",
]


# NIST PQC algorithm names as liboqs exposes them. liboqs accepts the FIPS names
# ("ML-DSA-65" / "ML-KEM-1024"); the historical names ("Dilithium3"/"Kyber1024")
# are the pre-standardization aliases.
ML_DSA_ALG = "ML-DSA-65"
ML_KEM_ALG = "ML-KEM-1024"

PQC_INSTALL_HINT = (
    "install openmoe-bft[pqc] (liboqs) for post-quantum signatures"
)


def pqc_available() -> bool:
    """Return ``True`` iff the optional ``oqs`` (liboqs) binding can be imported.

    A cheap, side-effect-free capability probe — does **not** generate keys or
    touch the network. Callers gate PQC-only paths on this; :class:`HybridSignature`
    uses it to decide whether to add a PQC leg or fall back to classical-only.
    """
    try:
        import oqs  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


def _require_oqs() -> Any:
    """Lazy-import ``oqs`` or raise the clear install-hint :class:`RuntimeError`."""
    try:
        import oqs  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only when absent
        raise RuntimeError(PQC_INSTALL_HINT) from exc
    return oqs


# ── ML-DSA (Dilithium) signatures ───────────────────────────────────


def keypair_ml_dsa() -> tuple[bytes, bytes]:
    """Generate an ``ML-DSA-65`` keypair -> ``(public_key, secret_key)`` bytes.

    Raises :class:`RuntimeError` with :data:`PQC_INSTALL_HINT` if liboqs is
    absent. The secret key is exported from the liboqs signer so it can be stored
    and re-imported by :func:`sign_ml_dsa`.
    """
    oqs = _require_oqs()
    with oqs.Signature(ML_DSA_ALG) as signer:
        public_key = signer.generate_keypair()
        secret_key = signer.export_secret_key()
    return public_key, secret_key


def sign_ml_dsa(message: bytes, secret_key: bytes) -> bytes:
    """Sign ``message`` with an ``ML-DSA-65`` ``secret_key``. Returns raw signature.

    Raises :class:`RuntimeError` with :data:`PQC_INSTALL_HINT` if liboqs is absent.
    """
    oqs = _require_oqs()
    with oqs.Signature(ML_DSA_ALG, secret_key) as signer:
        return signer.sign(message)


def verify_ml_dsa(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an ``ML-DSA-65`` ``signature`` over ``message`` under ``public_key``.

    Raises :class:`RuntimeError` with :data:`PQC_INSTALL_HINT` if liboqs is absent.
    """
    oqs = _require_oqs()
    with oqs.Signature(ML_DSA_ALG) as verifier:
        return bool(verifier.verify(message, signature, public_key))


# ── ML-KEM (Kyber) key encapsulation ────────────────────────────────


def keypair_ml_kem() -> tuple[bytes, bytes]:
    """Generate an ``ML-KEM-1024`` keypair -> ``(public_key, secret_key)`` bytes.

    Raises :class:`RuntimeError` with :data:`PQC_INSTALL_HINT` if liboqs is absent.
    """
    oqs = _require_oqs()
    with oqs.KeyEncapsulation(ML_KEM_ALG) as kem:
        public_key = kem.generate_keypair()
        secret_key = kem.export_secret_key()
    return public_key, secret_key


def kem_ml_kem_encapsulate(public_key: bytes) -> tuple[bytes, bytes]:
    """Encapsulate to ``public_key`` -> ``(ciphertext, shared_secret)`` bytes.

    Raises :class:`RuntimeError` with :data:`PQC_INSTALL_HINT` if liboqs is absent.
    """
    oqs = _require_oqs()
    with oqs.KeyEncapsulation(ML_KEM_ALG) as kem:
        ciphertext, shared_secret = kem.encap_secret(public_key)
    return ciphertext, shared_secret


def kem_ml_kem_decapsulate(ciphertext: bytes, secret_key: bytes) -> bytes:
    """Decapsulate ``ciphertext`` with ``secret_key`` -> ``shared_secret`` bytes.

    Raises :class:`RuntimeError` with :data:`PQC_INSTALL_HINT` if liboqs is absent.
    """
    oqs = _require_oqs()
    with oqs.KeyEncapsulation(ML_KEM_ALG, secret_key) as kem:
        return kem.decap_secret(ciphertext)


# ── Hybrid classical + PQC signing (the NIST transition pattern) ────


@dataclass(frozen=True)
class HybridSignature:
    """A hybrid signature: a *classical* leg always, an *ML-DSA* leg when available.

    The NIST/CNSA-2.0-recommended transition pattern. Verification **requires the
    classical signature to verify** and, **if a PQC signature is present, requires
    it to verify too** — so the bundle is no weaker than its strongest intact leg,
    and a break of *either* family alone cannot forge it. When liboqs is absent,
    construction transparently falls back to **classical-only** and still verifies
    (you do not lose signing on PQC-less hosts).

    Attributes
    ----------
    classical_sig:
        Hex HMAC-SHA256 signature over ``message`` (from
        :func:`openmoe_bft.receipts.sign_hmac`).
    classical_scheme:
        The classical scheme tag — currently always ``"hmac"``.
    pqc_sig:
        Raw ``ML-DSA-65`` signature bytes, or ``None`` if liboqs was unavailable.
    pqc_public_key:
        The ML-DSA public key the ``pqc_sig`` verifies under, or ``None``.
    pqc_scheme:
        :data:`ML_DSA_ALG` when a PQC leg is present, else ``None``.
    """

    classical_sig: str
    classical_scheme: str
    pqc_sig: bytes | None
    pqc_public_key: bytes | None
    pqc_scheme: str | None

    @property
    def is_hybrid(self) -> bool:
        """``True`` if a PQC leg is present (true hybrid), ``False`` if classical-only."""
        return self.pqc_sig is not None

    @classmethod
    def sign(
        cls,
        message: bytes,
        *,
        hmac_secret: str | bytes,
        ml_dsa_secret_key: bytes | None = None,
        ml_dsa_public_key: bytes | None = None,
    ) -> "HybridSignature":
        """Sign ``message`` with HMAC always + ML-DSA when liboqs and a key allow.

        The classical HMAC leg is always produced. The ML-DSA leg is added only
        when :func:`pqc_available` **and** both an ``ml_dsa_secret_key`` and its
        matching ``ml_dsa_public_key`` are supplied (generate them with
        :func:`keypair_ml_dsa`). If liboqs is absent, or no PQC key is supplied,
        the result is a valid **classical-only** :class:`HybridSignature` — never
        an error (graceful degradation is the whole point of the transition).
        """
        classical_sig = sign_hmac(_as_text(message), hmac_secret)
        pqc_sig: bytes | None = None
        pqc_pub: bytes | None = None
        pqc_scheme: str | None = None
        if (
            ml_dsa_secret_key is not None
            and ml_dsa_public_key is not None
            and pqc_available()
        ):
            pqc_sig = sign_ml_dsa(message, ml_dsa_secret_key)
            pqc_pub = ml_dsa_public_key
            pqc_scheme = ML_DSA_ALG
        return cls(
            classical_sig=classical_sig,
            classical_scheme="hmac",
            pqc_sig=pqc_sig,
            pqc_public_key=pqc_pub,
            pqc_scheme=pqc_scheme,
        )

    def verify(self, message: bytes, *, hmac_secret: str | bytes) -> bool:
        """Verify the bundle over ``message``.

        Requires the classical HMAC leg to verify. If a PQC leg is present it must
        verify too (under the bundle's ``pqc_public_key``) — and that *does*
        require liboqs, so verifying a hybrid signature on a PQC-less host raises
        the install-hint :class:`RuntimeError`. A classical-only bundle verifies
        with stdlib alone.
        """
        if not verify_hmac(_as_text(message), hmac_secret, self.classical_sig):
            return False
        if self.pqc_sig is None:
            return True  # classical-only bundle — stdlib verify is sufficient
        if self.pqc_public_key is None:
            return False
        return verify_ml_dsa(message, self.pqc_sig, self.pqc_public_key)


def _as_text(message: bytes) -> str:
    """HMAC helpers in ``receipts`` operate on text; carry bytes as hex losslessly."""
    return message.hex()


# ── Quantum readiness of an existing audit chain ────────────────────


@dataclass(frozen=True)
class QuantumReadiness:
    """How harvest-now-decrypt-later-resistant an :class:`AuditChain` is.

    Attributes
    ----------
    total:
        Number of receipts in the chain.
    pqc_signed:
        Receipts carrying a post-quantum signature (see :func:`quantum_readiness`
        for how that is detected).
    classical_only:
        Receipts with a classical signature but no PQC leg.
    unsigned:
        Receipts with no signature at all.
    readiness_pct:
        ``pqc_signed / total * 100`` (``0.0`` for an empty chain).
    advisory:
        Human-readable next-step guidance.
    """

    total: int
    pqc_signed: int
    classical_only: int
    unsigned: int
    readiness_pct: float
    advisory: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "pqc_signed": self.pqc_signed,
            "classical_only": self.classical_only,
            "unsigned": self.unsigned,
            "readiness_pct": self.readiness_pct,
            "advisory": self.advisory,
        }


# Signer tags / payload markers that indicate a receipt carries a PQC signature.
# A receipt is counted PQC-signed if its ``signer``/``co_signer`` names ML-DSA, or
# its payload records a hybrid/PQC signature marker.
_PQC_SIGNER_TAGS = {ML_DSA_ALG.lower(), "ml-dsa", "dilithium", "pqc", "hybrid"}


def _receipt_is_pqc(receipt: Any) -> bool:
    for tag in (getattr(receipt, "signer", None), getattr(receipt, "co_signer", None)):
        if tag and str(tag).lower() in _PQC_SIGNER_TAGS:
            return True
    payload = getattr(receipt, "payload", None) or {}
    if isinstance(payload, dict):
        marker = payload.get("pqc_scheme") or payload.get("signature_scheme")
        if marker and str(marker).lower() in _PQC_SIGNER_TAGS:
            return True
        if payload.get("pqc_signed") is True:
            return True
    return False


def quantum_readiness(chain: AuditChain) -> QuantumReadiness:
    """Report what fraction of ``chain``'s receipts are PQC-signed + an advisory.

    Quantifies harvest-now-decrypt-later resistance of the audit trail. A receipt
    counts as **PQC-signed** when its ``signer``/``co_signer`` names an ML-DSA /
    PQC / hybrid scheme, or its payload carries a PQC marker
    (``pqc_scheme`` / ``signature_scheme`` / ``pqc_signed: True``). Receipts with
    a classical signature but no such marker are **classical-only**; receipts with
    no ``signature`` are **unsigned**.

    On a classical-only (or unsigned) chain this returns ``readiness_pct == 0.0``
    with an advisory to adopt :class:`HybridSignature`. Pure / deterministic — no
    liboqs needed to *measure* readiness.
    """
    receipts = list(chain.receipts)
    total = len(receipts)
    pqc = sum(1 for r in receipts if _receipt_is_pqc(r))
    unsigned = sum(1 for r in receipts if getattr(r, "signature", None) is None)
    classical_only = total - pqc - unsigned
    if classical_only < 0:  # a PQC receipt may also be "unsigned" by classical tag
        classical_only = 0
    pct = (pqc / total * 100.0) if total else 0.0

    if total == 0:
        advisory = "empty chain: no receipts to assess."
    elif pqc == 0:
        advisory = (
            "0% post-quantum coverage — the audit trail is harvest-now-"
            "decrypt-later exposed. Adopt HybridSignature (classical HMAC/Ed25519 "
            f"+ {ML_DSA_ALG}) for new receipts; install openmoe-bft[pqc] (liboqs). "
            "CNSA 2.0 expects software signing to be post-quantum by 2030."
        )
    elif pqc < total:
        advisory = (
            f"{pct:.1f}% post-quantum coverage — {classical_only} classical-only "
            f"and {unsigned} unsigned receipt(s) remain. Migrate remaining signing "
            f"to HybridSignature ({ML_DSA_ALG}) to close the harvest-now gap."
        )
    else:
        advisory = (
            "100% post-quantum coverage — every receipt carries a PQC signature. "
            "Keep the classical leg (hybrid) through the CNSA 2.0 transition."
        )

    return QuantumReadiness(
        total=total,
        pqc_signed=pqc,
        classical_only=classical_only,
        unsigned=unsigned,
        readiness_pct=pct,
        advisory=advisory,
    )
