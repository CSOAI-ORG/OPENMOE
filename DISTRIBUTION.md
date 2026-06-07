# DISTRIBUTION.md — list openmoe-bft everywhere

The complete "list it everywhere" submission checklist for **openmoe-bft**. Each entry has:
the exact submission URL, what it needs (publish-first? account? PR?), the prepared payload to
paste, and whether the openMCP `meok-cross-post` CLI can automate it.

**Gating legend**
- **UNGATED-READY** — can be submitted the moment publishing unblocks; payload is prepared below.
- **GATED-ON-PUBLISH** — blocked until the PyPI package and/or a public GHCR image and/or the
  GitHub repo is public; do this step after the gate clears.

**Canonical metadata (single source of truth — keep all directories consistent):**
- Name: `openmoe-bft` (namespace `io.github.csoai-org/openmoe-bft`)
- Description: *Byzantine-fault-tolerant consensus for MoE routing plus the OpenScore safety-expert governance layer (EU AI Act, A2A, red-team) exposed as MCP tools.*
- Repo: https://github.com/CSOAI-ORG/OPENMOE
- Homepage: https://openmoe.ai
- License: Apache-2.0
- PyPI: `openmoe-bft`
- Transport: streamable-http; tools: `evaluate_eu_ai_act`, `validate_agent_card`, `red_team_scan`, `bft_quorum`

---

## 0. PyPI (the foundational gate)

- **URL:** https://upload.pypi.org/legacy/ (via `twine upload dist/*`)
- **Needs:** a PyPI account + API token for the `openmoe-bft` project. The wheel/sdist are already in `dist/`.
- **Payload:** metadata is read from `pyproject.toml` (name, version 0.1.0, Apache-2.0, keywords, classifiers).
- **Automatable via openMCP?** No — `meok-cross-post` audits/cross-posts directory listings, it does not publish to PyPI.
- **Gate status:** **GATED-ON-PUBLISH** — this *is* the gate. Most other entries depend on this.
- **Command:** `python -m twine upload dist/*`

---

## 1. MCP Registry (registry.modelcontextprotocol.io)

- **URL:** https://registry.modelcontextprotocol.io  → `POST /v0/publish`
- **Needs:** GitHub-based auth (PAT → JWT exchange). The PyPI package should exist first (the registry verifies the pypi identifier). `server.json` is already valid and present in the repo root.
- **Payload:** the repo's `server.json` (namespace `io.github.csoai-org/openmoe-bft`, pypi package `openmoe-bft`, streamable-http transport).
- **Automatable via openMCP?** **Yes** — `meok-cross-post cross-post .` POSTs `server.json` to the MCP Registry (idempotent).
- **Gate status:** **GATED-ON-PUBLISH** (waits on PyPI publish + repo public).

---

## 2. Smithery (smithery.ai)

- **URL:** https://smithery.ai → `PUT /servers/<namespace>/<name>` (display card). Manual fallback: https://smithery.ai/new
- **Needs:** a Smithery account / API key for the display-card PUT. `smithery.yaml` (declarative, no `runtime:` key) is present and enumerates all 4 tools.
- **Payload:** `smithery.yaml` (name `openmoe-bft`, displayName "OpenMoE-BFT Compliance Server", streamable-http, 4 tools).
- **Automatable via openMCP?** **Yes** — `meok-cross-post cross-post .` PUTs the display card to Smithery (idempotent).
- **Gate status:** **GATED-ON-PUBLISH** (needs repo public + Smithery API key configured).

---

## 3. Glama (glama.ai)

- **URL:** https://glama.ai/mcp/servers → "Add Server" → paste repo URL `https://github.com/CSOAI-ORG/OPENMOE`
- **Needs:** the repo to be public; `glama.json` (present) should claim CSOAI-ORG as maintainer. No public submission API — manual web form.
- **Payload:** repo URL + the canonical description above.
- **Automatable via openMCP?** No — Glama has no public API; openMCP prints this as a manual checklist line.
- **Gate status:** **GATED-ON-PUBLISH** (needs repo public).

---

## 4. MCPize (mcpize.com)

- **URL:** https://mcpize.com/developer/servers/new  (or CLI: `npm i -g mcpize && mcpize deploy`)
- **Needs:** an MCPize account; flip visibility to public in the dashboard after deploy.
- **Payload:** repo URL + canonical description; tool list (4 tools).
- **Automatable via openMCP?** No — printed as a manual checklist line.
- **Gate status:** **GATED-ON-PUBLISH** (needs repo public / account).

