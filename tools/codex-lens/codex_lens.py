#!/usr/bin/env python3
"""codex-lens: read-only inspector for local OpenAI Codex conversations.

Indexes a Codex home (default: $CODEX_HOME or ~/.codex): rollout transcripts,
thread names, state databases and app state. Groups threads by project, infers
live status, and exports redacted per-thread timelines as JSON, Markdown and a
self-contained HTML dashboard.

Guarantees:
  * Never writes inside the Codex home; SQLite is opened read-only.
  * Stdlib only; runs on the python3 that ships with macOS (3.9+).
  * Secrets are redacted from every exported string.

Usage:
  codex_lens.py discover                      # layout, schemas, record-type histogram
  codex_lens.py list   [--project P] [--since H] [--title T ...]
  codex_lens.py export --out DIR [--project P] [--since H] [--title T ...]
  codex_lens.py show   THREAD_ID_OR_TITLE [--full]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import html
import json
import os
import re
import sqlite3
import sys
import time

VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Redaction

_SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("xai_key", re.compile(r"xai-[A-Za-z0-9]{20,}")),
    ("stripe_key", re.compile(r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("github_token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("slack_token", re.compile(r"xox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("aws_key", re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}")),
    ("google_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("url_credentials", re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)")),
    ("bearer", re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._\-]{20,}")),
    ("assignment", re.compile(
        r"(?i)((?:api[_-]?key|secret|token|passw(?:or)?d|private[_-]?key|access[_-]?key|client[_-]?secret)"
        r"[A-Za-z0-9_]*[\"']?\s*[:=]\s*[\"']?)([^\s\"',;]{8,})")),
]


def redact(text):
    if not text:
        return text
    for kind, pattern in _SECRET_PATTERNS:
        if kind == "assignment":
            text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED:%s]" % kind, text)
    return text


def clip(text, limit):
    if text is None:
        return ""
    text = str(text)
    if limit and len(text) > limit:
        head = int(limit * 0.7)
        tail = limit - head
        return "%s\n…[%d chars elided]…\n%s" % (text[:head], len(text) - limit, text[-tail:])
    return text


# ---------------------------------------------------------------------------
# Time helpers

def parse_ts(value):
    """Parse ISO-8601 (with Z / arbitrary fraction digits) or epoch into aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e12 else float(value)
        return dt.datetime.fromtimestamp(seconds, dt.timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10,13}(\.\d+)?", s):
        return parse_ts(float(s))
    s = s.replace("Z", "+00:00")
    m = re.match(r"^(.*?\.\d{1,6})\d*(.*)$", s)
    if m:
        s = m.group(1) + m.group(2)
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def human_age(seconds):
    if seconds is None:
        return "?"
    seconds = int(seconds)
    if seconds < 90:
        return "%ds" % seconds
    if seconds < 5400:
        return "%dm" % (seconds // 60)
    if seconds < 172800:
        return "%.1fh" % (seconds / 3600.0)
    return "%.1fd" % (seconds / 86400.0)


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


# ---------------------------------------------------------------------------
# Codex home discovery

def candidate_homes():
    home = os.path.expanduser("~")
    out = []
    if os.environ.get("CODEX_HOME"):
        out.append(os.environ["CODEX_HOME"])
    out.append(os.path.join(home, ".codex"))
    support = os.path.join(home, "Library", "Application Support")
    for pattern in ("Codex*", "com.openai.codex*", "OpenAI*"):
        out.extend(glob.glob(os.path.join(support, pattern)))
    seen, result = set(), []
    for p in out:
        p = os.path.realpath(p)
        if p not in seen and os.path.isdir(p):
            seen.add(p)
            result.append(p)
    return result


def rollout_files(codex_home):
    files = []
    for sub in ("sessions", "archived_sessions"):
        root = os.path.join(codex_home, sub)
        for dirpath, _, names in os.walk(root):
            for name in names:
                if name.endswith(".jsonl"):
                    files.append(os.path.join(dirpath, name))
    return files


def sqlite_files(root, depth=2):
    out = []
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, names in os.walk(root):
        if dirpath.count(os.sep) - root_depth >= depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in ("sessions", "archived_sessions", "node_modules")]
        for name in names:
            if name.endswith((".sqlite", ".sqlite3", ".db")):
                out.append(os.path.join(dirpath, name))
    return out


def open_ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=2)


def sqlite_schema(path):
    info = {"path": path, "tables": []}
    try:
        con = open_ro(path)
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        for t in tables:
            cols = [r[1] for r in con.execute('pragma table_info("%s")' % t.replace('"', '""'))]
            try:
                n = con.execute('select count(*) from "%s"' % t.replace('"', '""')).fetchone()[0]
            except sqlite3.Error:
                n = None
            info["tables"].append({"name": t, "columns": cols, "rows": n})
        con.close()
    except sqlite3.Error as exc:
        info["error"] = str(exc)
    return info


# ---------------------------------------------------------------------------
# Thread metadata from side stores (names, archive flags, cwd)

_ID_COLS = ("id", "thread_id", "session_id", "conversation_id", "uuid")
_TITLE_COLS = ("title", "thread_name", "name", "display_name", "summary_title")
_CWD_COLS = ("cwd", "workspace", "workspace_root", "project_path", "root")
_ARCHIVE_COLS = ("archived", "is_archived", "archived_at")
_UPDATED_COLS = ("updated_at", "last_updated", "last_activity_at", "modified_at")


