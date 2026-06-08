# Repo Onboard

Repo Onboard scans a local repository and creates a Markdown onboarding report
that helps a developer understand the project structure, likely entry points,
tooling, tests, curated file snippets, and open questions.

## Quick Start

```bash
python -m onboard scan /path/to/repo --no-llm
```

After installing the package, the console script is available too:

```bash
onboard scan /path/to/repo --output onboarding.md
```

Useful scan options:

```bash
onboard scan /path/to/repo --max-files 1000 --snippet-bytes 4000
```

- `--max-files` limits how many files are inspected.
- `--snippet-bytes` limits how many bytes are read from each relevant text file.
- `--no-llm` disables the optional AI explanation.

The scanner only reads curated files such as READMEs, project manifests,
Docker/Make files, CI files, and likely entry points. Secret-like files such as
`.env` and private keys are skipped.

The first version works without an LLM. If `GEMINI_API_KEY`, `GOOGLE_API_KEY`,
or `OPENAI_API_KEY` is set and `--no-llm` is omitted, the CLI adds a short
AI-generated onboarding narrative based only on the deterministic scan summary.

## Gemini Free Tier Test

1. Create an API key in Google AI Studio.
2. Export the key:

```bash
export GEMINI_API_KEY="your-key"
```

3. Run a scan with the Gemini-backed explanation:

```bash
PYTHONPATH=src python -m onboard scan /path/to/repo
```

The default Gemini model is `gemini-2.5-flash`. You can override it:

```bash
export ONBOARD_GEMINI_MODEL="gemini-2.5-flash-lite"
```
