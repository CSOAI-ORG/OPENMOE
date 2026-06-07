"""Tiny CLI entrypoint for openmoe-bft.

Exposed as the ``openmoe-bft`` console script (see ``[project.scripts]`` in
``pyproject.toml``). It prints version / help and a quick inventory of the
fleet's safety experts; it deliberately has no heavy imports so
``openmoe-bft --version`` stays instant and dependency-free.
"""

from __future__ import annotations

import sys

from . import __version__


_USAGE = """\
openmoe-bft — Byzantine-fault-tolerant consensus for MoE routing.

Usage:
  openmoe-bft [--version | -V]    Print the installed version and exit.
  openmoe-bft [--help | -h]       Print this help and exit.
  openmoe-bft experts             List the registered safety experts.
  openmoe-bft serve               Hint for launching the MCP server.

The MCP compliance server lives in `server.py` at the repository root and is
launched with `python server.py` (streamable-http transport).
"""


def main(argv: "list[str] | None" = None) -> int:
    """Console-script entrypoint. Returns a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    cmd = args[0]

    if cmd in ("-V", "--version", "version"):
        print(f"openmoe-bft {__version__}")
        return 0

    if cmd == "experts":
        from .experts import EXPERTS

        for expert in EXPERTS:
            print(f"{expert.expert_id}\t{expert.domain}\t{expert.name}")
        return 0

    if cmd == "serve":
        print(
            "Run the MCP server with:  python server.py\n"
            "(FastMCP, streamable-http transport — see server.py)"
        )
        return 0

    print(f"openmoe-bft: unknown command {cmd!r}\n", file=sys.stderr)
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
