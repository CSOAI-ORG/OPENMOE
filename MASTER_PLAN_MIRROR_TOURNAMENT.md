# OpenMoE × MEOK — Mirror + Self-Improvement Tournament: Master Plan

**Date:** 2026-06-07
**Author:** Claude (Opus 4.8) for Nick Templeman / MEOK AI Labs
**Status:** PLAN ONLY — no code written yet. Approve before build.
**Companion:** `~/Downloads/OPENMOE_BFT_EMPIRE_SPEC_v1.0.md` (the 12-layer empire spec)

---

## 0. Decisions locked (from Nick, 2026-06-07)

| Question | Decision |
|---|---|
| A/B mirror meaning | **Two funnels, one engine.** openmoe.ai = developer/open-source framing; meok.ai = consumer/enterprise framing. Same underlying product. Shared analytics + comparison. |
| Competition style | **Internal self-improvement tournament** (private). The 14 safety experts / councils compete; BFT consensus picks winners; losers retrain (**learn**); drift gets corrected (**align**). No public leaderboard. |
| This session | **Write the master plan first.** No code until approved. |

---

## 1. The one insight that shapes everything

**The competition engine already exists in the codebase.** `openmoe_bft/harmony.py` contains a `ShadowArena`:

- `register(VariantResult)` — enrol competitors (funnel variants OR expert variants)
- `harmony_score(...)` — weighted multi-metric score
- `_two_proportion_z(...)` — statistical significance (this is a real A/B test)
- `score_all()` / `select()` → `SelectionVerdict` → `seal_verdict()` — pick a winner, sign the result

That single class is **both** an A/B-test statistics engine **and** a tournament selector. So Nick's asks are not separate systems — they are **one scoring spine with three consumers and four surfaces**:

```
                    ┌──────────────────────────────┐
                    │   harmony.ShadowArena (spine) │
                    │   score → z-test → seal       │
                    └───────────────┬──────────────┘
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
 CONSUMER A: Funnel A/B    CONSUMER B: Expert tournament   CONSUMER C: MCP scoreboard
 variants = {openmoe,meok} variants = {14 experts/configs} variants = {290+ fleet MCPs}
 metric = conversion       metric = compliance+reputation  metric = openmcp 0–100 score
 winner = better funnel    winner = promoted expert config  rank   = fleet leaderboard

 SURFACES:
   openmoe.ai   → dev funnel            (public)
   meok.ai      → consumer funnel       (public)
   openscore.ai → tournament dashboard  (PRIVATE/auth)
   proofof.ai   → MCP scoreboard        (public, proof-of-compliance)

 SCORING ENGINE for proofof.ai = openmcp (meok-cross-post): audits each MCP 0–100
 vs FLEET_BASE.md (A–E), cross-posts to 6 registries, KEEPS THE BOARD IN TUNE.
```

Everything else (BFT, debate, reputation, covenants, memory, SOV3 retrain, openmcp) already exists and plugs into this spine. We are **wiring, not inventing.**

---

## 2. Verified current state (checked live 2026-06-07)

| Asset | State | Note |
|---|---|---|
| openmoe.ai | ✅ LIVE (200) | GitHub Pages, `CSOAI-ORG/OPENMOE`, CNAME + HTTPS approved |
| meok.ai | ✅ LIVE (200) | `www.meok.ai`, Next.js UI in `~/meok-ai/ui` |
| councilof.ai | ✅ LIVE | |
| **proofof.ai** | ✅ LIVE | Already serves **"MEOK Compliance MCP Catalogue"** — the base the MCP scoreboard extends |
| **openmcp** (`CSOAI-ORG/openmcp` = `meok-cross-post`) | ✅ exists, 82 tests | Scores each MCP **0–100** vs `FLEET_BASE.md` (A–E) + cross-posts to Smithery/MCP Registry/Docker/Glama/MCPize/PulseMCP. This is the scoreboard's scoring + sync engine. Verify it's on PyPI. |
| **openscore.ai** | ❌ **DOWN** (timeout) | This is "The Score" domain — the natural tournament dashboard surface |
| `openmoe-bft` package | ✅ rich code, 183 tests claimed | `~/openmoe-bft/openmoe_bft/` — bft, moe, routing, experts, harmony, reputation, debate, covenants, memory, red_team, pqc, receipts, bazaar, a2a |
| **`openmoe-bft` on PyPI** | ❌ **404 — NOT published** | README claims it is. Distribution claim is currently false. |
| `openscore`/`openalign`/`openlearn` repos | ❌ do not exist | Blueprinted "AVAILABLE" only |
| openmoe.ai analytics | ❌ none in `web/` | No PostHog/GA — nothing to A/B-measure yet |
| meok.ai analytics | ⚠️ deps present | PostHog/analytics in `~/meok-ai/ui` package.json — needs confirming it's wired + shared |
| `CSOAI-ORG/safetyofai` | exists, has "model leaderboard" | Prior art; reuse patterns, don't duplicate |
| SOV3 neural retrain | ✅ running w/ rollback | `~/.sov3_neural_retrain.log` — last run 1 improved / 4 rolled back. This IS the learn loop. |

