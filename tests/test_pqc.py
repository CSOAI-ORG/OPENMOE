"""Post-Quantum Armor — hardening the receipt layer.

Hermetic and OFFLINE: liboqs (``oqs``) is NOT installed in the test venv, so the
PQC wrappers must raise the clear install-hint RuntimeError and HybridSignature
must fall back to classical-only signing+verifying. No clock / network / RNG.
"""

import pytest

from openmoe_bft.pqc import (
    ML_DSA_ALG,
    ML_KEM_ALG,
    PQC_INSTALL_HINT,
    HybridSignature,
    QuantumReadiness,
    kem_ml_kem_decapsulate,
    kem_ml_kem_encapsulate,
    keypair_ml_dsa,
    keypair_ml_kem,
    pqc_available,
    quantum_readiness,
    sign_ml_dsa,
    verify_ml_dsa,
)
from openmoe_bft.receipts import AuditChain


def test_pqc_available_returns_bool():
    assert isinstance(pqc_available(), bool)
    # liboqs is absent in this venv.
    assert pqc_available() is False


def test_algorithm_names():
    assert ML_DSA_ALG == "ML-DSA-65"
    assert ML_KEM_ALG == "ML-KEM-1024"


# ── wrappers raise the clear install hint when oqs is absent ────────


@pytest.mark.parametrize(
    "call",
    [
        lambda: keypair_ml_dsa(),
        lambda: sign_ml_dsa(b"m", b"sk"),
        lambda: verify_ml_dsa(b"m", b"sig", b"pk"),
        lambda: keypair_ml_kem(),
        lambda: kem_ml_kem_encapsulate(b"pk"),
        lambda: kem_ml_kem_decapsulate(b"ct", b"sk"),
    ],
)
def test_pqc_wrappers_raise_clear_runtime_error(call):
    with pytest.raises(RuntimeError) as exc:
        call()
    assert PQC_INSTALL_HINT in str(exc.value)
    assert "liboqs" in str(exc.value)


# ── HybridSignature falls back to classical-only and still verifies ─


def test_hybrid_falls_back_to_classical_only_and_verifies():
    msg = b"sealed-decision-bytes"
    sig = HybridSignature.sign(msg, hmac_secret="s3cr3t")
    # No PQC leg because liboqs is absent.
    assert sig.is_hybrid is False
    assert sig.pqc_sig is None
    assert sig.pqc_scheme is None
    assert sig.classical_scheme == "hmac"
    # Classical-only bundle still verifies with stdlib alone.
    assert sig.verify(msg, hmac_secret="s3cr3t") is True


def test_hybrid_rejects_wrong_secret_and_tampered_message():
    msg = b"payload"
    sig = HybridSignature.sign(msg, hmac_secret="k")
    assert sig.verify(msg, hmac_secret="WRONG") is False
    assert sig.verify(b"other", hmac_secret="k") is False


def test_hybrid_ignores_pqc_keys_when_oqs_absent():
    # Even if the caller passes ML-DSA keys, with liboqs absent we degrade to
    # classical-only rather than erroring.
    sig = HybridSignature.sign(
        b"m",
        hmac_secret="k",
        ml_dsa_secret_key=b"fake-sk",
        ml_dsa_public_key=b"fake-pk",
    )
    assert sig.is_hybrid is False
    assert sig.verify(b"m", hmac_secret="k") is True


# ── quantum_readiness ───────────────────────────────────────────────


def test_quantum_readiness_classical_only_chain_reports_zero_pct():
    chain = AuditChain()
    chain.append({"x": 1}, trace_id="t", timestamp=1, signer_key="k")
    chain.append({"x": 2}, trace_id="t", timestamp=2, signer_key="k")
    r = quantum_readiness(chain)
    assert isinstance(r, QuantumReadiness)
    assert r.total == 2
    assert r.pqc_signed == 0
    assert r.classical_only == 2
    assert r.readiness_pct == 0.0
    assert "harvest-now" in r.advisory
    assert "2030" in r.advisory


def test_quantum_readiness_empty_chain():
    r = quantum_readiness(AuditChain())
    assert r.total == 0
    assert r.readiness_pct == 0.0
    assert "empty" in r.advisory


def test_quantum_readiness_counts_pqc_marked_receipt():
    chain = AuditChain()
    chain.append({"x": 1}, trace_id="t", timestamp=1, signer_key="k")  # classical
    chain.append(
        {"x": 2, "pqc_scheme": ML_DSA_ALG}, trace_id="t", timestamp=2, signer_key="k"
    )  # PQC-marked
    chain.append({"x": 3}, trace_id="t", timestamp=3)  # unsigned
    r = quantum_readiness(chain)
    assert r.total == 3
    assert r.pqc_signed == 1
    assert r.unsigned == 1
    assert r.classical_only == 1
    assert 33.0 < r.readiness_pct < 34.0
