"""Cryptographic-receipt module (OpenMoE-BFT Empire, Layer 9: Audit & Receipts).

Hash-chained, tamper-evident receipts that seal *what was decided* — most
naturally each :class:`~openmoe_bft.bft.BFTConsensus` decision (see ``bft.py``)
becomes a sealed :class:`Receipt` — and that pair with x402 payment attestation
(Empire Layer 10). Every receipt links to its predecessor by hash, so the whole
:class:`AuditChain` is verifiable end-to-end and any post-hoc mutation is
detectable.

Absorbs **Signet** (https://github.com/Prismer-AI/signet, dual Apache-2.0 / MIT
— permissive, attribution preserved here). The core receipt primitives are
reimplemented cleanroom in Python.

Design (mirrors the sibling ``agentaudit`` project, but standalone — no
``agentaudit`` import):

- **Zero required dependencies.** The core uses only the stdlib (``hashlib`` for
  the hash chain, ``hmac`` for the always-available HMAC-SHA256 signer).
- **Optional Ed25519 upgrade path.** ``sign_ed25519`` / ``verify_ed25519`` lazily
  import ``nacl.signing`` (PyNaCl) only when called, raising a clear
  ``RuntimeError`` if it is not installed. Install it via the optional extra::

      pip install "openmoe-bft[ed25519]"     # extra [ed25519] -> pynacl

  PyNaCl is **not** a hard dependency; the extra is wired into ``pyproject.toml``
  by the orchestrator.

Hermeticity note: receipts never read the clock — the caller passes ``timestamp``
(an ``int``/``float``) explicitly, keeping construction deterministic and tests
reproducible.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field, replace
from typing import Any


__all__ = [
    "Receipt",
    "AuditChain",
    "VerifyResult",
    "sign_hmac",
    "verify_hmac",
    "sign_ed25519",
    "verify_ed25519",
]


def _canonical(obj: Any) -> str:
    """Canonical JSON serialization: stable, order-independent, compact.

    ``sort_keys=True`` makes dict ordering irrelevant and ``separators`` strips
    incidental whitespace, so the same logical content always hashes identically.
    """
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _entry_hash(
    trace_id: str,
    parent_receipt_id: str | None,
    timestamp: int | float,
    payload: dict[str, Any],
    prev_hash: str,
) -> str:
    """SHA-256 over the canonical serialization of a receipt's chained content.

    Includes ``prev_hash`` — this is what makes the chain link tamper-evident.
    """
    material = _canonical(
        {
            "trace_id": trace_id,
            "parent_receipt_id": parent_receipt_id,
            "timestamp": timestamp,
            "payload": payload,
            "prev_hash": prev_hash,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _receipt_id(
    trace_id: str,
    parent_receipt_id: str | None,
    timestamp: int | float,
    payload: dict[str, Any],
    prev_hash: str,
) -> str:
    """Deterministic content-address: same content + timestamp + prev -> same id."""
    return _entry_hash(trace_id, parent_receipt_id, timestamp, payload, prev_hash)


def sign_hmac(entry_hash: str, secret: str | bytes) -> str:
    """Always-available signer: HMAC-SHA256 of ``entry_hash`` under ``secret``.

    Returns a lowercase hex digest. Stdlib only.
    """
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(key, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac(entry_hash: str, secret: str | bytes, signature: str) -> bool:
    """Constant-time verification of an HMAC-SHA256 signature."""
    expected = sign_hmac(entry_hash, secret)
    return hmac.compare_digest(expected, signature)


def sign_ed25519(entry_hash: str, private_key: bytes) -> str:
    """Optional Ed25519 signer over ``entry_hash`` (lazy PyNaCl import).

    ``private_key`` is the 32-byte Ed25519 seed. Returns a hex-encoded signature.

    Raises
    ------
    RuntimeError
        If PyNaCl is not installed.
    """
    try:
        from nacl.signing import SigningKey
    except ImportError as exc:  # pragma: no cover - exercised only when absent
        raise RuntimeError(
            "install openmoe-bft[ed25519] for Ed25519 receipts"
        ) from exc

    signed = SigningKey(private_key).sign(entry_hash.encode("utf-8"))
    return signed.signature.hex()


def verify_ed25519(entry_hash: str, public_key: bytes, signature: str) -> bool:
    """Optional Ed25519 verification (lazy PyNaCl import).

    ``public_key`` is the 32-byte Ed25519 verify key; ``signature`` is hex.

    Raises
    ------
    RuntimeError
        If PyNaCl is not installed.
    """
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError as exc:  # pragma: no cover - exercised only when absent
        raise RuntimeError(
            "install openmoe-bft[ed25519] for Ed25519 receipts"
        ) from exc

    try:
        VerifyKey(public_key).verify(
            entry_hash.encode("utf-8"), bytes.fromhex(signature)
        )
        return True
    except BadSignatureError:
        return False


@dataclass(frozen=True)
class Receipt:
    """A single tamper-evident, hash-chained audit receipt (Layer 9).

    Attributes
    ----------
    receipt_id:
        Deterministic content hash of the receipt (SHA-256). Same content +
        timestamp + ``prev_hash`` always yields the same id.
    trace_id:
        Correlates receipts belonging to one logical operation / session.
    parent_receipt_id:
        The id of the logical parent receipt, or ``None`` for the genesis receipt.
    timestamp:
        Passed in by the caller (``int``/``float``). Never read from the clock.
    payload:
        The action / decision being attested (e.g. a sealed BFT consensus result).
    prev_hash:
        The previous receipt's ``entry_hash`` — ``""`` for the genesis receipt.
    entry_hash:
        SHA-256 over the canonical serialization (including ``prev_hash``); the
        hash-chain link.
    signature:
        ``None`` until signed; otherwise the primary signer's signature.
    signer:
        Key id / ``"hmac"`` / ``"ed25519"`` — identifies the signing scheme.
    co_signature:
        Optional second signature (the spec's *bilateral co-sign*).
    co_signer:
        Identifier of the co-signer, if any.
    """

    receipt_id: str
    trace_id: str
    parent_receipt_id: str | None
    timestamp: int | float
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str
    signature: str | None = None
    signer: str | None = None
    co_signature: str | None = None
    co_signer: str | None = None

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        payload: dict[str, Any],
        timestamp: int | float,
        prev_hash: str = "",
        parent_receipt_id: str | None = None,
    ) -> "Receipt":
        """Build an unsigned receipt, computing ``entry_hash`` and ``receipt_id``."""
        eh = _entry_hash(trace_id, parent_receipt_id, timestamp, payload, prev_hash)
        rid = _receipt_id(
            trace_id, parent_receipt_id, timestamp, payload, prev_hash
        )
        return cls(
            receipt_id=rid,
            trace_id=trace_id,
            parent_receipt_id=parent_receipt_id,
            timestamp=timestamp,
            payload=payload,
            prev_hash=prev_hash,
            entry_hash=eh,
        )

    def recomputed_entry_hash(self) -> str:
        """Recompute ``entry_hash`` from the receipt's own content (for verify)."""
        return _entry_hash(
            self.trace_id,
            self.parent_receipt_id,
            self.timestamp,
            self.payload,
            self.prev_hash,
        )


@dataclass
class VerifyResult:
    """Outcome of :meth:`AuditChain.verify`.

    ``ok`` is True only when every link verifies. On failure, ``broken_at`` is
    the index of the first bad receipt and ``reason`` explains it.
    """

    ok: bool
    broken_at: int | None = None
    reason: str = "chain verified"


class AuditChain:
    """An ordered, hash-chained sequence of :class:`Receipt` records (Layer 9).

    The genesis receipt has ``prev_hash == ""``; every subsequent receipt's
    ``prev_hash`` equals the prior receipt's ``entry_hash``. :meth:`verify`
    re-derives every ``entry_hash`` and checks every link, so any mutation of a
    sealed payload is detectable.
    """

    def __init__(self) -> None:
        self.receipts: list[Receipt] = []

    def append(
        self,
        payload: dict[str, Any],
        trace_id: str,
        timestamp: int | float,
        signer_key: str | bytes | None = None,
        co_sign_key: str | bytes | None = None,
    ) -> Receipt:
        """Build, optionally sign, and append a receipt; return it.

        ``prev_hash`` and ``parent_receipt_id`` are taken from the last receipt
        (``""`` / ``None`` for genesis). If ``signer_key`` is given the receipt is
        HMAC-SHA256 signed; ``co_sign_key`` adds a second (bilateral) signature.
        """
        if self.receipts:
            last = self.receipts[-1]
            prev_hash = last.entry_hash
            parent_receipt_id: str | None = last.receipt_id
        else:
            prev_hash = ""
            parent_receipt_id = None

        receipt = Receipt.create(
            trace_id=trace_id,
            payload=payload,
            timestamp=timestamp,
            prev_hash=prev_hash,
            parent_receipt_id=parent_receipt_id,
        )

        if signer_key is not None:
            receipt = replace(
                receipt,
                signature=sign_hmac(receipt.entry_hash, signer_key),
                signer="hmac",
            )
        if co_sign_key is not None:
            receipt = replace(
                receipt,
                co_signature=sign_hmac(receipt.entry_hash, co_sign_key),
                co_signer="hmac",
            )

        self.receipts.append(receipt)
        return receipt

    def verify(self) -> VerifyResult:
        """Walk the whole chain, re-deriving each ``entry_hash`` and link.

        Returns a :class:`VerifyResult`. On the first failure, ``broken_at`` is
        the offending index and ``reason`` describes the break.
        """
        prev_hash = ""
        for i, receipt in enumerate(self.receipts):
            if receipt.prev_hash != prev_hash:
                return VerifyResult(
                    ok=False,
                    broken_at=i,
                    reason=(
                        f"prev_hash mismatch at index {i}: "
                        f"expected {prev_hash!r}, got {receipt.prev_hash!r}"
                    ),
                )
            recomputed = receipt.recomputed_entry_hash()
            if recomputed != receipt.entry_hash:
                return VerifyResult(
                    ok=False,
                    broken_at=i,
                    reason=(
                        f"entry_hash mismatch at index {i}: payload tampered "
                        f"(stored {receipt.entry_hash}, recomputed {recomputed})"
                    ),
                )
            prev_hash = receipt.entry_hash
        return VerifyResult(ok=True)

    def verify_signatures(self, keys: dict[int, str | bytes]) -> VerifyResult:
        """Verify each receipt's HMAC signature against ``keys`` (index -> secret).

        Only indices present in ``keys`` are checked. A receipt at a checked index
        must carry a signature that verifies under the supplied secret; if the
        receipt also has a co-signature it must verify under the same secret too.
        """
        for i, secret in keys.items():
            if i < 0 or i >= len(self.receipts):
                return VerifyResult(
                    ok=False, broken_at=i, reason=f"no receipt at index {i}"
                )
            receipt = self.receipts[i]
            if receipt.signature is None:
                return VerifyResult(
                    ok=False, broken_at=i, reason=f"receipt {i} is unsigned"
                )
            if not verify_hmac(receipt.entry_hash, secret, receipt.signature):
                return VerifyResult(
                    ok=False,
                    broken_at=i,
                    reason=f"signature verification failed at index {i}",
                )
            if receipt.co_signature is not None and not verify_hmac(
                receipt.entry_hash, secret, receipt.co_signature
            ):
                return VerifyResult(
                    ok=False,
                    broken_at=i,
                    reason=f"co-signature verification failed at index {i}",
                )
        return VerifyResult(ok=True, reason="signatures verified")