**Three verified breakages to fix regardless of the big build:** openscore.ai down, openmoe-bft not actually on PyPI, openmoe.ai has no analytics.

---

## 3. Engine inventory — what we already have vs. what to build

| Tournament need | Already in code | Gap to build |
|---|---|---|
| Enrol competitors | `harmony.ShadowArena.register` + `VariantResult` | thin adapters (funnel events → VariantResult; expert run → VariantResult) |
| Score competitors | `harmony.harmony_score`, `HarmonyMetric` | metric weight config per consumer |
| Significance test | `harmony._two_proportion_z` | none |
| Pick winner | `harmony.select`/`SelectionVerdict`, `bft.BFTLedger`, `debate.run_debate` | wire BFT quorum around the verdict |
| **Learn** (losers retrain) | `memory.MemoryPyramid` (observe/distill/consolidate/dream), SOV3 `trigger_neural_retrain` (with rollback) | feed winner traces → memory → retrain trigger; "openlearn" wrapper |
| **Align** (drift correction) | `covenants.CovenantRegistry.check/trust_score`, `reputation.agent_fico`, `reputation.web_of_trust_score` | drift detector → covenant breach → reputation penalty; "openalign" wrapper |
| Adversarial pressure | `red_team.RedTeamOrchestrator` | include red-team score as a tournament metric |
| Sign/seal results | `harmony.seal_verdict`, `receipts.py`, `covenants.inscribe` | persist sealed verdicts to a ledger |
| Score surface | — | openscore.ai internal dashboard (revive domain) |
| Funnel telemetry | — | PostHog (or chosen) on BOTH sites, shared event taxonomy |

**Net:** the hard parts (stats, consensus, reputation, memory, retrain-with-rollback) exist. The build is adapters + telemetry + a dashboard + fixing distribution.

---

## 4. Workstream A — A/B Mirror (two funnels, one engine)

**Goal:** openmoe.ai (dev framing) and meok.ai (consumer framing) sell the same engine; we measure which framing converts and feed the result into harmony.ShadowArena.

1. **Shared event taxonomy** — one canonical event set across both sites:
   `page_view`, `cta_click`, `signup_start`, `signup_complete`, `activation` (first MCP call / first score), `checkout_start`, `purchase`. Every event carries `funnel` ∈ {`openmoe-dev`, `meok-consumer`} and a stable `anon_id`.
2. **Instrument both sites** with the SAME analytics backend (recommend PostHog — already in meok deps; openmoe.ai currently has none). One project, two funnel tags.
3. **Single source of truth for the "engine"** — both funnels CTA into the same backend (the openmoe-bft MCP / meok gateway), so we compare framing, not product.
4. **Comparison feed** — a small job pulls funnel conversion counts → builds two `VariantResult`s → `ShadowArena.select()` → `_two_proportion_z` tells us if the difference is significant.
5. **Dashboard** — surface "openmoe-dev vs meok-consumer: conversion, significance, current leader" (lives on the openscore.ai internal dashboard, §6).

**Acceptance:** a real visitor on either site produces events in one project tagged by funnel; a nightly job emits a signed `SelectionVerdict` naming the leading funnel with a p-value.

---

