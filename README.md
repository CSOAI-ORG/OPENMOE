# openmoe-bft

**Byzantine-fault-tolerant consensus for Mixture-of-Experts routing.**
_Every expert is a safety expert._

A standard MoE gate picks an expert with a single trainable router — and a single
compromised or buggy router can silently misroute a token to an unsafe expert.
`openmoe-bft` wraps the routing decision in a Byzantine-fault-tolerant (BFT)
consensus protocol: the decision is fanned out to **N router replicas**, their
proposals are hashed and voted, and the token is dispatched to an expert **only**
when a `2f + 1` quorum agrees (`f = floor((n - 1) / 3)`). No quorum, no dispatch.

## The Empire context

`openmoe-bft` is **Layer 2 (BFT Consensus Engine)** and **Layer 3 (OpenScore
Safety Experts)** of the 12-layer OpenMoE-BFT Empire — an open-source AI
governance stack built on "standing on the shoulders of giants": OpenMoE provides
the base model (Layer 1), this package adds Byzantine consensus over routing and
the 14-expert safety layer, and the upper layers add memory, planning,
observability, the MEOK compliance gateway, cryptographic audit receipts, x402
monetization, and A2A/MCP interoperability. OpenMoE built the brain; this is the
conscience.

## Install

```bash
pip install openmoe-bft            # core: zero runtime dependencies (stdlib only)
pip install "openmoe-bft[mcp]"     # + MCP transport for expert registration
pip install "openmoe-bft[x402]"    # + x402 per-consensus / per-expert-call paywall
```

## Quickstart

```python
from openmoe_bft import BFTRouter, NoConsensusError

# Data-driven experts: key -> callable. Keys are the 14 safety-expert ids/names.
experts = {
    1: lambda tok: f"EU AI Act expert handled {tok}",
    2: lambda tok: f"NIST RMF expert handled {tok}",
    3: lambda tok: f"DORA/NIS2 expert handled {tok}",
}

# Router replicas independently propose an expert assignment for each token.
def replica_a(tok): return 1
def replica_b(tok): return 1
def replica_c(tok): return 1
def replica_d(tok): return 2   # outvoted Byzantine replica

router = BFTRouter(experts, replicas=[replica_a, replica_b, replica_c, replica_d])

decision = router.route("token-42", session_id="req-1")
# n=4, f=1, quorum=3: replicas a/b/c agree on expert 1 -> dispatched.
assert decision.consensus and decision.dispatched
print(decision.expert_key, "->", decision.result)

# On a split vote, nothing is dispatched (or use strict=True to raise):
try:
    router.route("token-99", session_id="req-2", strict=True)
except NoConsensusError as e:
    print("no quorum:", e)
```

### MCP → Expert registration protocol

```python
from openmoe_bft import register_expert

candidate = {
    "expert_id": 1,
    "name": "EU AI Act Compliance",
    "tools": [{"name": "scan_agent_card"}],
    "metadata": {"riskAssessment": {"annexIII": "high-risk"}},
}
result = register_expert(candidate)        # transport-agnostic, no network
assert result.accepted and result.expert_id == 1
```

## The 14 OpenScore safety experts

| ID | Name | Domain | Regulation | A2A field |
|---:|------|--------|-----------|-----------|
| 1 | EU AI Act Compliance | compliance | eu_ai_act | `metadata.riskAssessment` |
| 2 | NIST RMF Risk Scoring | compliance | — | `metadata.nistRmfScore` |
| 3 | DORA / NIS2 Incident Taxonomy | compliance | dora | `metadata.ictRiskFramework` |
| 4 | Neurorights (GDPR Art 9) | governance | — | `metadata.neurorightsPolicy` |
| 5 | x402 Payment Validation | monetization | — | `metadata.x402Receipt` |
| 6 | MCP Tool Attestation | security | — | `metadata.mcpAttestation` |
| 7 | Blockchain Verification | verification | — | `metadata.blockchainAnchor` |
| 8 | Human-in-the-Loop Gate | governance | — | `metadata.hitlContact` |
| 9 | Red Team Automation | security | — | `metadata.redTeamReport` |
| 10 | Blue Team Defense | security | — | `metadata.blueTeamStatus` |
| 11 | Continuous Monitoring | security | — | `metadata.continuousMonitoring` |
| 12 | Fuzzing / Mutation | security | — | `metadata.fuzzingReport` |
| 13 | Autonomous Auditor | verification | — | `metadata.autonomousAudit` |
| 14 | Web Crawler / Extractor | verification | — | `metadata.webExtractionPolicy` |

## Roadmap

The next milestone is the **upstream OpenMoE fork integration**
([XueFuzhao/OpenMoE](https://github.com/XueFuzhao/OpenMoE)): wiring `BFTRouter`
into OpenMoE's token-choice gating layer so every routed token is
consensus-validated against the 14 safety experts.

## License

[Apache-2.0](LICENSE) © 2026 MEOK AI Labs.
