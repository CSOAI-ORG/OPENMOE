"""CLI entrypoint for openmoe-router."""

from .server import main


def main_entry() -> None:
    main()
