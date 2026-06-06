"""Layer 9 cryptographic receipts. Hermetic: stdlib only, no clock, no HOME I/O.

Timestamps are passed explicitly (1000, 1001, ...) — never read from the clock.
"""

import pytest

from openmoe_bft.receipts import (
    AuditChain,
    Receipt,
    VerifyResult,
    sign_hmac,
    verify_hmac,
    sign_ed25519,
    verify_ed25519,
)


def test_genesis_receipt_has_empty_prev_hash():
    chain = AuditChain()
    r0 = chain.append({"decision": "route->expert-1"}, trace_id="t", timestamp=1000)
    assert r0.prev_hash == ""
    assert r0.parent_receipt_id is None
    assert r0.entry_hash  # non-empty SHA-256 hex
    assert len(r0.entry_hash) == 64


def test_chain_links_prev_hash_to_prior_entry_hash():
    chain = AuditChain()
    r0 = chain.append({"step": 0}, trace_id="t", timestamp=1000)
    r1 = chain.append({"step": 1}, trace_id="t", timestamp=1001)
    r2 = chain.append({"step": 2}, trace_id="t", timestamp=1002)
    assert r1.prev_hash == r0.entry_hash
    assert r2.prev_hash == r1.entry_hash
    assert r1.parent_receipt_id == r0.receipt_id
    assert r2.parent_receipt_id == r1.receipt_id


def test_verify_ok_on_clean_chain():
    chain = AuditChain()
    for i in range(5):
        chain.append({"step": i}, trace_id="t", timestamp=1000 + i)
    result = chain.verify()
    assert isinstance(result, VerifyResult)
    assert result.ok is True
    assert result.broken_at is None


def test_verify_detects_payload_tampering():
    chain = AuditChain()
    chain.append({"step": 0}, trace_id="t", timestamp=1000)
    chain.append({"amount": "1.00"}, trace_id="t", timestamp=1001)
    chain.append({"step": 2}, trace_id="t", timestamp=1002)
    # Mutate a sealed payload in place after the fact (frozen dataclass, but the
    # payload dict is mutable) -> entry_hash no longer matches its content.
    chain.receipts[1].payload["amount"] = "9999.00"
    result = chain.verify()
    assert result.ok is False
    assert result.broken_at == 1
    assert "tampered" in result.reason


def test_hmac_sign_and_verify_roundtrip():
    chain = AuditChain()
    r = chain.append({"x": 1}, trace_id="t", timestamp=1000, signer_key="s3cret")
    assert r.signer == "hmac"
    assert r.signature is not None
    assert verify_hmac(r.entry_hash, "s3cret", r.signature) is True
    # Wrong secret is rejected.
    assert verify_hmac(r.entry_hash, "wrong", r.signature) is False


def test_verify_signatures_rejects_wrong_secret():
    chain = AuditChain()
    chain.append({"x": 1}, trace_id="t", timestamp=1000, signer_key="right")
    assert chain.verify_signatures({0: "right"}).ok is True
    bad = chain.verify_signatures({0: "nope"})
    assert bad.ok is False
    assert bad.broken_at == 0


def test_standalone_sign_hmac_helpers():
    sig = sign_hmac("deadbeef", "k")
    assert verify_hmac("deadbeef", "k", sig) is True
    assert verify_hmac("deadbeef", "other", sig) is False


def test_co_sign_stores_two_valid_signatures():
    chain = AuditChain()
    r = chain.append(
        {"decision": "approve"},
        trace_id="t",
        timestamp=1000,
        signer_key="alice",
        co_sign_key="bob",
    )
    assert r.signature is not None and r.co_signature is not None
    assert r.signer == "hmac" and r.co_signer == "hmac"
    assert verify_hmac(r.entry_hash, "alice", r.signature) is True
    assert verify_hmac(r.entry_hash, "bob", r.co_signature) is True
    # Each signature is bound to its own key.
    assert verify_hmac(r.entry_hash, "bob", r.signature) is False


def test_deterministic_receipt_id():
    # Same content + timestamp + prev_hash -> identical receipt_id.
    a = Receipt.create(trace_id="t", payload={"a": 1, "b": 2}, timestamp=1000)
    b = Receipt.create(trace_id="t", payload={"b": 2, "a": 1}, timestamp=1000)
    assert a.receipt_id == b.receipt_id  # key order is irrelevant (canonical)
    # Changing any field changes the id.
    c = Receipt.create(trace_id="t", payload={"a": 1, "b": 2}, timestamp=1001)
    assert c.receipt_id != a.receipt_id


def test_ed25519_raises_clear_runtime_error_when_pynacl_absent():
    # PyNaCl is absent in the test venv; both functions must raise clearly.
    with pytest.raises(RuntimeError, match=r"openmoe-bft\[ed25519\]"):
        sign_ed25519("deadbeef", b"\x00" * 32)
    with pytest.raises(RuntimeError, match=r"openmoe-bft\[ed25519\]"):
        verify_ed25519("deadbeef", b"\x00" * 32, "00")
