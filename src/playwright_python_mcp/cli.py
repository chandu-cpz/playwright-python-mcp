from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .mcp.config import load_config
from .mcp.server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="playwright-python-mcp")
    parser.add_argument(
        "--browser",
        default="chrome",
        help="Browser or channel to use. Initial implementation defaults to chrome.",
    )
    parser.add_argument(
        "--caps",
        default="",
        help="Comma-separated list of additional capabilities to enable.",
    )
    parser.add_argument(
        "--config",
        help="Path to a JSON configuration file.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode.",
    )
    parser.add_argument(
        "--test-id-attribute",
        default="data-testid",
        help="Attribute name to use for test ids.",
    )
    parser.add_argument(
        "--vision",
        action="store_true",
        help="Legacy option, use --caps=vision instead.",
    )

    subparsers = parser.add_subparsers(dest="command")
    install_parser = subparsers.add_parser(
        "install-browser",
        help="Install Playwright browser dependencies.",
    )
    install_parser.add_argument("browsers", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "install-browser":
        cmd = [sys.executable, "-m", "playwright", "install", *args.browsers]
        raise SystemExit(subprocess.call(cmd))

    config = load_config(
        browser=args.browser,
        caps=args.caps,
        config_path=Path(args.config) if args.config else None,
        headless=args.headless,
        test_id_attribute=args.test_id_attribute,
        vision=args.vision,
    )
    server = create_server(config)
    server.run()