def side_metadata(codex_home):
    """Map thread id -> {title, cwd, archived, updated, source} from index files and SQLite."""
    meta = collections.defaultdict(dict)
    sources = []

    for path in glob.glob(os.path.join(codex_home, "*index*.jsonl")):
        sources.append(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                tid = next((rec.get(k) for k in _ID_COLS if rec.get(k)), None)
                title = next((rec.get(k) for k in _TITLE_COLS if rec.get(k)), None)
                if tid and title:
                    meta[str(tid)]["title"] = str(title)
                    meta[str(tid)]["title_source"] = os.path.basename(path)
                    upd = next((rec.get(k) for k in _UPDATED_COLS if rec.get(k)), None)
                    if upd:
                        meta[str(tid)]["updated"] = upd

    for path in sqlite_files(codex_home):
        try:
            con = open_ro(path)
            tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
            for t in tables:
                qt = t.replace('"', '""')
                cols = [r[1] for r in con.execute('pragma table_info("%s")' % qt)]
                lower = {c.lower(): c for c in cols}
                idc = next((lower[c] for c in _ID_COLS if c in lower), None)
                if not idc:
                    continue
                pick = {}
                for key, cands in (("title", _TITLE_COLS), ("cwd", _CWD_COLS),
                                   ("archived", _ARCHIVE_COLS), ("updated", _UPDATED_COLS)):
                    col = next((lower[c] for c in cands if c in lower), None)
                    if col:
                        pick[key] = col
                if "title" not in pick and "cwd" not in pick:
                    continue
                sources.append("%s:%s" % (path, t))
                sel = ", ".join('"%s"' % c.replace('"', '""') for c in [idc] + list(pick.values()))
                for row in con.execute('select %s from "%s"' % (sel, qt)):
                    tid = str(row[0])
                    for (key, _), value in zip(pick.items(), row[1:]):
                        if value in (None, ""):
                            continue
                        if key == "title" and meta[tid].get("title_source", "").endswith(".jsonl"):
                            continue  # explicit rename index wins
                        meta[tid][key] = value
                        if key == "title":
                            meta[tid]["title_source"] = "%s:%s" % (os.path.basename(path), t)
            con.close()
        except sqlite3.Error:
            continue
    return meta, sources


# ---------------------------------------------------------------------------
# Rollout parsing

_SHELL_TOOLS = {"shell", "exec_command", "local_shell", "container.exec", "shell_command", "bash", "unified_exec"}
_PATCH_RE = re.compile(r"^\*\*\* (?:(Add|Update|Delete) File|Move to): (.+)$", re.M)
_EXIT_RE = re.compile(r"(?i)exit[_ ]?code[\"'\s:=]*(-?\d+)")
_INJECTED_PREFIXES = ("<environment_context", "<user_instructions", "# agents.md", "<permissions",
                      "<user_shell_command", "<turn_aborted", "<collaboration")


def _content_text(content):
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict):
                t = c.get("text") or c.get("input_text") or c.get("output_text")
                if isinstance(t, str):
                    parts.append(t)
                elif c.get("type") in ("input_image", "image"):
                    parts.append("[image]")
    return "\n".join(parts)