## 5. Workstream B — Internal Self-Improvement Tournament (learn + align)

**Goal:** the 14 safety experts (and council/model/prompt configs) continuously compete; winners get promoted; losers learn; drift is aligned away. Private — no public arena.

**The loop (one "season"):**
1. **Enrol** — each expert config becomes a `VariantResult` (from `experts.py`'s 14 `SafetyExpert`s + alternate configs).
2. **Compete** — run a fixed task battery (EU AI Act scoring cases + `red_team` probes). Each produces compliance/accuracy/latency/red-team metrics.
3. **Debate** — `debate.run_debate` over contested calls before scoring (mirrors spec's "debate = BFT consensus").
4. **Consensus pick** — `harmony.select` produces a `SelectionVerdict`; wrap it in `bft.BFTLedger` so a winner is promoted **only on 2f+1 quorum** (no quorum, no promotion — same safety contract as routing).
5. **LEARN** — winner traces → `memory.MemoryPyramid.observe/distill/consolidate` (dream consolidation) → trigger SOV3 `trigger_neural_retrain` for the relevant model. **Keep SOV3's rollback-on-degradation** (the log shows 4/5 rolled back last run — that guardrail stays; it's the whole point).
6. **ALIGN** — `covenants.CovenantRegistry.check` detects breaches (drift = covenant violation); `reputation.agent_fico` / `web_of_trust_score` down-weight drifted experts so they lose next season. Persisted via `covenants.inscribe` + `receipts`.
7. **Seal** — `harmony.seal_verdict` signs the season result → append to a tournament ledger.

**Cadence:** run as a scheduled "season" (e.g. nightly, alongside existing SOV3 overnight jobs). Reuse the guardian/heartbeat infra already running.

**Acceptance:** a season produces a signed verdict, a promoted expert config, at least one learn-trigger (with rollback honoured), and an alignment adjustment to reputation — all persisted and reproducible.

---

## 5b. Workstream D — proofof.ai MCP Scoreboard (public), kept in tune by openmcp

**Goal:** turn proofof.ai's existing "MEOK Compliance MCP Catalogue" into a live, scored, **public MCP scoreboard** of the whole fleet (290+ MCPs) — ranked by the openmcp 0–100 audit score, with signed proof-of-compliance per entry. openmcp keeps it **in tune** (re-audit + re-sync across registries).

1. **Score source = openmcp** — `meok-cross-post` already audits a repo 0–100 vs `FLEET_BASE.md` with an A–E category breakdown. Run it across the fleet → one score row per MCP (overall + A/B/C/D/E sub-scores + pass/fail vs the ≥80 merge gate).
2. **Scoreboard data model** — `{mcp, score, A..E, registries_present[], attestation_id, last_audited}`. Persist as a JSON/manifest proofof.ai renders (matches openmoe.ai's static-on-Pages style; or a small API if hosted on Vercel like meok).
3. **"In tune" sync loop** — a scheduled openmcp run re-audits changed repos and re-cross-posts, then refreshes the scoreboard manifest. The board never drifts from reality: score on the board == openmcp's current audit == registry presence.
4. **Feed the spine** — each MCP's openmcp score becomes a `VariantResult` in `harmony.ShadowArena` (CONSUMER C) so the public scoreboard and the internal scoring use the *same* engine; ranking + significance come for free.
5. **Proof layer** — attach the existing signed attestation (proofof.ai's current catalogue already does signed EU AI Act/DORA/NIS2/CRA/CSRD) to each scoreboard row, so a score is *provable*, not just claimed.

**Acceptance:** proofof.ai shows a ranked, scored board of the fleet; each row links a signed attestation; a scheduled openmcp run updates scores + registry presence without manual steps; scores reconcile with `harmony.ShadowArena`.

**Open items:** `meok-cross-post`/openmcp is **NOT on PyPI** (404, verified 2026-06-07) despite its README's `pip install` claim — publish it in P0 (same gap as openmoe-bft). Where does proofof.ai host (Pages vs Vercel) — decides static-manifest vs API.

---

## 6. Workstream C — Fix verified breakages (do first; low effort, high trust)

1. **Revive openscore.ai** — diagnose the timeout (DNS / Pages / Vercel), then point it at an **internal tournament + funnel dashboard** (since competition is private, this is auth-gated, not public).
2. **Actually publish `openmoe-bft` to PyPI** — use the gate-protected harness at `mcp-marketplace/_tooling/` (per memory: only ships importable wheels). Make the README's claim true. Then squat `openscore`/`openalign`/`openlearn` as placeholders pointing at the same engine.
3. **Add analytics to openmoe.ai** (`web/`) — prerequisite for Workstream A.

---

## 7. Sequence & milestones

| Phase | Work | Gate |
|---|---|---|
| **P0 — Fix & instrument** (fastest) | Workstream C: revive openscore.ai, publish openmoe-bft (+verify openmcp on PyPI), add analytics to both sites w/ shared taxonomy | openscore.ai 200; `pip install openmoe-bft` works; events flowing tagged by funnel |
| **P1 — Mirror + scoreboard live** | Workstream A (funnel comparison + dashboard) **+ Workstream D** (run openmcp across fleet → first scored proofof.ai board) | nightly signed funnel `SelectionVerdict` with p-value; proofof.ai shows ranked fleet scores |
| **P2 — Tournament v1** | Workstream B steps 1–4 (enrol → compete → debate → BFT pick), read-only (no retrain yet) | signed season verdict + promoted config, no model changes |
| **P3 — Learn + Align** | Workstream B steps 5–6 wired to SOV3 retrain (rollback on) + covenant/reputation drift correction | one full self-improvement season end-to-end, reversible |
| **P4 — Harden** | red-team metric in tournament, receipts ledger, dashboard polish, docs | reproducible season; audit trail |

---

## 8. Guardrails (non-negotiable)

- **Rollback everywhere** — keep SOV3's degrade→rollback (last run rolled back 4/5; that's correct behaviour, not a bug). No tournament season may push an unreversible model change.
- **BFT gate on promotion** — no expert promoted without 2f+1 quorum, same as routing.
- **Private by default** — tournament + funnel dashboards auth-gated. Nick chose internal; nothing public until he says so.
- **Care membrane** — tournament tasks and any agent actions pass the existing ethics gate (consistent with Gods Eye / care-gated robotics policy).
- **No false claims** — don't re-state "published"/"183 tests passing" until verified green in CI.

---

## 9. Decisions LOCKED (Nick, 2026-06-07)

1. **Analytics = PostHog.** Already in meok.ai deps; one tool covers funnels + events + A/B experiments + feature flags + session replay (Plausible/Umami are page-level only). Instrument both sites, tag every event `funnel` ∈ {`openmoe-dev`,`meok-consumer`}.
2. **openscore.ai DROPPED.** (Registered/parked on Namecheap but not core.) Internal tournament is **PRIVATE** — VM/local + repo artifacts, no public domain. Public competitive surface = **proofof.ai**. Dev landing stays **openmoe.ai** (GitHub Pages).
3. **Tournament cadence = DAILY** (piggybacks SOV3 overnight jobs).
4. **Funnel = ONE shared backend/signup, two branded skins.** A/B only valid if the product is held constant. This IS the "one funnel, not 50 Stripe links" fix: consolidate to one auth + one Stripe ladder (via `meok-stripe-acp-checkout-mcp`); openmoe.ai + meok.ai just tag the source.
5. **proofof.ai = Vercel (confirmed live), registrar Namecheap.** MCP scoreboard = **live API on Vercel** (not static manifest) — reads `mcp-marketplace/_scorecard/fleet_scorecard.json`, serves `/scorecard/<name>.html`, runs the daily openmcp tune.

---

## 10. One-line summary

We already own the competition engine (`harmony.ShadowArena`), the learn/align parts (SOV3 retrain + covenants + reputation + memory), and the MCP scoring/sync engine (`openmcp`/`meok-cross-post`). The job is to (a) fix three real breakages, (b) point two funnels at one analytics spine, (c) wire the 14 experts into a nightly BFT-gated season that learns and self-aligns with rollback — on a revived private **openscore.ai**, and (d) turn the existing **proofof.ai** catalogue into a public, openmcp-scored MCP scoreboard kept in tune across registries. One scoring spine, three consumers, four surfaces.