---

## 5. PulseMCP (pulsemcp.com)

- **URL:** https://www.pulsemcp.com/submit
- **Needs:** nothing beyond a public repo; a single ~2-minute form.
- **Payload:** repo URL + canonical description.
- **Automatable via openMCP?** No — printed as a manual checklist line.
- **Gate status:** **GATED-ON-PUBLISH** (needs repo public).

---

## 6. Docker MCP Catalog (docker/mcp-registry)

- **URL:** https://github.com/docker/mcp-registry/new → open a PR adding `servers/openmoe-bft.yaml`
- **Needs:** a public GHCR image (built from `Dockerfile.glama`) and a GitHub PR. ~24h review SLA.
- **Payload:** a `servers/openmoe-bft.yaml` entry (name, description, image ref, 4 tools). openMCP generates a Docker-catalog YAML template during cross-post.
- **Automatable via openMCP?** Partial — openMCP generates the YAML template, but the PR itself is manual.
- **Gate status:** **GATED-ON-PUBLISH** (needs public GHCR image + repo public).

---

## 7. mcp.so

- **URL:** https://mcp.so/submit
- **Needs:** public repo; web form. mcp.so also auto-indexes from the MCP Registry, so #1 may cover it.
- **Payload:** repo URL + canonical description + tool list.
- **Automatable via openMCP?** No (not in the cross-post target set) — manual.
- **Gate status:** **GATED-ON-PUBLISH** (needs repo public).

---

## 8. GitHub Topics

- **URL:** repo → About → ⚙ Topics (https://github.com/CSOAI-ORG/OPENMOE)
- **Needs:** repo public + write access. No payload publish needed.
- **Payload (topics to add):** `mcp`, `model-context-protocol`, `byzantine-fault-tolerance`, `mixture-of-experts`, `moe`, `ai-safety`, `ai-governance`, `eu-ai-act`, `compliance`, `a2a`, `consensus`, `red-team`.
- **Automatable via openMCP?** No — manual (GitHub UI / `gh api`).
- **Gate status:** **GATED-ON-PUBLISH** (needs repo public). *Topic strings are UNGATED-READY to paste.*

---

## 9. awesome-mcp-servers lists (community PRs)

- **URLs:** https://github.com/punkpeye/awesome-mcp-servers , https://github.com/wong2/awesome-mcp-servers , https://github.com/appcypher/awesome-mcp-servers
- **Needs:** repo public; a PR to each list adding a one-line entry under the right category.
- **Payload (list line):**
  `- [openmoe-bft](https://github.com/CSOAI-ORG/OPENMOE) — Byzantine-fault-tolerant consensus for MoE routing + an EU AI Act / A2A compliance toolkit (EU AI Act scoring, A2A card validation, red-team, BFT quorum) over MCP.`
- **Automatable via openMCP?** No — manual PRs.
- **Gate status:** **GATED-ON-PUBLISH** (needs repo public).

---

## Summary

| # | Directory | Automatable via openMCP | Gate |
|--:|-----------|:-----------------------:|------|
| 0 | PyPI | No | GATED-ON-PUBLISH |
| 1 | MCP Registry | Yes | GATED-ON-PUBLISH |
| 2 | Smithery | Yes | GATED-ON-PUBLISH |
| 3 | Glama | No | GATED-ON-PUBLISH |
| 4 | MCPize | No | GATED-ON-PUBLISH |
| 5 | PulseMCP | No | GATED-ON-PUBLISH |
| 6 | Docker MCP Catalog | Partial | GATED-ON-PUBLISH |
| 7 | mcp.so | No | GATED-ON-PUBLISH |
| 8 | GitHub Topics | No | GATED-ON-PUBLISH |
| 9 | awesome-mcp-servers | No | GATED-ON-PUBLISH |

**Total directories: 10.** Every payload above is **prepared and UNGATED-READY to paste**, but
each *submission* is **GATED-ON-PUBLISH** because all of them require at least the GitHub repo
(and usually the PyPI package and/or a public GHCR image) to be public first. Once PyPI publish +
repo-public clear, 3 are automatable (MCP Registry, Smithery fully; Docker catalog YAML partially)
via `meok-cross-post cross-post .`; the rest are manual web forms / PRs with the payloads above.
