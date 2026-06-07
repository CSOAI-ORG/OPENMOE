"""openmoe-bft — FastMCP compliance server.

Exposes the OpenMoE-BFT Empire's safety + governance primitives as MCP tools
over the streamable-http transport:

  * ``evaluate_eu_ai_act``  — severity-weighted EU AI Act conformity scoring
  * ``validate_agent_card`` — A2A Agent Card compliance verdict (14 experts)
  * ``red_team_scan``       — adversarial probe sweep + risk score
  * ``bft_quorum``          — Byzantine quorum / fault-tolerance arithmetic

Import-safe: constructing ``mcp`` and registering tools has no network or
filesystem side effects. The server is only started under ``__main__``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

import openmoe_bft
from openmoe_bft.red_team import AttackResult, default_orchestrator


mcp = FastMCP("openmoe-bft")


@mcp.tool()
def evaluate_eu_ai_act(evidence: dict) -> dict:
    """Score conformity evidence against the EU AI Act conformity checks.

    ``evidence`` maps check/requirement keys to booleans (or truthy values)
    describing which controls a high-risk AI system has in place. Returns the
    severity-weighted :class:`ComplianceReport` as a dict: per-article results,
    pass/fail counts, and an overall score.
    """
    report = openmoe_bft.evaluate(evidence)
    return report.to_dict()


@mcp.tool()
def validate_agent_card(card: dict) -> dict:
    """Validate an A2A Agent Card against the Empire compliance layer.

    Builds an :class:`AgentCard` from ``card`` and runs the 14-safety-expert
    coverage check plus EU AI Act scoring over its flattened evidence. Returns
    the :class:`A2AComplianceVerdict` as a dict (score, expert coverage,
    EU AI Act sub-report).
    """
    agent_card = openmoe_bft.AgentCard.from_dict(card)
    verdict = openmoe_bft.validate_card(agent_card)
    return verdict.to_dict()


@mcp.tool()
def red_team_scan(target: dict) -> dict:
    """Run the canonical adversarial strategy sweep against ``target``.

    ``target`` describes the system under test (e.g. ``{"id": ..., "defenses":
    [...]}``). Each canonical strategy is probed with a deterministic heuristic:
    an attack "lands" only when ``target['defenses']`` does not name the
    strategy's category. Returns the :class:`RedTeamReport` as a dict, including
    a risk score in ``[0, 1]`` (1.0 == every attack defended).
    """
    target_id = str(target.get("id", "target"))
    defenses = {str(d).lower() for d in target.get("defenses", [])}

    def probe_for(strategy):
        def _probe(tgt: Any, ctx: "dict[str, Any]") -> AttackResult:
            defended = strategy.category.lower() in defenses
            return AttackResult(
                strategy_id=strategy.id,
                target_id=target_id,
                succeeded=not defended,
                severity=strategy.severity_if_successful,
                evidence=(
                    f"category {strategy.category!r} "
                    + ("covered by a declared defense" if defended else "undefended")
                ),
                timestamp=int(ctx.get("timestamp", 0)),
            )

        return _probe

    orchestrator = default_orchestrator(probe_for=probe_for)
    results = orchestrator.run(target)
    report = orchestrator.report(results)
    return report.to_dict()


@mcp.tool()
def bft_quorum(num_nodes: int) -> dict:
    """Compute Byzantine quorum arithmetic for an ``num_nodes``-node cluster.

    Returns the number of Byzantine faults tolerated (``f = floor((n-1)/3)``)
    and the agreeing-vote quorum required for consensus (``2f + 1``).
    """
    n = int(num_nodes)
    faults = openmoe_bft.tolerated_faults(n)
    quorum = openmoe_bft.quorum_size(n)
    return {
        "num_nodes": n,
        "tolerated_faults": faults,
        "quorum_size": quorum,
        "byzantine_safe": n >= 3 * faults + 1,
    }


def main() -> None:
    """Launch the MCP server on the streamable-http transport.

    Referenced by ``package.json`` (``mcp.entry = "server:main"``) and usable
    as ``python -c "import server; server.main()"``.
    """
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
