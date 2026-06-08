from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .llm import generate_llm_summary
from .report import build_markdown_report
from .scanner import scan_repo


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        return _scan_command(args)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="onboard", description="Scan a local repository and create an onboarding report.")
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="Scan a local repository.")
    scan.add_argument("repo_path", help="Path to the local repository to scan.")
    scan.add_argument("--output", "-o", help="Write the Markdown report to this file.")
    scan.add_argument("--no-llm", action="store_true", help="Disable optional LLM-generated explanation.")
    scan.add_argument("--max-files", type=int, default=500, help="Maximum number of files to scan.")
    scan.add_argument("--snippet-bytes", type=int, default=4000, help="Maximum bytes to read from each relevant text file.")
    scan.add_argument("--verbose", action="store_true", help="Print scan progress details to stderr.")
    return parser


def _scan_command(args: argparse.Namespace) -> int:
    try:
        analysis = scan_repo(args.repo_path, max_files=args.max_files, snippet_bytes=args.snippet_bytes)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"scanned {analysis.scanned_files} files in {analysis.root}", file=sys.stderr)

    llm_summary = None if args.no_llm else generate_llm_summary(analysis)
    report = build_markdown_report(analysis, llm_summary=llm_summary)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
