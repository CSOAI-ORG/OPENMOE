#!/usr/bin/env python3
"""Real end-to-end test for the openmoe-bft MCP server.

Boots ``server.py`` over the streamable-HTTP transport in a subprocess,
connects with the official MCP streamable-HTTP client, lists the tools,
and CALLS every tool once with a minimal valid argument — proving the
server is operationally live, not just unit-green.

This is a standalone script, NOT a pytest module: its basename does not
match ``test_*.py`` so the normal ``pytest tests/`` run never collects it
(it needs a live server). Invoke it explicitly::

    python tests/e2e_server.py

Exits 0 on success (with a clear pass line per tool) and non-zero on any
failure. The server subprocess is always killed in a ``finally`` block.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = REPO_ROOT / "server.py"

EXPECTED_TOOLS = {
    "evaluate_eu_ai_act",
    "validate_agent_card",
    "red_team_scan",
    "bft_quorum",
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_ready(host: str, port: int, proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"server exited early with code {proc.returncode} before becoming ready"
            )
        if _port_open(host, port):
            return
        time.sleep(0.25)
    raise TimeoutError(f"server did not open {host}:{port} within {timeout}s")


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _content_text(result) -> str:
    """Concatenate text content blocks from a CallToolResult."""
    parts = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts)


def _payload(result) -> dict:
    """Return the tool's dict payload.

    Newer FastMCP fills ``structuredContent``; older builds only serialise the
    return value into a JSON text block. Handle both so the shape assertions
    work across versions.
    """
    if result.structuredContent:
        return result.structuredContent
    text = _content_text(result).strip()
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
    return {}


async def _exercise(host: str, port: int) -> None:
    url = f"http://{host}:{port}/mcp"
    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("PASS  initialize: session established")

            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            missing = EXPECTED_TOOLS - names
            _check(not missing, f"missing expected tools: {missing}")
            print(f"PASS  list_tools: all expected tools present ({sorted(names)})")

            # 1) evaluate_eu_ai_act
            r = await session.call_tool(
                "evaluate_eu_ai_act",
                {"evidence": {"metadata.riskAssessment": True}},
            )
            _check(not r.isError, f"evaluate_eu_ai_act errored: {_content_text(r)}")
            sc = _payload(r)
            _check(bool(sc), f"evaluate_eu_ai_act unexpected shape: {sc!r}")
            print(f"PASS  evaluate_eu_ai_act -> {sorted(sc)[:6]}")

            # 2) validate_agent_card
            card = {
                "name": "t",
                "description": "",
                "version": "1",
                "url": "https://x/a",
                "capabilities": {},
                "skills": [],
                "metadata": {"riskAssessment": True},
            }
            r = await session.call_tool("validate_agent_card", {"card": card})
            _check(not r.isError, f"validate_agent_card errored: {_content_text(r)}")
            sc = _payload(r)
            _check(bool(sc), "validate_agent_card empty result")
            print(f"PASS  validate_agent_card -> {sorted(sc)[:6]}")

            # 3) red_team_scan
            r = await session.call_tool(
                "red_team_scan",
                {"target": {"id": "t", "defenses": ["RT-CRESCENDO"]}},
            )
            _check(not r.isError, f"red_team_scan errored: {_content_text(r)}")
            sc = _payload(r)
            _check(bool(sc), "red_team_scan empty result")
            print(f"PASS  red_team_scan -> {sorted(sc)[:6]}")

            # 4) bft_quorum
            r = await session.call_tool("bft_quorum", {"num_nodes": 7})
            _check(not r.isError, f"bft_quorum errored: {_content_text(r)}")
            sc = _payload(r)
            _check(
                sc.get("num_nodes") == 7 and "quorum_size" in sc,
                f"bft_quorum unexpected shape: {sc!r}",
            )
            print(
                f"PASS  bft_quorum(7) -> tolerated_faults="
                f"{sc.get('tolerated_faults')} quorum_size={sc.get('quorum_size')}"
            )


def main() -> int:
    host = "127.0.0.1"
    port = _free_port()

    tmp_home = tempfile.mkdtemp(prefix="e2e-omb-home-")
    env = dict(os.environ)
    env["HOME"] = tmp_home
    # server.main() reads HOST/PORT and steers FastMCP's settings to bind here.
    env["HOST"] = host
    env["PORT"] = str(port)

    proc = subprocess.Popen(
        [sys.executable, str(SERVER_PY)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        try:
            _wait_ready(host, port, proc)
        except Exception:
            # surface server logs to help debugging
            try:
                out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            except Exception:
                out = ""
            print("--- server output ---", file=sys.stderr)
            print(out, file=sys.stderr)
            raise
        print(f"PASS  boot: server live on http://{host}:{port}/mcp (pid {proc.pid})")
        asyncio.run(_exercise(host, port))
        print("\nE2E OK: all openmoe-bft tools answered over streamable-HTTP")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\nE2E FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
