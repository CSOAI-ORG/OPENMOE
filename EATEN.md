# EATEN.md — openmoe-bft acquisition tracker

> "We didn't build 75 tools. We found 75 brilliant open-source projects and
> connected them into one empire." — Empire spec v1.0
>
> This file tracks what we've **absorbed** (cleanroom-reimplemented or vendored),
> what's **queued**, and — critically — what we must **NOT vendor** for license
> reasons. Source of truth for fork targets: `OPENMOE_BFT_EMPIRE_SPEC_v1.0.md`
> PART 2. Verified URLs/licenses here override the spec's optimistic guesses.

Legend: 🟢 absorbed · 🍴 queued · 🔵 integrate-on-top · 🔴 skip
Modes: **cleanroom** = reimplemented from papers/specs (no code copied) ·
**vendor** = adapted permissively-licensed code with attribution ·
**adapter** = external dependency, we write the bridge.

## Absorbed 🟢

| Target | Source | License | Mode | Landed as | Citation |
|---|---|---|---|---|---|
| **ByzFL** robust aggregators | LPD-EPFL/byzfl | MIT | cleanroom | `openmoe_bft/aggregators.py` — Krum, MultiKrum, trimmed-mean, coordinate-median + `robust_route()` | Blanchard et al. NeurIPS 2017 (Krum); Yin et al. ICML 2018 (trimmed mean) |
| **Agent4Debate** debate protocol | zhangyiqun018/agent-for-debate | **GPL-3.0 → no-vendor** | cleanroom | `openmoe_bft/debate.py` — debate-rounds-as-consensus, final claims → BFT ledger | ICASSP 2026 paper (not the GPL code) |
| **OpenMoE** sparse router (Layer 1) | XueFuzhao/OpenMoE | **NO LICENSE → no-vendor** | cleanroom | `openmoe_bft/moe.py` — stable softmax, top-k + noisy gating, Switch load-balance loss, `SparseMoERouter` w/ capacity | OpenMoE arXiv:2402.01739; Switch (Fedus 2022); Shazeer 2017 |
| **AIR Blackbox** EU AI Act checks (Expert #1) | airblackbox/gateway (Apache-2.0, ref only) | cleanroom from regulation | cleanroom | `openmoe_bft/eu_ai_act.py` — 19 checks Art 9-15, severity-weighted `evaluate()` → `ComplianceReport` | Regulation (EU) 2024/1689 |
| **Signet** receipts (Layer 9) | Prismer-AI/signet (Apache-2.0/MIT) | reimpl (permissive) | `openmoe_bft/receipts.py` — SHA-256 hash-chain, HMAC-SHA256 signing (stdlib) + optional Ed25519 `[ed25519]` extra, bilateral co-sign, `AuditChain.verify()` tamper detection | Signet, attribution in docstring |
| **Tencent Agent Memory** (Layer 4 / SOV3) | TencentCloud/TencentDB-Agent-Memory (MIT) | cleanroom | `openmoe_bft/memory.py` — L0→L3 pyramid (raw→atom→scenario→persona), plug-in distill/consolidate/aggregate, `dream()` consolidation + L0 compaction (idempotent), lexical recall | published architecture |
| **Nobulex** covenants + trust | arian-gogani/nobulex (MIT) | cleanroom | `openmoe_bft/covenants.py` — covenant inscription, action audit, breach severity, web-of-trust `trust_score()` + propagation; `expert_covenants()` maps the 14 experts | published PROTOCOL |
| **PyRIT + RedAmon** red-team (Expert #9) | microsoft/PyRIT + samugit83/redamon (both MIT) | cleanroom | `openmoe_bft/red_team.py` — 8 attack strategies (Crescendo/BargIn/IDOR-BOLA/BFLA…) across 5 categories, `RedTeamOrchestrator`, severity-weighted `risk_score`, `to_a2a_evidence` → `metadata.redTeamReport` | PyRIT + RedAmon, attribution in docstring |

Stdlib-first; 131 tests across the eight absorption modules. "Debate refines, BFT decides"; "every expert is a safety expert"; every decision sealable as a verifiable receipt.

## Queued 🍴 (verified EAT-NOW — real, permissive, valuable)

| Target | Source | License | Mode | Plan |
|---|---|---|---|---|

## Integrate-on-top 🔵

| Target | Source | License | Plan |
|---|---|---|---|
| **A2A Protocol** | a2aproject/A2A | Apache-2.0 | Don't fork. Build `meok-a2a-compliance` validating A2A tasks vs EU AI Act; extract AgentCard JSON Schema as the data contract. |

## Skip 🔴 (spec was wrong / not worth it)

- **LangGraph Approval Hub** (suryamr2002) — 2★ dormant student project; HITL API is trivially reimplementable.
- **OpenLane awesome-compliance** (theopenlane) — CC0 but it's a **markdown link list**, not a GRC backbone. Spec's description is incorrect.
- **ClusterMoE** (The-Swarm-Corporation) — 4★, AI-generated, 8mo dead, no benchmarks. Cleanroom the hierarchical-routing idea only if needed.

## ⚠️ License landmines (do not vendor code from these)

- **OpenMoE** — repo has no LICENSE file = all rights reserved. Paper + HF weights only.
- **Agent4Debate** — GPL-3.0. Cleanroom from the paper; never copy the code.

---
*Verified 2026-06-06. Absorbed (8): ByzFL, Agent4Debate, OpenMoE router, AIR Blackbox (EU AI Act), Signet (receipts), Tencent Agent Memory (SOV3), Nobulex (covenants/trust), PyRIT+RedAmon (Expert #9 red-team). Next: A2A (integrate-on-top → meok-a2a-compliance).*
