from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .git_source import GitCloneError, repo_source
from .llm import LlmResult, generate_llm_report_sections
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

    scan = subparsers.add_parser("scan", help="Scan a local repository path or Git URL.")
    scan.add_argument("repo_path", help="Local repository path or Git URL to scan.")
    scan.add_argument("--output", "-o", help="Write the Markdown report to this file.")
    scan.add_argument("--no-llm", action="store_true", help="Disable optional LLM-generated explanation.")
    scan.add_argument("--max-files", type=int, default=500, help="Maximum number of files to scan.")
    scan.add_argument("--snippet-bytes", type=int, default=4000, help="Maximum bytes to read from each relevant text file.")
    scan.add_argument("--verbose", action="store_true", help="Print scan progress details to stderr.")
    return parser


def _scan_command(args: argparse.Namespace) -> int:
    try:
        with repo_source(args.repo_path, verbose=args.verbose) as repo_path:
            if args.verbose and str(repo_path) != args.repo_path:
                print(f"cloned {args.repo_path} to {repo_path}", file=sys.stderr)
            analysis = scan_repo(repo_path, max_files=args.max_files, snippet_bytes=args.snippet_bytes)
    except (FileNotFoundError, NotADirectoryError, ValueError, GitCloneError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"scanned {analysis.scanned_files} files in {analysis.root}", file=sys.stderr)

    llm_sections: LlmResult | None = None
    if not args.no_llm:
        llm_sections = generate_llm_report_sections(analysis)
        if args.verbose:
            for warning in llm_sections.warnings:
                print(f"llm warning: {warning}", file=sys.stderr)
        if not _has_complete_llm_sections(llm_sections):
            message = "; ".join(llm_sections.warnings) or "LLM did not return all required report sections"
            print(f"error: LLM report generation failed: {message}", file=sys.stderr)
            print("hint: set GEMINI_API_KEY, GOOGLE_API_KEY, or OPENAI_API_KEY, or use --no-llm for debug output", file=sys.stderr)
            return 2
    report = build_markdown_report(analysis, llm_sections=llm_sections)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


def _has_complete_llm_sections(result: LlmResult) -> bool:
    return bool(result.summary and result.startup_guide and result.project_structure)


if __name__ == "__main__":
    raise SystemExit(main())
