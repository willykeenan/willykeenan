# codex-lens

A read-only inspector for local OpenAI Codex threads, from the desktop app or the CLI. It has no dependencies beyond the standard library and runs on the macOS system `python3`.

It shows what every thread is doing:
- status: `running`, `stalled`, `awaiting_approval`, `waiting_on_user`, `aborted` or `idle`
- the current plan
- commands and failures
- files touched
- git branch
- tokens and context-window pressure
- the last exchange

Output is Markdown, JSON or a self-contained HTML dashboard, with secrets redacted.

```bash
python3 codex_lens.py list --since 72
python3 codex_lens.py list --project "PID Migration"
python3 codex_lens.py show "Core Engineer" [--full]
python3 codex_lens.py export --project "PID Migration" --out ~/.codex-lens/exports/now
python3 codex_lens.py discover
```

Sources it reads under `$CODEX_HOME` (default `~/.codex`):
- `sessions/**/rollout-*.jsonl`, `archived_sessions/`: transcripts, in both the current `{timestamp,type,payload}` format and the legacy pre-2025-09 format
- `*index*.jsonl`: thread renames
- `*.sqlite`: any table with an id column plus a title or cwd column, opened read-only
- `config.toml`: only the model, approval and sandbox keys, printed by `discover`

It never writes inside `$CODEX_HOME`. `export` refuses an output directory inside it.

Claude sessions use this through the `codex-lens` skill (`.claude/skills/codex-lens/SKILL.md`), which covers running it on the Mac directly or through the Remote Control bridge from a cloud session.