def _loads_maybe(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _command_str(args):
    cmd = args.get("command") if isinstance(args, dict) else None
    if cmd is None and isinstance(args, dict):
        cmd = args.get("cmd") or args.get("script")
    if isinstance(cmd, list):
        if len(cmd) >= 3 and cmd[0] in ("bash", "zsh", "sh", "/bin/bash", "/bin/zsh") and cmd[1] in ("-lc", "-c"):
            return cmd[2]
        return " ".join(str(c) for c in cmd)
    return str(cmd) if cmd is not None else json.dumps(args)[:500]


def _output_text(payload):
    out = payload.get("output")
    out = _loads_maybe(out)
    exit_code = None
    if isinstance(out, dict):
        md = out.get("metadata") or {}
        exit_code = md.get("exit_code", out.get("exit_code"))
        text = out.get("output") or out.get("content") or json.dumps(out)[:2000]
    elif isinstance(out, list):
        text = _content_text(out)
    else:
        text = str(out) if out is not None else ""
    if exit_code is None:
        m = _EXIT_RE.search(text[:400])
        if m:
            exit_code = int(m.group(1))
    return text, exit_code


def _is_injected(text):
    t = (text or "").lstrip().lower()
    return any(t.startswith(p) for p in _INJECTED_PREFIXES)


class Thread(object):
    def __init__(self, path):
        self.paths = [path]
        self.id = None
        self.meta = {}
        self.turn_context = {}
        self.entries = []        # (ts, kind, data dict)
        self.first_ts = None
        self.last_ts = None
        self.title_events = []
        self.tokens = None
        self.context_window = None
        self.rate_limits = None
        self.plan = None
        self.plan_ts = None
        self.pending_calls = {}  # call_id -> entry index
        self.turn_state = []     # sequence of ("start"|"complete"|"abort", ts)
        self.approvals = []      # (ts, kind, detail, resolved)
        self.counts = collections.Counter()
        self.shapes = collections.Counter()
        self.has_event_user = False
        self.has_event_agent = False
        self.files = collections.OrderedDict()
        self.errors = []
        self.mtime = os.path.getmtime(path)

    # -- ingest ------------------------------------------------------------
    def ingest(self):
        with open(self.paths[-1], "r", encoding="utf-8", errors="replace") as fh:
            legacy_first = True
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    self.counts["bad_json"] += 1
                    continue
                if not isinstance(rec, dict):
                    continue
                if "payload" in rec and "type" in rec:
                    self._record(rec.get("timestamp"), rec["type"], rec.get("payload") or {})
                else:
                    self._legacy(rec, legacy_first)
                legacy_first = False

    def _stamp(self, ts):
        d = parse_ts(ts)
        if d:
            if not self.first_ts or d < self.first_ts:
                self.first_ts = d
            if not self.last_ts or d > self.last_ts:
                self.last_ts = d
        return d

    def _add(self, d, kind, **data):
        self.entries.append((d, kind, data))
        self.counts[kind] += 1
        return len(self.entries) - 1

    def _legacy(self, rec, first):
        # Pre-2025-09 rollouts: first line is session meta, then bare response items.
        if first and ("id" in rec and "instructions" in rec or rec.get("record_type") == "meta"):
            self.meta.update({k: rec.get(k) for k in ("id", "timestamp", "cwd", "git") if k in rec})
            self.id = self.id or rec.get("id")
            self._stamp(rec.get("timestamp"))
            return
        if rec.get("record_type") == "state":
            return
        self._response_item(rec.get("timestamp"), rec)

    def _record(self, ts, rtype, payload):
        ptype = payload.get("type") if isinstance(payload, dict) else None
        self.shapes["%s/%s" % (rtype, ptype)] += 1
        d = self._stamp(ts)
        if rtype == "session_meta":
            meta = payload.get("meta", payload) if isinstance(payload, dict) else {}
            for k in ("id", "timestamp", "cwd", "originator", "cli_version", "source",
                      "model_provider", "git", "instructions"):
                if k in meta and k not in self.meta:
                    self.meta[k] = meta[k]
            if isinstance(payload, dict) and isinstance(payload.get("git"), dict):
                self.meta["git"] = payload["git"]
            self.id = self.id or meta.get("id")
        elif rtype == "turn_context":
            self.turn_context = payload
        elif rtype == "compacted":
            self._add(d, "compaction", text=payload.get("message") or "")
        elif rtype == "response_item":
            self._response_item(ts, payload, d)
        elif rtype == "event_msg":
            self._event(d, payload)
        else:
            self.counts["other:%s" % rtype] += 1

    def _event(self, d, p):
        t = p.get("type", "")
        if t == "user_message":
            self.has_event_user = True
            msg = p.get("message") or ""
            if not _is_injected(msg):
                images = p.get("images") or p.get("local_images") or []
                self._add(d, "user", text=msg + (" [+%d image(s)]" % len(images) if images else ""))
        elif t == "agent_message":
            self.has_event_agent = True
            self._add(d, "assistant", text=p.get("message") or "")
        elif t in ("agent_reasoning", "agent_reasoning_raw_content", "agent_reasoning_section_break"):
            self.counts["reasoning"] += 1
        elif t == "token_count":
            info = p.get("info") or {}
            if info.get("total_token_usage"):
                self.tokens = info
            if info.get("model_context_window"):
                self.context_window = info["model_context_window"]
            if p.get("rate_limits"):
                self.rate_limits = p["rate_limits"]
        elif t in ("task_started", "turn_started"):
            self.turn_state.append(("start", d))
            if p.get("model_context_window"):
                self.context_window = p["model_context_window"]
        elif t in ("task_complete", "turn_complete"):
            self.turn_state.append(("complete", d))
        elif t == "turn_aborted":
            self.turn_state.append(("abort", d))
            self._add(d, "abort", text=str(p.get("reason") or "aborted"))
        elif t in ("error", "stream_error"):
            msg = p.get("message") or json.dumps(p)[:500]
            self.errors.append((d, msg))
            self._add(d, "error", text=msg)
        elif "approval_request" in t or t in ("request_user_input", "elicitation_request"):
            detail = p.get("command") or p.get("reason") or p.get("changes") or p.get("message") or p
            if isinstance(detail, (list, dict)):
                detail = json.dumps(detail)[:600]
            self.approvals.append([d, t, str(detail), False])
            self._add(d, "approval_request", text="%s: %s" % (t, detail))
        elif t.endswith("approval_response") or t in ("exec_approval", "patch_approval"):
            for a in self.approvals:
                a[3] = True
        elif "thread_name" in t or t in ("thread_renamed", "session_renamed", "title_updated"):
            name = p.get("thread_name") or p.get("name") or p.get("title")
            if name:
                self.title_events.append((d, str(name)))
        elif t in ("entered_review_mode", "exited_review_mode", "context_compacted", "turn_diff",
                   "plan_update", "background_event", "warning"):
            if t == "plan_update" and p.get("plan"):
                self.plan, self.plan_ts = p, d
            self._add(d, "event", text="%s %s" % (t, clip(json.dumps({k: v for k, v in p.items() if k != "type"}), 300)))
        elif t.startswith(("exec_command", "patch_apply", "mcp_tool_call", "web_search", "view_image")):
            self.counts["evt:" + t] += 1
        else:
            self.counts["evt:" + t] += 1
            if t and not t.endswith(("_delta", "_begin")):
                self._add(d, "event", text="%s %s" % (t, clip(json.dumps({k: v for k, v in p.items() if k != "type"}), 300)))

    def _response_item(self, ts, p, d=None):
        if d is None:
            d = self._stamp(ts)
        t = p.get("type")
        if t == "message":
            role = p.get("role")
            text = _content_text(p.get("content"))
            if role == "user":
                if not _is_injected(text):
                    self._add(d, "ri_user", text=text)
            elif role == "assistant":
                self._add(d, "ri_assistant", text=text)
            else:
                self.counts["msg:%s" % role] += 1
        elif t in ("function_call", "custom_tool_call", "local_shell_call"):
            name = p.get("name") or ("local_shell" if t == "local_shell_call" else "?")
            call_id = p.get("call_id") or p.get("id")
            raw = p.get("arguments") if t == "function_call" else (p.get("input") if t == "custom_tool_call" else p.get("action"))
            args = _loads_maybe(raw)
            short = name.split(".")[-1]
            if short in _SHELL_TOOLS or t == "local_shell_call":
                cmd = _command_str(args if isinstance(args, dict) else {"command": args})
                files = _PATCH_RE.findall(cmd) if "apply_patch" in cmd else []
                if files:
                    idx = self._add(d, "patch", files=[f[1].strip() for f in files], text=cmd)
                    for f in files:
                        self.files[f[1].strip()] = f[0] or "Move"
                else:
                    workdir = args.get("workdir") if isinstance(args, dict) else None
                    idx = self._add(d, "cmd", text=cmd, workdir=workdir, exit=None, out="")
            elif name == "apply_patch":
                body = args.get("input") if isinstance(args, dict) else str(args or "")
                files = _PATCH_RE.findall(body or "")
                idx = self._add(d, "patch", files=[f[1].strip() for f in files], text=body or "")
                for f in files:
                    self.files[f[1].strip()] = f[0] or "Move"
            elif name == "update_plan":
                plan = args if isinstance(args, dict) else {"raw": args}
                self.plan, self.plan_ts = plan, d
                idx = self._add(d, "plan", plan=plan)
            else:
                idx = self._add(d, "tool", name=name, text=raw if isinstance(raw, str) else json.dumps(raw))
            if call_id:
                self.pending_calls[call_id] = idx
        elif t in ("function_call_output", "custom_tool_call_output"):
            call_id = p.get("call_id")
            text, exit_code = _output_text(p)
            idx = self.pending_calls.pop(call_id, None)
            if idx is not None:
                ts0, kind, data = self.entries[idx]
                data["out"] = text
                data["exit"] = exit_code
                data["done"] = True
            else:
                self._add(d, "tool_out", text=text, exit=exit_code)
        elif t == "reasoning":
            self.counts["reasoning_items"] += 1
        elif t == "web_search_call":
            action = p.get("action") or {}
            self._add(d, "tool", name="web_search", text=json.dumps(action)[:300])
        else:
            self.counts["ri:%s" % t] += 1

    # -- derived -------------------------------------------------------------
    def finalize(self, side, now):
        # Prefer event_msg user/assistant text; fall back to response items (legacy files).
        keep = []
        for e in self.entries:
            if e[1] == "ri_user":
                if self.has_event_user:
                    continue
                e = (e[0], "user", e[2])
            elif e[1] == "ri_assistant":
                if self.has_event_agent:
                    continue
                e = (e[0], "assistant", e[2])
            keep.append(e)
        self.entries = keep
        self.id = str(self.id or re.sub(r"^.*?([0-9a-f]{8}-[0-9a-f-]{27,})\.jsonl$", r"\1", os.path.basename(self.paths[-1])))
        s = side.get(self.id, {})
        user_msgs = [e for e in self.entries if e[1] == "user"]
        first_user = next((e[2]["text"] for e in user_msgs if e[2].get("text")), "")
        if self.title_events:
            self.title, self.title_source = self.title_events[-1][1], "rollout"
        elif s.get("title"):
            self.title, self.title_source = str(s["title"]), s.get("title_source", "side")
        else:
            self.title = (first_user.strip().splitlines() or ["(untitled)"])[0][:80]
            self.title_source = "first_user_message"
        self.cwd = self.turn_context.get("cwd") or self.meta.get("cwd") or s.get("cwd") or ""
        self.archived = bool(s.get("archived")) or any("archived_sessions" in p for p in self.paths)

        # Event timestamps are authoritative; mtime only when a file carries none (copies/backups touch mtime).
        self.last_activity = self.last_ts or dt.datetime.fromtimestamp(self.mtime, dt.timezone.utc)
        self.age_s = (now - self.last_activity).total_seconds()

        last_turn = self.turn_state[-1][0] if self.turn_state else None
        open_turn = last_turn == "start"
        # A call with no output yet means a tool is executing (long builds/tests write nothing until done).
        self.in_flight = None
        if self.pending_calls:
            idx = max(self.pending_calls.values())
            ts0, kind, data = self.entries[idx]
            if kind in ("cmd", "tool", "patch") and not data.get("done"):
                self.in_flight = "%s: %s" % (kind, clip(data.get("text") or data.get("name"), 200))
        unresolved = [a for a in self.approvals if not a[3] and (not self.turn_state or a[0] is None
                      or self.turn_state[-1][1] is None or a[0] >= self.turn_state[-1][1])]
        last_assistant = next((e[2]["text"] for e in reversed(self.entries) if e[1] == "assistant"), "")
        self.last_assistant = last_assistant
        self.asks_user = bool(re.search(r"\?\s*$|\b(should i|do you want|would you like|which (one|option)|confirm|let me know)\b",
                                        last_assistant[-600:], re.I)) if last_assistant else False
        if unresolved and open_turn:
            status = "awaiting_approval"
        elif open_turn and (self.age_s < 900 or (self.in_flight and self.age_s < 7200)):
            status = "running"
        elif open_turn:
            status = "stalled"
        elif last_turn == "abort":
            status = "aborted"
        elif last_turn == "complete":
            status = "waiting_on_user" if self.asks_user else "idle"
        else:
            status = "running" if self.age_s < 300 else "idle"
        self.status = status

        cmds = [e for e in self.entries if e[1] == "cmd"]
        failed = [e for e in cmds if isinstance(e[2].get("exit"), int) and e[2]["exit"] != 0]
        tok = (self.tokens or {}).get("total_token_usage") or {}
        last_tok = (self.tokens or {}).get("last_token_usage") or {}
        ctx = self.context_window or (self.tokens or {}).get("model_context_window")
        ctx_pct = None
        if ctx and last_tok.get("input_tokens"):
            ctx_pct = round(100.0 * last_tok["input_tokens"] / ctx, 1)
        git = self.meta.get("git") or {}
        self.summary = {
            "id": self.id,
            "title": redact(self.title),
            "title_source": self.title_source,
            "project": os.path.basename(self.cwd.rstrip("/")) if self.cwd else "",
            "cwd": self.cwd,
            "archived": self.archived,
            "status": status,
            "asks_user": self.asks_user,
            "in_flight": redact(self.in_flight) if self.in_flight else None,
            "created": iso(self.first_ts),
            "last_activity": iso(self.last_activity),
            "age": human_age(self.age_s),
            "age_s": int(self.age_s),
            "model": self.turn_context.get("model"),
            "effort": self.turn_context.get("effort") or self.turn_context.get("reasoning_effort"),
            "approval_policy": self.turn_context.get("approval_policy"),
            "sandbox": (self.turn_context.get("sandbox_policy") or {}).get("mode")
                       if isinstance(self.turn_context.get("sandbox_policy"), dict)
                       else self.turn_context.get("sandbox_policy"),
            "originator": self.meta.get("originator"),
            "source": self.meta.get("source") if isinstance(self.meta.get("source"), str) else json.dumps(self.meta.get("source")) if self.meta.get("source") else None,
            "cli_version": self.meta.get("cli_version"),
            "git_branch": git.get("branch"),
            "git_commit": (git.get("commit_hash") or "")[:12] or None,
            "git_repo": redact(git.get("repository_url") or "") or None,
            "turns": sum(1 for s_ in self.turn_state if s_[0] == "start"),
            "user_messages": len(user_msgs),
            "assistant_messages": sum(1 for e in self.entries if e[1] == "assistant"),
            "commands": len(cmds),
            "failed_commands": len(failed),
            "patches": sum(1 for e in self.entries if e[1] == "patch"),
            "files_touched": list(self.files.keys()),
            "tool_calls": sum(1 for e in self.entries if e[1] == "tool"),
            "errors": len(self.errors),
            "aborts": sum(1 for s_ in self.turn_state if s_[0] == "abort"),
            "compactions": sum(1 for e in self.entries if e[1] == "compaction"),
            "pending_approvals": [redact(a[2])[:400] for a in unresolved],
            "tokens_total": tok.get("total_tokens"),
            "tokens_input": tok.get("input_tokens"),
            "tokens_cached": tok.get("cached_input_tokens"),
            "tokens_output": tok.get("output_tokens"),
            "context_pct": ctx_pct,
            "plan": _plan_summary(self.plan),
            "last_user": redact(clip(user_msgs[-1][2]["text"], 1200)) if user_msgs else "",
            "last_assistant": redact(clip(last_assistant, 2500)),
            "rollouts": self.paths,
            "rollout_bytes": sum(os.path.getsize(p) for p in self.paths if os.path.exists(p)),
        }
        return self.summary

    def timeline_md(self, limits):
        s = self.summary
        out = []
        out.append("# %s" % s["title"])
        out.append("")
        out.append("| field | value |\n|---|---|")
        for k in ("id", "status", "cwd", "git_branch", "model", "effort", "approval_policy", "sandbox",
                  "created", "last_activity", "age", "turns", "user_messages", "commands", "failed_commands",
                  "patches", "errors", "aborts", "compactions", "tokens_total", "context_pct"):
            out.append("| %s | %s |" % (k, "" if s.get(k) is None else str(s.get(k)).replace("|", "\\|")))
        if s["pending_approvals"]:
            out.append("\n## Pending approvals\n")
            out.extend("- %s" % a for a in s["pending_approvals"])
        if s["plan"]:
            out.append("\n## Latest plan (%s)\n" % iso(self.plan_ts))
            out.append(s["plan"])
        if s["files_touched"]:
            out.append("\n## Files touched (%d)\n" % len(s["files_touched"]))
            out.extend("- `%s` (%s)" % (f, self.files[f]) for f in s["files_touched"][:300])
        out.append("\n## Last assistant message\n")
        out.append(s["last_assistant"] or "_none_")
        out.append("\n## Timeline\n")
        for d, kind, data in self.entries:
            stamp = d.strftime("%m-%d %H:%M:%S") if d else "--"
            if kind == "user":
                out.append("\n### [%s] USER\n\n%s" % (stamp, redact(clip(data.get("text"), limits["msg"]))))
            elif kind == "assistant":
                out.append("\n### [%s] ASSISTANT\n\n%s" % (stamp, redact(clip(data.get("text"), limits["msg"]))))
            elif kind == "cmd":
                ex = data.get("exit")
                flag = "" if ex in (None, 0) else " **EXIT %s**" % ex
                out.append("- `%s` $ %s%s" % (stamp, redact(clip(data.get("text"), limits["cmd"])).replace("\n", " ⏎ "), flag))
                if ex not in (None, 0) and data.get("out"):
                    out.append("  ```\n  %s\n  ```" % redact(clip(data["out"], limits["out"])).replace("\n", "\n  "))
            elif kind == "patch":
                out.append("- `%s` PATCH %s" % (stamp, ", ".join(data.get("files") or []) or clip(data.get("text"), 200)))
            elif kind == "plan":
                out.append("- `%s` PLAN\n%s" % (stamp, _indent(_plan_summary(data.get("plan")) or "", "  ")))
            elif kind == "tool":
                out.append("- `%s` TOOL %s %s" % (stamp, data.get("name"), redact(clip(data.get("text"), limits["args"])).replace("\n", " ")))
            elif kind == "tool_out":
                continue
            elif kind == "compaction":
                out.append("\n### [%s] CONTEXT COMPACTED\n\n%s" % (stamp, redact(clip(data.get("text"), limits["msg"]))))
            elif kind in ("error", "abort", "approval_request"):
                out.append("- `%s` **%s** %s" % (stamp, kind.upper(), redact(clip(data.get("text"), limits["out"]))))
            elif kind == "event":
                out.append("- `%s` %s" % (stamp, redact(clip(data.get("text"), limits["args"]))))
        return "\n".join(out) + "\n"


def _indent(text, prefix):
    return "\n".join(prefix + ln for ln in text.splitlines())


def _plan_summary(plan):
    if not plan:
        return ""
    if isinstance(plan, dict):
        steps = plan.get("plan") or []
        lines = []
        if plan.get("explanation"):
            lines.append(redact(clip(str(plan["explanation"]), 600)))
        mark = {"completed": "[x]", "in_progress": "[~]", "pending": "[ ]"}
        for st in steps if isinstance(steps, list) else []:
            if isinstance(st, dict):
                lines.append("- %s %s" % (mark.get(st.get("status"), "[?]"), redact(clip(str(st.get("step")), 300))))
        if not lines and plan.get("raw"):
            lines.append(redact(clip(str(plan["raw"]), 1200)))
        return "\n".join(lines)
    return redact(clip(str(plan), 1200))


# ---------------------------------------------------------------------------
# Loading + selection

def load_threads(codex_home, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    side, _ = side_metadata(codex_home)
    by_id = collections.OrderedDict()
    for path in sorted(rollout_files(codex_home), key=os.path.getmtime):
        th = Thread(path)
        try:
            th.ingest()
        except OSError as exc:
            sys.stderr.write("skip %s: %s\n" % (path, exc))
            continue
        key = str(th.id or path)
        if key in by_id:
            # Same thread in several files (resume/fork): keep the newest, remember the rest.
            th.paths = by_id[key].paths + th.paths
        by_id[key] = th
    threads = list(by_id.values())
    for th in threads:
        th.finalize(side, now)
    return threads


def select(threads, project=None, since_h=None, titles=None, ids=None, include_archived=False):
    out = []
    np = norm(project) if project else None
    ntitles = [norm(t) for t in (titles or []) if norm(t)]
    for th in threads:
        s = th.summary
        if s["archived"] and not include_archived:
            continue
        if since_h is not None and s["age_s"] > since_h * 3600:
            continue
        if ids and not any(s["id"].startswith(i) for i in ids):
            continue
        hit_project = np is None or np in norm(s["cwd"]) or np in norm(s["project"]) or np in norm(s["title"])
        hit_title = bool(ntitles) and any(t in norm(s["title"]) for t in ntitles)
        if np is not None and ntitles:
            if not (hit_project or hit_title):
                continue
        elif np is not None and not hit_project:
            continue
        elif ntitles and not hit_title:
            continue
        out.append(th)
    out.sort(key=lambda t: (t.summary["project"], t.summary["created"] or ""))
    return out


# ---------------------------------------------------------------------------
# Output

_STATUS_ORDER = ["awaiting_approval", "stalled", "waiting_on_user", "running", "aborted", "idle"]


def digest_md(threads, generated):
    lines = ["# Codex threads — %s" % generated, ""]
    cnt = collections.Counter(t.summary["status"] for t in threads)
    lines.append("**%d threads** · " % len(threads) + " · ".join("%s: %d" % (k, cnt[k]) for k in _STATUS_ORDER if cnt[k]))
    lines.append("")
    lines.append("| # | title | status | age | turns | cmds (fail) | patches | files | tokens | ctx% | branch |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, t in enumerate(threads, 1):
        s = t.summary
        lines.append("| %d | %s | %s%s | %s | %s | %s (%s) | %s | %d | %s | %s | %s |" % (
            i, s["title"].replace("|", "/"), s["status"], " ⚠approval" if s["pending_approvals"] else "",
            s["age"], s["turns"], s["commands"], s["failed_commands"], s["patches"], len(s["files_touched"]),
            _fmt_int(s["tokens_total"]), s["context_pct"] if s["context_pct"] is not None else "", s["git_branch"] or ""))
    lines.append("")
    for t in threads:
        s = t.summary
        lines.append("## %s — %s (%s ago)" % (s["title"], s["status"], s["age"]))
        lines.append("`%s` · cwd `%s` · model %s · approval %s · sandbox %s" % (
            s["id"], s["cwd"], s["model"], s["approval_policy"], s["sandbox"]))
        if s["pending_approvals"]:
            lines.append("\n**Pending approvals:**\n" + "\n".join("- " + a for a in s["pending_approvals"]))
        if s["plan"]:
            lines.append("\n**Plan:**\n" + s["plan"])
        lines.append("\n**Last user:** " + (clip(s["last_user"], 500) or "_none_"))
        lines.append("\n**Last assistant:** " + (clip(s["last_assistant"], 900) or "_none_"))
        lines.append("")
    return "\n".join(lines) + "\n"


def _fmt_int(n):
    if n is None:
        return ""
    if n >= 1_000_000:
        return "%.1fM" % (n / 1e6)
    if n >= 1000:
        return "%.0fk" % (n / 1e3)
    return str(n)


def slug(s):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:48] or "thread"


def dashboard_html(threads, generated, timelines):
    rows = []
    for t in threads:
        s = t.summary
        rows.append({k: s[k] for k in ("id", "title", "status", "age", "age_s", "turns", "commands",
                                       "failed_commands", "patches", "tokens_total", "context_pct",
                                       "git_branch", "cwd", "model", "approval_policy", "sandbox",
                                       "pending_approvals", "plan", "last_user", "last_assistant",
                                       "asks_user", "last_activity", "created")})
        rows[-1]["files"] = len(s["files_touched"])
        rows[-1]["timeline"] = timelines.get(s["id"], "")
    data = json.dumps({"generated": generated, "threads": rows}).replace("</", "<\\/")
    return _HTML.replace("__DATA__", data).replace("__GENERATED__", html.escape(generated))


_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codex Lens</title>
<style>
:root{--bg:#fbfaf8;--fg:#1d1c1a;--muted:#6b6862;--line:#e4e1db;--card:#ffffff;--accent:#2f5bd3;
--run:#1f7a4d;--warn:#b25e00;--bad:#b3261e;--idle:#6b6862;--ask:#7a3fb0;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#151514;--fg:#ecebe8;--muted:#a19e97;--line:#2e2d2a;--card:#1d1d1b;--accent:#8aa8ff;--run:#5bc98f;--warn:#f0a44a;--bad:#ff7a70;--idle:#a19e97;--ask:#c79bf2}}
:root[data-theme="dark"]{--bg:#151514;--fg:#ecebe8;--muted:#a19e97;--line:#2e2d2a;--card:#1d1d1b;--accent:#8aa8ff;--run:#5bc98f;--warn:#f0a44a;--bad:#ff7a70;--idle:#a19e97;--ask:#c79bf2}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 18px}.chip{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12px;cursor:pointer;background:var(--card)}
.chip[aria-pressed="true"]{border-color:var(--accent);color:var(--accent)}
.st{font:600 11px/1 var(--mono);text-transform:uppercase;letter-spacing:.04em;padding:3px 6px;border-radius:4px;border:1px solid currentColor;white-space:nowrap}
.st.running{color:var(--run)}.st.stalled,.st.aborted{color:var(--bad)}.st.awaiting_approval{color:var(--warn)}.st.waiting_on_user{color:var(--ask)}.st.idle{color:var(--idle)}
.t{border:1px solid var(--line);border-radius:10px;background:var(--card);margin:0 0 10px;overflow:hidden}
.t>summary{list-style:none;cursor:pointer;padding:12px 14px;display:grid;grid-template-columns:1fr auto;gap:6px 12px}.t>summary::-webkit-details-marker{display:none}
.title{font-weight:600}.meta{color:var(--muted);font:12px/1.4 var(--mono);grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px 14px}
.body{border-top:1px solid var(--line);padding:12px 14px}.body h3{font-size:13px;margin:14px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
pre{white-space:pre-wrap;word-break:break-word;font:12px/1.5 var(--mono);margin:0;max-height:560px;overflow:auto;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px}
input[type=search]{width:100%;max-width:360px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg)}
</style></head><body><main>
<h1>Codex Lens</h1><div class="sub">Generated __GENERATED__ · read-only export · secrets redacted</div>
<input type="search" id="q" placeholder="Filter threads…" aria-label="Filter threads">
<div class="chips" id="chips"></div><div id="list"></div>
</main>
<script>
const D=__DATA__;const order=["awaiting_approval","stalled","waiting_on_user","running","aborted","idle"];
let active=null;const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function fmt(n){if(n==null)return"–";return n>=1e6?(n/1e6).toFixed(1)+"M":n>=1e3?Math.round(n/1e3)+"k":n}
function chips(){const c={};D.threads.forEach(t=>c[t.status]=(c[t.status]||0)+1);
document.getElementById("chips").innerHTML=`<span class="chip" data-s="" aria-pressed="${!active}">all ${D.threads.length}</span>`+
order.filter(s=>c[s]).map(s=>`<span class="chip" data-s="${s}" aria-pressed="${active===s}">${s.replace(/_/g," ")} ${c[s]}</span>`).join("");
document.querySelectorAll(".chip").forEach(el=>el.onclick=()=>{active=el.dataset.s||null;render()})}
function render(){chips();const q=document.getElementById("q").value.toLowerCase();
const rows=D.threads.filter(t=>(!active||t.status===active)&&(!q||(t.title+t.cwd+t.last_assistant).toLowerCase().includes(q)));
document.getElementById("list").innerHTML=rows.map(t=>`<details class="t"><summary><span class="title">${esc(t.title)}</span><span class="st ${t.status}">${t.status.replace(/_/g," ")}</span>
<span class="meta"><span>${esc(t.age)} ago</span><span>${t.turns} turns</span><span>${t.commands} cmds${t.failed_commands?` · ${t.failed_commands} failed`:""}</span><span>${t.patches} patches · ${t.files} files</span><span>${fmt(t.tokens_total)} tok${t.context_pct!=null?` · ctx ${t.context_pct}%`:""}</span><span>${esc(t.git_branch||"")}</span><span>${esc(t.model||"")}</span></span></summary>
<div class="body">${t.pending_approvals.length?`<h3>Pending approvals</h3><pre>${esc(t.pending_approvals.join("\n"))}</pre>`:""}
${t.plan?`<h3>Plan</h3><pre>${esc(t.plan)}</pre>`:""}<h3>Last user</h3><pre>${esc(t.last_user||"–")}</pre>
<h3>Last assistant</h3><pre>${esc(t.last_assistant||"–")}</pre><h3>Timeline</h3><pre>${esc(t.timeline)}</pre>
<div class="sub">${esc(t.id)} · ${esc(t.cwd)} · approval ${esc(t.approval_policy)} · sandbox ${esc(t.sandbox)}</div></div></details>`).join("")||"<p class=sub>No threads.</p>"}
document.getElementById("q").oninput=render;render();
</script></body></html>
"""


# ---------------------------------------------------------------------------
# Commands

def pick_home(arg):
    if arg:
        return os.path.expanduser(arg)
    for h in candidate_homes():
        if os.path.isdir(os.path.join(h, "sessions")):
            return h
    return os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex"))


def cmd_discover(args):
    home = pick_home(args.home)
    files = rollout_files(home)
    shapes = collections.Counter()
    recent = sorted(files, key=os.path.getmtime, reverse=True)
    for path in recent[: args.sample]:
        th = Thread(path)
        th.ingest()
        shapes.update(th.shapes)
    side, side_sources = side_metadata(home)
    report = {
        "codex_lens": VERSION,
        "codex_home": home,
        "candidate_homes": candidate_homes(),
        "top_level": sorted(os.listdir(home)) if os.path.isdir(home) else [],
        "rollouts": len(files),
        "rollout_bytes": sum(os.path.getsize(f) for f in files),
        "recent_rollouts": [{"path": p, "mtime": iso(dt.datetime.fromtimestamp(os.path.getmtime(p), dt.timezone.utc)),
                             "bytes": os.path.getsize(p)} for p in recent[:15]],
        "record_shapes_sample": shapes.most_common(),
        "side_metadata_sources": side_sources,
        "side_metadata_threads": len(side),
        "sqlite": [sqlite_schema(p) for p in sqlite_files(home)],
    }
    cfg = os.path.join(home, "config.toml")
    if os.path.exists(cfg):
        keep = re.compile(r"^\s*(model|model_reasoning_effort|approval_policy|sandbox_mode|profile|\[.*\])\s*(=|$)")
        with open(cfg, "r", encoding="utf-8", errors="replace") as fh:
            report["config_toml"] = [redact(ln.rstrip()) for ln in fh if keep.match(ln)]
    print(json.dumps(report, indent=2, default=str))


def _limits(full):
    if full:
        return {"msg": 0, "cmd": 4000, "out": 8000, "args": 4000}
    return {"msg": 6000, "cmd": 400, "out": 1500, "args": 400}


def cmd_list(args):
    home = pick_home(args.home)
    threads = select(load_threads(home), args.project, args.since, args.title, args.id, args.archived)
    print("%-36s  %-18s %6s %5s %6s %8s  %s" % ("id", "status", "age", "turns", "cmds", "tokens", "title  [cwd]"))
    for t in threads:
        s = t.summary
        print("%-36s  %-18s %6s %5d %6d %8s  %s  [%s]" % (s["id"][:36], s["status"], s["age"], s["turns"],
              s["commands"], _fmt_int(s["tokens_total"]), s["title"][:60], s["cwd"]))
    print("\n%d thread(s)" % len(threads))


def cmd_export(args):
    home = pick_home(args.home)
    now = dt.datetime.now(dt.timezone.utc)
    generated = iso(now)
    all_threads = load_threads(home, now)
    threads = select(all_threads, args.project, args.since, args.title, args.id, args.archived)
    out = os.path.abspath(os.path.expanduser(args.out))
    if out.startswith(os.path.realpath(home) + os.sep):
        sys.exit("refusing to write inside the Codex home")
    os.makedirs(os.path.join(out, "threads"), exist_ok=True)
    limits = _limits(args.full)
    timelines = {}
    index = []
    for t in threads:
        md = t.timeline_md(limits)
        name = "%s-%s" % (slug(t.summary["title"]), t.summary["id"][:8])
        with open(os.path.join(out, "threads", name + ".md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        t.summary["export_file"] = "threads/%s.md" % name
        timelines[t.summary["id"]] = md
        index.append(t.summary)
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": generated, "codex_home": home, "codex_lens": VERSION,
                   "filters": {"project": args.project, "since_h": args.since, "titles": args.title},
                   "total_threads_on_disk": len(all_threads), "threads": index}, fh, indent=2, default=str)
    with open(os.path.join(out, "digest.md"), "w", encoding="utf-8") as fh:
        fh.write(digest_md(threads, generated))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(dashboard_html(threads, generated, timelines))
    print(json.dumps({"out": out, "threads": len(threads), "total_on_disk": len(all_threads),
                      "status": collections.Counter(t.summary["status"] for t in threads)}, indent=2))


def cmd_show(args):
    home = pick_home(args.home)
    threads = load_threads(home)
    key = args.thread
    hits = [t for t in threads if t.summary["id"].startswith(key)] or \
           [t for t in threads if norm(key) and norm(key) in norm(t.summary["title"])]
    if not hits:
        sys.exit("no thread matches %r" % key)
    hits.sort(key=lambda t: t.summary["last_activity"] or "", reverse=True)
    sys.stdout.write(hits[0].timeline_md(_limits(args.full)))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="codex-lens", description=__doc__.split("\n\n")[0])
    ap.add_argument("--home", help="Codex home (default: $CODEX_HOME or ~/.codex)")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd")

    def filters(p):
        p.add_argument("--project", help="substring of cwd / folder / title (case- and punctuation-insensitive)")
        p.add_argument("--since", type=float, help="only threads active in the last N hours")
        p.add_argument("--title", action="append", help="title substring; repeatable; OR-ed with --project")
        p.add_argument("--id", action="append", help="thread id prefix; repeatable")
        p.add_argument("--archived", action="store_true", help="include archived threads")

    p = sub.add_parser("discover", help="print Codex home layout and record shapes")
    p.add_argument("--sample", type=int, default=5, help="recent rollouts to histogram")
    p.set_defaults(fn=cmd_discover)
    p = sub.add_parser("list", help="table of threads")
    filters(p)
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("export", help="write index.json, digest.md, index.html, threads/*.md")
    filters(p)
    p.add_argument("--out", required=True)
    p.add_argument("--full", action="store_true", help="do not truncate messages")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("show", help="print one thread's timeline")
    p.add_argument("thread", help="id prefix or title substring")
    p.add_argument("--full", action="store_true")
    p.set_defaults(fn=cmd_show)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
