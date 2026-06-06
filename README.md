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

## Robust aggregation

When router replicas emit *numeric* per-expert score vectors (e.g. router
logits) rather than discrete expert-key votes, `openmoe_bft.aggregators`
provides the Byzantine-robust fusion rules absorbed from ByzFL (cleanroom,
stdlib-only): `coordinate_wise_median`, `trimmed_mean`, `krum` / `multi_krum`,
and a `robust_route` convenience that aggregates and returns the argmax expert.
Up to `f` adversarial replicas cannot move the winner.

```python
from openmoe_bft import robust_route

# 7 router replicas score 3 experts; 5 honest favour expert 0,
# 2 Byzantine replicas scream for expert 2 with absurd values.
honest = [[10.0, 0.0, 0.0]] * 5
byzantine = [[-1e6, 0.0, 1e6], [-1e6, 0.0, 1e6]]
scores = honest + byzantine                     # n=7, tolerate f=2

expert = robust_route(scores, f=2, method="krum")
assert expert == 0                              # Byzantine outliers ignored
```

References: Krum — Blanchard et al., NeurIPS 2017; coordinate-wise median /
trimmed mean — Yin et al., ICML 2018.

## Debate consensus

`openmoe_bft.debate` absorbs Agent4Debate with the spec's twist —
**debate refines positions, BFT decides.** Participants ("proposers", plain
callables so any LLM backend plugs in later) argue over several rounds, each
seeing the accumulated transcript; after the final round every participant's
position is cast as a vote into the existing BFT ledger, and the same `2f+1`
quorum engine settles it.

```python
from openmoe_bft import BFTLedger, run_debate

def hold(claim):                                # a fixed-stance proposer
    return lambda transcript: (claim, f"I argue for {claim}")

proposers = {"p1": hold("A"), "p2": hold("A"),
             "p3": hold("A"), "p4": hold("B")}  # n=4, quorum 3

result = run_debate("debate-1", proposers, rounds=2, ledger=BFTLedger())
assert result.consensus and result.agreed_hash == "A"
print(result.debate.transcript)                 # full (id, message) log
```

## MoE base routing (Layer 1)

`openmoe_bft.moe` is the sparse router the whole stack sits on — cleanroom from
the OpenMoE paper ([arXiv:2402.01739](https://arxiv.org/abs/2402.01739)) plus
Switch/GShard top-k gating and Shazeer et al. (2017) noisy gating. Pure stdlib,
no copied code (the upstream repo ships no license). The BFT layer above makes
this routing Byzantine-robust; `aggregators` robustly combines several routers'
logits.

```python
from openmoe_bft import SparseMoERouter

router = SparseMoERouter(num_experts=4, k=2, capacity_factor=1.25)
result = router.route([[2.0, 0.1, 0.1, 0.1],     # token 0 -> expert 0
                       [0.1, 0.1, 3.0, 0.1]])     # token 1 -> expert 2
print(result.assignments)            # per-token [(expert, weight), ...]
print(result.load_balancing_loss)    # Switch aux loss; 1.0 == perfectly balanced
print(result.dropped)                # tokens dropped to capacity overflow
```

## EU AI Act check backend (Expert #1)

`openmoe_bft.eu_ai_act` is Expert #1's embeddable check core — 19 checks across
Articles 9–15 of Regulation (EU) 2024/1689, cleanroom from the regulation text
(full enforcement **2026-08-02**). The production MCP server is the
`eu-ai-act-compliance-mcp` flagship; this is the in-process registry.

```python
from openmoe_bft import evaluate

report = evaluate({"metadata.riskAssessment": True,
                   "metadata.humanOversight": True})
print(report.score)              # severity-weighted 0.0–1.0
print(report.blocking_failures)  # failed blocker checks
print(report.compliant)          # True only when no blockers fail
```

## Cryptographic receipts (Layer 9)

`openmoe_bft.receipts` absorbs [Signet](https://github.com/Prismer-AI/signet)
(Apache-2.0/MIT) — hash-chained, tamper-evident receipts so every BFT decision
or x402 payment can be sealed and independently verified offline. SHA-256 chain
links and HMAC-SHA256 signing are stdlib (zero deps); `pip install
openmoe-bft[ed25519]` upgrades signing to Ed25519. Bilateral co-sign supported.

```python
from openmoe_bft import AuditChain

chain = AuditChain()
r0 = chain.append({"decision": "route->expert-1"}, trace_id="t1", timestamp=1000)
r1 = chain.append({"decision": "settle x402"},      trace_id="t1", timestamp=1001)

assert chain.verify().ok            # whole chain links + hashes check out
r1.payload["decision"] = "tampered" # mutate after the fact
assert not chain.verify().ok        # tamper detected, .broken_at points to it
```

## Hierarchical memory (Layer 4 / SOV3)

`openmoe_bft.memory` absorbs
[Tencent Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)
(MIT) — the **L0→L3 pyramid**: raw conversation → atomic facts → scenarios →
durable persona traits. `dream()` is the overnight-learning pass that distills,
consolidates, forms personas, and **compacts fully-distilled raw events** (the
token-saving the spec advertises — computed honestly, not hardcoded). Promotion
steps are plug-in callables, so an LLM or heuristic extractor swaps in behind the
same interface; recall is lexical-overlap by default (vector backend plugs in the
same way). Pure stdlib.

```python
from openmoe_bft import MemoryPyramid, MemoryEvent

mem = MemoryPyramid()
mem.observe(MemoryEvent(id="e1", timestamp=1000, role="user",
                        content="prefers EU-hosted models", meta={}))
stats = mem.dream(extractor=my_extractor, clusterer=my_clusterer,
                  aggregator=my_aggregator)   # idempotent: re-running promotes 0
print(stats.token_savings_ratio)              # measured compaction
print(mem.recall("EU hosting", k=3))          # top-k across tiers
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
