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

Both stdlib-only; 27 tests; "debate refines, BFT decides."

## Queued 🍴 (verified EAT-NOW — real, permissive, valuable)

| Target | Source | License | Mode | Plan |
|---|---|---|---|---|
| **OpenMoE** router | XueFuzhao/OpenMoE | **NO LICENSE → no-vendor** | cleanroom | `SparseMLP` top-k/noisy gating from arXiv:2402.01739 → `openmoe_bft/moe.py`. HF weights (OrionZheng) are separately Apache-2.0. |
| **AIR Blackbox** | airblackbox/gateway | Apache-2.0 | vendor | 51 EU AI Act checks (Art 9-15) + AI-BOM → Expert #1 backend; `pip install air-blackbox`, has MCP server. |
| **Signet** | Prismer-AI/signet | Apache+MIT | vendor | Ed25519 + SHA-256 hash-chain receipts → audit/receipt layer (Layer 9). |
| **Nobulex** | arian-gogani/nobulex | MIT | vendor/adapter | Covenant pre-commitment + breach propagation → OpenScore trust score. |
| **Tencent Agent Memory** | TencentCloud/TencentDB-Agent-Memory | MIT | adapter | L0→L3 memory pyramid as SOV3 backend (Layer 4); −61% tokens. |
| **PyRIT** | microsoft/PyRIT | MIT | adapter | Orchestrator + attack strategies (Crescendo…) → Expert #9. |
| **RedAmon** | samugit83/redamon | MIT | adapter | Agentic network/API red-team, markdown skills → Expert #9 (complements PyRIT). |

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
*Verified 2026-06-06. Next bites by value: OpenMoE router (cleanroom), then AIR Blackbox (vendor, Expert #1).*
