# Security Policy

## Supported Versions

openmoe-bft is in active development (0.x). Security fixes are applied to the
latest released version on the `main` branch.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

Please report security vulnerabilities **privately** — do not open a public
GitHub issue for security-sensitive reports.

Email: **security@meok.ai**

Include, where possible:

- A description of the vulnerability and its impact.
- Steps to reproduce (a minimal proof of concept is ideal).
- The affected version / commit.

We aim to acknowledge reports within 3 business days and to provide a
remediation timeline within 10 business days. Coordinated disclosure is
appreciated; we will credit reporters who wish to be acknowledged.

## Scope

The MCP server (`server.py`, `mcp-wrapper.py`) and the `openmoe_bft` library
are in scope. The bearer-token middleware (`auth_middleware.py`) gates the
network transport; deployments MUST set `OPENMOE_BFT_TOKEN` in production.
