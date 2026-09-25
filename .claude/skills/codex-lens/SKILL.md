---
name: codex-lens
description: See into and audit Will's local OpenAI Codex conversations (Codex desktop app / CLI threads), including what each thread is doing, whether it is running, stalled, waiting on him or blocked on an approval, its current plan, the commands that failed, the files it touched, tokens and context pressure. Use whenever Will mentions Codex threads, agents, conversations or projects (e.g. "PID Migration"), asks what his Codex agents are doing, or shares a screenshot of the Codex sidebar. Codex data lives only on his Mac, so from a cloud session this skill routes through the Mac Remote Control bridge.
---

# codex-lens

Codex keeps every thread on the Mac under `~/.codex`:
- `sessions/YYYY/MM/DD/rollout-*.jsonl` holds one transcript per thread (`archived_sessions/` for archived threads).
- Thread names are in `session_index.jsonl` and/or a `state_*.sqlite` threads table.
- A thread's project in the app sidebar is its working directory (`cwd`).

None of this is visible to the claude.ai session APIs, which is why `list_sessions` never shows Codex threads.

`tools/codex-lens/codex_lens.py` (this repo) is a read-only, stdlib-only parser for all of it. It never writes inside `~/.codex`, opens SQLite read-only and redacts secrets from every exported string.

## 1. Get the data

### A. Shell on the Mac (`~/.codex` exists)

```bash
L=~/.codex-lens/codex_lens.py
[ -f $L ] || { mkdir -p ~/.codex-lens && curl -fsSL \
  https://raw.githubusercontent.com/willykeenan/willykeenan/main/tools/codex-lens/codex_lens.py -o $L \
  || curl -fsSL https://raw.githubusercontent.com/willykeenan/willykeenan/kestudios/trusting-ramanujan-r18a8z/tools/codex-lens/codex_lens.py -o $L; }
python3 $L list --since 72                       # every thread active in the last 3 days, all projects
python3 $L list --project "PID Migration"        # one project (matches cwd/folder/title, punctuation-insensitive)
python3 $L show "Core Engineer"                  # one thread's timeline (add --full for untruncated)
python3 $L export --project "PID Migration" --out ~/.codex-lens/exports/$(date +%Y%m%d-%H%M)
python3 $L discover                              # layout, SQLite schemas, record-type histogram (schema drift check)
```

`export` writes `index.json` (structured summaries), `digest.md` (overview and per-thread status), `threads/*.md` (redacted timelines) and `index.html` (a self-contained dashboard you can publish as a private Artifact).

### B. Cloud session (no `~/.codex` here)

1. `list_environments` and pick the `bridge` environment named `Mac.lan:*` (currently `Mac.lan:Workbench`, `env_012x6T475RNE7Me8mVr3XkpY`). If none is active, tell Will to run `claude remote-control` on the Mac.
2. `create_session` in that environment with `model: "claude-sonnet-5"` and `extra_allowed_tools: ["Bash","Read","Write","Artifact","SendMessage"]`.
   - Keep the prompt short and mechanical, like the template below. A long investigative prompt (process listings, grepping for keys, poking app databases) once tripped an Opus safeguard false positive `[cyber]` and killed the session. The script does all the investigating, so the Mac session only runs it.
3. Don't sleep-poll. Schedule `send_later` about 8 minutes out, then check `get_session` (`status_bucket`) and `Artifact` `action: "list"`. The newest "Codex Lens" artifact is the export.
4. Pull the files with `Artifact` `action: "read"` plus `paths` (`index.json`, `digest.md`, `threads/...`). They land in the scratchpad for local reading and subagents.

Mac prompt template:

```
Run these commands on this Mac and publish the result. Read-only; do not change anything under ~/.codex.
1. mkdir -p ~/.codex-lens && curl -fsSL <RAW_URL_OF codex_lens.py> -o ~/.codex-lens/codex_lens.py
2. OUT=~/.codex-lens/exports/$(date +%Y%m%d-%H%M); python3 ~/.codex-lens/codex_lens.py export --out "$OUT" <FILTERS>
   and python3 ~/.codex-lens/codex_lens.py discover > "$OUT/discover.json"
   If export reports 0 threads, run `python3 ~/.codex-lens/codex_lens.py list --since 72`, choose the project
   folder whose thread titles match <EXPECTED TITLES>, and re-run export with --project <that folder>.
3. Publish a private Artifact titled "Codex Lens — <PROJECT>": page = $OUT/index.html; files = index.json,
   digest.md, discover.json and every threads/*.md (published at the same relative paths).
4. SendMessage to "<THIS SESSION'S NAME from ListAgents header>" with the artifact URL and the export's JSON
   status line. Finish with the artifact URL.
```

## 2. Read it

Read `digest.md` first; the table gives status for every thread. Status meanings:

| status | meaning | typical action |
|---|---|---|
| `awaiting_approval` | open turn with an unresolved approval request | Will must approve, or change the thread's approval policy |
| `stalled` | turn open >15 min with no tool in flight (crash, disconnect, killed app) | resume or restart the thread |
| `waiting_on_user` | turn finished and the last message asks Will something | answer it, since the thread is idle until then |
| `running` | turn open with recent activity or a tool still executing (`in_flight`) | leave it |
| `aborted` | last turn was interrupted | check whether the work was lost |
| `idle` | last turn completed | done, or needs a next instruction |

Signals worth checking on every thread include:
- `failed_commands` (and the failure output in the timeline)
- `context_pct` above 80, meaning it will compact soon and lose detail
- `compactions`
- `errors`
- the latest `plan` with unfinished steps
- `files_touched` overlapping with other threads, meaning edit conflicts
- `git_branch` collisions, where several threads share one branch
- `approval_policy` / `sandbox` per thread

## 3. Audit a multi-agent project

For a team of threads (e.g. PID Migration's Workstream Owner, engineers, external auditors, researchers and installer):
1. Split `threads/*.md` across parallel subagents, three or four threads each. Have each return per thread its role, mandate (first user message), actual progress against its plan, blockers, failures, what it's waiting on, files and branches touched, and quality concerns, citing timeline timestamps.
2. Do a cross-thread pass from `index.json` and the subagent results:
   - overlapping `files_touched` and shared branches
   - duplicated work
   - hand-offs that reference other threads by name but never happened
   - auditor findings with no engineer response
   - threads idle while others wait on them
   - wasted token spend
3. Verify every "X is broken" or "Y conflicts with Z" claim against the timeline text before reporting it.
4. Report ranked actions: what Will must do now (approvals, questions to answer), what to restart, what to consolidate, and what's healthy.

## Rules

- Read-only. Never write into `~/.codex`, and never type into, interrupt or kill a Codex thread unless Will asks.
- Exports are private data. Publish them only as private Artifacts and never commit them to git. Redaction is best-effort, not a guarantee.
- If `discover` shows record shapes the parser does not handle (new `event_msg/*` or `response_item/*` types), extend `codex_lens.py` in this repo and push, rather than patching a copy on the Mac.
