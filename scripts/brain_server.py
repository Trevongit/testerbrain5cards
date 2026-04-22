#!/usr/bin/env python3
import errno
import hashlib
import json
import os
import re
import shlex
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from shutil import which
from typing import Any

HOST = "127.0.0.1"
PORT = 8765
PORT_KILL_TIMEOUT_SEC = 1.0
PORT_KILL_POLL_SEC = 0.1
STARTUP_RETRIES = 3
STARTUP_RETRY_DELAY_SEC = 0.3

ROOT = Path(__file__).resolve().parents[1]
BRAIN = ROOT / "G-Codex-brain"
CONDUCTOR = ROOT / "scripts" / "conductor.sh"
REMOVE_GCODEX = ROOT / "scripts" / "remove-gcodex.sh"
FIRST_HANDOFF_PATH = BRAIN / "02_FIRST_HANDOFF.md"
AGENT_ROLES_PATH = BRAIN / "AGENT_ROLES.md"
PROPOSAL_OUTCOMES_PATH = BRAIN / "PROPOSAL_OUTCOMES.md"
USER_DOMAIN_NODES_PATH = BRAIN / "user_domain_nodes.json"
NODE_MANIFEST_PATH = BRAIN / "NODE_MANIFEST.json"
REPO_POSTURE_PATH = BRAIN / "REPO_POSTURE.json"
USER_PROFILE_PATH = BRAIN / "user_profile.json"
CHANGELOG_PATH = BRAIN / "CHANGELOG.md"
BACKUPS_DIR = ROOT / ".backups"

CONTEXT_FILES = [
    ROOT / "AGENTS.md",
    BRAIN / "00_INDEX.md",
    BRAIN / "01_FIRST_RUN_GUIDE.md",
    BRAIN / "02_FIRST_HANDOFF.md",
    BRAIN / "AGENT_ROLES.md",
    BRAIN / "ROADMAP.md",
    BRAIN / "00_BOOTSTRAP_GUIDE.md",
    BRAIN / "02_ETHOS_AND_PRODUCT_PRINCIPLES.md",
    BRAIN / "03_ACTIVE_NOW.md",
    BRAIN / "MERGE_LOG.md",
    BRAIN / "CHANGELOG.md",
    BRAIN / "DYNAMIC_MEMORY.md",
    BRAIN / "PROPOSAL_OUTCOMES.md",
    BRAIN / "user_domain_nodes.json",
    BRAIN / "AGENT_RULES.md",
]
SWARM_PACKET_PATH = ROOT / ".swarm_packet.txt"
SWARM_PACKET_GLOBS = [".swarm_packet.txt", "*.swarm_packet.txt"]
NOTIFY_ENABLED_FILE = ROOT / ".notify_enabled"
WATCHER_PID_FILE = ROOT / ".watcher.pid"
AMBIENT_INGRESS_PID_FILE = ROOT / ".ambient_ingress.pid"
AMBIENT_INGRESS_PARENT_FILE = ROOT / ".ambient_ingress.parent"
AMBIENT_AUTO_START_FILE = ROOT / ".ambient_ingress.auto_start"
MD_CORE_STATE_PATH = ROOT / ".md_core_state.json"
ALLOWED_RISK_LEVELS = {"LOW ADVENTURE", "MEDIUM ADVENTURE", "HIGH ADVENTURE"}
ACTIVITY_REFRESH_TOKEN = 0
ACTIVITY_REFRESH_AT = ""
DEFAULT_LEAD_EXECUTOR = "OAC"
PREFERRED_LEAD_KEYS = ("OAC", "GGC")
DEFAULT_MD_BRAIN_ENGINE = "GGC"
GITHUB_STATUS_TTL_SEC = 45.0
GITHUB_META_SCAN_TTL_SEC = 86400.0  # Once per day
GITHUB_STATUS_LOCK = threading.Lock()
GITHUB_STATUS_CACHE = {
    "checked_at": 0.0,
    "payload": {
        "default_branch": None,
        "last_commit_sha": None,
        "last_commit_message": None,
        "last_pushed_at": "unavailable",
        "ahead_behind": None,
        "open_issues_count": None,
        "open_prs": None,
        "active_path": "unavailable",
        "repo": None,
    },
}
GITHUB_META_SCAN_CACHE = {
    "checked_at": 0.0,
    "payload": None,
}
AGENT_ROLES_TEMPLATE = """# AGENT ROLES

# Preferred CLI co-leads: OAC and GGC.
# MD_BRAIN_ENGINE defaults to GGC for synthesis/supportive guidance; OAC remains execution lead.
# AGa remains troubleshooter/visual auditor (manual use; not default lead).
LEAD_EXECUTOR: OAC
MD_BRAIN_ENGINE: GGC
AGENTS:
  OAC:
    display: OAC
    description: Surgical code & deterministic execution (preferred CLI co-lead)
  GGC:
    display: GGC
    description: Google Gemini Codex CLI - strong reasoning & execution (preferred CLI co-lead)
  AGa:
    display: AGa
    description: Troubleshooter & Visual Auditor (manual use only; not default lead)
  Gemini 3:
    display: Gemini 3
    description: Deep reasoning & architecture
  Grok:
    display: Grok
    description: Alignment, truth-seeking & anti-drift
  ChatGPT:
    display: ChatGPT
    description: Polish, UX clarity & creative refinement
"""

BRIDGE_HEADER_LINE_RE = re.compile(
    r"^\s*#{2,4}\s*(?:🧠\s*)?G[\s-]*CODEX\s*INJECTION\s*:?\s*(.*)$",
    flags=re.IGNORECASE,
)
BRIDGE_HEADER_ANY_RE = re.compile(
    r"(?im)^\s*#{2,4}\s*(?:🧠\s*)?G[\s-]*CODEX\s*INJECTION\s*:?\s*(.*)$"
)
BRIDGE_META_LINE_RE = re.compile(
    r"(?im)^(?:[-*•]\s*)?(?:\*\*)?(?:source|from|model|timestamp|content)(?:\*\*)?\s*:\s*(.+)$"
)
MAJOR_CHANGE_HINT_RE = re.compile(
    r"(?i)\b(major|breaking|overhaul|rewrite|migration|repo-shaping|architecture|re-architect|large refactor)\b"
)
ERROR_HINT_RE = re.compile(r"(?i)\b(error|failed|failure|traceback|exception|fatal)\b")
ACTIVITY_HEADERS = {
    "SESSION_LOG_ENTRY",
    "GCODEX_BRIDGE_INJECTION",
    "HUMAN_INJECTION",
    "CLI_OUTPUT",
    "MD_REPORT",
    "MD_GUIDANCE",
    "MD_HARMONIZED_ENTRY",
    "MD_ASSIGNMENT",
    "MD_PROPOSAL",
}
PROJECT_MEMORY_MAJOR_TRIGGERS = {"HUMAN_INJECTION", "PROPOSAL_ACCEPTED", "MANUAL_REQUEST"}
LARGE_REPO_FILE_THRESHOLD = 50
LARGE_REPO_DEPTH_THRESHOLD = 6
OLLAMA_STATUS_TTL_SEC = 45
OLLAMA_PROBE_TIMEOUT_SEC = 2.0
OLLAMA_WARMUP_TIMEOUT_SEC = 12.0
OLLAMA_WARMUP_COOLDOWN_SEC = 30.0
LOCAL_REASONING_ACTIVE_TTL_SEC = 600.0
OLLAMA_COMMON_MODELS = (
    "llama3.2:3b",
    "llama3.1:8b",
    "llama3:8b",
    "llama3",
    "mistral:latest",
    "mistral",
)
OLLAMA_STATUS_LOCK = threading.Lock()
OLLAMA_STATUS_CACHE = {
    "checked_at": 0.0,
    "probe_in_progress": False,
    "warmup_in_progress": False,
    "warmup_cooldown_until": 0.0,
    "last_success_epoch": 0.0,
    "status": {
        "deep_sea_requested": False,
        "ollama_available": False,
        "warmup_state": "Idle",
        "last_warmup_timestamp": "",
        "last_failure_reason": "",
        "active_model": None,
    },
}
CONVERSATION_BUS_HEALTHY_SEC = 1800
CONVERSATION_BUS_STALE_SEC = 7200
MCP_AUTH_STATUS_IDLE = "IDLE"
MCP_AUTH_STATUS_PENDING = "REQUEST_PENDING"
MCP_AUTH_STATUS_AUTHORIZED = "AUTHORIZED"
MCP_AUTH_STATUS_REVOKED = "REVOKED"
MCP_AUTH_LOCK = threading.Lock()
MCP_AUTH_STATE = {
    "status": MCP_AUTH_STATUS_IDLE,
    "session_id": f"mcp-{uuid.uuid4().hex[:10]}",
    "requested_at": "",
    "requested_by": "",
    "request_reason": "",
    "authorized_at": "",
    "authorized_by": "",
    "revoked_at": "",
    "revoked_by": "",
    "last_event_at": "",
    "client_connected": False,
    "client_last_seen": "",
}
DOMAIN_NODE_HINTS = {
    "isan_study": ("isan", "thai", "teacher", "grammar", "dialect"),
    "marine_systems": ("marine", "reef", "reefsys", "aqua one", "aquarium", "water chemistry"),
}
DEFAULT_USER_DOMAIN_NODES = ("isan_study", "marine_systems")


def _dynamic_memory_text():
    path = BRAIN / "DYNAMIC_MEMORY.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _split_dynamic_memory_blocks(text):
    if not text:
        return []
    blocks = []
    current_header = ""
    current_lines = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            if current_header:
                blocks.append((current_header, "\n".join(current_lines).strip()))
            current_header = line[3:].strip()
            current_lines = [line]
            continue
        if current_header:
            current_lines.append(line)
    if current_header:
        blocks.append((current_header, "\n".join(current_lines).strip()))
    return blocks


def _block_field_value(block, key):
    pattern = re.compile(rf"(?im)^- {re.escape(key)}:\s*(.*)$")
    match = pattern.search(block or "")
    return match.group(1).strip() if match else ""


def _extract_content_body(block):
    if not block:
        return ""
    fenced_match = re.search(
        r"(?ims)^- content:\s*\n```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)\n```",
        block,
    )
    if fenced_match:
        return fenced_match.group(1).strip()
    inline_match = re.search(r"(?im)^- content:\s*(.+)$", block)
    if inline_match:
        return inline_match.group(1).strip()
    summary_match = re.search(r"(?im)^- summary:\s*(.+)$", block)
    if summary_match:
        return summary_match.group(1).strip()
    return ""


def _parse_cli_output_block(block):
    timestamp = _normalize_one_line(_block_field_value(block, "timestamp"), _now_iso())
    source = _normalize_one_line(_block_field_value(block, "source"), "OAC")
    session_label = _normalize_one_line(_block_field_value(block, "session_label"), "terminal")
    command = _normalize_one_line(_block_field_value(block, "command"), "")
    raw_return_code = _normalize_one_line(_block_field_value(block, "return_code"), "")
    stdout_summary = _compact_excerpt(_normalize_one_line(_block_field_value(block, "stdout_summary"), ""), limit=180)
    stderr_summary = _compact_excerpt(_normalize_one_line(_block_field_value(block, "stderr_summary"), ""), limit=180)
    excerpt = _compact_excerpt(_extract_content_body(block), limit=280)

    return_code = None
    if raw_return_code:
        try:
            return_code = int(raw_return_code)
        except ValueError:
            return_code = None

    if not stdout_summary and not stderr_summary:
        fallback = _compact_excerpt(excerpt or block or "CLI output captured.", limit=180)
        stdout_summary = fallback

    status_label = "ok" if return_code == 0 else (f"exit {return_code}" if return_code is not None else "captured")
    summary_parts = []
    if command:
        summary_parts.append(f"{command} [{status_label}]")
    else:
        summary_parts.append(f"CLI session [{status_label}]")
    if stdout_summary:
        summary_parts.append(f"stdout: {stdout_summary}")
    if stderr_summary and stderr_summary.lower() not in {"none", "(none)", "n/a"}:
        summary_parts.append(f"stderr: {stderr_summary}")

    summary_line = _compact_excerpt(" | ".join(summary_parts), limit=220)
    return {
        "timestamp": timestamp,
        "source": source,
        "session_label": session_label,
        "command": command,
        "return_code": return_code,
        "stdout_summary": stdout_summary,
        "stderr_summary": stderr_summary,
        "excerpt": excerpt,
        "summary_line": summary_line,
    }


def _recent_cli_output_events(limit=6):
    events = []
    for header, block in reversed(_split_dynamic_memory_blocks(_dynamic_memory_text())):
        if str(header).upper() != "CLI_OUTPUT":
            continue
        parsed = _parse_cli_output_block(block)
        parsed["sort_epoch"] = _to_epoch(parsed.get("timestamp", ""))
        events.append(parsed)
        if len(events) >= limit:
            break
    return events


def _conversation_bus_status():
    latest = _recent_cli_output_events(limit=1)
    event = latest[0] if latest else {}
    last_capture_at = _normalize_one_line(event.get("timestamp", ""), "")
    age_seconds = None
    if last_capture_at:
        age = time.time() - _to_epoch(last_capture_at)
        if age >= 0:
            age_seconds = int(age)

    capture_active = bool(CONDUCTOR.exists())
    if not capture_active:
        state = "UNAVAILABLE"
        healthy = False
    elif age_seconds is None:
        state = "IDLE"
        healthy = True
    elif age_seconds <= CONVERSATION_BUS_HEALTHY_SEC:
        state = "HEALTHY"
        healthy = True
    elif age_seconds <= CONVERSATION_BUS_STALE_SEC:
        state = "STALE"
        healthy = False
    else:
        state = "QUIET"
        healthy = False

    return {
        "active": capture_active,
        "healthy": healthy,
        "state": state,
        "last_capture_at": last_capture_at,
        "seconds_since_last_capture": age_seconds,
        "last_source": _normalize_one_line(event.get("source", ""), ""),
        "last_session_label": _normalize_one_line(event.get("session_label", ""), ""),
        "last_command": _normalize_one_line(event.get("command", ""), ""),
        "last_summary": _normalize_one_line(event.get("summary_line", ""), ""),
    }


def _normalize_md_conversation_items(raw_items, limit=12):
    items = []
    for raw in raw_items or []:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role", "")).strip().lower()
        if role not in {"human", "md"}:
            continue
        text = _compact_excerpt(str(raw.get("text", "")).strip(), limit=220)
        if not text:
            continue
        items.append(
            {
                "role": role,
                "text": text,
                "timestamp": str(raw.get("timestamp", "")).strip(),
                "source": str(raw.get("source", "")).strip(),
            }
        )
    if limit and len(items) > limit:
        return items[-limit:]
    return items


def _infer_human_request_focus(text):
    lowered = str(text or "").strip().lower()
    if not lowered:
        return ""
    if any(
        token in lowered
        for token in (
            "design_proposal_id:",
            "review with md",
            "review design proposal",
            "worth_assessment:",
            "value_score:",
            "design review request",
        )
    ):
        return "design_review"
    if any(token in lowered for token in ("health", "status", "steady", "risk")):
        return "health"
    if any(
        token in lowered
        for token in (
            "what should i work on",
            "what should i focus on",
            "what next",
            "next mission",
            "next step",
            "work on next",
            "focus on next",
        )
    ):
        return "next_mission"
    if any(token in lowered for token in ("stuck", "blocked", "friction", "help", "struggling")):
        return "support"
    if any(token in lowered for token in ("report", "summary", "synthesize")):
        return "report"
    return "general"


def _extract_design_review_request(text):
    raw = str(text or "")
    if not raw.strip():
        return {}

    proposal_match = re.search(r"(?:DESIGN_PROPOSAL_ID|PROPOSAL_ID)\s*:\s*(P-\d+)", raw, flags=re.IGNORECASE)
    summary_match = re.search(r"(?:SUMMARY)\s*:\s*(.+)", raw, flags=re.IGNORECASE)
    targets_match = re.search(r"(?:TARGET_FILES)\s*:\s*(.+)", raw, flags=re.IGNORECASE)
    excerpt_match = re.search(r"(?:DESIGN_PAYLOAD_EXCERPT)\s*:\s*(.+)", raw, flags=re.IGNORECASE)
    worth_match = re.search(r"WORTH_ASSESSMENT\s*:\s*(.+?)(?=\s+[A-Z_]+\s*:|$)", raw, flags=re.IGNORECASE | re.DOTALL)
    value_match = re.search(r"VALUE_SCORE\s*:\s*(10|[1-9])(?:\s*/\s*10)?", raw, flags=re.IGNORECASE)

    return {
        "proposal_id": _normalize_one_line(proposal_match.group(1), "") if proposal_match else "",
        "summary": _compact_excerpt(_normalize_one_line(summary_match.group(1), ""), limit=220) if summary_match else "",
        "target_files": _compact_excerpt(_normalize_one_line(targets_match.group(1), ""), limit=220) if targets_match else "",
        "design_payload_excerpt": _compact_excerpt(_normalize_one_line(excerpt_match.group(1), ""), limit=220) if excerpt_match else "",
        "worth_assessment": _compact_excerpt(_normalize_one_line(worth_match.group(1), ""), limit=220) if worth_match else "",
        "value_score": int(value_match.group(1)) if value_match else None,
    }


def _collect_md_conversation_window(max_turns=8):
    pair_target = int(max_turns or 8)
    if pair_target < 6:
        pair_target = 6
    if pair_target > 8:
        pair_target = 8

    messages = []
    for header, block in _split_dynamic_memory_blocks(_dynamic_memory_text()):
        normalized = str(header).upper()
        timestamp = _block_field_value(block, "timestamp")
        if normalized == "HUMAN_INJECTION":
            text = _extract_content_body(block)
            if not text:
                continue
            messages.append(
                {
                    "role": "human",
                    "text": _compact_excerpt(text, limit=220),
                    "timestamp": timestamp,
                    "source": _block_field_value(block, "source") or "Human",
                }
            )
            continue

        if normalized == "MD_GUIDANCE":
            suggestion = _block_field_value(block, "suggestion") or _extract_content_body(block)
            if not suggestion:
                continue
            messages.append(
                {
                    "role": "md",
                    "text": _compact_excerpt(suggestion, limit=220),
                    "timestamp": timestamp,
                    "source": "Managing Director",
                }
            )

    # Keep enough context to preserve the most recent 6-8 paired turns.
    messages = _normalize_md_conversation_items(messages, limit=max(18, pair_target * 5))
    if not messages:
        return {
            "messages": [],
            "human_recent": [],
            "md_recent": [],
            "latest_human": "",
            "latest_md": "",
            "prior_human": "",
            "prior_md": "",
            "paired_turns": [],
            "focus": "",
            "history_summary": "",
            "recent_summary": "",
        }

    human_positions = [idx for idx, item in enumerate(messages) if item.get("role") == "human"]
    paired_turns = []
    if human_positions:
        tracked_positions = human_positions[-pair_target:]
        for index, pos in enumerate(tracked_positions):
            human_item = messages[pos]
            next_human_pos = tracked_positions[index + 1] if index + 1 < len(tracked_positions) else len(messages)
            md_text = ""
            for candidate in messages[pos + 1 : next_human_pos]:
                if candidate.get("role") == "md":
                    md_text = candidate.get("text", "")
                    break
            paired_turns.append(
                {
                    "human": human_item.get("text", ""),
                    "md": md_text,
                }
            )
    else:
        for item in messages[-pair_target:]:
            if item.get("role") == "md":
                paired_turns.append({"human": "", "md": item.get("text", "")})

    paired_turns = paired_turns[-pair_target:]

    selected = []
    for turn in paired_turns:
        human_text = str(turn.get("human", "")).strip()
        md_text = str(turn.get("md", "")).strip()
        if human_text:
            selected.append({"role": "human", "text": human_text, "timestamp": "", "source": "Human"})
        if md_text:
            selected.append({"role": "md", "text": md_text, "timestamp": "", "source": "Managing Director"})
    selected = _normalize_md_conversation_items(selected, limit=max(12, pair_target * 2))

    history_summary = ""
    if len(messages) > len(selected):
        history_summary = _summarize_conversation_messages(messages[:-len(selected)], limit=260)
    if not history_summary and len(messages) > max(12, pair_target * 2):
        history_summary = _summarize_conversation_messages(messages[:-pair_target], limit=240)

    recent_summary = _summarize_conversation_messages(selected, limit=240)

    human_recent = [item["text"] for item in selected if item.get("role") == "human"][-pair_target:]
    md_recent = [item["text"] for item in selected if item.get("role") == "md"][-pair_target:]
    latest_human = human_recent[-1] if human_recent else ""
    latest_md = md_recent[-1] if md_recent else ""
    prior_human = human_recent[-2] if len(human_recent) >= 2 else ""
    prior_md = md_recent[-2] if len(md_recent) >= 2 else ""

    return {
        "messages": selected,
        "human_recent": human_recent,
        "md_recent": md_recent,
        "latest_human": latest_human,
        "latest_md": latest_md,
        "prior_human": prior_human,
        "prior_md": prior_md,
        "paired_turns": paired_turns,
        "focus": _infer_human_request_focus(latest_human),
        "history_summary": _compact_excerpt(history_summary, limit=260),
        "recent_summary": _compact_excerpt(recent_summary, limit=240),
    }


def _repo_size_profile():
    file_count = 0
    max_depth = 0
    large = False
    ignored_dirs = {
        ".git",
        ".venv",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        "__pycache__",
        ".cache",
        ".codex",
        "dist",
        "build",
        "target",
    }

    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = Path(dirpath).relative_to(ROOT)
        depth = len(rel.parts)
        if depth > max_depth:
            max_depth = depth
        dirnames[:] = [name for name in dirnames if name not in ignored_dirs]

        file_count += len(filenames)
        if file_count > LARGE_REPO_FILE_THRESHOLD or max_depth >= LARGE_REPO_DEPTH_THRESHOLD:
            large = True
            break

    return {
        "file_count": int(file_count),
        "max_depth": int(max_depth),
        "is_large": bool(large),
    }


def _summarize_conversation_messages(messages, limit=320):
    items = _normalize_md_conversation_items(messages or [], limit=10)
    if not items:
        return ""
    human = [item.get("text", "") for item in items if item.get("role") == "human"][-3:]
    md = [item.get("text", "") for item in items if item.get("role") == "md"][-2:]
    parts = []
    if human:
        parts.append(f"human themes: {' | '.join(human)}")
    if md:
        parts.append(f"MD guidance themes: {' | '.join(md)}")
    if not parts:
        return ""
    return _compact_excerpt("; ".join(parts), limit=limit)


def _merge_project_state_summary(existing, addition, limit=520):
    base = _normalize_one_line(existing, "")
    extra = _normalize_one_line(addition, "")
    if not extra:
        return base
    if not base:
        return _compact_excerpt(extra, limit=limit)
    if extra in base:
        return _compact_excerpt(base, limit=limit)
    merged = f"{base} || {extra}"
    return _compact_excerpt(merged, limit=limit)


def _compact_conversation_for_large_repo(messages, keep_recent=6):
    items = _normalize_md_conversation_items(messages or [], limit=16)
    if len(items) <= keep_recent:
        return items, ""
    older = items[:-keep_recent]
    recent = items[-keep_recent:]
    summary = _summarize_conversation_messages(older, limit=260)
    return recent, summary


def _compose_project_pattern_summary(summary_line, analysis, conversation):
    summary = _normalize_one_line(summary_line, "")
    mission = _normalize_one_line(analysis.get("next_mission", ""), "")
    focus = _normalize_one_line(analysis.get("conversation_focus", ""), "")
    risks = analysis.get("risks", []) or []
    risk = _normalize_one_line(risks[0], "")
    trend = _normalize_one_line(_summarize_conversation_messages(conversation.get("messages", []), limit=220), "")
    parts = []
    if summary:
        parts.append(f"recent event: {summary}")
    if mission:
        parts.append(f"preferred next slice: {mission}")
    if risk:
        parts.append(f"risk trend: {risk}")
    if focus:
        parts.append(f"focus pattern: {focus}")
    if trend:
        parts.append(f"interaction pattern: {trend}")
    return _compact_excerpt("; ".join(parts), limit=420)


def _detect_repeated_focus_area(conversation):
    convo = conversation if isinstance(conversation, dict) else {}
    recent = [str(item).strip() for item in (convo.get("human_recent", []) or []) if str(item).strip()]
    if len(recent) < 2:
        return ""
    counts = {}
    for text in recent[-4:]:
        focus = _infer_human_request_focus(text)
        if focus and focus != "general":
            counts[focus] = counts.get(focus, 0) + 1
    repeated = [focus for focus, count in counts.items() if count >= 2]
    return repeated[0] if repeated else ""


def _focus_to_creator_tags(focus):
    mapping = {
        "next_mission": ["small_safe_steps", "planning_rhythm"],
        "support": ["supportive_guidance", "small_safe_steps"],
        "health": ["health_check_rhythm"],
        "report": ["planning_rhythm"],
    }
    return list(mapping.get(str(focus or "").strip().lower(), []))


def _extract_creator_focus_tags(human_text="", focus="", next_mission=""):
    combined = " ".join(
        [
            _normalize_one_line(human_text, ""),
            _normalize_one_line(next_mission, ""),
        ]
    ).lower()
    tags = set(_focus_to_creator_tags(focus))

    if any(token in combined for token in ("visual", "ui", "ux", "layout", "dashboard", "polish", "styling", "visual polish")):
        tags.add("visual_polish")
    if any(token in combined for token in ("test", "regression", "verify", "verification", "check", "qa", "testing rhythm", "test rhythm")):
        tags.add("testing_rhythm")
    if any(token in combined for token in ("doc", "readme", "guide", "notes", "document")):
        tags.add("documentation_rhythm")
    if any(token in combined for token in ("roadmap", "milestone", "plan", "focus on next", "next step")):
        tags.add("planning_rhythm")
    if any(token in combined for token in ("low-adventure", "small", "surgical", "deterministic", "safe", "small safe steps", "safe steps")):
        tags.add("small_safe_steps")
    if any(token in combined for token in ("stuck", "friction", "support", "calm", "help")):
        tags.add("supportive_guidance")

    return sorted(tags)


def _canonical_creator_tag(raw):
    tag = _normalize_one_line(raw, "").lower().replace(" ", "_")
    aliases = {
        "low_adventure_preference": "small_safe_steps",
        "testing_focus": "testing_rhythm",
        "visual_polish_preference": "visual_polish",
        "safe_steps_preference": "small_safe_steps",
    }
    return aliases.get(tag, tag)


def _update_creator_focus_patterns(existing, tags, max_tags=8, cap=9):
    current = existing if isinstance(existing, dict) else {}
    updated = {}
    for key, value in current.items():
        tag = _canonical_creator_tag(key)
        if not tag:
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        updated[tag] = min(count, cap)

    for raw in tags or []:
        tag = _canonical_creator_tag(raw)
        if not tag:
            continue
        updated[tag] = min(updated.get(tag, 0) + 1, cap)

    ordered = sorted(updated.items(), key=lambda pair: (-pair[1], pair[0]))[:max_tags]
    return {key: value for key, value in ordered}


def _creator_focus_patterns_summary(patterns, limit=180):
    mapping = {
        "visual_polish": "visual polish",
        "testing_rhythm": "a steady testing rhythm",
        "documentation_rhythm": "documentation rhythm",
        "small_safe_steps": "small safe steps",
        "planning_rhythm": "roadmap sequencing",
        "supportive_guidance": "calm course-corrections",
        "health_check_rhythm": "health check-ins",
    }
    rows = patterns.items() if isinstance(patterns, dict) else []
    normalized = []
    for key, value in rows:
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        normalized.append((str(key), count))
    ordered = sorted(normalized, key=lambda pair: (-pair[1], pair[0]))
    labels = []
    for key, count in ordered:
        if int(count) <= 0:
            continue
        label = mapping.get(str(key), str(key).replace("_", " "))
        labels.append(label)
        if len(labels) >= 3:
            break
    if not labels:
        return ""
    if len(labels) == 1:
        text = f"you often prefer {labels[0]}"
    elif len(labels) == 2:
        text = f"you often prefer {labels[0]} and {labels[1]}"
    else:
        text = f"you often prefer {labels[0]}, {labels[1]}, and {labels[2]}"
    return _compact_excerpt(text, limit=limit)


def _creator_style_anticipation_line(patterns=None, detected_tags=None):
    canonical_detected = {_canonical_creator_tag(tag) for tag in (detected_tags or []) if _canonical_creator_tag(tag)}
    normalized = _update_creator_focus_patterns(patterns or {}, [], max_tags=8, cap=9)
    ordered = sorted(
        [(str(key), int(value)) for key, value in normalized.items() if str(key)],
        key=lambda pair: (-pair[1], pair[0]),
    )
    top_pattern = ordered[0][0] if ordered else ""

    if "visual_polish" in canonical_detected or top_pattern == "visual_polish":
        return "Knowing you often enjoy visual polish, I recommend a calm refinement pass that keeps this slice small and safe."
    if "testing_rhythm" in canonical_detected or top_pattern == "testing_rhythm":
        return "Knowing you value a steady testing rhythm, I recommend a quick verify-first pass before expanding scope."
    if "small_safe_steps" in canonical_detected or top_pattern == "small_safe_steps":
        return "From your recent patterns, a calm low-adventure step in this direction may feel right."
    return ""


def _normalize_project_personality_profile(existing):
    payload = existing if isinstance(existing, dict) else {}
    preferred_slice_size = _normalize_one_line(payload.get("preferred_slice_size", ""), "").lower()
    if preferred_slice_size not in {"small", "medium", "deep"}:
        preferred_slice_size = "small"

    def _clean_list(raw, cap=3):
        values = []
        for item in raw if isinstance(raw, list) else []:
            text = _normalize_one_line(item, "")
            if not text:
                continue
            if text in values:
                continue
            values.append(text)
            if len(values) >= cap:
                break
        return values

    recurring = _clean_list(payload.get("recurring_themes", []), cap=3)
    flow = _clean_list(payload.get("flow_preferences", []), cap=3)
    recent_focus_notes = _clean_list(payload.get("recent_focus_notes", []), cap=5)
    preference_signals = _clean_list(payload.get("preference_signals", []), cap=6)
    summary = _normalize_one_line(payload.get("summary", ""), "")
    return {
        "preferred_slice_size": preferred_slice_size,
        "recurring_themes": recurring,
        "flow_preferences": flow,
        "recent_focus_notes": recent_focus_notes,
        "preference_signals": preference_signals,
        "summary": summary,
    }


def _project_personality_summary_line(profile):
    normalized = _normalize_project_personality_profile(profile)
    themes = normalized.get("recurring_themes", [])
    flow = normalized.get("flow_preferences", [])
    signals = normalized.get("preference_signals", [])
    preferred = normalized.get("preferred_slice_size", "small")

    if themes:
        top_theme = themes[0].lower()
        if "visual polish" in top_theme:
            return "a calm visual polish pass may feel right"
        if "testing" in top_theme:
            return "a steady verify-first pass may feel right"
        if "documentation" in top_theme:
            return "a clean documentation refinement pass may feel right"
        return f"a calm {themes[0]} pass may feel right"
    if flow:
        return f"a {flow[0].lower()} pass may feel right"
    if signals:
        signal = str(signals[0]).replace("_", " ").strip()
        if signal:
            return f"a calm {signal.lower()} step may feel right"
    if preferred == "deep":
        return "a focused deep-thinking session may feel right before execution"
    if preferred == "medium":
        return "a focused medium-size slice may feel right"
    return "a calm low-adventure step may feel right"


def _update_project_personality_profile(existing, latest_human="", detected_tags=None, focus="", next_mission=""):
    profile = _normalize_project_personality_profile(existing)
    combined = " ".join(
        [
            _normalize_one_line(latest_human, ""),
            _normalize_one_line(next_mission, ""),
        ]
    ).lower()
    tags = {_canonical_creator_tag(tag) for tag in (detected_tags or []) if _canonical_creator_tag(tag)}

    if any(token in combined for token in ("small", "low-adventure", "safe", "surgical", "tiny slice")):
        profile["preferred_slice_size"] = "small"
    elif any(token in combined for token in ("medium", "moderate")):
        profile["preferred_slice_size"] = "medium"
    elif any(token in combined for token in ("deep", "strategic", "multi-quarter", "architecture")):
        profile["preferred_slice_size"] = "deep"

    theme_candidates = []
    if "visual_polish" in tags or any(token in combined for token in ("visual", "ui", "ux", "polish", "dashboard")):
        theme_candidates.append("visual polish")
    if "testing_rhythm" in tags or any(token in combined for token in ("test", "verify", "regression", "qa")):
        theme_candidates.append("testing rhythm")
    if "documentation_rhythm" in tags or any(token in combined for token in ("doc", "readme", "guide", "notes")):
        theme_candidates.append("documentation clarity")
    if "planning_rhythm" in tags or any(token in combined for token in ("roadmap", "milestone", "plan", "next step")):
        theme_candidates.append("roadmap sequencing")

    flow_candidates = []
    if "small_safe_steps" in tags or any(token in combined for token in ("low-adventure", "small safe", "calm step", "surgical")):
        flow_candidates.append("calm low-adventure")
    if "supportive_guidance" in tags or any(token in combined for token in ("calm", "support", "gentle", "friction")):
        flow_candidates.append("supportive rhythm")
    if any(token in combined for token in ("verify first", "test first", "regression first", "verify-first")):
        flow_candidates.append("verify-first rhythm")

    for candidate in theme_candidates:
        if candidate in profile["recurring_themes"]:
            profile["recurring_themes"].remove(candidate)
        profile["recurring_themes"].insert(0, candidate)
    profile["recurring_themes"] = profile["recurring_themes"][:3]

    for candidate in flow_candidates:
        if candidate in profile["flow_preferences"]:
            profile["flow_preferences"].remove(candidate)
        profile["flow_preferences"].insert(0, candidate)
    profile["flow_preferences"] = profile["flow_preferences"][:3]

    if focus == "health" and "supportive rhythm" not in profile["flow_preferences"]:
        profile["flow_preferences"].append("supportive rhythm")
        profile["flow_preferences"] = profile["flow_preferences"][:3]

    signal_candidates = []
    if "visual_polish" in tags:
        signal_candidates.append("visual_polish")
    if "testing_rhythm" in tags:
        signal_candidates.append("testing_rhythm")
    if "small_safe_steps" in tags:
        signal_candidates.append("small_safe_steps")
    if "supportive_guidance" in tags:
        signal_candidates.append("supportive_guidance")
    if "planning_rhythm" in tags:
        signal_candidates.append("planning_rhythm")
    if "health_check_rhythm" in tags:
        signal_candidates.append("health_check_rhythm")
    if focus in {"next_mission", "support", "health", "report"}:
        signal_candidates.append(f"focus_{focus}")

    for candidate in signal_candidates:
        if candidate in profile["preference_signals"]:
            profile["preference_signals"].remove(candidate)
        profile["preference_signals"].insert(0, candidate)
    profile["preference_signals"] = profile["preference_signals"][:6]

    focus_note_seed = _normalize_one_line(latest_human, "") or _normalize_one_line(next_mission, "")
    if focus_note_seed:
        focus_note = _compact_excerpt(focus_note_seed, limit=120)
        if focus_note in profile["recent_focus_notes"]:
            profile["recent_focus_notes"].remove(focus_note)
        profile["recent_focus_notes"].insert(0, focus_note)
    profile["recent_focus_notes"] = profile["recent_focus_notes"][:5]

    profile["summary"] = _project_personality_summary_line(profile)
    return profile


def _build_persona_influence(profile=None, creator_focus_summary="", detected_tags=None, focus=""):
    normalized = _normalize_project_personality_profile(profile or {})
    detected = {_canonical_creator_tag(item) for item in (detected_tags or []) if _canonical_creator_tag(item)}
    signals = [str(item).strip().lower() for item in normalized.get("preference_signals", []) if str(item).strip()]
    recurring = [str(item).strip().lower() for item in normalized.get("recurring_themes", []) if str(item).strip()]
    flow = [str(item).strip().lower() for item in normalized.get("flow_preferences", []) if str(item).strip()]
    recent_notes = [str(item).strip() for item in normalized.get("recent_focus_notes", []) if str(item).strip()]

    top_signal = ""
    if "visual_polish" in detected or "visual_polish" in signals or any("visual polish" in item for item in recurring):
        top_signal = "visual polish"
        attuned_line = "Knowing your visual polish rhythm, I recommend one small interface refinement in a single file, then run one local verification."
    elif "testing_rhythm" in detected or "testing_rhythm" in signals:
        top_signal = "testing rhythm"
        attuned_line = "Knowing your testing rhythm, I recommend one targeted verification on the touched path before any broader changes."
    elif "small_safe_steps" in detected or "small_safe_steps" in signals or any("calm low-adventure" in item for item in flow):
        top_signal = "small safe steps"
        attuned_line = "Given your preference for small safe steps, I recommend one deterministic file-level change and one quick local verify."
    elif creator_focus_summary:
        top_signal = "recent creator focus patterns"
        attuned_line = "From your recent focus patterns, I recommend one calm low-adventure step with one local verification."
    elif recent_notes:
        top_signal = "recent focus notes"
        attuned_line = "From your recent focus notes, I recommend one small deterministic step and one local verification before expanding scope."
    else:
        attuned_line = ""

    focus_key = str(focus or "").strip().lower()
    recent_note_attuned = False
    if top_signal == "recent focus notes":
        joined_notes = " ".join(recent_notes).lower()
        recent_note_attuned = any(
            token in joined_notes
            for token in ("visual", "testing", "test", "low-adventure", "safe", "calm", "roadmap")
        )
    attuned = bool(
        attuned_line
        and focus_key in {"general", "support", "next_mission", "health"}
        and (top_signal != "recent focus notes" or recent_note_attuned)
    )
    if attuned:
        persona_influence = f"attuned by {top_signal}"
    else:
        persona_influence = "no personality signal applied"

    return {
        "attuned": attuned,
        "persona_influence": _compact_excerpt(_normalize_one_line(persona_influence, ""), limit=120),
        "attuned_line": _compact_excerpt(_normalize_one_line(attuned_line, ""), limit=220),
    }


def _ensure_single_step_mission(next_mission):
    mission = _compact_excerpt(_normalize_one_line(next_mission, ""), limit=260)
    if not mission:
        return "Apply one small deterministic change in one target file, then run one local verification."
    mission_lower = mission.lower()
    if not any(token in mission_lower for token in ("verify", "verification", "test", "check")):
        mission = f"{mission} Then run one local verification."
    return _compact_excerpt(mission, limit=320)


def _stable_block_event_id(kind, timestamp, block):
    digest = hashlib.md5((block or "").encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{timestamp}:{digest}"


def _read_md_core_state():
    default_state = {
        "last_event_id": "",
        "last_report_at": "",
        "last_health": "yellow",
        "last_guidance": "",
        "last_sentiment": "",
        "last_md_brain_engine": DEFAULT_MD_BRAIN_ENGINE,
        "last_oac_handoff": "",
        "last_trigger": "",
        "conversation_window": [],
        "project_state_summary": "",
        "creator_focus_patterns": {},
        "creator_focus_summary": "",
        "project_personality_profile": {},
        "project_personality_summary": "",
        "last_persona_influence": "",
        "last_persona_attuned": False,
        "last_complexity_flag": False,
        "last_complexity_reason": "",
        "last_matched_route": "",
        "last_matched_route_note": "",
        "last_ollama_available": False,
        "repo_memory_mode": "raw",
        "repo_file_count": 0,
        "repo_max_depth": 0,
    }
    if not MD_CORE_STATE_PATH.exists():
        return default_state
    try:
        payload = json.loads(MD_CORE_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state
    if not isinstance(payload, dict):
        return default_state
    merged = dict(default_state)
    merged.update({k: payload.get(k, merged[k]) for k in merged})
    merged["conversation_window"] = _normalize_md_conversation_items(payload.get("conversation_window", []), limit=12)
    merged["project_state_summary"] = _normalize_one_line(payload.get("project_state_summary", ""), "")
    merged["creator_focus_patterns"] = payload.get("creator_focus_patterns", {}) if isinstance(payload.get("creator_focus_patterns", {}), dict) else {}
    merged["creator_focus_patterns"] = _update_creator_focus_patterns(merged["creator_focus_patterns"], [])
    merged["creator_focus_summary"] = _normalize_one_line(payload.get("creator_focus_summary", ""), "")
    if not merged["creator_focus_summary"]:
        merged["creator_focus_summary"] = _creator_focus_patterns_summary(merged["creator_focus_patterns"])
    merged["project_personality_profile"] = _normalize_project_personality_profile(payload.get("project_personality_profile", {}))
    merged["project_personality_summary"] = _normalize_one_line(payload.get("project_personality_summary", ""), "") or _project_personality_summary_line(merged["project_personality_profile"])
    merged["last_persona_influence"] = _normalize_one_line(payload.get("last_persona_influence", ""), "")
    merged["last_persona_attuned"] = bool(payload.get("last_persona_attuned", False))
    merged["last_complexity_flag"] = bool(payload.get("last_complexity_flag", False))
    merged["last_complexity_reason"] = _normalize_one_line(payload.get("last_complexity_reason", ""), "")
    merged["last_matched_route"] = _normalize_one_line(payload.get("last_matched_route", ""), "")
    merged["last_matched_route_note"] = _normalize_one_line(payload.get("last_matched_route_note", ""), "")
    merged["last_ollama_available"] = bool(payload.get("last_ollama_available", False))
    merged["repo_memory_mode"] = _normalize_one_line(payload.get("repo_memory_mode", "raw"), "raw").lower()
    merged["repo_file_count"] = int(payload.get("repo_file_count") or 0)
    merged["repo_max_depth"] = int(payload.get("repo_max_depth") or 0)
    return merged


def _write_md_core_state(state):
    payload = {
        "last_event_id": str(state.get("last_event_id", "")).strip(),
        "last_report_at": str(state.get("last_report_at", "")).strip(),
        "last_health": str(state.get("last_health", "yellow")).strip().lower(),
        "last_guidance": str(state.get("last_guidance", "")).strip(),
        "last_sentiment": str(state.get("last_sentiment", "")).strip(),
        "last_md_brain_engine": str(state.get("last_md_brain_engine", DEFAULT_MD_BRAIN_ENGINE)).strip(),
        "last_oac_handoff": str(state.get("last_oac_handoff", "")).strip(),
        "last_trigger": str(state.get("last_trigger", "")).strip(),
        "conversation_window": _normalize_md_conversation_items(state.get("conversation_window", []), limit=12),
        "project_state_summary": _normalize_one_line(state.get("project_state_summary", ""), ""),
        "creator_focus_patterns": _update_creator_focus_patterns(state.get("creator_focus_patterns", {}), []),
        "creator_focus_summary": _normalize_one_line(state.get("creator_focus_summary", ""), ""),
        "project_personality_profile": _normalize_project_personality_profile(state.get("project_personality_profile", {})),
        "project_personality_summary": _normalize_one_line(state.get("project_personality_summary", ""), ""),
        "last_persona_influence": _normalize_one_line(state.get("last_persona_influence", ""), ""),
        "last_persona_attuned": bool(state.get("last_persona_attuned", False)),
        "last_complexity_flag": bool(state.get("last_complexity_flag", False)),
        "last_complexity_reason": _normalize_one_line(state.get("last_complexity_reason", ""), ""),
        "last_matched_route": _normalize_one_line(state.get("last_matched_route", ""), ""),
        "last_matched_route_note": _normalize_one_line(state.get("last_matched_route_note", ""), ""),
        "last_ollama_available": bool(state.get("last_ollama_available", False)),
        "repo_memory_mode": _normalize_one_line(state.get("repo_memory_mode", "raw"), "raw").lower(),
        "repo_file_count": int(state.get("repo_file_count") or 0),
        "repo_max_depth": int(state.get("repo_max_depth") or 0),
    }
    MD_CORE_STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _reset_md_core_state():
    try:
        if MD_CORE_STATE_PATH.exists():
            MD_CORE_STATE_PATH.unlink()
    except OSError:
        pass


def _latest_block_by_header(header_name):
    target = str(header_name or "").strip().upper()
    if not target:
        return {}
    blocks = _split_dynamic_memory_blocks(_dynamic_memory_text())
    for header, block in reversed(blocks):
        if str(header).upper() != target:
            continue
        timestamp = _block_field_value(block, "timestamp")
        guidance = _block_field_value(block, "heart_guidance") or _block_field_value(block, "suggestion")
        complexity_raw = _block_field_value(block, "complexity_flag").strip().lower()
        attuned_raw = _block_field_value(block, "attuned_guidance").strip().lower()
        return {
            "header": header,
            "block": block,
            "timestamp": timestamp,
            "event_id": _block_field_value(block, "event_id"),
            "md_health": _block_field_value(block, "md_health").lower(),
            "guidance": guidance,
            "project_sentiment": _block_field_value(block, "project_sentiment"),
            "md_brain_engine": _block_field_value(block, "md_brain_engine"),
            "next_mission": _block_field_value(block, "next_low_adventure_mission") or _block_field_value(block, "suggested_next_mission"),
            "suggested_mission": _block_field_value(block, "suggested_mission"),
            "oac_handoff_prompt": _block_field_value(block, "oac_handoff_prompt"),
            "trigger": _block_field_value(block, "trigger"),
            "complexity_flag": complexity_raw in {"1", "true", "yes", "active"},
            "complexity_reason": _block_field_value(block, "complexity_reason"),
            "complexity_message": _block_field_value(block, "complexity_message"),
            "matched_route": _block_field_value(block, "matched_route"),
            "matched_route_note": _block_field_value(block, "matched_route_note"),
            "ollama_available": _block_field_value(block, "ollama_available").strip().lower() in {"1", "true", "yes", "available"},
            "ollama_note": _block_field_value(block, "ollama_note"),
            "ollama_preferred_model": _block_field_value(block, "ollama_preferred_model"),
            "project_personality_profile": _block_field_value(block, "project_personality_profile"),
            "persona_influence": _block_field_value(block, "persona_influence"),
            "persona_attuned": attuned_raw in {"1", "true", "yes", "active"},
        }
    return {}


def _normalize_agents_map(raw_agents):
    agents = {}
    for key, raw_meta in (raw_agents or {}).items():
        name = str(key).strip()
        if not name:
            continue
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        display = str(meta.get("display", name)).strip() or name
        description = str(meta.get("description", "")).strip()
        agents[name] = {
            "display": display,
            "description": description,
        }
    return agents


def _preferred_lead_key(agents_map, explicit=""):
    agents = _normalize_agents_map(agents_map)
    explicit_value = str(explicit or "").strip()
    if explicit_value:
        resolved = _resolve_agent_key(explicit_value, agents)
        if resolved:
            return resolved

    for preferred in PREFERRED_LEAD_KEYS:
        if preferred in agents:
            return preferred

    if agents:
        return next(iter(agents))
    return DEFAULT_LEAD_EXECUTOR


def _preferred_md_brain_key(agents_map, explicit=""):
    agents = _normalize_agents_map(agents_map)
    explicit_value = str(explicit or "").strip()
    if explicit_value:
        resolved = _resolve_agent_key(explicit_value, agents)
        if resolved:
            return resolved

    for preferred in (DEFAULT_MD_BRAIN_ENGINE, "OAC"):
        if preferred in agents:
            return preferred

    if agents:
        return next(iter(agents))
    return DEFAULT_MD_BRAIN_ENGINE


def _parse_agent_roles_text(text):
    lead_executor = ""
    md_brain_engine = ""
    agents = {}
    in_agents = False
    current_agent = ""

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("LEAD_EXECUTOR:"):
            lead_executor = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("MD_BRAIN_ENGINE:"):
            md_brain_engine = stripped.split(":", 1)[1].strip()
            continue

        if stripped == "AGENTS:":
            in_agents = True
            current_agent = ""
            continue

        if not in_agents:
            continue

        agent_match = re.match(r"^\s{2}(.+?):\s*$", line)
        if agent_match:
            current_agent = agent_match.group(1).strip()
            if current_agent and current_agent not in agents:
                agents[current_agent] = {}
            continue

        field_match = re.match(r"^\s{4}(display|description):\s*(.+)$", line)
        if field_match and current_agent:
            agents.setdefault(current_agent, {})[field_match.group(1)] = field_match.group(2).strip()

    return {
        "lead_executor": lead_executor,
        "md_brain_engine": md_brain_engine,
        "agents": _normalize_agents_map(agents),
    }


def _resolve_agent_key(agent_value, agents_map):
    value = str(agent_value or "").strip()
    if not value:
        return ""

    if value in agents_map:
        return value

    lowered = value.lower()
    for key, meta in agents_map.items():
        if key.lower() == lowered:
            return key

    for key, meta in agents_map.items():
        display = str(meta.get("display", "")).strip()
        if display and display.lower() == lowered:
            return key

    return ""


def _roles_to_description_map(agents_map):
    descriptions = {}
    for key, meta in (agents_map or {}).items():
        display = str(meta.get("display", key)).strip() or key
        descriptions[display] = str(meta.get("description", "")).strip()
    return descriptions


def _render_agent_roles_text(state):
    lead_executor = str(state.get("lead_executor", "")).strip()
    md_brain_engine = str(state.get("md_brain_engine", "")).strip()
    agents = _normalize_agents_map(state.get("agents", {}))

    if not lead_executor:
        raise ValueError("AGENT_ROLES.md requires LEAD_EXECUTOR")
    if not md_brain_engine:
        raise ValueError("AGENT_ROLES.md requires MD_BRAIN_ENGINE")
    if not agents:
        raise ValueError("AGENT_ROLES.md requires AGENTS entries")

    lines = [
        "# AGENT ROLES",
        "",
        "# Preferred CLI co-leads: OAC and GGC.",
        "# MD_BRAIN_ENGINE defaults to GGC for synthesis/supportive guidance; OAC remains execution lead.",
        "# AGa remains troubleshooter/visual auditor (manual use; not default lead).",
        f"LEAD_EXECUTOR: {lead_executor}",
        f"MD_BRAIN_ENGINE: {md_brain_engine}",
        "AGENTS:",
    ]
    for key, meta in agents.items():
        display = str(meta.get("display", key)).strip() or key
        description = str(meta.get("description", "")).strip()
        lines.extend(
            [
                f"  {key}:",
                f"    display: {display}",
                f"    description: {description}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _read_agent_roles():
    if not AGENT_ROLES_PATH.exists():
        AGENT_ROLES_PATH.parent.mkdir(parents=True, exist_ok=True)
        AGENT_ROLES_PATH.write_text(AGENT_ROLES_TEMPLATE, encoding="utf-8")

    text = AGENT_ROLES_PATH.read_text(encoding="utf-8")
    parsed = _parse_agent_roles_text(text)
    agents = _normalize_agents_map(parsed.get("agents", {}))
    lead_executor = str(parsed.get("lead_executor", "")).strip()
    md_brain_engine = str(parsed.get("md_brain_engine", "")).strip()

    if not lead_executor:
        lead_executor = _preferred_lead_key(agents)
    if not md_brain_engine:
        md_brain_engine = _preferred_md_brain_key(agents)
    if not agents:
        raise ValueError("AGENT_ROLES.md: AGENTS section is required")

    lead_key = _resolve_agent_key(lead_executor, agents)
    if not lead_key:
        lead_key = _preferred_lead_key(agents)
        lead_executor = lead_key

    md_brain_key = _resolve_agent_key(md_brain_engine, agents)
    if not md_brain_key:
        md_brain_key = _preferred_md_brain_key(agents)
        md_brain_engine = md_brain_key

    for key, meta in agents.items():
        if not str(meta.get("description", "")).strip():
            raise ValueError(f"AGENT_ROLES.md: description is required for agent '{key}'")

    return {
        "lead_executor": lead_executor,
        "lead_key": lead_key,
        "md_brain_engine": md_brain_engine,
        "md_brain_key": md_brain_key,
        "agents": agents,
        "roles": _roles_to_description_map(agents),
    }


def _write_agent_roles(state_or_lead=None):
    if isinstance(state_or_lead, dict):
        state = {
            "lead_executor": str(state_or_lead.get("lead_executor", "")).strip(),
            "md_brain_engine": str(state_or_lead.get("md_brain_engine", "")).strip(),
            "agents": _normalize_agents_map(state_or_lead.get("agents", {})),
        }
    else:
        current = _read_agent_roles()
        requested = str(state_or_lead or "").strip() or str(current.get("lead_executor", "")).strip()
        state = {
            "lead_executor": requested,
            "md_brain_engine": str(current.get("md_brain_engine", "")).strip(),
            "agents": _normalize_agents_map(current.get("agents", {})),
        }

    if not state["lead_executor"]:
        state["lead_executor"] = _preferred_lead_key(state["agents"])
    if not state["md_brain_engine"]:
        state["md_brain_engine"] = _preferred_md_brain_key(state["agents"])
    if not state["agents"]:
        raise ValueError("AGENT_ROLES.md: AGENTS section is required")

    resolved_lead = _resolve_agent_key(state["lead_executor"], state["agents"])
    if not resolved_lead:
        raise ValueError("AGENT_ROLES.md: LEAD_EXECUTOR must match an AGENTS key or display")
    resolved_md_brain = _resolve_agent_key(state["md_brain_engine"], state["agents"])
    if not resolved_md_brain:
        raise ValueError("AGENT_ROLES.md: MD_BRAIN_ENGINE must match an AGENTS key or display")

    state["lead_executor"] = state["lead_executor"].strip()
    state["md_brain_engine"] = state["md_brain_engine"].strip()

    AGENT_ROLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENT_ROLES_PATH.write_text(_render_agent_roles_text(state), encoding="utf-8")
    return state["lead_executor"]


def _normalize_lead_agent(value):
    roles_state = _read_agent_roles()
    return _resolve_agent_key(value, roles_state.get("agents", {}))


def _role_description_for(lead_executor, roles_state=None):
    state = roles_state or _read_agent_roles()
    agents = state.get("agents", {})
    resolved_key = _resolve_agent_key(lead_executor, agents)
    if not resolved_key:
        return ""
    return str(agents.get(resolved_key, {}).get("description", "")).strip()


def _destination_handoff_profile(destination: str) -> dict[str, Any]:
    name = str(destination or "").strip()
    upper = name.upper()

    profile: dict[str, Any] = {
        "template_name": "Remote Advisory Handoff",
        "expected_role": "Evidence-bound advisory memo: findings, scoped recommendations, and explicit unknowns.",
        "truth_anchor": "Use provided `G-Codex-brain/ROADMAP.md` excerpt + supplied repo evidence.",
        "preflight_step": "Do not assume local shell access. If supplied repo status evidence is missing or stale, stop and return an evidence-gap request for a local executor refresh (`git status --short --branch`).",
        "can_assume": [
            "Supplied evidence inventory: handoff mission/constraints, pasted excerpts, and explicitly provided repo-status snippets.",
            "Coordination overlay excerpts from `G-Codex-brain/`.",
        ],
        "do_not_assume": [
            "Facts not present in supplied evidence; label unknowns instead of inferring.",
            "Local filesystem write access or deterministic local test execution in this environment.",
        ],
    }

    if name in {"OAC", "GGC"}:
        profile.update(
            {
                "template_name": "Local Executor Handoff",
                "expected_role": "Direct repository execution: implement, verify, and document deterministic slices.",
                "truth_anchor": "Run `git status --short --branch` and use `G-Codex-brain/ROADMAP.md` as coordination truth anchor.",
                "preflight_step": "Run `git status --short --branch` before planning. If dirty, treat as continuation work.",
                "can_assume": [
                    "Local filesystem access in this repository.",
                    "Local shell + git availability for deterministic checks.",
                ],
                "do_not_assume": [
                    "Remote-only advisory constraints.",
                    "Unverified cloud environment parity.",
                ],
            }
        )
        return profile

    if "GITHUB" in upper or upper.startswith("GH"):
        profile.update(
            {
                "template_name": "GitHub-Connected Advisory Handoff",
                "expected_role": "Evidence-bound GitHub advisory note (link-backed findings + scoped recommendations), not local execution.",
                "truth_anchor": "Use linked GitHub refs plus `G-Codex-brain/ROADMAP.md` excerpt from the source repo.",
                "preflight_step": "Use supplied branch/status evidence from GitHub or request a local executor refresh when missing; stop if branch or PR evidence cannot be verified.",
                "can_assume": [
                    "Supplied evidence inventory: linked GitHub repo/PR/issue refs, visible diff/discussion context, and provided branch/status snapshot.",
                    "Structured mission and acceptance criteria in handoff.",
                ],
                "do_not_assume": [
                    "Unlinked or unverified repository facts; report as unknown and request evidence.",
                    "Direct local shell execution or guaranteed writable local repository access.",
                ],
            }
        )
        return profile

    if "CLOUD" in upper:
        profile.update(
            {
                "template_name": "Cloud Coding Handoff",
                "expected_role": "Bounded cloud execution report: scoped implementation notes, verification outcomes, and environment-difference notes.",
                "truth_anchor": "Use pinned branch/ref + `G-Codex-brain/ROADMAP.md` intent + required acceptance checks.",
                "preflight_step": "Confirm branch/ref and workspace state first; if branch/ref pin, scope, or acceptance checks are missing, stop and request clarification before execution.",
                "can_assume": [
                    "Supplied evidence inventory: pinned branch/ref, scoped mission, and listed acceptance checks.",
                    "Isolated cloud workspace execution capability for scoped code changes.",
                ],
                "do_not_assume": [
                    "Missing or unverified local-environment facts; call out unknowns instead of inferring parity.",
                    "Implicit access to local machine processes or unpublished state.",
                ],
            }
        )
        return profile

    return profile


def _read_notify_enabled():
    if not NOTIFY_ENABLED_FILE.exists():
        return True
    raw = NOTIFY_ENABLED_FILE.read_text(encoding="utf-8").strip().lower()
    if raw in {"0", "off", "false", "calm", "no"}:
        return False
    return True


def _write_notify_enabled(enabled):
    NOTIFY_ENABLED_FILE.write_text("1\n" if enabled else "0\n", encoding="utf-8")


NOTIFY_ENABLED = _read_notify_enabled()


def get_git_status():
    if not (ROOT / ".git").exists():
        return {"state": "NOT_INITIALIZED", "summary": "No git repository found"}
    try:
        # Porcelain status for counts
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        lines = res.stdout.strip().splitlines()
        if not lines:
            return {"state": "CLEAN", "summary": "Working tree clean", "staged": 0, "modified": 0, "untracked": 0}

        staged = 0
        unstaged = 0
        untracked = 0
        for line in lines:
            if len(line) < 3:
                continue
            x, y = line[0], line[1]
            if x == "?":
                untracked += 1
            else:
                if x != " ":
                    staged += 1
                if y != " " and y != "?":
                    unstaged += 1

        summary_parts = []
        if staged:
            summary_parts.append(f"{staged} staged")
        if unstaged:
            summary_parts.append(f"{unstaged} modified")
        if untracked:
            summary_parts.append(f"{untracked} untracked")

        summary = ", ".join(summary_parts) or "Changes detected"
        return {
            "state": "DIRTY",
            "summary": summary,
            "staged": staged,
            "modified": unstaged,
            "untracked": untracked,
        }
    except Exception as e:
        return {"state": "UNKNOWN", "summary": f"Git status error: {e}", "staged": 0, "modified": 0, "untracked": 0}


def _run_quiet_cmd(args, timeout_sec=3.0):
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
            timeout=timeout_sec,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, "", ""
    return int(proc.returncode), (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _detect_github_repo_slug():
    for remote_name in ("private", "origin"):
        code, out, _err = _run_quiet_cmd(["git", "remote", "get-url", remote_name], timeout_sec=2.0)
        if code != 0 or not out:
            continue
        match = re.search(
            r"github\.com[:/](?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$",
            out,
        )
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return ""


def _humanize_utc_iso(iso_text):
    raw = str(iso_text or "").strip()
    if not raw:
        return "unavailable"
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
    except ValueError:
        return "unavailable"
    seconds = max(0, int((datetime.now().astimezone() - parsed.astimezone()).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    return parsed.strftime("%Y-%m-%d")


def _check_sight_status():
    """Truthful Sight presence detection (Phase 22c Audit Correction)."""
    browser_detected = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        if s.connect_ex(("127.0.0.1", 9222)) == 0:
            browser_detected = True
        s.close()
    except Exception:
        pass

    mcp_detected = False
    try:
        proc = subprocess.run(["ps", "aux"], capture_output=True, text=True, check=False)
        stdout_lower = proc.stdout.lower()
        if "chrome-devtools-mcp" in stdout_lower or "devtools-mcp" in stdout_lower:
            mcp_detected = True
    except Exception:
        pass

    capability_verified = False # Reserved for future client-architecture control

    # In this phase, we do NOT attempt a one-shot capability test as the CLI is server-only.
    # Presence of both signals connectivity readiness for an MCP client, but not yet verified control.
    status = "offline"
    if capability_verified:
        status = "ready"
    elif browser_detected or mcp_detected:
        status = "partial" # browser+mcp with no verified control is still 'partial'

    return {
        "status": status,
        "browser_detected": browser_detected,
        "mcp_detected": mcp_detected,
        "capability_verified": capability_verified,
        "last_capability_check": "never",
        "last_capability_error": "One-shot CLI not supported by chrome-devtools-mcp; requires MCP client architecture.",
        "port": 9222,
    }


def _capture_screenshot_lite():
    """Captures a screenshot via direct CDP (Phase 23 Lite)."""
    # 1. Fetch targets from Chrome
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=2.0) as f:
            targets = json.loads(f.read().decode())
    except Exception as e:
        return {"ok": False, "error": f"Chrome port 9222 not responding: {e}"}

    # 2. Select target (prefer dashboard)
    target = None
    dashboard_file = "named_agent_dashboard.html"
    for t in targets:
        if t.get("type") == "page" and dashboard_file in t.get("url", ""):
            target = t
            break
    if not target:
        for t in targets:
            if t.get("type") == "page":
                target = t
                break
    if not target:
        return {"ok": False, "error": "No active page targets found in Chrome."}

    ws_url = target.get("webSocketDebuggerUrl")
    target_title = target.get("title", "Untitled")
    target_url = target.get("url", "unknown")
    if not ws_url:
        return {"ok": False, "error": "Target found but no WebSocket URL available."}

    # 3. Use helper to capture
    screenshot_dir = ROOT / ".screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    filename = f"screenshot_{int(time.time())}.png"
    filepath = screenshot_dir / filename
    
    helper_script = ROOT / "scripts" / "screenshot_helper.py"
    cmd = [sys.executable, str(helper_script), ws_url, str(filepath)]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0, check=False)
        if proc.returncode == 0 and "SUCCESS" in proc.stdout:
            detail = f"Captured '{target_title}' ({target_url})"
            _log_external_tool_injection(
                action_type="screenshot_lite",
                target="Chrome CDP",
                status="OK",
                detail=detail,
                source="Sight Protocol",
                authorized=True
            )
            return {
                "ok": True, 
                "filename": filename, 
                "path": str(filepath.relative_to(ROOT)),
                "title": target_title,
                "url": target_url
            }
        else:
            err = proc.stdout.strip() + " " + proc.stderr.strip()
            return {"ok": False, "error": f"Handshake failed: {err}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Screenshot attempt timed out (15s)."}
    except Exception as e:
        return {"ok": False, "error": f"Internal error during capture: {e}"}


def _collect_github_status_payload(force=False):
    now = time.time()
    with GITHUB_STATUS_LOCK:
        cached_at = float(GITHUB_STATUS_CACHE.get("checked_at") or 0.0)
        if not force and (now - cached_at) <= GITHUB_STATUS_TTL_SEC:
            return dict(GITHUB_STATUS_CACHE.get("payload", {}))

    default_branch = None
    commit_sha = None
    commit_message = None
    pushed_iso = ""
    ahead_behind = None
    open_issues_count = None
    repo_slug = _detect_github_repo_slug()

    code, out, _err = _run_quiet_cmd(["git", "log", "-1", "--pretty=format:%H%n%s%n%cI"], timeout_sec=2.5)
    if code == 0 and out:
        lines = out.splitlines()
        commit_sha = (lines[0].strip() if lines else "")[:7] or None
        commit_message = _compact_excerpt(lines[1].strip() if len(lines) > 1 else "", limit=120) or None
        pushed_iso = lines[2].strip() if len(lines) > 2 else ""

    code, out, _err = _run_quiet_cmd(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], timeout_sec=2.0)
    if code == 0 and out:
        branch_name = out.split("/")[-1].strip()
        default_branch = branch_name or None

    code, out, _err = _run_quiet_cmd(["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"], timeout_sec=2.0)
    if code == 0 and out:
        parts = out.split()
        if len(parts) == 2:
            try:
                ahead_behind = {"ahead": int(parts[0]), "behind": int(parts[1])}
            except ValueError:
                ahead_behind = None

    gh_available = bool(which("gh"))
    if gh_available and repo_slug:
        code, out, _err = _run_quiet_cmd(
            ["gh", "repo", "view", repo_slug, "--json", "defaultBranchRef,pushedAt"],
            timeout_sec=3.2,
        )
        if code == 0 and out:
            try:
                payload = json.loads(out)
            except json.JSONDecodeError:
                payload = {}
            default_ref = payload.get("defaultBranchRef")
            if isinstance(default_ref, dict):
                default_branch = _normalize_one_line(default_ref.get("name", ""), default_branch or "") or default_branch
            pushed_candidate = _normalize_one_line(payload.get("pushedAt", ""), "")
            if pushed_candidate:
                pushed_iso = pushed_candidate

        code, out, _err = _run_quiet_cmd(["gh", "api", f"repos/{repo_slug}", "--jq", ".open_issues_count"], timeout_sec=3.0)
        if code == 0 and out:
            try:
                open_issues_count = int(str(out).strip())
            except ValueError:
                open_issues_count = None

    docker_available = bool(which("docker"))
    if docker_available and bool(os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()):
        active_path = "docker_mcp"
    elif gh_available:
        active_path = "gh_cli_fallback"
    else:
        active_path = "unavailable"

    open_prs = None
    if active_path != "unavailable":
        with MCP_AUTH_LOCK:
            mcp_status_state = MCP_AUTH_STATE.get("status")
        
        mcp_script = ROOT / "scripts" / "mcp_server.py"
        cmd = [sys.executable, str(mcp_script), "--list-prs"]
        if mcp_status_state == "AUTHORIZED":
            cmd.append("--bootstrap-authorized")
        code, out, _err = _run_quiet_cmd(cmd, timeout_sec=4.0)
        if code == 0 and out:
            try:
                result = json.loads(out)
                if result.get("status") == "OK" and isinstance(result.get("prs"), list):
                    open_prs = result["prs"]
            except json.JSONDecodeError:
                pass

        # Periodic Meta-Scan discovery
        meta_now = time.time()
        with GITHUB_STATUS_LOCK:
            meta_cached_at = float(GITHUB_META_SCAN_CACHE.get("checked_at") or 0.0)
            if force or (meta_now - meta_cached_at) >= GITHUB_META_SCAN_TTL_SEC:
                do_meta = True
            else:
                do_meta = False

        if do_meta:
            cmd_meta = [sys.executable, str(mcp_script), "--meta-scan"]
            if mcp_status_state == "AUTHORIZED":
                cmd_meta.append("--bootstrap-authorized")
            m_code, m_out, _m_err = _run_quiet_cmd(cmd_meta, timeout_sec=6.0)
            if m_code == 0 and m_out:
                try:
                    m_result = json.loads(m_out)
                    if m_result.get("status") == "OK":
                        with GITHUB_STATUS_LOCK:
                            GITHUB_META_SCAN_CACHE["checked_at"] = meta_now
                            GITHUB_META_SCAN_CACHE["payload"] = m_result.get("meta_scan")
                except json.JSONDecodeError:
                    pass

    with GITHUB_STATUS_LOCK:
        meta_scan_payload = GITHUB_META_SCAN_CACHE.get("payload")

    sight_status = _check_sight_status()
    git_status = get_git_status()

    payload = {
        "default_branch": default_branch,
        "last_commit_sha": commit_sha,
        "last_commit_message": commit_message,
        "last_pushed_at": _humanize_utc_iso(pushed_iso),
        "ahead_behind": ahead_behind,
        "open_issues_count": open_issues_count,
        "open_prs": open_prs,
        "meta_scan": meta_scan_payload,
        "sight_status": sight_status,
        "git_status": git_status,
        "active_path": active_path,
        "repo": repo_slug or None,
    }
    with GITHUB_STATUS_LOCK:
        GITHUB_STATUS_CACHE["checked_at"] = now
        GITHUB_STATUS_CACHE["payload"] = payload
    return dict(payload)


def _repo_posture_payload():
    payload = {
        "posture_mode": "UNKNOWN",
        "role": "unknown",
        "source_ref": "",
        "project_id": ROOT.name,
        "purity_status": "unknown",
        "valid": False,
    }
    if not REPO_POSTURE_PATH.exists():
        payload["note"] = "REPO_POSTURE.json not found"
        return payload
    try:
        parsed = json.loads(REPO_POSTURE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        payload["note"] = f"invalid JSON: {exc.msg}"
        return payload
    except OSError as exc:
        payload["note"] = f"read error: {exc}"
        return payload

    if not isinstance(parsed, dict):
        payload["note"] = "invalid posture shape: expected object"
        return payload

    posture_mode = str(parsed.get("posture_mode", "")).strip()
    role = str(parsed.get("role", "")).strip()
    source_ref = str(parsed.get("source_ref", "")).strip()
    project_id = str(parsed.get("project_id", "")).strip()
    purity_status = str(parsed.get("purity_status", "")).strip()

    payload.update(
        {
            "posture_mode": posture_mode or payload["posture_mode"],
            "role": role or payload["role"],
            "source_ref": source_ref,
            "project_id": project_id or payload["project_id"],
            "purity_status": purity_status or payload["purity_status"],
            "valid": bool(posture_mode and role and purity_status),
        }
    )
    return payload


def _now_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _to_epoch(ts):
    try:
        normalized = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return 0.0


def _compact_excerpt(text, limit=220):
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _extract_active_now_excerpt():
    active_now = BRAIN / "03_ACTIVE_NOW.md"
    if not active_now.exists():
        return "03_ACTIVE_NOW.md not found."
    text = active_now.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    body_lines = [line for line in lines if line and not line.startswith("#")]
    if body_lines:
        return _compact_excerpt(" ".join(body_lines[:4]))
    return _compact_excerpt(text)


def _truth_anchor_status():
    roadmap_path = BRAIN / "ROADMAP.md"
    if roadmap_path.exists():
        return {
            "exists": True,
            "path": str(roadmap_path.relative_to(ROOT)),
            "warning": "",
            "note": "Truth Anchor: `G-Codex-brain/ROADMAP.md` is present and canonical.",
        }
    warning = "Missing Truth Anchor: G-Codex-brain/ROADMAP.md was not found."
    return {
        "exists": False,
        "path": str(roadmap_path.relative_to(ROOT)),
        "warning": warning,
        "note": f"{warning} Regenerate ingress/roadmap before relying on generated summaries.",
    }


def _extract_roadmap_highlights():
    anchor = _truth_anchor_status()
    roadmap_path = BRAIN / "ROADMAP.md"
    if not roadmap_path.exists():
        return [anchor["note"]]

    text = roadmap_path.read_text(encoding="utf-8")
    without_mermaid = re.sub(r"```mermaid[\s\S]*?```", "", text, flags=re.IGNORECASE)
    without_mermaid = re.sub(
        r"##\s+Roadmap Node Actions[\s\S]*?(?=\n##\s+|\Z)",
        "",
        without_mermaid,
        flags=re.IGNORECASE,
    )
    highlights = []
    for raw in without_mermaid.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            highlights.append(line[2:].strip())
        elif re.match(r"^\d+\.\s+", line):
            highlights.append(re.sub(r"^\d+\.\s+", "", line))
        if len(highlights) >= 5:
            break
    return highlights or ["Roadmap exists but no highlights were extracted yet."]


def _extract_roadmap_next_milestone():
    roadmap_path = BRAIN / "ROADMAP.md"
    if not roadmap_path.exists():
        return ""

    text = roadmap_path.read_text(encoding="utf-8")
    without_mermaid = re.sub(r"```mermaid[\s\S]*?```", "", text, flags=re.IGNORECASE)
    without_mermaid = re.sub(
        r"##\s+Roadmap Node Actions[\s\S]*?(?=\n##\s+|\Z)",
        "",
        without_mermaid,
        flags=re.IGNORECASE,
    )

    def clean_candidate(raw_line):
        line = str(raw_line or "").strip()
        if not line:
            return ""
        line = re.sub(r"^\s*[-*]\s*\[[ xX]\]\s*", "", line)
        line = re.sub(r"^\s*[-*]\s*", "", line)
        line = re.sub(r"^\s*\d+\.\s*", "", line)
        line = re.sub(r"^\s*next\s*:\s*", "", line, flags=re.IGNORECASE)
        line = line.strip(" -")
        return _compact_excerpt(line, limit=150)

    milestone_section = re.search(
        r"##\s+Suggested Milestones\s*([\s\S]*?)(?=\n##\s+|\Z)",
        without_mermaid,
        flags=re.IGNORECASE,
    )
    if milestone_section:
        for raw in milestone_section.group(1).splitlines():
            line = raw.strip()
            if not line:
                continue
            if re.match(r"^\d+\.\s+", line) or re.match(r"^[-*]\s+", line):
                candidate = clean_candidate(line)
                if candidate:
                    return candidate

    fallback_candidates = []
    for raw in without_mermaid.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("#"):
            continue
        if "roadmap summary" in lowered:
            continue
        if line.startswith("- [ ]"):
            candidate = clean_candidate(line)
            if candidate:
                return candidate
            continue
        if re.match(r"^[-*]\s+", line) or re.match(r"^\d+\.\s+", line):
            candidate = clean_candidate(line)
            if not candidate:
                continue
            if "next:" in lowered:
                return candidate
            if "✓" in candidate or "[x]" in lowered:
                continue
            fallback_candidates.append(candidate)

    return fallback_candidates[0] if fallback_candidates else ""


def _build_roadmap_suggested_mission(milestone_text):
    milestone = _normalize_one_line(milestone_text, "")
    if not milestone:
        return ""
    return (
        f"Advance roadmap milestone: {milestone}. "
        "Take one low-adventure implementation step, verify locally, and log the outcome."
    )


def _extract_current_mission():
    for path in sorted(_iter_swarm_packet_paths(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^Slice:\s*(.+)$", text, flags=re.MULTILINE)
        if match:
            return match.group(1).strip()
    return "Dispatch the next smallest high-confidence slice from Control Room."


def _regenerate_first_handoff(lead_executor=None):
    role_state = _read_agent_roles()
    agents = role_state.get("agents", {})
    explicit_lead = str(lead_executor or "").strip()
    explicit_key = _resolve_agent_key(explicit_lead, agents) if explicit_lead else ""
    current_lead = _resolve_agent_key(str(role_state.get("lead_executor", "")).strip(), agents)

    if explicit_key:
        lead = explicit_key
    elif current_lead in PREFERRED_LEAD_KEYS:
        lead = current_lead
    else:
        lead = _preferred_lead_key(agents)

    if not lead:
        raise ValueError("AGENT_ROLES.md: LEAD_EXECUTOR is required before generating first handoff")

    role_desc = _role_description_for(lead, role_state)
    if not role_desc:
        raise ValueError("AGENT_ROLES.md: lead executor description is required before generating first handoff")
    active_summary = _extract_active_now_excerpt().lstrip("- ").strip()
    roadmap_highlights = _extract_roadmap_highlights()
    truth_anchor = _truth_anchor_status()
    mission = _extract_current_mission()
    destination_profile = _destination_handoff_profile(lead)
    timestamp = _now_iso()
    roadmap_block = "\n".join(f"- {item}" for item in roadmap_highlights[:4])

    if not truth_anchor["exists"]:
        _append_dynamic_memory_entry(
            "\n".join(
                [
                    "## SESSION_LOG_ENTRY",
                    f"- timestamp: {timestamp}",
                    "- agent: scripts/brain_server.py",
                    f"- repo: {ROOT.name}",
                    "- objective: Preserve generator coherence and avoid stale defaults.",
                    "- actions:",
                    f"  - {truth_anchor['warning']}",
                    "- verification:",
                    "  - Generated handoff includes explicit missing truth anchor warning.",
                    "- status: WARNING",
                    "- blockers: ROADMAP truth anchor missing.",
                    "- next_step: Regenerate roadmap with ingress and retry handoff generation.",
                    "",
                ]
            )
        )

    FIRST_HANDOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIRST_HANDOFF_PATH.write_text(
        "\n".join(
            [
                "# G-Codex First Handoff",
                "",
                f"Generated: {timestamp}",
                "",
                "## Repository Snapshot",
                f"- Repository Name: {ROOT.name}",
                f"- Repository Path: {ROOT}",
                "",
                "## Lead Executor",
                f"- Agent: {lead}",
                f"- Strength: {role_desc}",
                "- Preferred CLI co-leads: OAC and GGC.",
                "- AGa remains visual troubleshooter/auditor unless explicitly chosen by human.",
                "",
                "## Current Brain Context Summary",
                f"- {active_summary}",
                "",
                "## Dynamic Roadmap Snapshot",
                roadmap_block,
                "",
                "## Destination Capability Template",
                f"- Template: {destination_profile['template_name']}",
                f"- Expected Role: {destination_profile['expected_role']}",
                f"- Truth Anchor: {destination_profile['truth_anchor']}",
                "",
                "### Can Assume Access",
                *[f"- {item}" for item in destination_profile["can_assume"]],
                "",
                "### Do Not Assume",
                *[f"- {item}" for item in destination_profile["do_not_assume"]],
                "",
                "## System Truth Anchor",
                f"- {truth_anchor['note']}",
                "",
                "## Continue From Here",
                f"Please continue as **{lead}**.",
                f"Current mission: **{mission}**",
                destination_profile["preflight_step"],
                "If the reported working tree is not clean, treat this session as continuation work and override inherited clean-slate/bootstrap assumptions when repo reality disagrees.",
                "Treat the repository as primary; use `G-Codex-brain/` as a coordination overlay that reflects and serves repo reality.",
                "Use proposal lifecycle states exactly: HARMONIZATION_PENDING -> ASSESSED/READY_FOR_OAC/REJECTED -> explicit harmonized execution.",
                "Keep persona alignment user-agnostic from `G-Codex-brain/user_domain_nodes.json`.",
                "Prefer durable repo improvements over behavior unnecessarily coupled to continued overlay presence.",
                "Keep execution local-first, deterministic, and document coordination updates in brain files.",
                "",
                "## Ready-To-Paste Prompt",
                f"You are {lead} continuing in `{ROOT.name}`.",
                f"Lead with: {role_desc}.",
                f"Mission focus: {mission}",
                f"Destination template: {destination_profile['template_name']}.",
                destination_profile["preflight_step"],
                "If the reported tree is not clean, treat this as continuation work and override inherited clean-slate/bootstrap assumptions.",
                "Treat the repository as primary and `G-Codex-brain/` as a coordination overlay.",
                "Use `G-Codex-brain/ROADMAP.md` as the canonical coordination source-of-truth before making changes.",
                "Use local-first deterministic flow, verify behavior, and keep docs aligned.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"lead_executor": lead, "handoff_path": str(FIRST_HANDOFF_PATH.relative_to(ROOT))}


def _detect_source(text, fallback="Human"):
    upper = text.upper()
    if "AGA" in upper:
        return "AGa"
    if "GEMINI 3" in upper or "GEMINI3" in upper:
        return "GEMINI 3"
    if "GROK" in upper:
        return "GROK"
    if "CHATGPT" in upper:
        return "CHATGPT"
    if "OAC" in upper:
        return "OAC"
    if "HUMAN" in upper:
        return "Human"
    return fallback


def _extract_bridge_entry(block):
    source = ""
    source_match = re.search(
        r"(?im)^(?:[-*•]\s*)?(?:\*\*)?(?:source|from|model)(?:\*\*)?\s*:\s*(.+)$",
        block,
    )
    if source_match:
        source = source_match.group(1).strip()

    content_match = re.search(
        r"(?im)^(?:[-*•]\s*)?(?:\*\*)?content(?:\*\*)?\s*:\s*\n```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)\n```",
        block,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    if content_match:
        summary = content_match.group(1).strip()
    else:
        inline_match = re.search(
            r"(?im)^(?:[-*•]\s*)?(?:\*\*)?content(?:\*\*)?\s*:\s*(.+)$",
            block,
        )
        summary = inline_match.group(1).strip() if inline_match else ""

    if not summary:
        header_match = BRIDGE_HEADER_ANY_RE.search(block)
        if header_match:
            summary = header_match.group(1).strip()

    model_or_source = re.search(r"(?im)^(?:[-*•]\s*)?(?:\*\*)?(?:source|from|model)(?:\*\*)?\s*:\s*(.+)$", summary)
    if not source and model_or_source:
        source = model_or_source.group(1).strip()

    summary = BRIDGE_HEADER_ANY_RE.sub("", summary).strip()
    summary = BRIDGE_META_LINE_RE.sub("", summary).strip()
    return {
        "source": source,
        "summary": summary,
    }


def _parse_dynamic_memory_entries():
    path = BRAIN / "DYNAMIC_MEMORY.md"
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    split_blocks = _split_dynamic_memory_blocks(text)

    parsed = []
    fallback_ts = datetime.fromtimestamp(path.stat().st_mtime).astimezone().replace(microsecond=0).isoformat()
    for header, block in split_blocks:
        normalized_header = str(header).upper()
        if normalized_header not in ACTIVITY_HEADERS:
            continue
        ts_match = re.search(r"(?im)^(?:[-*•]\s*)?(?:\*\*)?timestamp(?:\*\*)?\s*:\s*(.+)$", block)
        source_match = re.search(r"(?im)^(?:[-*•]\s*)?(?:\*\*)?(?:source|from|model)(?:\*\*)?\s*:\s*(.+)$", block)
        timestamp = ts_match.group(1).strip() if ts_match else fallback_ts
        bridge_entry = normalized_header == "GCODEX_BRIDGE_INJECTION" or bool(BRIDGE_HEADER_ANY_RE.search(block))
        if bridge_entry:
            parsed_bridge = _extract_bridge_entry(block)
            summary = _compact_excerpt(parsed_bridge.get("summary", "").strip() or "Bridge injection recorded.", limit=180)
            source = (
                parsed_bridge.get("source", "").strip()
                or (source_match.group(1).strip() if source_match else "")
                or _detect_source(block, fallback="Human")
            )
            kind = "bridge"
        elif normalized_header == "CLI_OUTPUT":
            cli_event = _parse_cli_output_block(block)
            summary = _compact_excerpt(cli_event.get("summary_line") or "CLI output captured.", limit=180)
            source = _normalize_one_line(cli_event.get("source"), "OAC")
            kind = "cli"
        elif normalized_header == "HUMAN_INJECTION":
            body = _extract_content_body(block) or block
            summary = _compact_excerpt(body.strip() or "Human injection recorded.", limit=180)
            source = source_match.group(1).strip() if source_match else "Human"
            kind = "human"
        elif normalized_header == "MD_REPORT":
            what_happened = _block_field_value(block, "what_happened")
            guidance = _block_field_value(block, "heart_guidance")
            summary_seed = what_happened or guidance or _extract_content_body(block) or "Managing Director report generated."
            summary = _compact_excerpt(summary_seed, limit=180)
            source = "Managing Director"
            kind = "md_report"
        elif normalized_header == "MD_GUIDANCE":
            guidance = _block_field_value(block, "suggestion") or _extract_content_body(block)
            summary = _compact_excerpt(guidance or "Managing Director guidance posted.", limit=180)
            source = "Managing Director"
            kind = "md_guidance"
        elif normalized_header == "MD_HARMONIZED_ENTRY":
            harmonized_summary = _normalize_one_line(_block_field_value(block, "harmonized_summary"), "")
            feature_slice = _normalize_one_line(_block_field_value(block, "feature_slice"), "")
            integration_summary = _normalize_one_line(_block_field_value(block, "integration_summary"), "")
            summary_seed = (
                harmonized_summary
                or (f"Harmonized proposal: {feature_slice}" if feature_slice else "")
                or integration_summary
                or "Harmonized proposal entry recorded."
            )
            summary = _compact_excerpt(summary_seed, limit=180)
            source = "Managing Director"
            kind = "md_harmonized"
        else:
            summary_text = re.sub(
                r"\s+",
                " ",
                block.replace("## SESSION_LOG_ENTRY", "").replace("## GCODEX_BRIDGE_INJECTION", "").strip(),
            )
            summary = _compact_excerpt(summary_text, limit=180)
            source = source_match.group(1).strip() if source_match else _detect_source(block, fallback="Human")
            kind = "memory"
        parsed.append({
            "timestamp": timestamp,
            "sort_epoch": _to_epoch(timestamp),
            "source": source,
            "summary": summary,
            "kind": kind,
            "source_file": "G-Codex-brain/DYNAMIC_MEMORY.md",
        })
    return parsed


def _iter_swarm_packet_paths():
    found = []
    seen = set()
    for pattern in SWARM_PACKET_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                found.append(path)
    return found


def _parse_swarm_packet_entries():
    entries = []
    for path in _iter_swarm_packet_paths():
        text = path.read_text(encoding="utf-8")
        ts_match = re.search(r"^Timestamp:\s*(.+)$", text, flags=re.MULTILINE)
        slice_match = re.search(r"^Slice:\s*(.+)$", text, flags=re.MULTILINE)
        timestamp = (
            ts_match.group(1).strip()
            if ts_match
            else datetime.fromtimestamp(path.stat().st_mtime).astimezone().replace(microsecond=0).isoformat()
        )
        slice_line = slice_match.group(1).strip() if slice_match else "Swarm packet updated."
        entries.append({
            "timestamp": timestamp,
            "sort_epoch": _to_epoch(timestamp),
            "source": _detect_source(text, fallback="Human"),
            "summary": _compact_excerpt(slice_line, limit=180),
            "kind": "packet",
            "source_file": path.name,
        })
    return entries


def _build_activity_feed(limit=5):
    entries = _parse_dynamic_memory_entries() + _parse_swarm_packet_entries()
    entries.sort(key=lambda item: item["sort_epoch"], reverse=True)
    trimmed = entries[:limit]
    for item in trimmed:
        item.pop("sort_epoch", None)
    return trimmed


def _latest_bridge_injection_timestamp():
    latest_ts = ""
    latest_epoch = 0.0
    for item in _parse_dynamic_memory_entries():
        if item.get("kind") != "bridge":
            continue
        epoch = float(item.get("sort_epoch") or 0.0)
        if epoch > latest_epoch:
            latest_epoch = epoch
            latest_ts = str(item.get("timestamp", "")).strip()
    return latest_ts


def _collect_md_core_trigger_events():
    events = []
    for idx, (header, block) in enumerate(_split_dynamic_memory_blocks(_dynamic_memory_text())):
        normalized = str(header).upper()
        if normalized not in {"CLI_OUTPUT", "HUMAN_INJECTION", "MD_PROPOSAL", "MD_HARMONIZED_ENTRY"}:
            continue
        timestamp = _block_field_value(block, "timestamp") or _now_iso()
        if normalized == "MD_PROPOSAL":
            status = _block_field_value(block, "status").upper()
            if status != "ACCEPTED":
                continue
            proposal_id = _block_field_value(block, "proposal_id") or "proposal"
            trigger = "PROPOSAL_ACCEPTED"
            summary = _block_field_value(block, "feature_slice") or "Accepted proposal"
            event_id = f"proposal:{proposal_id}:{timestamp}"
        elif normalized == "MD_HARMONIZED_ENTRY":
            proposal_id = _block_field_value(block, "proposal_id") or "proposal"
            trigger = "PROPOSAL_ACCEPTED"
            summary = _block_field_value(block, "feature_slice") or "Harmonized proposal"
            event_id = f"harmonized:{proposal_id}:{timestamp}"
        elif normalized == "HUMAN_INJECTION":
            trigger = "HUMAN_INJECTION"
            summary = _extract_content_body(block) or "Human input posted."
            event_id = _stable_block_event_id("human", timestamp, block)
        else:
            trigger = "CLI_OUTPUT"
            cli_event = _parse_cli_output_block(block)
            summary = cli_event.get("summary_line") or cli_event.get("excerpt") or "CLI output captured."
            event_id = _stable_block_event_id("cli", timestamp, block)
        events.append(
            {
                "trigger": trigger,
                "timestamp": timestamp,
                "sort_epoch": _to_epoch(timestamp),
                "sort_order": idx,
                "event_id": event_id,
                "summary": _compact_excerpt(summary, limit=160),
            }
        )
    events.sort(key=lambda item: (item["sort_epoch"], item["sort_order"]), reverse=True)
    return events


def _recent_cli_output_blocks(limit=6):
    found = []
    for header, block in reversed(_split_dynamic_memory_blocks(_dynamic_memory_text())):
        if str(header).upper() != "CLI_OUTPUT":
            continue
        parsed = _parse_cli_output_block(block)
        content = " ".join(
            [
                _normalize_one_line(parsed.get("command", ""), ""),
                _normalize_one_line(parsed.get("stdout_summary", ""), ""),
                _normalize_one_line(parsed.get("stderr_summary", ""), ""),
                _normalize_one_line(parsed.get("excerpt", ""), ""),
            ]
        ).strip()
        if content:
            found.append(content)
        if len(found) >= limit:
            break
    return found


def _compute_feed_quiet_seconds():
    newest_epoch = 0.0
    for item in _parse_dynamic_memory_entries():
        epoch = float(item.get("sort_epoch") or 0.0)
        if epoch > newest_epoch:
            newest_epoch = epoch
    if newest_epoch <= 0:
        return None
    delta = int(time.time() - newest_epoch)
    return delta if delta >= 0 else 0


def _mission_looks_code_related(text):
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    keywords = (
        "fix",
        "implement",
        "update",
        "regression",
        "verify",
        "test",
        "patch",
        "refactor",
        "dispatch",
        "code",
    )
    return any(token in lowered for token in keywords)


def _is_truthy(value):
    raw = str(value or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled", "y"}


def _safe_utc_iso(epoch=None):
    ts = float(epoch) if epoch is not None else time.time()
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deep_sea_requested():
    mode_raw = _normalize_one_line(os.getenv("GCODEX_OLLAMA_DEEP_SEA_MODE", "auto"), "auto").lower()
    if mode_raw in {"0", "off", "false", "disabled"}:
        return False
    priority_raw = _normalize_one_line(
        os.getenv("GCODEX_REASONING_PRIORITY", os.getenv("GCODEX_MD_PRIORITY", "")),
        "",
    ).lower()
    if priority_raw in {"cloud", "remote", "api", "ggc"}:
        return False
    return True


def _preferred_ollama_model():
    return _normalize_one_line(os.getenv("GCODEX_OLLAMA_MODEL", "llama3.2:3b"), "llama3.2:3b")


def _candidate_ollama_models():
    candidates = []
    seen = set()
    for name in (_preferred_ollama_model(), *OLLAMA_COMMON_MODELS):
        item = _normalize_one_line(name, "")
        lowered = item.lower()
        if not item or lowered in seen:
            continue
        seen.add(lowered)
        candidates.append(item)
    return candidates


def _parse_ollama_models(list_stdout):
    found = []
    seen = set()
    for raw_line in (list_stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        first = line.split()[0].strip()
        lowered = first.lower()
        if lowered in {"name", "model"}:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        found.append(first)
    return found


def _choose_ollama_model(available_models, candidates):
    if not available_models:
        return ""
    lookup = {model.lower(): model for model in available_models}
    for candidate in candidates:
        chosen = lookup.get(candidate.lower())
        if chosen:
            return chosen
    return available_models[0]


def _base_local_reasoning_status():
    return {
        "deep_sea_requested": bool(_deep_sea_requested()),
        "ollama_available": False,
        "warmup_state": "Idle",
        "last_warmup_timestamp": "",
        "last_failure_reason": "",
        "active_model": None,
    }


def _update_local_reasoning_snapshot(updates):
    with OLLAMA_STATUS_LOCK:
        status = dict(OLLAMA_STATUS_CACHE.get("status", {}))
        status.update(updates)
        OLLAMA_STATUS_CACHE["status"] = status
        OLLAMA_STATUS_CACHE["checked_at"] = time.time()


def _run_ollama_warmup(binary, candidate_models):
    started_at = time.time()
    selected_model = ""
    failure_reason = ""
    warmup_ok = False
    try:
        deadline = started_at + OLLAMA_WARMUP_TIMEOUT_SEC
        for model_name in candidate_models:
            remaining = deadline - time.time()
            if remaining <= 0:
                failure_reason = "Warmup timed out."
                break
            try:
                warm = subprocess.run(
                    [binary, "show", model_name],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=max(1.0, min(4.0, remaining)),
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                failure_reason = f"Warmup timed out for `{model_name}`."
                continue

            if warm.returncode == 0:
                selected_model = model_name
                warmup_ok = True
                break
            stderr_line = _normalize_one_line((warm.stderr or "").strip(), "")
            failure_reason = stderr_line or f"Warmup failed for `{model_name}`."

        finished_at = time.time()
        with OLLAMA_STATUS_LOCK:
            status = dict(OLLAMA_STATUS_CACHE.get("status", {}))
            status["last_warmup_timestamp"] = _safe_utc_iso(finished_at)
            if warmup_ok:
                status["warmup_state"] = "Ready"
                status["active_model"] = selected_model
                status["last_failure_reason"] = ""
                OLLAMA_STATUS_CACHE["last_success_epoch"] = finished_at
            else:
                status["warmup_state"] = "Failed"
                if not status.get("active_model"):
                    status["active_model"] = selected_model or None
                status["last_failure_reason"] = _normalize_one_line(
                    failure_reason,
                    "Warmup failed quietly; fallback remains safe.",
                )
            OLLAMA_STATUS_CACHE["status"] = status
            OLLAMA_STATUS_CACHE["warmup_in_progress"] = False
            OLLAMA_STATUS_CACHE["warmup_cooldown_until"] = finished_at + OLLAMA_WARMUP_COOLDOWN_SEC
            OLLAMA_STATUS_CACHE["checked_at"] = finished_at
    except Exception:
        finished_at = time.time()
        with OLLAMA_STATUS_LOCK:
            status = dict(OLLAMA_STATUS_CACHE.get("status", {}))
            status["warmup_state"] = "Failed"
            status["last_warmup_timestamp"] = _safe_utc_iso(finished_at)
            status["last_failure_reason"] = "Warmup failed unexpectedly; fallback remains safe."
            OLLAMA_STATUS_CACHE["status"] = status
            OLLAMA_STATUS_CACHE["warmup_in_progress"] = False
            OLLAMA_STATUS_CACHE["warmup_cooldown_until"] = finished_at + OLLAMA_WARMUP_COOLDOWN_SEC
            OLLAMA_STATUS_CACHE["checked_at"] = finished_at


def _maybe_start_ollama_warmup(binary, available_models):
    if not _is_truthy(os.getenv("GCODEX_OLLAMA_WARMUP", "1")):
        return False
    now = time.time()
    with OLLAMA_STATUS_LOCK:
        if OLLAMA_STATUS_CACHE.get("warmup_in_progress"):
            return False
        cooldown_until = float(OLLAMA_STATUS_CACHE.get("warmup_cooldown_until") or 0.0)
        if now < cooldown_until:
            return False
        status = dict(OLLAMA_STATUS_CACHE.get("status", {}))
        if str(status.get("warmup_state", "Idle")) == "Ready":
            return False
        candidates = _candidate_ollama_models()
        candidate_models = []
        available_lookup = {model.lower(): model for model in available_models}
        for candidate in candidates:
            resolved = available_lookup.get(candidate.lower())
            if resolved:
                candidate_models.append(resolved)
        if not candidate_models:
            status["warmup_state"] = "Failed"
            status["last_failure_reason"] = "No common local models found (mistral/llama3)."
            OLLAMA_STATUS_CACHE["status"] = status
            OLLAMA_STATUS_CACHE["warmup_cooldown_until"] = now + OLLAMA_WARMUP_COOLDOWN_SEC
            OLLAMA_STATUS_CACHE["checked_at"] = now
            return False
        status["warmup_state"] = "Warming"
        status["last_failure_reason"] = ""
        status["active_model"] = candidate_models[0]
        OLLAMA_STATUS_CACHE["status"] = status
        OLLAMA_STATUS_CACHE["warmup_in_progress"] = True
        OLLAMA_STATUS_CACHE["warmup_cooldown_until"] = now + OLLAMA_WARMUP_COOLDOWN_SEC
        OLLAMA_STATUS_CACHE["checked_at"] = now
    thread = threading.Thread(
        target=_run_ollama_warmup,
        args=(binary, candidate_models),
        daemon=True,
    )
    thread.start()
    return True


def _ollama_probe_worker(trigger_warmup=True):
    now = time.time()
    deep_requested = _deep_sea_requested()
    status = _base_local_reasoning_status()
    status["deep_sea_requested"] = bool(deep_requested)
    binary = which("ollama")
    available_models = []
    failure_reason = ""
    try:
        if binary:
            probe = subprocess.run(
                [binary, "list"],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=OLLAMA_PROBE_TIMEOUT_SEC,
                check=False,
            )
            if probe.returncode == 0:
                available_models = _parse_ollama_models(probe.stdout or "")
                status["ollama_available"] = True
                chosen = _choose_ollama_model(available_models, _candidate_ollama_models())
                status["active_model"] = chosen or None
            else:
                failure_reason = _normalize_one_line(
                    probe.stderr or "",
                    "Ollama runtime returned an error.",
                )
        else:
            failure_reason = "Ollama binary not found."
    except (OSError, subprocess.TimeoutExpired):
        failure_reason = "Ollama runtime probe timed out."
    finally:
        with OLLAMA_STATUS_LOCK:
            current = dict(OLLAMA_STATUS_CACHE.get("status", {}))
            if status.get("warmup_state") == "Idle":
                status["warmup_state"] = str(current.get("warmup_state", "Idle"))
            status["last_warmup_timestamp"] = _normalize_one_line(
                current.get("last_warmup_timestamp", ""),
                "",
            )
            if not status.get("active_model"):
                status["active_model"] = current.get("active_model")
            if failure_reason:
                status["last_failure_reason"] = _normalize_one_line(failure_reason, "")
                if deep_requested and not status["ollama_available"]:
                    status["warmup_state"] = "Failed"
            else:
                if not current.get("last_failure_reason"):
                    status["last_failure_reason"] = ""
                else:
                    status["last_failure_reason"] = _normalize_one_line(current.get("last_failure_reason", ""), "")
            if OLLAMA_STATUS_CACHE.get("warmup_in_progress"):
                status["warmup_state"] = "Warming"

            ready_age = now - float(OLLAMA_STATUS_CACHE.get("last_success_epoch") or 0.0)
            if status.get("warmup_state") == "Ready" and (ready_age <= 0 or ready_age > LOCAL_REASONING_ACTIVE_TTL_SEC):
                status["warmup_state"] = "Idle"

            if not deep_requested and status.get("warmup_state") == "Failed":
                status["warmup_state"] = "Idle"
                status["last_failure_reason"] = ""

            OLLAMA_STATUS_CACHE["status"] = status
            OLLAMA_STATUS_CACHE["checked_at"] = now
            OLLAMA_STATUS_CACHE["probe_in_progress"] = False

        if deep_requested and status.get("ollama_available") and trigger_warmup:
            _maybe_start_ollama_warmup(binary, available_models)


def _run_ollama_probe(force=False, trigger_warmup=True):
    now = time.time()
    with OLLAMA_STATUS_LOCK:
        if OLLAMA_STATUS_CACHE.get("probe_in_progress"):
            return
        cached_at = float(OLLAMA_STATUS_CACHE.get("checked_at") or 0.0)
        stale = (now - cached_at) > OLLAMA_STATUS_TTL_SEC
        if not force and not stale:
            return
        OLLAMA_STATUS_CACHE["probe_in_progress"] = True

    thread = threading.Thread(
        target=_ollama_probe_worker,
        args=(trigger_warmup,),
        daemon=True,
    )
    thread.start()


def _mark_local_reasoning_used(active_model=""):
    now = time.time()
    with OLLAMA_STATUS_LOCK:
        status = dict(OLLAMA_STATUS_CACHE.get("status", {}))
        OLLAMA_STATUS_CACHE["last_success_epoch"] = now
        status["warmup_state"] = "Ready"
        if active_model:
            status["active_model"] = _normalize_one_line(active_model, active_model)
        elif not status.get("active_model"):
            status["active_model"] = _preferred_ollama_model()
        status["last_failure_reason"] = ""
        if not status.get("last_warmup_timestamp"):
            status["last_warmup_timestamp"] = _safe_utc_iso(now)
        OLLAMA_STATUS_CACHE["status"] = status
        OLLAMA_STATUS_CACHE["checked_at"] = now


def _local_reasoning_status_payload(force=False, trigger_warmup=True):
    _run_ollama_probe(force=force, trigger_warmup=trigger_warmup)
    now = time.time()
    with OLLAMA_STATUS_LOCK:
        status = dict(OLLAMA_STATUS_CACHE.get("status", {}))
        last_success_epoch = float(OLLAMA_STATUS_CACHE.get("last_success_epoch") or 0.0)
        warmup_in_progress = bool(OLLAMA_STATUS_CACHE.get("warmup_in_progress"))
        probe_in_progress = bool(OLLAMA_STATUS_CACHE.get("probe_in_progress"))

    warmup_state = str(status.get("warmup_state", "Idle")).strip().title()
    if warmup_state not in {"Idle", "Warming", "Ready", "Failed"}:
        warmup_state = "Idle"
    if warmup_in_progress:
        warmup_state = "Warming"
    recently_active = bool(last_success_epoch > 0 and (now - last_success_epoch) <= LOCAL_REASONING_ACTIVE_TTL_SEC)
    if warmup_state == "Ready" and not recently_active and not warmup_in_progress:
        warmup_state = "Idle"
        _update_local_reasoning_snapshot({"warmup_state": "Idle"})

    deep_requested = bool(status.get("deep_sea_requested", _deep_sea_requested()))
    ollama_available = bool(status.get("ollama_available", False))
    active_model = _normalize_one_line(status.get("active_model", ""), "") or None
    last_warmup_timestamp = _normalize_one_line(status.get("last_warmup_timestamp", ""), "")
    last_failure_reason = _normalize_one_line(status.get("last_failure_reason", ""), "")
    preferred_model = _preferred_ollama_model()

    if not deep_requested:
        note = "Deep Sea Mode standby (not requested)."
    elif probe_in_progress and not ollama_available:
        note = "Checking local Ollama runtime..."
    elif warmup_state == "Warming":
        note = f"Warming local model `{active_model or preferred_model}` (bounded 12s)."
    elif warmup_state == "Ready":
        note = f"Deep Sea local reasoning ready with `{active_model or preferred_model}`."
    elif ollama_available:
        note = f"Local Ollama runtime detected. Warmup is idle for `{active_model or preferred_model}`."
    else:
        note = "Deep Sea requested, but local Ollama runtime is unavailable."
    if last_failure_reason and warmup_state == "Failed":
        note = f"{note} {last_failure_reason}"

    return {
        "deep_sea_requested": deep_requested,
        "ollama_available": ollama_available,
        "warmup_state": warmup_state,
        "last_warmup_timestamp": last_warmup_timestamp,
        "last_failure_reason": last_failure_reason if warmup_state == "Failed" else "",
        "active_model": active_model,
        "recently_active": recently_active,
        "probe_in_progress": probe_in_progress,
        "last_success_timestamp": _safe_utc_iso(last_success_epoch) if last_success_epoch > 0 else "",
        "preferred_model": preferred_model,
        "note": note,
    }


def _ollama_runtime_status(force=False):
    local_status = _local_reasoning_status_payload(force=force, trigger_warmup=True)
    model_ready = str(local_status.get("warmup_state", "Idle")) == "Ready" and bool(local_status.get("recently_active"))
    preferred_model = _normalize_one_line(local_status.get("active_model", ""), "") or _preferred_ollama_model()
    return {
        "mode_enabled": bool(local_status.get("deep_sea_requested", False)),
        "available": bool(local_status.get("ollama_available", False)),
        "preferred_model": preferred_model,
        "model_ready": bool(model_ready),
        "warmup_attempted": bool(local_status.get("last_warmup_timestamp", "")),
        "warmup_ok": bool(model_ready),
        "note": _normalize_one_line(local_status.get("note", ""), ""),
        "warmup_state": _normalize_one_line(local_status.get("warmup_state", ""), "Idle"),
        "last_failure_reason": _normalize_one_line(local_status.get("last_failure_reason", ""), ""),
    }


def _assess_complexity_and_route(latest_human="", focus="", next_mission="", ollama_status=None):
    human = _normalize_one_line(latest_human, "").lower()
    mission = _normalize_one_line(next_mission, "").lower()
    combined = f"{human} {mission}".strip()
    words = [w for w in re.split(r"\s+", combined) if w]

    vague_phrases = (
        "make it better",
        "improve everything",
        "do it all",
        "handle it",
        "fix the whole thing",
        "clean everything up",
        "just make it work",
        "whatever you think",
    )
    high_adventure_tokens = (
        "overhaul",
        "rewrite",
        "re-architect",
        "rearchitect",
        "from scratch",
        "entire platform",
        "whole system",
        "everything at once",
        "massive",
        "big bang",
    )
    deep_strategy_tokens = (
        "strategy",
        "north star",
        "operating model",
        "long-term",
        "multi-quarter",
        "portfolio",
        "org design",
        "system architecture",
    )
    surgical_tokens = (
        "fix",
        "patch",
        "implement",
        "endpoint",
        "function",
        "regression",
        "test",
        "verify",
        "small slice",
        "deterministic",
    )

    has_vague_phrase = any(phrase in combined for phrase in vague_phrases)
    is_short_vague = bool(focus == "general" and 0 < len(words) <= 6)
    has_high_adventure = any(token in combined for token in high_adventure_tokens)
    has_deep_strategy = any(token in combined for token in deep_strategy_tokens)
    has_surgical_human = any(token in human for token in surgical_tokens)
    mission_code_hint = _mission_looks_code_related(next_mission)
    has_surgical = bool(has_surgical_human or (mission_code_hint and focus in {"next_mission"}))

    needs_clarification = bool((has_high_adventure and not has_surgical) or has_vague_phrase or is_short_vague)
    complexity_reason = ""
    if needs_clarification:
        if has_high_adventure and not has_surgical:
            complexity_reason = "high-adventure scope without clear boundaries"
        elif has_vague_phrase:
            complexity_reason = "unclear intent needs sharper scope"
        else:
            complexity_reason = "request is short and broad; goals need clarity"

    ollama = ollama_status if isinstance(ollama_status, dict) else _ollama_runtime_status()
    ollama_available = bool(ollama.get("available") and ollama.get("model_ready"))
    route = "GGC_SYNTHESIS"
    route_note = "Matched Intelligence: calm GGC synthesis is a reliable default for this context."
    if needs_clarification:
        route = "PERSONAL_TRAINER_CLARIFY"
        route_note = "Matched Intelligence: we pause execution first to clarify intent and keep the slice safe and high-fidelity."
    elif has_surgical:
        route = "OAC_SURGICAL_EXECUTION"
        route_note = "Matched Intelligence: this looks like a surgical implementation slice, so OAC execution is the best primary path."
    elif has_deep_strategy:
        if ollama_available:
            route = "HEAVY_LOCAL_OR_GGC"
            route_note = "Matched Intelligence: this looks strategic, so a heavier local reasoning pass or GGC synthesis is recommended."
        else:
            route = "GGC_DEEP_REASONING"
            route_note = "Matched Intelligence: this looks strategic, so deeper GGC reasoning is recommended."
    elif focus in {"health", "next_mission", "general", "support"} and ollama_available:
        route = "OLLAMA_FAST_LOCAL"
        route_note = "Matched Intelligence: Deep Sea Mode prefers fast local Ollama synthesis for crisp status and next-step guidance."
    elif ollama.get("available") and not ollama.get("model_ready"):
        route_note = f"{route_note} Deep Sea Mode fallback: preferred Ollama model `{ollama.get('preferred_model', 'llama3.2:3b')}` is not ready."

    if route == "OLLAMA_FAST_LOCAL" and ollama_available:
        _mark_local_reasoning_used(ollama.get("preferred_model", ""))

    return {
        "complexity_flag": bool(needs_clarification),
        "complexity_reason": complexity_reason,
        "complexity_message": (
            "This feels like a high-adventure or unclear slice. Would you like to have a quick Personal Trainer meeting to clarify the intent before we proceed?"
            if needs_clarification
            else ""
        ),
        "matched_route": route,
        "matched_route_note": route_note,
        "ollama_available": bool(ollama_available),
        "ollama_note": _normalize_one_line(ollama.get("note", ""), ""),
        "ollama_preferred_model": _normalize_one_line(ollama.get("preferred_model", ""), ""),
        "ollama_mode_enabled": bool(ollama.get("mode_enabled", True)),
        "ollama_warmup_ok": bool(ollama.get("warmup_ok", False)),
    }


def _select_relevant_cli_context(latest_human="", focus="", cli_events=None):
    events = cli_events if isinstance(cli_events, list) else []
    if not events:
        return {}

    query = _normalize_one_line(latest_human, "").lower()
    focus_text = _normalize_one_line(focus, "").lower()
    query_tokens = {token for token in re.findall(r"[a-z0-9_]{3,}", query)}
    cli_keywords = {
        "cli",
        "terminal",
        "command",
        "stdout",
        "stderr",
        "shell",
        "output",
        "error",
        "failed",
        "traceback",
        "log",
        "logs",
        "test",
        "verify",
    }
    wants_cli = any(token in query for token in cli_keywords)

    best_event = None
    best_score = -1
    for event in events[:6]:
        command = _normalize_one_line(event.get("command", ""), "").lower()
        stdout_summary = _normalize_one_line(event.get("stdout_summary", ""), "").lower()
        stderr_summary = _normalize_one_line(event.get("stderr_summary", ""), "").lower()
        excerpt = _normalize_one_line(event.get("excerpt", ""), "").lower()
        blob = " ".join([command, stdout_summary, stderr_summary, excerpt]).strip()

        score = 0
        if wants_cli:
            score += 2
        if focus_text in {"health", "report", "support"}:
            score += 1
        if event.get("return_code") not in {None, 0}:
            score += 2 if focus_text in {"health", "report", "support"} else 1

        overlap = sum(1 for token in query_tokens if token in blob)
        if overlap >= 2:
            score += 2
        elif overlap == 1:
            score += 1

        if any(token in query for token in ("status", "health", "risk")) and event.get("return_code") not in {None, 0}:
            score += 1

        if score > best_score:
            best_score = score
            best_event = event

    threshold = 2 if wants_cli else 3
    if best_event is None or best_score < threshold:
        return {}

    summary_line = _normalize_one_line(best_event.get("summary_line", ""), "")
    if not summary_line:
        summary_line = _normalize_one_line(best_event.get("stdout_summary", ""), "") or "Recent CLI output captured."

    return {
        "event": best_event,
        "summary_line": _compact_excerpt(summary_line, limit=220),
        "wants_cli": wants_cli,
        "score": best_score,
    }


def _build_oac_handoff_prompt(summary_line, analysis, trigger, md_brain_engine):
    mission = str(analysis.get("next_mission", "")).strip() or "Execute one deterministic low-adventure slice and verify locally."
    risks = analysis.get("risks", []) or []
    risk_note = risks[0] if risks else "No immediate friction signals detected."
    focus = str(analysis.get("conversation_focus", "")).strip() or _compact_excerpt(str(summary_line or "").strip(), limit=120)
    engine = str(md_brain_engine or DEFAULT_MD_BRAIN_ENGINE).strip() or DEFAULT_MD_BRAIN_ENGINE

    steps = (
        "Steps: 1) Confirm baseline behavior for this objective. "
        "2) Implement the smallest deterministic change only. "
        "3) Run one local verification and capture clear pass/fail evidence. "
        "4) Log outcome in DYNAMIC_MEMORY with next action."
    )
    prompt = (
        f"OAC execution handoff ({engine} MD synthesis) | Trigger: {trigger} | Objective: {mission} | "
        f"Why now: {risk_note} | Context focus: {focus} | {steps} | "
        "Definition of done: objective verified locally and documented. | "
        "Guardrails: local-first, low-adventure, anti-drift, no unrelated file changes."
    )
    return _compact_excerpt(_normalize_one_line(prompt), limit=560)


def _analyze_md_context(conversation=None, md_brain_engine=DEFAULT_MD_BRAIN_ENGINE):
    cli_blocks = _recent_cli_output_blocks(limit=8)
    error_hits = 0
    for block in cli_blocks:
        if ERROR_HINT_RE.search(block or ""):
            error_hits += 1

    proposal_data = _list_md_proposals()
    pending = proposal_data.get("pending", [])
    now_epoch = time.time()
    stalled_proposals = []
    for item in pending:
        ts = str(item.get("timestamp", "")).strip()
        epoch = _to_epoch(ts)
        if epoch <= 0:
            continue
        age_sec = max(0, int(now_epoch - epoch))
        if age_sec >= 3600:
            stalled_proposals.append({"proposal_id": item.get("proposal_id", ""), "age_sec": age_sec})

    quiet_seconds = _compute_feed_quiet_seconds()
    quiet_feed = bool(quiet_seconds is not None and quiet_seconds >= 1200)

    risks = []
    if error_hits >= 2:
        risks.append("Repeated CLI errors detected in recent output.")
    if stalled_proposals:
        oldest = max(stalled_proposals, key=lambda item: item["age_sec"])
        age_min = int(oldest["age_sec"] / 60)
        risks.append(f"Proposal review appears stalled (oldest pending ~{age_min}m).")
    if quiet_feed:
        quiet_min = int((quiet_seconds or 0) / 60)
        risks.append(f"Activity feed has been quiet for ~{quiet_min}m.")
    if not risks:
        risks.append("No immediate friction signals detected.")

    if error_hits >= 3 or any(item["age_sec"] >= 6 * 3600 for item in stalled_proposals):
        health = "red"
    elif error_hits >= 1 or stalled_proposals or quiet_feed:
        health = "yellow"
    else:
        health = "green"

    if health == "green":
        sentiment = "Project feels steady."
    elif health == "red":
        sentiment = "Project feels strained right now."
    elif error_hits >= 1:
        sentiment = "Some friction detected in recent CLI output."
    elif stalled_proposals:
        sentiment = "Some friction detected in proposal flow."
    else:
        sentiment = "Some friction detected, but momentum is recoverable."

    convo = conversation if isinstance(conversation, dict) else {}
    latest_human = str(convo.get("latest_human", "")).strip()
    prior_human = str(convo.get("prior_human", "")).strip()
    prior_md = str(convo.get("prior_md", "")).strip()
    focus = str(convo.get("focus", "")).strip().lower()
    paired_turns = convo.get("paired_turns", []) or []
    recent_cli_context = convo.get("recent_cli_context", []) or []
    history_summary = _compact_excerpt(str(convo.get("history_summary", "")).strip(), limit=210)
    recent_summary = _compact_excerpt(str(convo.get("recent_summary", "")).strip(), limit=210)
    project_state_summary = _compact_excerpt(str(convo.get("project_state_summary", "")).strip(), limit=220)
    using_project_summary = bool(convo.get("using_project_summary")) and bool(project_state_summary)
    creator_focus_summary = _compact_excerpt(str(convo.get("creator_focus_summary", "")).strip(), limit=170)
    creator_patterns_active = bool(creator_focus_summary)
    creator_focus_patterns = _update_creator_focus_patterns(convo.get("creator_focus_patterns", {}), [])
    project_personality_profile = _normalize_project_personality_profile(convo.get("project_personality_profile", {}))
    project_personality_summary = _normalize_one_line(convo.get("project_personality_summary", ""), "") or _project_personality_summary_line(project_personality_profile)
    project_personality_active = bool(project_personality_summary)
    roadmap_milestone = _extract_roadmap_next_milestone()
    md_engine = str(md_brain_engine or DEFAULT_MD_BRAIN_ENGINE).strip() or DEFAULT_MD_BRAIN_ENGINE
    local_reasoning_status = _local_reasoning_status_payload(trigger_warmup=True)
    deep_sea_active = bool(
        local_reasoning_status.get("deep_sea_requested")
        and local_reasoning_status.get("ollama_available")
        and str(local_reasoning_status.get("warmup_state", "")).lower() == "ready"
        and bool(local_reasoning_status.get("recently_active"))
    )
    ollama_status = _ollama_runtime_status()

    design_review = _extract_design_review_request(latest_human)
    is_design_review = bool(focus == "design_review" or design_review.get("proposal_id"))

    if is_design_review:
        proposal_id = _normalize_one_line(design_review.get("proposal_id", ""), "")
        proposal_summary = _normalize_one_line(design_review.get("summary", ""), "")
        target_files = _normalize_one_line(design_review.get("target_files", ""), "")
        payload_excerpt = _normalize_one_line(design_review.get("design_payload_excerpt", ""), "")
        worth_assessment = _normalize_one_line(design_review.get("worth_assessment", ""), "")
        value_score = design_review.get("value_score")
        if value_score is None:
            score_seed = 7
            low_risk_tokens = ("low-adventure", "safe", "polish", "clarity", "readability", "non-destructive")
            high_risk_tokens = ("rewrite", "overhaul", "re-architect", "rearchitect", "large", "high-adventure")
            design_blob = " ".join([proposal_summary, target_files, payload_excerpt]).lower()
            if any(token in design_blob for token in low_risk_tokens):
                score_seed += 1
            if any(token in design_blob for token in high_risk_tokens):
                score_seed -= 2
            value_score = max(1, min(10, score_seed))
        if not worth_assessment:
            if proposal_summary:
                worth_assessment = f"The slice is practical and aligned with project direction: {proposal_summary}"
            else:
                worth_assessment = "The slice is practical, low-adventure, and suitable for staged harmonization."
        if int(value_score) >= 8:
            md_recommendation = "HARMONIZE"
        elif int(value_score) <= 4:
            md_recommendation = "REJECT"
        else:
            md_recommendation = "INTERVIEW_USER"
        status_recommendation = "REJECTED" if md_recommendation == "REJECT" else "ASSESSED"
        proposal_label = proposal_id or "P-UNKNOWN"
        guidance = (
            f"Design review completed for {proposal_label}. "
            "ASSESSMENT_REPORT: "
            f"DESIGN_PROPOSAL_ID: {proposal_label}. "
            f"WORTH_ASSESSMENT: {worth_assessment}. "
            f"VALUE_SCORE: {int(value_score)}. "
            f"MD_RECOMMENDATION: {md_recommendation}. "
            f"STATUS_RECOMMENDATION: {status_recommendation}."
        )
        next_mission = (
            f"Capture MD assessment for {proposal_label} and queue OAC harmonization review."
            if md_recommendation == "HARMONIZE"
            else (
                f"Capture MD assessment for {proposal_label} and run a short interview with the user before harmonization."
                if md_recommendation == "INTERVIEW_USER"
                else f"Capture MD assessment for {proposal_label}, mark it rejected, and keep alternatives non-destructive."
            )
        )
        suggested_mission = ""
    else:
        if error_hits >= 2:
            guidance = "I noticed repeated CLI errors in recent output. I recommend a quick regression check with OAC to stabilize this slice."
            next_mission = "Run a low-adventure regression check focused on the latest failing CLI path and capture one deterministic fix."
        elif stalled_proposals:
            guidance = "I noticed a proposal has been waiting for review. I recommend a concise accept/refine decision so momentum stays calm."
            next_mission = "Review the oldest pending proposal, choose accept/refine, and log the decision for harmonization."
        elif quiet_feed:
            guidance = "I noticed the feed is quiet right now. I recommend queuing one low-adventure mission to keep momentum steady."
            next_mission = "Dispatch one small deterministic slice from the roadmap and verify locally."
        else:
            guidance = "I noticed steady project signals. I recommend continuing with one focused low-adventure mission."
            next_mission = _extract_current_mission()

        suggested_mission = ""
        if focus == "next_mission" or quiet_feed:
            suggested_mission = _build_roadmap_suggested_mission(roadmap_milestone)
        if not suggested_mission and focus == "next_mission":
            suggested_mission = next_mission
        if suggested_mission:
            next_mission = suggested_mission

    detected_style_tags = _extract_creator_focus_tags(
        human_text=latest_human,
        focus=focus,
        next_mission=next_mission,
    )
    persona_profile_influence = _build_persona_influence(
        profile=project_personality_profile,
        creator_focus_summary=creator_focus_summary,
        detected_tags=detected_style_tags,
        focus=focus,
    )
    anticipatory_line = _creator_style_anticipation_line(
        patterns=creator_focus_patterns,
        detected_tags=detected_style_tags,
    )
    complexity_info = _assess_complexity_and_route(
        latest_human=latest_human,
        focus=focus,
        next_mission=next_mission,
        ollama_status=ollama_status,
    )
    cli_context_match = _select_relevant_cli_context(
        latest_human=latest_human,
        focus=focus,
        cli_events=recent_cli_context,
    )
    complexity_flag = bool(complexity_info.get("complexity_flag"))
    complexity_reason = _normalize_one_line(complexity_info.get("complexity_reason", ""), "")
    matched_route = _normalize_one_line(complexity_info.get("matched_route", ""), "GGC_SYNTHESIS")
    matched_route_note = _normalize_one_line(complexity_info.get("matched_route_note", ""), "")
    ollama_available = bool(complexity_info.get("ollama_available", False))
    ollama_note = _normalize_one_line(complexity_info.get("ollama_note", ""), "")
    ollama_preferred_model = _normalize_one_line(complexity_info.get("ollama_preferred_model", ""), "")

    if complexity_flag:
        guidance = _normalize_one_line(complexity_info.get("complexity_message", ""), "") or guidance
        if creator_patterns_active:
            guidance = f"{guidance} I want to respect your style and keep the mission crisp before we execute."
        if matched_route_note:
            guidance = f"{guidance} {matched_route_note}"
        if ollama_note:
            guidance = f"{guidance} {ollama_note}"
        next_mission = "Personal Trainer clarification meeting: define intent, boundaries, and success checks for the next low-adventure slice."
        suggested_mission = ""
        requires_oac_execution = False
    else:
        if not is_design_review:
            next_mission = _ensure_single_step_mission(next_mission)

        if prior_md and focus in {"general", "support", "next_mission"}:
            prior_note = _compact_excerpt(prior_md, limit=96)
            guidance = f"{guidance} I also remember our recent guidance: \"{prior_note}\"."

        if focus == "health":
            guidance = f"{sentiment} {guidance}"
        elif focus == "next_mission":
            guidance = f"{sentiment} I recommend this next low-adventure mission: {next_mission}"
        elif focus == "support":
            guidance = f"I noticed you're feeling friction. {guidance}"
        elif focus == "report":
            guidance = f"Current synthesis: {sentiment} {guidance}"

        if prior_human:
            prior_line = _compact_excerpt(prior_human, limit=96)
            guidance = f"{guidance} I noticed your earlier focus was: \"{prior_line}\"."

        if next_mission and focus not in {"next_mission", "report"} and (health in {"yellow", "red"} or focus in {"support", "general"}):
            guidance = f"{guidance} I recommend this next low-adventure mission: {next_mission}"
        if suggested_mission and suggested_mission not in guidance and focus in {"next_mission", "support"}:
            guidance = f"{guidance} Suggested next slice: {suggested_mission}"
        if project_state_summary and (focus in {"next_mission", "support", "general"} or quiet_feed):
            guidance = f"{guidance} Based on recent project patterns, {project_state_summary}."
        if cli_context_match:
            cli_line = _normalize_one_line(cli_context_match.get("summary_line", ""), "")
            cli_event = cli_context_match.get("event", {}) if isinstance(cli_context_match.get("event"), dict) else {}
            cli_source = _normalize_one_line(cli_event.get("source", ""), "CLI")
            cli_should_show = bool(focus in {"health", "report", "support"} or cli_context_match.get("wants_cli"))
            if cli_line and cli_should_show:
                guidance = f"{guidance} Recent terminal context from {cli_source}: {cli_line}."
        if recent_summary and focus in {"next_mission", "support", "general"}:
            guidance = f"{guidance} Recent conversation thread: {recent_summary}."
        elif history_summary and focus in {"next_mission", "support", "general"}:
            guidance = f"{guidance} Earlier context summary: {history_summary}."
        if deep_sea_active:
            anchor_fragments = []
            if roadmap_milestone and roadmap_milestone.lower() not in guidance.lower():
                anchor_fragments.append(f"ROADMAP anchor: {roadmap_milestone}.")
            if cli_context_match:
                cli_anchor = _normalize_one_line(cli_context_match.get("summary_line", ""), "")
                if cli_anchor and cli_anchor.lower() not in guidance.lower():
                    anchor_fragments.append(f"DYNAMIC_MEMORY anchor: {cli_anchor}.")
            if anchor_fragments:
                guidance = f"{guidance} {' '.join(anchor_fragments)}"
        if creator_patterns_active and (focus in {"next_mission", "support", "general"} or quiet_feed):
            if anticipatory_line:
                guidance = f"{guidance} {anticipatory_line}"
            if len(paired_turns) % 2 == 0:
                guidance = f"{guidance} From what I've noticed about how you like to work, {creator_focus_summary}."
            else:
                guidance = f"{guidance} Based on your recent focus patterns, I recommend keeping this momentum with a calm low-adventure step."
        elif anticipatory_line and focus in {"next_mission", "support", "general"}:
            guidance = f"{guidance} {anticipatory_line}"

        if persona_profile_influence.get("attuned") and focus in {"next_mission", "support", "general", "health"}:
            attuned_line = _normalize_one_line(persona_profile_influence.get("attuned_line", ""), "")
            if attuned_line:
                guidance = f"{guidance} {attuned_line}"

        if matched_route_note:
            guidance = f"{guidance} {matched_route_note}"
        if ollama_note and matched_route == "OLLAMA_FAST_LOCAL":
            guidance = f"{guidance} {ollama_note}"

        if project_personality_active and focus in {"next_mission", "support", "general"}:
            personality_lower = project_personality_summary.lower()
            if "calm low-adventure" in personality_lower:
                guidance = f"{guidance} Given your preference for calm low-adventure steps, {project_personality_summary}."
            else:
                guidance = f"{guidance} Knowing this project and your style, {project_personality_summary}."

        if creator_patterns_active and "visual" in creator_focus_summary.lower() and focus in {"next_mission", "support", "general"}:
            guidance = f"{guidance} From what I've noticed about how you like to work on visual flows, this direction can stay elegant and low-adventure."

        milestone_relevant = bool(roadmap_milestone and focus in {"next_mission", "support", "general"})
        if milestone_relevant:
            guidance_lower = guidance.lower()
            milestone_lower = str(roadmap_milestone).lower()
            if milestone_lower not in guidance_lower:
                guidance = f"{guidance} Relevant roadmap milestone: {roadmap_milestone}."

        if not is_design_review and focus in {"next_mission", "support", "general", "health"}:
            low_adventure_step = _normalize_one_line(next_mission, "")
            if low_adventure_step and "one low-adventure step:" not in guidance.lower():
                guidance = f"{guidance} One low-adventure step: {low_adventure_step}"

    if md_engine == "GGC" and not complexity_flag:
        guidance = f"{guidance} If helpful, I can draft a clean OAC handoff now."

    guidance = _compact_excerpt(_normalize_one_line(guidance, ""), limit=980)
    next_mission = _compact_excerpt(_normalize_one_line(next_mission, ""), limit=320)
    suggested_mission = _compact_excerpt(_normalize_one_line(suggested_mission, ""), limit=320)

    if complexity_flag:
        requires_oac_execution = False
    else:
        requires_oac_execution = _mission_looks_code_related(next_mission) or matched_route == "OAC_SURGICAL_EXECUTION"
        if stalled_proposals and error_hits == 0 and not quiet_feed and focus not in {"next_mission", "support"}:
            requires_oac_execution = False

    focus_text = latest_human or "No direct human query in the recent window."
    if prior_human:
        focus_text = f"Latest: {latest_human} | Prior: {prior_human}"

    return {
        "md_brain_engine": md_engine,
        "health": health,
        "project_sentiment": sentiment,
        "risks": risks,
        "guidance": guidance,
        "next_mission": next_mission,
        "suggested_mission": suggested_mission,
        "requires_oac_execution": bool(requires_oac_execution),
        "error_hits": error_hits,
        "stalled_count": len(stalled_proposals),
        "quiet_feed": quiet_feed,
        "conversation_focus": _compact_excerpt(focus_text, limit=220),
        "conversation_turns": len(paired_turns),
        "project_state_summary": project_state_summary,
        "using_project_summary": using_project_summary,
        "creator_focus_summary": creator_focus_summary,
        "creator_patterns_active": creator_patterns_active,
        "project_personality_profile": project_personality_profile,
        "project_personality_summary": project_personality_summary,
        "project_personality_active": project_personality_active,
        "persona_influence": _normalize_one_line(persona_profile_influence.get("persona_influence", ""), ""),
        "persona_attuned": bool(persona_profile_influence.get("attuned", False)),
        "complexity_flag": complexity_flag,
        "complexity_reason": complexity_reason,
        "matched_route": matched_route,
        "matched_route_note": matched_route_note,
        "ollama_available": ollama_available,
        "ollama_note": ollama_note,
        "ollama_preferred_model": ollama_preferred_model,
        "ollama_mode_enabled": bool(complexity_info.get("ollama_mode_enabled", True)),
        "ollama_warmup_ok": bool(complexity_info.get("ollama_warmup_ok", False)),
        "local_reasoning_status": local_reasoning_status,
        "deep_sea_active": deep_sea_active,
        "cli_context_used": bool(cli_context_match),
        "cli_context_summary": _normalize_one_line(cli_context_match.get("summary_line", ""), ""),
    }


def _append_md_report(trigger, event_id, summary_line, analysis, md_brain_engine, oac_handoff_prompt="", reason=""):
    timestamp = _now_iso()
    risk_lines = analysis.get("risks", []) or ["No immediate friction signals detected."]
    risk_block = "\n".join([f"  - {line}" for line in risk_lines])
    suggested_mission = _normalize_one_line(analysis.get("suggested_mission", ""), "")
    creator_focus_summary = _normalize_one_line(analysis.get("creator_focus_summary", ""), "")
    project_personality_summary = _normalize_one_line(analysis.get("project_personality_summary", ""), "")
    persona_influence = _normalize_one_line(analysis.get("persona_influence", ""), "")
    persona_attuned = bool(analysis.get("persona_attuned", False))
    reason_line = _normalize_one_line(reason, "")
    if reason_line:
        summary_text = f"{summary_line} ({reason_line})"
    else:
        summary_text = summary_line

    block = "\n".join(
        [
            "## MD_REPORT",
            f"- timestamp: {timestamp}",
            f"- event_id: {event_id}",
            f"- trigger: {trigger}",
            f"- md_health: {str(analysis.get('health', 'yellow')).upper()}",
            f"- md_brain_engine: {md_brain_engine}",
            f"- project_sentiment: {analysis.get('project_sentiment', 'Project feels steady.')}",
            f"- what_happened: {summary_text}",
            f"- conversation_focus: {analysis.get('conversation_focus', 'No direct human query in the recent window.')}",
            "- risks:",
            risk_block,
            f"- next_low_adventure_mission: {analysis.get('next_mission', 'Dispatch one deterministic low-adventure mission.')}",
            f"- suggested_mission: {suggested_mission or '(none)'}",
            f"- creator_focus_patterns: {creator_focus_summary or '(learning)'}",
            f"- project_personality_profile: {project_personality_summary or '(forming)'}",
            f"- persona_influence: {persona_influence or '(none)'}",
            f"- attuned_guidance: {'TRUE' if persona_attuned else 'FALSE'}",
            f"- complexity_flag: {'TRUE' if analysis.get('complexity_flag') else 'FALSE'}",
            f"- complexity_reason: {_normalize_one_line(analysis.get('complexity_reason', ''), '(none)')}",
            f"- complexity_message: {_normalize_one_line(analysis.get('guidance', ''), '(none)') if analysis.get('complexity_flag') else '(none)'}",
            f"- matched_route: {_normalize_one_line(analysis.get('matched_route', ''), 'GGC_SYNTHESIS')}",
            f"- matched_route_note: {_normalize_one_line(analysis.get('matched_route_note', ''), '(none)')}",
            f"- ollama_available: {'TRUE' if analysis.get('ollama_available') else 'FALSE'}",
            f"- ollama_note: {_normalize_one_line(analysis.get('ollama_note', ''), '(none)')}",
            f"- ollama_preferred_model: {_normalize_one_line(analysis.get('ollama_preferred_model', ''), '(none)')}",
            f"- heart_guidance: {analysis.get('guidance', 'System calm. Continue with a small deterministic slice.')}",
            f"- oac_handoff_prompt: {_normalize_one_line(oac_handoff_prompt, '(not needed for this report)')}",
            "- triad_of_truth: OAC + GGC + Human Lead review.",
            "- ethos_reference: Follow `G-Codex-brain/AGENT_RULES.md` and keep changes deterministic, local-first, and anti-drift.",
            "- gatekeeper: Major repo-shaping changes require accepted harmonization + brain logging before commit/push.",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)

    guidance_block = "\n".join(
        [
            "## MD_GUIDANCE",
            f"- timestamp: {timestamp}",
            f"- trigger: {trigger}",
            f"- md_health: {str(analysis.get('health', 'yellow')).upper()}",
            f"- md_brain_engine: {md_brain_engine}",
            f"- suggestion: {analysis.get('guidance', 'System calm. Continue with a small deterministic slice.')}",
            f"- suggested_next_mission: {analysis.get('next_mission', 'Dispatch one deterministic low-adventure mission.')}",
            f"- suggested_mission: {suggested_mission or '(none)'}",
            f"- creator_focus_patterns: {creator_focus_summary or '(learning)'}",
            f"- project_personality_profile: {project_personality_summary or '(forming)'}",
            f"- complexity_flag: {'TRUE' if analysis.get('complexity_flag') else 'FALSE'}",
            f"- complexity_reason: {_normalize_one_line(analysis.get('complexity_reason', ''), '(none)')}",
            f"- complexity_message: {_normalize_one_line(analysis.get('guidance', ''), '(none)') if analysis.get('complexity_flag') else '(none)'}",
            f"- matched_route: {_normalize_one_line(analysis.get('matched_route', ''), 'GGC_SYNTHESIS')}",
            f"- matched_route_note: {_normalize_one_line(analysis.get('matched_route_note', ''), '(none)')}",
            f"- ollama_available: {'TRUE' if analysis.get('ollama_available') else 'FALSE'}",
            f"- ollama_note: {_normalize_one_line(analysis.get('ollama_note', ''), '(none)')}",
            f"- ollama_preferred_model: {_normalize_one_line(analysis.get('ollama_preferred_model', ''), '(none)')}",
            f"- oac_handoff_prompt: {_normalize_one_line(oac_handoff_prompt, '(not needed for this guidance)')}",
            "",
        ]
    )
    _append_dynamic_memory_entry(guidance_block)
    return timestamp


def _run_md_core(trigger="ACTIVITY_SIGNAL", force=False, reason=""):
    state = _read_md_core_state()
    roles_state = _read_agent_roles()
    md_brain_engine = str(roles_state.get("md_brain_engine", DEFAULT_MD_BRAIN_ENGINE)).strip() or DEFAULT_MD_BRAIN_ENGINE
    repo_profile = _repo_size_profile()
    repo_is_large = bool(repo_profile.get("is_large"))
    project_state_summary = _normalize_one_line(state.get("project_state_summary", ""), "")
    creator_focus_patterns = _update_creator_focus_patterns(state.get("creator_focus_patterns", {}), [])
    creator_focus_summary = _normalize_one_line(state.get("creator_focus_summary", ""), "") or _creator_focus_patterns_summary(creator_focus_patterns)
    project_personality_profile = _normalize_project_personality_profile(state.get("project_personality_profile", {}))
    project_personality_summary = _normalize_one_line(state.get("project_personality_summary", ""), "") or _project_personality_summary_line(project_personality_profile)
    events = _collect_md_core_trigger_events()
    latest_event = events[0] if events else None
    event_id = latest_event.get("event_id", "") if latest_event else ""

    if not force:
        if not latest_event:
            return {"generated": False, "reason": "no trigger events yet"}
        if event_id and event_id == state.get("last_event_id"):
            return {"generated": False, "reason": "already up to date"}

    summary = latest_event.get("summary", "Managing Director synthesized current context.") if latest_event else "Manual MD report requested."
    trigger_label = latest_event.get("trigger", trigger) if latest_event else trigger
    conversation = _collect_md_conversation_window(max_turns=8)
    if not conversation.get("messages"):
        conversation["messages"] = _normalize_md_conversation_items(state.get("conversation_window", []), limit=16)

    history_summary = _normalize_one_line(conversation.get("history_summary", ""), "")
    if repo_is_large:
        compacted_messages, older_summary = _compact_conversation_for_large_repo(conversation.get("messages", []), keep_recent=8)
        conversation["messages"] = compacted_messages
        if older_summary:
            history_summary = _merge_project_state_summary(history_summary, older_summary, limit=320)
            project_state_summary = _merge_project_state_summary(project_state_summary, older_summary, limit=520)

    conversation["project_state_summary"] = project_state_summary
    conversation["using_project_summary"] = bool(repo_is_large and project_state_summary)
    conversation["creator_focus_summary"] = creator_focus_summary
    conversation["creator_focus_patterns"] = creator_focus_patterns
    conversation["project_personality_profile"] = project_personality_profile
    conversation["project_personality_summary"] = project_personality_summary
    conversation["history_summary"] = history_summary
    conversation["recent_cli_context"] = _recent_cli_output_events(limit=6)

    analysis = _analyze_md_context(conversation=conversation, md_brain_engine=md_brain_engine)
    
    # Domain Node Hygiene Audit (Phase 18)
    try:
        _audit_domain_nodes()
    except Exception:
        pass

    if trigger_label in PROJECT_MEMORY_MAJOR_TRIGGERS:
        pattern_summary = _compose_project_pattern_summary(summary, analysis, conversation)
        project_state_summary = _merge_project_state_summary(project_state_summary, pattern_summary, limit=520)
    repeated_focus = _detect_repeated_focus_area(conversation)
    should_update_creator_patterns = trigger_label in PROJECT_MEMORY_MAJOR_TRIGGERS or bool(repeated_focus)
    tags = []
    if should_update_creator_patterns:
        tags = _extract_creator_focus_tags(
            human_text=conversation.get("latest_human", ""),
            focus=conversation.get("focus", ""),
            next_mission=analysis.get("next_mission", ""),
        )
        if repeated_focus:
            tags.extend(_focus_to_creator_tags(repeated_focus))
        creator_focus_patterns = _update_creator_focus_patterns(creator_focus_patterns, tags)
        creator_focus_summary = _creator_focus_patterns_summary(creator_focus_patterns)
        if creator_focus_summary:
            project_state_summary = _merge_project_state_summary(
                project_state_summary,
                f"creator style trend: {creator_focus_summary}",
                limit=520,
            )
    else:
        tags = _extract_creator_focus_tags(
            human_text=conversation.get("latest_human", ""),
            focus=conversation.get("focus", ""),
            next_mission=analysis.get("next_mission", ""),
        )

    project_personality_profile = _update_project_personality_profile(
        project_personality_profile,
        latest_human=conversation.get("latest_human", ""),
        detected_tags=tags,
        focus=conversation.get("focus", ""),
        next_mission=analysis.get("next_mission", ""),
    )
    project_personality_summary = _normalize_one_line(project_personality_profile.get("summary", ""), "") or _project_personality_summary_line(project_personality_profile)

    analysis["project_state_summary"] = project_state_summary
    analysis["using_project_summary"] = bool(repo_is_large and project_state_summary)
    analysis["creator_focus_summary"] = creator_focus_summary
    analysis["creator_patterns_active"] = bool(creator_focus_summary)
    analysis["project_personality_profile"] = project_personality_profile
    analysis["project_personality_summary"] = project_personality_summary
    analysis["project_personality_active"] = bool(project_personality_summary)

    oac_handoff_prompt = ""
    if analysis.get("requires_oac_execution"):
        oac_handoff_prompt = _build_oac_handoff_prompt(summary, analysis, trigger_label, md_brain_engine)
    report_ts = _append_md_report(
        trigger_label,
        event_id or f"manual:{_now_iso()}",
        summary,
        analysis,
        md_brain_engine=md_brain_engine,
        oac_handoff_prompt=oac_handoff_prompt,
        reason=reason,
    )
    next_state = {
        "last_event_id": event_id,
        "last_report_at": report_ts,
        "last_health": str(analysis.get("health", "yellow")).lower(),
        "last_guidance": str(analysis.get("guidance", "")).strip(),
        "last_sentiment": str(analysis.get("project_sentiment", "")).strip(),
        "last_md_brain_engine": md_brain_engine,
        "last_oac_handoff": oac_handoff_prompt,
        "last_trigger": trigger_label,
        "conversation_window": conversation.get("messages", []),
        "project_state_summary": project_state_summary,
        "creator_focus_patterns": creator_focus_patterns,
        "creator_focus_summary": creator_focus_summary,
        "project_personality_profile": project_personality_profile,
        "project_personality_summary": project_personality_summary,
        "last_persona_influence": _normalize_one_line(analysis.get("persona_influence", ""), ""),
        "last_persona_attuned": bool(analysis.get("persona_attuned", False)),
        "last_complexity_flag": bool(analysis.get("complexity_flag")),
        "last_complexity_reason": _normalize_one_line(analysis.get("complexity_reason", ""), ""),
        "last_matched_route": _normalize_one_line(analysis.get("matched_route", ""), ""),
        "last_matched_route_note": _normalize_one_line(analysis.get("matched_route_note", ""), ""),
        "last_ollama_available": bool(analysis.get("ollama_available", False)),
        "repo_memory_mode": "summary" if repo_is_large else "raw",
        "repo_file_count": int(repo_profile.get("file_count") or 0),
        "repo_max_depth": int(repo_profile.get("max_depth") or 0),
    }
    _write_md_core_state(next_state)
    _touch_activity_refresh()
    return {
        "generated": True,
        "timestamp": report_ts,
        "trigger": trigger_label,
        "event_id": event_id,
        "health": next_state["last_health"],
        "guidance": next_state["last_guidance"],
        "project_sentiment": next_state["last_sentiment"],
        "md_brain_engine": md_brain_engine,
        "oac_handoff": oac_handoff_prompt,
        "suggested_mission": analysis.get("suggested_mission", ""),
        "project_state_summary": project_state_summary,
        "using_project_summary": bool(repo_is_large and project_state_summary),
        "creator_focus_summary": creator_focus_summary,
        "creator_patterns_active": bool(creator_focus_summary),
        "project_personality_profile": project_personality_profile,
        "project_personality_summary": project_personality_summary,
        "project_personality_active": bool(project_personality_summary),
        "persona_influence": _normalize_one_line(analysis.get("persona_influence", ""), ""),
        "persona_attuned": bool(analysis.get("persona_attuned", False)),
        "complexity_flag": bool(analysis.get("complexity_flag")),
        "complexity_reason": _normalize_one_line(analysis.get("complexity_reason", ""), ""),
        "matched_route": _normalize_one_line(analysis.get("matched_route", ""), ""),
        "matched_route_note": _normalize_one_line(analysis.get("matched_route_note", ""), ""),
        "ollama_available": bool(analysis.get("ollama_available", False)),
        "ollama_note": _normalize_one_line(analysis.get("ollama_note", ""), ""),
        "ollama_preferred_model": _normalize_one_line(analysis.get("ollama_preferred_model", ""), ""),
        "summary": summary,
        "conversation_focus": analysis.get("conversation_focus", ""),
    }


def _derive_md_suggestion_id(report_event_id, mission_text):
    mission = _normalize_one_line(mission_text, "")
    event_id = _normalize_one_line(report_event_id, "")
    if not mission:
        return ""
    seed = event_id or mission
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:10].upper()
    return f"MDS-{digest}"


def _md_status_payload():
    state = _read_md_core_state()
    roles_state = _read_agent_roles()
    latest_report = _latest_block_by_header("MD_REPORT")
    latest_guidance = _latest_block_by_header("MD_GUIDANCE")
    health = str(latest_report.get("md_health") or state.get("last_health") or "yellow").strip().lower()
    if health not in {"green", "yellow", "red"}:
        health = "yellow"
    guidance = (
        str(latest_guidance.get("guidance") or "").strip()
        or str(latest_report.get("guidance") or "").strip()
        or str(state.get("last_guidance", "")).strip()
    )
    if not guidance:
        guidance = "Managing Director standby. Synthesis will trigger automatically on activity, or you can request one manually."
    report_timestamp = str(latest_report.get("timestamp") or state.get("last_report_at") or "").strip()
    trigger = str(latest_report.get("trigger") or state.get("last_trigger") or "").strip()
    if not trigger and report_timestamp:
        trigger = "BOOTSTRAP"
    sentiment = (
        str(latest_report.get("project_sentiment") or "").strip()
        or str(state.get("last_sentiment", "")).strip()
    )
    next_mission = str(latest_report.get("next_mission") or "").strip()
    suggested_mission = (
        str(latest_guidance.get("suggested_mission") or "").strip()
        or str(latest_report.get("suggested_mission") or "").strip()
    )
    if suggested_mission.startswith("(") and suggested_mission.endswith(")"):
        suggested_mission = ""
    report_event_id = str(latest_report.get("event_id") or state.get("last_event_id") or "").strip()
    suggestion_id = _derive_md_suggestion_id(report_event_id, suggested_mission)
    md_brain_engine = (
        str(latest_guidance.get("md_brain_engine") or "").strip()
        or str(latest_report.get("md_brain_engine") or "").strip()
        or str(state.get("last_md_brain_engine", "")).strip()
        or str(roles_state.get("md_brain_engine", DEFAULT_MD_BRAIN_ENGINE)).strip()
        or DEFAULT_MD_BRAIN_ENGINE
    )
    oac_handoff = (
        str(latest_guidance.get("oac_handoff_prompt") or "").strip()
        or str(latest_report.get("oac_handoff_prompt") or "").strip()
        or str(state.get("last_oac_handoff", "")).strip()
    )
    if oac_handoff.startswith("(") and oac_handoff.endswith(")"):
        oac_handoff = ""
    project_state_summary = _normalize_one_line(state.get("project_state_summary", ""), "")
    repo_memory_mode = _normalize_one_line(state.get("repo_memory_mode", "raw"), "raw").lower()
    using_project_summary = bool(repo_memory_mode == "summary" and project_state_summary)
    creator_focus_patterns = _update_creator_focus_patterns(state.get("creator_focus_patterns", {}), [])
    creator_focus_summary = _normalize_one_line(state.get("creator_focus_summary", ""), "") or _creator_focus_patterns_summary(creator_focus_patterns)
    creator_focus_active = bool(creator_focus_summary)
    project_personality_profile = _normalize_project_personality_profile(state.get("project_personality_profile", {}))
    project_personality_summary = _normalize_one_line(state.get("project_personality_summary", ""), "") or _project_personality_summary_line(project_personality_profile)
    project_personality_active = bool(project_personality_summary)
    persona_influence = (
        _normalize_one_line(latest_guidance.get("persona_influence", ""), "")
        or _normalize_one_line(latest_report.get("persona_influence", ""), "")
        or _normalize_one_line(state.get("last_persona_influence", ""), "")
    )
    persona_attuned = bool(
        latest_guidance.get("persona_attuned")
        or latest_report.get("persona_attuned")
        or state.get("last_persona_attuned", False)
    )
    if persona_influence and persona_influence.lower() in {"(none)", "no personality signal applied"}:
        persona_attuned = False
    complexity_flag = bool(
        latest_guidance.get("complexity_flag")
        or latest_report.get("complexity_flag")
        or state.get("last_complexity_flag", False)
    )
    complexity_reason = (
        _normalize_one_line(latest_guidance.get("complexity_reason", ""), "")
        or _normalize_one_line(latest_report.get("complexity_reason", ""), "")
        or _normalize_one_line(state.get("last_complexity_reason", ""), "")
    )
    complexity_message = (
        _normalize_one_line(latest_guidance.get("complexity_message", ""), "")
        or _normalize_one_line(latest_report.get("complexity_message", ""), "")
    )
    matched_route = (
        _normalize_one_line(latest_guidance.get("matched_route", ""), "")
        or _normalize_one_line(latest_report.get("matched_route", ""), "")
        or _normalize_one_line(state.get("last_matched_route", ""), "")
        or "GGC_SYNTHESIS"
    )
    matched_route_note = (
        _normalize_one_line(latest_guidance.get("matched_route_note", ""), "")
        or _normalize_one_line(latest_report.get("matched_route_note", ""), "")
        or _normalize_one_line(state.get("last_matched_route_note", ""), "")
    )
    runtime_local_reasoning = _local_reasoning_status_payload(trigger_warmup=True)
    runtime_ollama = _ollama_runtime_status()
    ollama_available = bool(
        latest_guidance.get("ollama_available")
        or latest_report.get("ollama_available")
        or state.get("last_ollama_available", False)
        or runtime_ollama.get("model_ready", False)
    )
    ollama_note = (
        _normalize_one_line(latest_guidance.get("ollama_note", ""), "")
        or _normalize_one_line(latest_report.get("ollama_note", ""), "")
        or _normalize_one_line(runtime_local_reasoning.get("note", ""), "")
        or _normalize_one_line(runtime_ollama.get("note", ""), "")
    )
    ollama_preferred_model = (
        _normalize_one_line(latest_guidance.get("ollama_preferred_model", ""), "")
        or _normalize_one_line(latest_report.get("ollama_preferred_model", ""), "")
        or _normalize_one_line(runtime_local_reasoning.get("active_model", ""), "")
        or _normalize_one_line(runtime_ollama.get("preferred_model", ""), "")
    )
    ollama_mode_enabled = bool(runtime_local_reasoning.get("deep_sea_requested", runtime_ollama.get("mode_enabled", True)))
    ollama_runtime_available = bool(runtime_local_reasoning.get("ollama_available", runtime_ollama.get("available", False)))
    ollama_warmup_state = _normalize_one_line(runtime_local_reasoning.get("warmup_state", ""), "Idle")
    ollama_model_ready = bool(ollama_warmup_state.lower() == "ready" and runtime_local_reasoning.get("recently_active"))
    ollama_label = ollama_preferred_model or "local Ollama"
    if ollama_mode_enabled and ollama_model_ready:
        runtime_posture_line = f"Powered by {md_brain_engine} • Deep Sea Mode available ({ollama_label})"
    elif ollama_mode_enabled and ollama_warmup_state.lower() == "warming":
        runtime_posture_line = f"Powered by {md_brain_engine} • Deep Sea Mode warming ({ollama_label})"
    elif ollama_mode_enabled and ollama_warmup_state.lower() == "failed":
        runtime_posture_line = f"Powered by {md_brain_engine} • Deep Sea Mode unavailable"
    elif ollama_mode_enabled and ollama_runtime_available:
        runtime_posture_line = f"Powered by {md_brain_engine} • Deep Sea Mode warm-up pending ({ollama_label})"
    elif ollama_mode_enabled:
        runtime_posture_line = f"Powered by {md_brain_engine} • Deep Sea Mode unavailable"
    else:
        runtime_posture_line = f"Powered by {md_brain_engine} • Deep Sea Mode disabled"

    ggc_cli_path = which("gemini") or which("ggc")
    ggc_cli_detected = bool(ggc_cli_path)
    ggc_cli_command_hint = Path(ggc_cli_path).name if ggc_cli_path else ""
    ggc_terminal_supported = False
    ggc_escalation_hint = (
        f"Local GGC CLI detected ({ggc_cli_command_hint}). Open terminal manually and paste prepared prompt."
        if ggc_cli_detected
        else "Auto-launch is helper-only here. Use copied prompt with your preferred GGC environment."
    )
    if not project_personality_summary:
        project_personality_summary = _normalize_one_line(latest_guidance.get("project_personality_profile", ""), "") or _normalize_one_line(latest_report.get("project_personality_profile", ""), "")
        project_personality_active = bool(project_personality_summary)
    conversation_bus = _conversation_bus_status()
    roadmap_next_milestone = _normalize_one_line(_extract_roadmap_next_milestone(), "")
    conversation_bus_last_summary = _normalize_one_line(conversation_bus.get("last_summary", ""), "")
    rich_parts = [guidance]
    guidance_lower = guidance.lower()
    if project_personality_summary and project_personality_summary.lower() not in guidance_lower:
        rich_parts.append(f"Project personality: {project_personality_summary}.")
    if roadmap_next_milestone and roadmap_next_milestone.lower() not in guidance_lower:
        rich_parts.append(f"Roadmap milestone: {roadmap_next_milestone}.")
    if conversation_bus_last_summary and "recent cli" not in guidance_lower:
        rich_parts.append(f"Recent CLI context: {conversation_bus_last_summary}.")
    ticker_rich_guidance = _compact_excerpt(" ".join(part for part in rich_parts if part).strip(), limit=520)
    ticker_preview_parts = [runtime_posture_line]
    if next_mission:
        ticker_preview_parts.append(f"Mission: {next_mission}")
    elif roadmap_next_milestone:
        ticker_preview_parts.append(f"Roadmap: {roadmap_next_milestone}")
    if conversation_bus_last_summary:
        ticker_preview_parts.append(f"CLI: {conversation_bus_last_summary}")
    ticker_preview_line = _compact_excerpt(" • ".join(part for part in ticker_preview_parts if part), limit=240)
    repo_posture = _repo_posture_payload()
    payload = {
        "health": health,
        "last_report_at": report_timestamp,
        "last_trigger": trigger,
        "guidance": guidance,
        "sentiment": sentiment,
        "next_mission": next_mission,
        "suggested_mission": suggested_mission,
        "suggestion_id": suggestion_id,
        "md_brain_engine": md_brain_engine,
        "oac_handoff": oac_handoff,
        "oac_handoff_target": "OAC",
        "report_event_id": report_event_id,
        "project_state_summary": project_state_summary,
        "using_project_summary": using_project_summary,
        "creator_focus_patterns": creator_focus_patterns,
        "creator_focus_summary": creator_focus_summary,
        "creator_focus_active": creator_focus_active,
        "project_personality_profile": project_personality_profile,
        "project_personality_summary": project_personality_summary,
        "project_personality_active": project_personality_active,
        "persona_influence": persona_influence,
        "persona_attuned": persona_attuned,
        "roadmap_next_milestone": roadmap_next_milestone,
        "complexity_flag": complexity_flag,
        "complexity_reason": complexity_reason,
        "complexity_message": complexity_message,
        "complexity_note": complexity_message or (complexity_reason if complexity_flag else ""),
        "matched_route": matched_route,
        "matched_route_note": matched_route_note,
        "ollama_available": bool(ollama_available),
        "ollama_note": ollama_note,
        "ollama_preferred_model": ollama_preferred_model,
        "runtime_posture_line": runtime_posture_line,
        "local_reasoning_status": runtime_local_reasoning,
        "ticker_rich_guidance": ticker_rich_guidance,
        "ticker_preview_line": ticker_preview_line,
        "ggc_terminal_supported": bool(ggc_terminal_supported),
        "ggc_cli_detected": bool(ggc_cli_detected),
        "ggc_cli_command_hint": ggc_cli_command_hint,
        "ggc_escalation_hint": ggc_escalation_hint,
        "conversation_bus_active": bool(conversation_bus.get("active")),
        "conversation_bus_healthy": bool(conversation_bus.get("healthy")),
        "conversation_bus_state": _normalize_one_line(conversation_bus.get("state", ""), "IDLE"),
        "conversation_bus_last_capture_at": _normalize_one_line(conversation_bus.get("last_capture_at", ""), ""),
        "conversation_bus_seconds_since_last_capture": conversation_bus.get("seconds_since_last_capture"),
        "conversation_bus_last_source": _normalize_one_line(conversation_bus.get("last_source", ""), ""),
        "conversation_bus_last_session_label": _normalize_one_line(conversation_bus.get("last_session_label", ""), ""),
        "conversation_bus_last_command": _normalize_one_line(conversation_bus.get("last_command", ""), ""),
        "conversation_bus_last_summary": conversation_bus_last_summary,
        "repo_memory_mode": repo_memory_mode,
        "repo_file_count": int(state.get("repo_file_count") or 0),
        "repo_max_depth": int(state.get("repo_max_depth") or 0),
        "repo_posture": repo_posture,
    }

    try:
        all_proposals = _list_md_proposals()
        design_pending = all_proposals.get("design_pending", [])
        if design_pending:
            latest = design_pending[0]
            if latest.get("github_issue_ready"):
                payload["github_issue_ready"] = True
                payload["github_issue_payload"] = latest.get("github_issue_payload")
    except Exception:
        pass

    return payload


def _suggest_pr_calmness_score(title, body):
    combined = f"{title} {body}".lower()
    if any(t in combined for token in ("fix", "chore", "refactor", "docs", "polish", "typo") for t in (token,)):
        return 9
    if any(t in combined for token in ("overhaul", "rewrite", "major", "breaking", "massive") for t in (token,)):
        return 3
    return 7


def _get_pr_persona_alignment_hint(title, body):
    combined = f"{title} {body}".lower()
    # In a real scenario, we might call mcp_server or read the file.
    # For now, we'll try to find user_domain_nodes.json in the brain folder or root.
    nodes = []
    try:
        nodes_path = ROOT / "G-Codex-brain" / "user_domain_nodes.json"
        if not nodes_path.exists():
            nodes_path = ROOT / "user_domain_nodes.json"
        if nodes_path.exists():
            payload = json.loads(nodes_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                nodes = payload.get("nodes", [])
            elif isinstance(payload, list):
                nodes = payload
    except Exception:
        pass

    matches = []
    for node in nodes:
        if str(node).lower() in combined:
            matches.append(str(node))
    
    if matches:
        return f"Aligns with {', '.join(matches)} study."
    return ""


def _build_enriched_pr_review_prompt(pr_details):
    pr_number = pr_details.get("number", "???")
    title = pr_details.get("title", "")
    body_desc = pr_details.get("body", "")
    head = pr_details.get("headRefName", "unknown")
    base = pr_details.get("baseRefName", "unknown")

    state = _read_md_core_state()
    profile = state.get("project_personality_profile", {})
    recent_notes = profile.get("recent_focus_notes", [])
    signals = profile.get("preference_signals", [])

    relevant_signals = []
    combined_pr = f"{title} {body_desc}".lower()
    
    # Material relevance gating
    for signal in signals:
        sig_norm = str(signal).replace("_", " ").lower()
        if sig_norm in combined_pr:
            relevant_signals.append(f"Preference: {sig_norm}")
    
    for note in recent_notes:
        note_lower = str(note).lower()
        # Find overlapping keywords
        words = [w for w in re.split(r"\s+", note_lower) if len(w) > 4]
        if any(w in combined_pr for w in words):
            relevant_signals.append(f"Recent focus: {note}")

    attuned = bool(relevant_signals)
    calmness = _suggest_pr_calmness_score(title, body_desc)
    persona_hint = _get_pr_persona_alignment_hint(title, body_desc)

    prompt = [
        "MD, please review this incoming PR and assess its alignment with our surgical, calm defaults (Blueprint v6.0).",
        "Provide an ASSESSMENT_REPORT (WORTH_ASSESSMENT, VALUE_SCORE, MD_RECOMMENDATION)."
    ]

    if relevant_signals:
        prompt.append("\nProject Personality Signals detected as relevant:")
        for rs in relevant_signals[:3]:
            prompt.append(f"- {rs}")
    
    if persona_hint:
        prompt.append(f"\nPersona Alignment Hint: {persona_hint}")

    prompt.append(f"\nSuggested Calmness Score: {calmness}/10")
    prompt.append(f"\nPR #{pr_number}: {title}")
    prompt.append(f"Branches: {head} -> {base}")
    prompt.append(f"\nDescription:\n{body_desc or '(No description provided.)'}")
    prompt.append("\n✦ Sovereign Assessment by G-Codex MD")

    return {
        "prompt": "\n".join(prompt).strip(),
        "attuned": attuned,
        "persona_influence": "attuned by relevant signals" if attuned else "none"
    }


def _review_md_suggestion(payload):
    decision = _normalize_one_line(payload.get("decision", ""), "").lower()
    notes = _normalize_one_line(payload.get("notes", ""), "-")
    reviewer = _normalize_one_line(payload.get("reviewed_by", ""), "Lead Executor")
    if decision not in {"accept", "refine", "dismiss"}:
        raise ValueError("decision must be one of: accept, refine, dismiss")

    status = _md_status_payload()
    suggested_mission = _normalize_one_line(payload.get("suggested_mission", ""), "")
    if not suggested_mission:
        suggested_mission = _normalize_one_line(status.get("suggested_mission", ""), "")
    if not suggested_mission:
        suggested_mission = _normalize_one_line(status.get("next_mission", ""), "")
    if not suggested_mission:
        raise ValueError("no suggested mission is available to review")

    suggestion_id = _normalize_one_line(payload.get("suggestion_id", ""), "")
    if not suggestion_id:
        suggestion_id = _derive_md_suggestion_id(status.get("report_event_id", ""), suggested_mission)
    if not suggestion_id:
        ts_seed = datetime.now().strftime("%Y%m%d-%H%M%S")
        suggestion_id = f"MDS-{ts_seed}"

    timestamp = _now_iso()
    md_engine = _normalize_one_line(status.get("md_brain_engine", DEFAULT_MD_BRAIN_ENGINE), DEFAULT_MD_BRAIN_ENGINE)

    oac_handoff = ""
    harmonized_commit = {}
    state = _read_md_core_state()
    project_state_summary = _normalize_one_line(state.get("project_state_summary", ""), "")
    creator_focus_patterns = _update_creator_focus_patterns(state.get("creator_focus_patterns", {}), [])
    creator_focus_summary = _normalize_one_line(state.get("creator_focus_summary", ""), "") or _creator_focus_patterns_summary(creator_focus_patterns)
    if decision == "accept":
        analysis = {
            "next_mission": suggested_mission,
            "risks": [status.get("sentiment", "No immediate friction signals detected.") or "No immediate friction signals detected."],
            "conversation_focus": f"Accepted MD suggestion {suggestion_id}",
        }
        oac_handoff = _build_oac_handoff_prompt(
            "Accepted MD suggested mission for OAC execution.",
            analysis,
            "MD_SUGGESTION_ACCEPTED",
            md_engine,
        )
        item = {
            "proposal_id": suggestion_id,
            "managing_director": "Managing Director",
            "feature_slice": suggested_mission,
            "done_summary": "Accepted MD suggested low-adventure mission and prepared OAC handoff.",
            "friction_removed": "Reduced mission selection friction with proactive roadmap suggestion.",
            "creativity_added": "Supportive proactive orchestration by MD.",
            "integration_suggestion": "Execute the handoff with OAC using deterministic local verification.",
        }
        item["harmonized_summary"] = _build_md_harmonized_summary(item, notes)
        _append_proposal_outcome_row(item, reviewer, "ACCEPTED", notes)
        _append_harmonized_proposal_entry(item, reviewer, notes or "Accepted MD proactive mission suggestion.")
        _append_brain_changelog(
            what_changed=f"Accepted MD suggested next slice {suggestion_id}: {suggested_mission}.",
            agent=reviewer,
            why="Proactive roadmap-aligned mission accepted with immediate OAC handoff.",
        )
        project_state_summary = _merge_project_state_summary(
            project_state_summary,
            _compact_excerpt(f"accepted MD suggestion {suggestion_id}: {suggested_mission}", limit=260),
            limit=520,
        )
        creator_focus_patterns = _update_creator_focus_patterns(
            creator_focus_patterns,
            _extract_creator_focus_tags(
                human_text=suggested_mission,
                focus="next_mission",
                next_mission=suggested_mission,
            ),
        )
        creator_focus_summary = _creator_focus_patterns_summary(creator_focus_patterns)
        git_status_obj = get_git_status()
        if git_status_obj.get("state") == "DIRTY":
            harmonized_commit = _build_harmonized_commit_metadata(item, notes)

    action_map = {
        "accept": "ACCEPTED",
        "refine": "REFINE_REQUESTED",
        "dismiss": "DISMISSED",
    }
    state_label = action_map.get(decision, "DISMISSED")
    suggestion_line = (
        f"I noticed this mission needed a decision. MD suggestion {state_label.lower().replace('_', ' ')}: "
        f"{suggested_mission}"
    )
    if decision == "accept":
        suggestion_line = (
            "I noticed this roadmap-aligned mission is accepted. "
            "I recommend running the OAC handoff as the next low-adventure slice."
        )
    elif decision == "refine":
        suggestion_line = (
            "I noticed this suggestion needs refinement. "
            "I recommend clarifying scope and asking MD for the next mission variant."
        )
    elif decision == "dismiss":
        suggestion_line = (
            "I noticed this suggestion was dismissed. "
            "I recommend requesting a fresh mission when you're ready."
        )

    block = "\n".join(
        [
            "## MD_GUIDANCE",
            f"- timestamp: {timestamp}",
            "- trigger: MD_SUGGESTION_REVIEW",
            f"- md_health: {str(status.get('health', 'yellow')).upper()}",
            f"- md_brain_engine: {md_engine}",
            f"- suggestion: {suggestion_line}",
            f"- suggested_next_mission: {suggested_mission}",
            f"- suggested_mission: {suggested_mission}",
            f"- suggestion_id: {suggestion_id}",
            f"- suggestion_decision: {state_label}",
            f"- reviewer: {reviewer}",
            f"- review_notes: {notes}",
            f"- oac_handoff_prompt: {_normalize_one_line(oac_handoff, '(not generated)')}",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)
    state["project_state_summary"] = project_state_summary
    state["creator_focus_patterns"] = creator_focus_patterns
    state["creator_focus_summary"] = creator_focus_summary
    _write_md_core_state(state)

    return {
        "decision": state_label,
        "suggestion_id": suggestion_id,
        "suggested_mission": suggested_mission,
        "oac_handoff": oac_handoff,
        "harmonized_commit": harmonized_commit,
    }


def _append_human_injection(message, source="Human"):
    content = str(message or "").strip()
    if not content:
        raise ValueError("message is required")
    source_name = _normalize_one_line(source, "Human")
    timestamp = _now_iso()
    block = "\n".join(
        [
            "## HUMAN_INJECTION",
            f"- timestamp: {timestamp}",
            f"- source: {source_name}",
            "- content:",
            "```text",
            content,
            "```",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)
    return timestamp


def _watcher_status_payload():
    running = False
    watcher_pid = 0
    if WATCHER_PID_FILE.exists():
        try:
            watcher_pid = int(WATCHER_PID_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            watcher_pid = 0
    if watcher_pid > 0 and _pid_exists(watcher_pid):
        running = True

    last_injection_at = _latest_bridge_injection_timestamp()
    age_seconds = None
    if last_injection_at:
        age = time.time() - _to_epoch(last_injection_at)
        if age >= 0:
            age_seconds = int(age)

    if not running:
        signal = "red"
        state = "WATCHER_OFFLINE"
    elif age_seconds is None:
        signal = "yellow"
        state = "WATCHER_ONLINE_WAITING"
    elif age_seconds <= 240:
        signal = "green"
        state = "LIVE"
    elif age_seconds <= 1800:
        signal = "yellow"
        state = "STALE"
    else:
        signal = "red"
        state = "STALE_CRITICAL"

    return {
        "watcher_running": running,
        "watcher_pid": watcher_pid if running else None,
        "last_bridge_injection_at": last_injection_at or "",
        "seconds_since_last_injection": age_seconds,
        "signal": signal,
        "state": state,
    }


def _ambient_watch_status_payload():
    running = False
    watcher_pid = 0
    parent_path = ""
    auto_start_enabled = False
    auto_start_parent = ""
    auto_start_interval = ""
    auto_start_quiet = ""

    if AMBIENT_INGRESS_PID_FILE.exists():
        try:
            watcher_pid = int(AMBIENT_INGRESS_PID_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            watcher_pid = 0
    if watcher_pid > 0 and _pid_exists(watcher_pid):
        running = True

    if AMBIENT_INGRESS_PARENT_FILE.exists():
        try:
            parent_path = AMBIENT_INGRESS_PARENT_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            parent_path = ""

    if AMBIENT_AUTO_START_FILE.exists():
        auto_start_enabled = True
        try:
            for line in AMBIENT_AUTO_START_FILE.read_text(encoding="utf-8").splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().lower()
                value = value.strip()
                if key == "parent":
                    auto_start_parent = value
                elif key == "interval":
                    auto_start_interval = value
                elif key == "quiet":
                    auto_start_quiet = value
        except OSError:
            auto_start_enabled = False

    state = "RUNNING" if running else "STOPPED"
    return {
        "running": running,
        "pid": watcher_pid if running else None,
        "parent_path": parent_path,
        "state": state,
        "auto_start_enabled": auto_start_enabled,
        "auto_start_parent": auto_start_parent,
        "auto_start_interval": auto_start_interval,
        "auto_start_quiet": auto_start_quiet,
    }


def _touch_activity_refresh():
    global ACTIVITY_REFRESH_TOKEN, ACTIVITY_REFRESH_AT
    ACTIVITY_REFRESH_TOKEN += 1
    ACTIVITY_REFRESH_AT = _now_iso()


def _ensure_proposal_outcomes_file():
    if PROPOSAL_OUTCOMES_PATH.exists():
        return
    PROPOSAL_OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROPOSAL_OUTCOMES_PATH.write_text(
        "\n".join(
            [
                "# PROPOSAL OUTCOMES",
                "",
                "Accepted Managing Director proposals are logged here for pattern reuse.",
                "",
                "| Timestamp | Proposal ID | Managing Director | Feature Slice | Outcome | Reviewer | Notes |",
                "|---|---|---|---|---|---|---|",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _ensure_brain_changelog_file():
    if CHANGELOG_PATH.exists():
        return
    CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_PATH.write_text(
        "\n".join(
            [
                "# CHANGELOG",
                "",
                "Timestamped record of accepted harmonizations and major brain transitions.",
                "",
                "| Timestamp | Agent | What Changed | Why |",
                "|---|---|---|---|",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _escape_table_cell(value, fallback="-"):
    text = " ".join(str(value or "").split()).strip()
    if not text:
        text = fallback
    return text.replace("|", "\\|")


def _append_brain_changelog(what_changed, agent, why):
    _ensure_brain_changelog_file()
    row = (
        f"| {_now_iso()} | {_escape_table_cell(agent, 'GCagent')} | "
        f"{_escape_table_cell(what_changed, '(change not specified)')} | "
        f"{_escape_table_cell(why, '(why not specified)')} |"
    )
    with CHANGELOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(row + "\n")
    return True


def _create_brain_snapshot(reason="", actor="scripts/brain_server.py"):
    if not BRAIN.exists():
        return None

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    base_name = f"G-Codex-brain-{stamp}"
    target = BACKUPS_DIR / f"{base_name}.zip"
    suffix = 1
    while target.exists():
        target = BACKUPS_DIR / f"{base_name}-{suffix:02d}.zip"
        suffix += 1

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BRAIN.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, arcname=path.relative_to(ROOT).as_posix())

    return str(target.relative_to(ROOT))


def _list_brain_snapshots(limit=12):
    if not BACKUPS_DIR.exists():
        return []

    snapshots = []
    for path in BACKUPS_DIR.glob("G-Codex-brain-*.zip"):
        if not path.is_file():
            continue
        stat = path.stat()
        modified_iso = datetime.fromtimestamp(stat.st_mtime).astimezone().replace(microsecond=0).isoformat()
        snapshots.append(
            {
                "name": path.name,
                "relative_path": str(path.relative_to(ROOT)),
                "size_bytes": stat.st_size,
                "size_human": _format_bytes_py(stat.st_size),
                "modified_at": modified_iso,
                "modified_human": _humanize_utc_iso(modified_iso),
            }
        )
    snapshots.sort(key=lambda item: _to_epoch(item.get("modified_at", "")), reverse=True)
    return snapshots[:limit]


def _format_bytes_py(num):
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def _restore_brain_snapshot(snapshot_name, restored_by="Lead Executor"):
    raw_name = str(snapshot_name or "").strip()
    if not raw_name:
        raise ValueError("snapshot is required")

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_root = BACKUPS_DIR.resolve()
    candidate = (BACKUPS_DIR / raw_name).resolve()
    try:
        candidate.relative_to(backup_root)
    except ValueError as exc:
        raise ValueError("snapshot must stay inside .backups") from exc

    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"snapshot not found: {raw_name}")
    if candidate.suffix.lower() != ".zip":
        raise ValueError("snapshot must be a .zip file")

    pre_restore_snapshot = _create_brain_snapshot(
        reason=f"Pre-restore safety snapshot before applying {candidate.name}.",
        actor=restored_by,
    )

    temp_root = Path(tempfile.mkdtemp(prefix="gcodex-restore-", dir=str(BACKUPS_DIR)))
    extracted_files = 0

    try:
        with zipfile.ZipFile(candidate, "r") as archive:
            for member in archive.infolist():
                member_name = str(member.filename or "").replace("\\", "/")
                if not member_name or member_name.endswith("/"):
                    continue

                rel_member = Path(member_name)
                if rel_member.is_absolute() or ".." in rel_member.parts:
                    raise ValueError("snapshot contains unsafe path entries")
                if not rel_member.parts or rel_member.parts[0] != "G-Codex-brain":
                    continue

                target_path = temp_root / rel_member
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                extracted_files += 1

        if extracted_files == 0:
            raise ValueError("snapshot does not contain G-Codex-brain files")

        extracted_brain = temp_root / "G-Codex-brain"
        if not extracted_brain.exists():
            raise ValueError("snapshot extraction missing G-Codex-brain directory")

        if BRAIN.exists():
            shutil.rmtree(BRAIN)
        shutil.move(str(extracted_brain), str(BRAIN))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    actor_name = _normalize_one_line(restored_by, "Lead Executor")
    _append_brain_changelog(
        what_changed=f"Restored brain state from snapshot `{candidate.name}`.",
        agent=actor_name,
        why="Rollback/recovery to restore a known-good deterministic brain state.",
    )

    return {
        "snapshot": candidate.name,
        "snapshot_path": str(candidate.relative_to(ROOT)),
        "pre_restore_snapshot": pre_restore_snapshot,
        "restored_at": _now_iso(),
        "restored_by": actor_name,
    }


def _normalize_one_line(value, fallback=""):
    text = " ".join(str(value or "").split()).strip()
    return text if text else fallback


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_domain_node_key(value):
    key = _normalize_one_line(value, "").lower()
    key = re.sub(r"[^a-z0-9_]+", "_", key).strip("_")
    return key


def _ensure_user_domain_nodes_file():
    USER_DOMAIN_NODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if USER_DOMAIN_NODES_PATH.exists():
        return
    USER_DOMAIN_NODES_PATH.write_text(
        json.dumps(list(DEFAULT_USER_DOMAIN_NODES), indent=2) + "\n",
        encoding="utf-8",
    )


def _read_user_domain_nodes():
    _ensure_user_domain_nodes_file()
    source = "user_domain_nodes.json"
    nodes = []
    try:
        payload = json.loads(USER_DOMAIN_NODES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = []
        source = "fallback_scan"

    if isinstance(payload, dict):
        raw_nodes = payload.get("nodes", [])
    elif isinstance(payload, list):
        raw_nodes = payload
    else:
        raw_nodes = []

    for raw in raw_nodes if isinstance(raw_nodes, list) else []:
        key = _normalize_domain_node_key(raw)
        if not key or key in nodes:
            continue
        nodes.append(key)

    if not nodes:
        nodes = list(DEFAULT_USER_DOMAIN_NODES)
        source = "fallback_scan"

    return {
        "nodes": nodes,
        "source": source,
        "path": str(USER_DOMAIN_NODES_PATH.relative_to(ROOT)),
    }


def _read_user_profile():
    if not USER_PROFILE_PATH.exists():
        return {"interests": [], "focus_areas": []}
    try:
        return json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"interests": [], "focus_areas": []}


def _audit_domain_nodes():
    now = _now_iso()
    node_registry = _read_user_domain_nodes()
    node_keys = node_registry.get("nodes", [])
    
    manifest_nodes = []
    required_files = ["node_config.json", "README.md"]
    
    for key in node_keys:
        node_dir = BRAIN / key
        node_dir.mkdir(parents=True, exist_ok=True)
        
        present_files = []
        for rf in required_files:
            target = node_dir / rf
            if not target.exists():
                if rf == "node_config.json":
                    config = {
                        "name": key,
                        "last_updated": now,
                        "active": True,
                        "type": "USER_DOMAIN",
                        "status": "initial"
                    }
                    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
                elif rf == "README.md":
                    target.write_text(f"# Domain Node: {key}\n\nManaged by G-Codex (Phase 18).\n", encoding="utf-8")
            
            if target.exists():
                present_files.append(rf)
        
        status = "valid" if len(present_files) == len(required_files) else "incomplete"
        
        # Read last_updated from config if available
        last_updated = now
        config_path = node_dir / "node_config.json"
        if config_path.exists():
            try:
                cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
                last_updated = cfg_data.get("last_updated") or now
            except Exception:
                pass

        manifest_nodes.append({
            "name": key,
            "last_updated": last_updated,
            "status": status,
            "required_files_present": present_files,
            "path": str(node_dir.relative_to(ROOT))
        })
    
    manifest = {
        "last_audit_at": now,
        "nodes": manifest_nodes
    }
    
    NODE_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _domain_hint_terms(node_key):
    key = _normalize_domain_node_key(node_key)
    base = tuple(DOMAIN_NODE_HINTS.get(key, ()))
    if base:
        return base
    split_terms = tuple(part for part in key.replace("-", "_").split("_") if part)
    return split_terms or (key,)


def _calculate_persona_alignment(text_parts, node_registry=None):
    registry = node_registry if isinstance(node_registry, dict) else _read_user_domain_nodes()
    active_nodes = [str(item) for item in registry.get("nodes", []) if str(item).strip()]
    source = _normalize_one_line(registry.get("source", ""), "fallback_scan")
    combined = " ".join([_normalize_one_line(item, "") for item in (text_parts or [])]).lower()
    matched_nodes = []
    for node in active_nodes:
        hints = _domain_hint_terms(node)
        if any(hint and hint.lower() in combined for hint in hints):
            matched_nodes.append(node)

    ratio = float(len(matched_nodes)) / float(len(active_nodes) or 1)
    if not matched_nodes:
        label = "LOW"
        score = 3
    elif ratio >= 0.6 or len(matched_nodes) >= 2:
        label = "HIGH"
        score = 9
    else:
        label = "MEDIUM"
        score = 7

    matched_display = ", ".join(matched_nodes) if matched_nodes else "none"
    return {
        "label": label,
        "score": int(score),
        "matched_nodes": matched_nodes,
        "active_nodes": active_nodes,
        "source": source,
        "summary": f"{label} [{matched_display}]",
    }


def _derive_surgical_impact(value_score, md_recommendation):
    score = max(1, min(10, int(value_score or 1)))
    recommendation = _normalize_one_line(md_recommendation, "").upper()
    if recommendation == "REJECT":
        return "LOW"
    if score >= 8:
        return "HIGH"
    if score >= 5:
        return "MEDIUM"
    return "LOW"


def _derive_calmness_score(text_parts, md_recommendation=""):
    combined = " ".join([_normalize_one_line(item, "") for item in (text_parts or [])]).lower()
    score = 7
    if any(token in combined for token in ("calm", "low-adventure", "safe", "surgical", "non-destructive", "small")):
        score += 1
    if any(token in combined for token in ("rewrite", "overhaul", "migration", "high-adventure", "risky", "large")):
        score -= 2
    if _normalize_one_line(md_recommendation, "").upper() == "REJECT":
        score -= 1
    return max(1, min(10, int(score)))


def _extract_latest_design_assessment_metrics(worth_and_value):
    text = _normalize_one_line(worth_and_value, "")
    latest = text.split("||")[-1].strip() if text else ""
    worth_match = re.search(r"WORTH_ASSESSMENT\s*:\s*(.+?)(?=\s+\|\s+[A-Z_]+\s*:|$)", latest, flags=re.IGNORECASE)
    value_match = re.search(r"VALUE_SCORE\s*:\s*(10|[1-9])(?:\s*/\s*10)?", latest, flags=re.IGNORECASE)
    recommendation_match = re.search(r"MD_RECOMMENDATION\s*:\s*(HARMONIZE|REJECT|INTERVIEW_USER)", latest, flags=re.IGNORECASE)
    persona_match = re.search(r"PERSONA_ALIGNMENT\s*:\s*([A-Z]+(?:\s*\[[^\]]*\])?)", latest, flags=re.IGNORECASE)
    impact_match = re.search(r"SURGICAL_IMPACT\s*:\s*(LOW|MEDIUM|HIGH)", latest, flags=re.IGNORECASE)
    calmness_match = re.search(r"CALMNESS_SCORE\s*:\s*(10|[1-9])(?:\s*/\s*10)?", latest, flags=re.IGNORECASE)
    layer_match = re.search(r"PERSONA_LAYER\s*:\s*([A-Za-z0-9._-]+)", latest, flags=re.IGNORECASE)
    return {
        "latest_entry": latest,
        "worth_assessment": _compact_excerpt(_normalize_one_line(worth_match.group(1), ""), limit=320) if worth_match else "",
        "value_score": int(value_match.group(1)) if value_match else None,
        "md_recommendation": _normalize_one_line(recommendation_match.group(1), "").upper() if recommendation_match else "",
        "persona_alignment": _normalize_one_line(persona_match.group(1), "") if persona_match else "",
        "surgical_impact": _normalize_one_line(impact_match.group(1), "").upper() if impact_match else "",
        "calmness_score": int(calmness_match.group(1)) if calmness_match else None,
        "persona_layer": _normalize_one_line(layer_match.group(1), "") if layer_match else "",
    }


def _trigger_aga_audit(proposal_id, *, status="ASSESSED", source="MD_GUIDANCE", persona_layer="fallback_scan", persona_alignment="LOW [none]"):
    pid = _normalize_one_line(proposal_id, "").upper()
    if not pid:
        return {"status": "SKIPPED", "reason": "missing proposal id"}
    detail = (
        f"AGa audit stub queued for {pid}; status={_normalize_one_line(status, 'ASSESSED')}; "
        f"persona_alignment={_normalize_one_line(persona_alignment, 'LOW [none]')}; "
        f"persona_layer={_normalize_one_line(persona_layer, 'fallback_scan')}. "
        "Full AGa visual audit wiring remains intentionally deferred."
    )
    _log_external_tool_injection(
        action_type="aga_audit_stub",
        target=f"design_proposal:{pid}",
        status="STUB_LOGGED",
        detail=detail,
        source=source,
        authorized=True,
    )
    return {"status": "STUB_LOGGED", "proposal_id": pid}


def _dynamic_memory_path():
    path = BRAIN / "DYNAMIC_MEMORY.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# DYNAMIC MEMORY\n\n", encoding="utf-8")
    return path


def _append_dynamic_memory_entry(entry_text):
    path = _dynamic_memory_path()
    current = path.read_text(encoding="utf-8")
    block = entry_text.strip() + "\n"
    if current.strip():
        if not current.endswith("\n"):
            current += "\n"
        current += "\n" + block
    else:
        current = "# DYNAMIC MEMORY\n\n" + block
    path.write_text(current, encoding="utf-8")


def _log_external_tool_injection(action_type, target, status, detail, source="MCP_GATEKEEPER", authorized=None):
    auth_flag = "unknown"
    if authorized is True:
        auth_flag = "true"
    elif authorized is False:
        auth_flag = "false"

    with MCP_AUTH_LOCK:
        session_id = _normalize_one_line(str(MCP_AUTH_STATE.get("session_id") or "mcp-session"), "mcp-session")

    block = "\n".join(
        [
            "## EXTERNAL_TOOL_INJECTION",
            f"- timestamp: {_now_iso()}",
            f"- source: {_normalize_one_line(source, 'MCP_GATEKEEPER')}",
            f"- session_id: {session_id}",
            f"- action_type: {_normalize_one_line(action_type, 'mcp_request')}",
            f"- target: {_normalize_one_line(target, '/mcp')}",
            f"- status: {_normalize_one_line(status, 'RECORDED')}",
            f"- authorized: {auth_flag}",
            f"- detail: {_compact_excerpt(_normalize_one_line(detail, '(none)'), limit=360)}",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)


def _mcp_status_payload():
    with MCP_AUTH_LOCK:
        state = dict(MCP_AUTH_STATE)
    local_reasoning_status = _local_reasoning_status_payload(trigger_warmup=True)
    github_status = _collect_github_status_payload(force=False)

    domain_nodes = None
    readiness_score = 100
    active_nodes_count = 0
    profile_match_hint = ""

    if NODE_MANIFEST_PATH.exists():
        try:
            domain_nodes = json.loads(NODE_MANIFEST_PATH.read_text(encoding="utf-8"))
            if domain_nodes and isinstance(domain_nodes.get("nodes"), list):
                nodes = domain_nodes["nodes"]
                active_nodes_count = len(nodes)
                if active_nodes_count > 0:
                    sum_score = 0
                    for n in nodes:
                        if n.get("status") == "valid":
                            sum_score += 100
                        elif n.get("status") == "incomplete":
                            sum_score += 50
                    readiness_score = int(sum_score / active_nodes_count)
                
                # Profile match hint
                user_profile = _read_user_profile()
                interests = [str(i).lower() for i in user_profile.get("interests", [])]
                if interests:
                    matched_interests = []
                    for n in nodes:
                        node_name = str(n.get("name", "")).lower()
                        if any(i in node_name for i in interests):
                            matched_interests.append(n.get("name"))
                    if matched_interests:
                        profile_match_hint = f"Aligned with interests: {', '.join(matched_interests[:2])}"
        except Exception:
            pass

    if domain_nodes:
        domain_nodes["readiness_score"] = readiness_score
        domain_nodes["active_nodes_count"] = active_nodes_count
        domain_nodes["profile_match_hint"] = profile_match_hint

    status = _normalize_one_line(state.get("status", MCP_AUTH_STATUS_IDLE), MCP_AUTH_STATUS_IDLE).upper()
    client_connected = bool(state.get("client_connected", False))
    context_release_allowed = status == MCP_AUTH_STATUS_AUTHORIZED
    request_pending = status == MCP_AUTH_STATUS_PENDING
    healthy_but_gated = status in {MCP_AUTH_STATUS_IDLE, MCP_AUTH_STATUS_PENDING, MCP_AUTH_STATUS_REVOKED}
    note_map = {
        MCP_AUTH_STATUS_IDLE: "Bridge is healthy and discovery is available. Context resources/tools are gated until MD authorization (403 is expected while gated).",
        MCP_AUTH_STATUS_PENDING: "Authorization is pending. Discovery remains available, but context resources/tools stay gated (403 expected) until approved.",
        MCP_AUTH_STATUS_AUTHORIZED: "Design interview authorized. Read-only context access is enabled for this server session.",
        MCP_AUTH_STATUS_REVOKED: "Authorization revoked for this session. Discovery remains available, but context resources/tools are gated again (403 expected).",
    }

    payload = {
        "status": status,
        "session_state": status,
        "client_connected": client_connected,
        "client_last_seen": _normalize_one_line(state.get("client_last_seen", ""), ""),
        "request_pending": request_pending,
        "context_release_allowed": context_release_allowed,
        "requested_at": _normalize_one_line(state.get("requested_at", ""), ""),
        "requested_by": _normalize_one_line(state.get("requested_by", ""), ""),
        "request_reason": _normalize_one_line(state.get("request_reason", ""), ""),
        "authorized_at": _normalize_one_line(state.get("authorized_at", ""), ""),
        "authorized_by": _normalize_one_line(state.get("authorized_by", ""), ""),
        "revoked_at": _normalize_one_line(state.get("revoked_at", ""), ""),
        "revoked_by": _normalize_one_line(state.get("revoked_by", ""), ""),
        "last_event_at": _normalize_one_line(state.get("last_event_at", ""), ""),
        "note": note_map.get(status, note_map[MCP_AUTH_STATUS_IDLE]),
        "discovery_available": True,
        "resource_access_mode": "read_only_authorized" if context_release_allowed else "gated",
        "healthy_but_gated": healthy_but_gated,
        "expected_gated_http_status": 403,
        "authorization_scope": "server_session",
        "authorization_resets_on_session_reset": True,
        "local_reasoning_status": local_reasoning_status,
        "github_status": github_status,
        "domain_nodes": domain_nodes,
    }
    return payload


def _mcp_mark_request_pending(requested_by, request_reason):
    now = _now_iso()
    with MCP_AUTH_LOCK:
        MCP_AUTH_STATE["status"] = MCP_AUTH_STATUS_PENDING
        MCP_AUTH_STATE["requested_at"] = now
        MCP_AUTH_STATE["requested_by"] = _normalize_one_line(requested_by, "External Tool")
        MCP_AUTH_STATE["request_reason"] = _normalize_one_line(
            request_reason, "External tool requested design interview context."
        )
        MCP_AUTH_STATE["last_event_at"] = now
    return _mcp_status_payload()


def _mcp_authorize_design_interview(actor):
    now = _now_iso()
    with MCP_AUTH_LOCK:
        MCP_AUTH_STATE["status"] = MCP_AUTH_STATUS_AUTHORIZED
        MCP_AUTH_STATE["authorized_at"] = now
        MCP_AUTH_STATE["authorized_by"] = _normalize_one_line(actor, "Dashboard Human")
        MCP_AUTH_STATE["last_event_at"] = now
    return _mcp_status_payload()


def _mcp_revoke_design_interview(actor):
    now = _now_iso()
    with MCP_AUTH_LOCK:
        MCP_AUTH_STATE["status"] = MCP_AUTH_STATUS_REVOKED
        MCP_AUTH_STATE["revoked_at"] = now
        MCP_AUTH_STATE["revoked_by"] = _normalize_one_line(actor, "Dashboard Human")
        MCP_AUTH_STATE["last_event_at"] = now
    return _mcp_status_payload()


def _mcp_heartbeat():
    now = _now_iso()
    with MCP_AUTH_LOCK:
        MCP_AUTH_STATE["client_connected"] = True
        MCP_AUTH_STATE["client_last_seen"] = now
        MCP_AUTH_STATE["last_event_at"] = now
    return _mcp_status_payload()


def _mcp_reset_session():
    with MCP_AUTH_LOCK:
        MCP_AUTH_STATE["status"] = MCP_AUTH_STATUS_IDLE
        MCP_AUTH_STATE["session_id"] = f"mcp-{uuid.uuid4().hex[:10]}"
        MCP_AUTH_STATE["requested_at"] = ""
        MCP_AUTH_STATE["requested_by"] = ""
        MCP_AUTH_STATE["request_reason"] = ""
        MCP_AUTH_STATE["authorized_at"] = ""
        MCP_AUTH_STATE["authorized_by"] = ""
        MCP_AUTH_STATE["revoked_at"] = ""
        MCP_AUTH_STATE["revoked_by"] = ""
        MCP_AUTH_STATE["last_event_at"] = ""
        MCP_AUTH_STATE["client_connected"] = False
        MCP_AUTH_STATE["client_last_seen"] = ""
    return _mcp_status_payload()


def _parse_md_proposals_with_spans(text):
    proposals = []
    pattern = re.compile(r"(^## MD_PROPOSAL\n(?:.*?)(?=^## |\Z))", flags=re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(text):
        block = match.group(1).rstrip()
        fields = {}
        for field_match in re.finditer(r"^- ([a-z_]+):[ \t]*(.*)$", block, flags=re.MULTILINE):
            fields[field_match.group(1)] = field_match.group(2).strip()
        proposal_id = fields.get("proposal_id", "").strip()
        if not proposal_id:
            continue
        timestamp = fields.get("timestamp", "") or _now_iso()
        status = fields.get("status", "PENDING") or "PENDING"
        proposals.append(
            {
                "proposal_id": proposal_id,
                "timestamp": timestamp,
                "status": status,
                "managing_director": fields.get("managing_director", ""),
                "feature_slice": fields.get("feature_slice", ""),
                "done_summary": fields.get("done_summary", ""),
                "friction_removed": fields.get("friction_removed", ""),
                "creativity_added": fields.get("creativity_added", ""),
                "integration_suggestion": fields.get("integration_suggestion", ""),
                "harmonized_summary": fields.get("harmonized_summary", ""),
                "review_action": fields.get("review_action", ""),
                "reviewed_by": fields.get("reviewed_by", ""),
                "reviewed_at": fields.get("reviewed_at", ""),
                "review_notes": fields.get("review_notes", ""),
                "_span": (match.start(1), match.end(1)),
                "_block": block,
            }
        )
    return proposals


def _next_md_proposal_id(existing):
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    prefix = f"MDP-{stamp}-"
    count = sum(1 for item in existing if str(item.get("proposal_id", "")).startswith(prefix)) + 1
    return f"{prefix}{count:02d}"


def _proposal_to_payload(item):
    return {
        "proposal_id": item.get("proposal_id", ""),
        "timestamp": item.get("timestamp", ""),
        "status": item.get("status", ""),
        "managing_director": item.get("managing_director", ""),
        "feature_slice": item.get("feature_slice", ""),
        "done_summary": item.get("done_summary", ""),
        "friction_removed": item.get("friction_removed", ""),
        "creativity_added": item.get("creativity_added", ""),
        "integration_suggestion": item.get("integration_suggestion", ""),
        "harmonized_summary": item.get("harmonized_summary", ""),
        "review_action": item.get("review_action", ""),
        "reviewed_by": item.get("reviewed_by", ""),
        "reviewed_at": item.get("reviewed_at", ""),
        "review_notes": item.get("review_notes", ""),
    }


def _parse_design_proposals(text):
    proposals = []
    pattern = re.compile(r"(^## DESIGN_PROPOSAL\n(?:.*?)(?=^## |\Z))", flags=re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(text or ""):
        block = match.group(1).rstrip()
        fields = {}
        for field_match in re.finditer(r"^- ([a-z_]+):[ \t]*(.*)$", block, flags=re.MULTILINE):
            fields[field_match.group(1)] = field_match.group(2).strip()
        proposal_id = _normalize_one_line(fields.get("proposal_id", ""), "")
        if not proposal_id:
            continue
        proposals.append(
            {
                "proposal_id": proposal_id,
                "source_tool": _normalize_one_line(fields.get("source_tool", ""), "External Tool"),
                "session_id": _normalize_one_line(fields.get("session_id", ""), ""),
                "status": _normalize_one_line(fields.get("status", ""), "HARMONIZATION_PENDING"),
                "timestamp": _normalize_one_line(fields.get("timestamp", ""), ""),
                "summary": _normalize_one_line(fields.get("summary", ""), ""),
                "target_files": _normalize_one_line(fields.get("target_files", ""), ""),
                "design_payload_excerpt": _normalize_one_line(fields.get("design_payload_excerpt", ""), ""),
                "persona_alignment_hint": _normalize_one_line(fields.get("persona_alignment_hint", ""), ""),
                "worth_and_value": _normalize_one_line(fields.get("worth_and_value", ""), "PENDING"),
            }
        )
    for item in proposals:
        metrics = _extract_latest_design_assessment_metrics(item.get("worth_and_value", ""))
        item["worth_assessment"] = metrics.get("worth_assessment", "")
        item["value_score"] = metrics.get("value_score")
        item["md_recommendation"] = metrics.get("md_recommendation", "")
        item["persona_alignment"] = metrics.get("persona_alignment", "") or _normalize_one_line(item.get("persona_alignment_hint", ""), "")
        item["surgical_impact"] = metrics.get("surgical_impact", "")
        item["calmness_score"] = metrics.get("calmness_score")
        item["persona_layer"] = metrics.get("persona_layer", "")
    return proposals


def _next_design_proposal_id(existing):
    highest = 0
    for item in existing:
        pid = _normalize_one_line(item.get("proposal_id", ""), "")
        match = re.match(r"^P-(\d+)$", pid)
        if not match:
            continue
        try:
            highest = max(highest, int(match.group(1)))
        except ValueError:
            continue
    return f"P-{highest + 1:03d}"


def _build_github_issue_payload(item):
    status = str(item.get("status", "")).upper()
    if status not in {"READY_FOR_OAC", "ASSESSED"}:
        return None

    proposal_id = _normalize_one_line(item.get("proposal_id", ""), "").upper()
    summary = _normalize_one_line(item.get("summary", ""), "")
    worth_assessment = _normalize_one_line(item.get("worth_assessment", ""), "")
    calmness_score = item.get("calmness_score")
    target_files = _normalize_one_line(item.get("target_files", ""), "")

    next_step = _build_low_adventure_next_step(target_files, summary)

    title = f"Mission: {summary} [{proposal_id}]"
    body = [
        f"## Proposal ID: {proposal_id}",
        "",
        "### Summary",
        summary,
        "",
        "### MD Worth & Value Assessment",
        worth_assessment or "Pending assessment.",
        "",
        f"### Calmness Score: {calmness_score or 'Pending'}/10",
        "",
        "### Suggested Next Step",
        next_step,
        "",
        "---",
        "Logged via G-Codex Dashboard (Phase 14).",
    ]

    return {
        "title": title,
        "body": "\n".join(body).strip(),
        "labels": "low-adventure,md-proposal",
    }


def _design_proposal_to_payload(item):
    payload = {
        "proposal_id": item.get("proposal_id", ""),
        "source_tool": item.get("source_tool", ""),
        "session_id": item.get("session_id", ""),
        "status": item.get("status", ""),
        "timestamp": item.get("timestamp", ""),
        "summary": item.get("summary", ""),
        "target_files": item.get("target_files", ""),
        "design_payload_excerpt": item.get("design_payload_excerpt", ""),
        "persona_alignment_hint": item.get("persona_alignment_hint", ""),
        "worth_and_value": item.get("worth_and_value", "PENDING"),
        "worth_assessment": item.get("worth_assessment", ""),
        "value_score": item.get("value_score"),
        "md_recommendation": item.get("md_recommendation", ""),
        "persona_alignment": item.get("persona_alignment", ""),
        "surgical_impact": item.get("surgical_impact", ""),
        "calmness_score": item.get("calmness_score"),
        "persona_layer": item.get("persona_layer", ""),
    }
    payload["github_issue_payload"] = _build_github_issue_payload(payload)
    payload["github_issue_ready"] = bool(payload["github_issue_payload"])
    return payload


def _extract_design_assessment_from_text(text):
    raw = str(text or "").strip()
    if not raw:
        return {}

    has_assessment_report = bool(re.search(r"\bASSESSMENT_REPORT\b", raw, flags=re.IGNORECASE))
    proposal_match = re.search(r"(?:DESIGN_PROPOSAL_ID|PROPOSAL_ID)\s*:\s*(P-\d+)", raw, flags=re.IGNORECASE)
    if not proposal_match:
        proposal_match = re.search(r"\b(P-\d{1,6})\b", raw, flags=re.IGNORECASE)
    worth_match = re.search(
        r"WORTH_ASSESSMENT\s*:\s*(.+?)(?=\s+(?:VALUE_SCORE|MD_RECOMMENDATION|STATUS_RECOMMENDATION|DESIGN_PROPOSAL_ID|PROPOSAL_ID)\s*:|$)",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    value_match = re.search(r"VALUE_SCORE\s*:\s*(10|[1-9])(?:\s*/\s*10)?", raw, flags=re.IGNORECASE)
    recommendation_match = re.search(
        r"MD_RECOMMENDATION\s*:\s*(HARMONIZE|REJECT|INTERVIEW_USER)",
        raw,
        flags=re.IGNORECASE,
    )

    recommendation = _normalize_one_line(recommendation_match.group(1), "").upper() if recommendation_match else ""
    if not recommendation and value_match:
        recommendation = "HARMONIZE" if int(value_match.group(1)) >= 8 else "INTERVIEW_USER"

    return {
        "has_assessment_report": has_assessment_report,
        "proposal_id": _normalize_one_line(proposal_match.group(1), "").upper() if proposal_match else "",
        "worth_assessment": _compact_excerpt(_normalize_one_line(worth_match.group(1), ""), limit=320) if worth_match else "",
        "value_score": int(value_match.group(1)) if value_match else None,
        "md_recommendation": recommendation,
    }


def _format_design_assessment_entry(
    worth_assessment="",
    value_score=None,
    md_recommendation="",
    timestamp="",
    persona_alignment="LOW [none]",
    persona_layer="fallback_scan",
    surgical_impact="MEDIUM",
    calmness_score=7,
):
    worth_text = _compact_excerpt(_normalize_one_line(worth_assessment, ""), limit=320)
    if value_score is None:
        return ""
    score = max(1, min(10, int(value_score)))
    recommendation = _normalize_one_line(md_recommendation, "INTERVIEW_USER").upper()
    if recommendation not in {"HARMONIZE", "REJECT", "INTERVIEW_USER"}:
        recommendation = "INTERVIEW_USER"
    ts = _normalize_one_line(timestamp, "") or _now_iso()
    surgical = _normalize_one_line(surgical_impact, "MEDIUM").upper()
    persona = _normalize_one_line(persona_alignment, "LOW [none]")
    layer = _normalize_one_line(persona_layer, "fallback_scan")
    calmness = max(1, min(10, int(calmness_score or 7)))
    return _compact_excerpt(
        (
            f"{ts} | WORTH_ASSESSMENT: {worth_text or '(none)'} | VALUE_SCORE: {score}/10 | "
            f"MD_RECOMMENDATION: {recommendation} | SURGICAL_IMPACT: {surgical} | "
            f"CALMNESS_SCORE: {calmness}/10 | PERSONA_ALIGNMENT: {persona} | PERSONA_LAYER: {layer}"
        ),
        limit=1200,
    )


def _update_design_proposal_assessment(proposal_id, worth_assessment="", value_score=None, md_recommendation="INTERVIEW_USER"):
    pid = _normalize_one_line(proposal_id, "").upper()
    if not pid:
        raise ValueError("proposal_id is required for design assessment")

    recommendation = _normalize_one_line(md_recommendation, "INTERVIEW_USER").upper()
    if recommendation not in {"HARMONIZE", "REJECT", "INTERVIEW_USER"}:
        recommendation = "INTERVIEW_USER"
    if value_score is None:
        raise ValueError("value_score is required for design assessment")

    _ensure_proposal_outcomes_file()
    text = PROPOSAL_OUTCOMES_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r"(^## DESIGN_PROPOSAL\n(?:.*?)(?=^## |\Z))", flags=re.MULTILINE | re.DOTALL)
    target_match = None
    for match in pattern.finditer(text):
        block = match.group(1)
        block_pid = _normalize_one_line(_block_field_value(block, "proposal_id"), "").upper()
        if block_pid == pid:
            target_match = match
            break

    if target_match is None:
        raise ValueError(f"design proposal {pid} not found")

    block = target_match.group(1)
    lines = block.splitlines()
    existing_status = _normalize_one_line(_block_field_value(block, "status"), "HARMONIZATION_PENDING").upper()
    existing_worth = _normalize_one_line(_block_field_value(block, "worth_and_value"), "PENDING")
    proposal_summary = _normalize_one_line(_block_field_value(block, "summary"), "")
    target_files = _normalize_one_line(_block_field_value(block, "target_files"), "")
    payload_excerpt = _normalize_one_line(_block_field_value(block, "design_payload_excerpt"), "")
    persona_hint = _normalize_one_line(_block_field_value(block, "persona_alignment_hint"), "")
    persona_alignment = _calculate_persona_alignment(
        [proposal_summary, target_files, payload_excerpt, worth_assessment, persona_hint]
    )
    persona_alignment_text = _normalize_one_line(persona_alignment.get("summary", ""), "LOW [none]")
    persona_layer = _normalize_one_line(persona_alignment.get("source", ""), "fallback_scan")
    surgical_impact = _derive_surgical_impact(value_score, recommendation)
    calmness_score = _derive_calmness_score([proposal_summary, target_files, payload_excerpt, worth_assessment], recommendation)
    assessment_entry = _format_design_assessment_entry(
        worth_assessment=worth_assessment,
        value_score=value_score,
        md_recommendation=recommendation,
        persona_alignment=persona_alignment_text,
        persona_layer=persona_layer,
        surgical_impact=surgical_impact,
        calmness_score=calmness_score,
    )

    if existing_worth.upper() in {"", "PENDING"}:
        worth_value = assessment_entry
    elif assessment_entry and assessment_entry not in existing_worth:
        worth_value = _compact_excerpt(f"{existing_worth} || {assessment_entry}", limit=1800)
    else:
        worth_value = existing_worth
    worth_value = worth_value or "PENDING"

    score = max(1, min(10, int(value_score)))
    if recommendation == "REJECT":
        next_status = "REJECTED"
    elif recommendation == "HARMONIZE" and score >= 8:
        next_status = "READY_FOR_OAC"
    else:
        next_status = "ASSESSED"

    updated_lines = []
    status_written = False
    worth_written = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- status:"):
            updated_lines.append(f"- status: {next_status}")
            status_written = True
            continue
        if stripped.startswith("- worth_and_value:"):
            updated_lines.append(f"- worth_and_value: {worth_value}")
            worth_written = True
            continue
        updated_lines.append(line)

    if not status_written:
        updated_lines.append(f"- status: {next_status}")
    if not worth_written:
        updated_lines.append(f"- worth_and_value: {worth_value}")

    updated_block = "\n".join(updated_lines).rstrip() + "\n"
    updated_text = text[: target_match.start()] + updated_block + text[target_match.end() :]
    PROPOSAL_OUTCOMES_PATH.write_text(updated_text, encoding="utf-8")
    return {
        "proposal_id": pid,
        "status": next_status,
        "worth_and_value": worth_value,
        "assessment_entry": assessment_entry,
        "md_recommendation": recommendation,
        "persona_alignment": persona_alignment_text,
        "persona_layer_source": persona_layer,
        "surgical_impact": surgical_impact,
        "calmness_score": calmness_score,
        "previous_status": existing_status,
        "previous_worth_and_value": existing_worth,
    }


def _apply_design_assessment_from_md(guidance_text, requested_proposal_id="", source="MD_GUIDANCE"):
    extracted = _extract_design_assessment_from_text(guidance_text)
    has_assessment_report = bool(extracted.get("has_assessment_report"))
    worth_assessment = _normalize_one_line(extracted.get("worth_assessment", ""), "")
    value_score = extracted.get("value_score")
    md_recommendation = _normalize_one_line(extracted.get("md_recommendation", ""), "").upper()
    if not worth_assessment and value_score is None and not md_recommendation:
        return {"updated": False, "reason": "no structured worth/value triggers detected"}
    if has_assessment_report and (not worth_assessment or value_score is None or md_recommendation not in {"HARMONIZE", "REJECT", "INTERVIEW_USER"}):
        return {"updated": False, "reason": "ASSESSMENT_REPORT is missing required fields"}
    if not md_recommendation:
        md_recommendation = "HARMONIZE" if value_score is not None and int(value_score) >= 8 else "INTERVIEW_USER"
    if value_score is None:
        return {"updated": False, "reason": "VALUE_SCORE is required for assessment update"}

    proposal_id = _normalize_one_line(requested_proposal_id, "").upper() or _normalize_one_line(extracted.get("proposal_id", ""), "").upper()
    if not proposal_id:
        return {"updated": False, "reason": "proposal id missing for structured assessment"}

    result = _update_design_proposal_assessment(
        proposal_id,
        worth_assessment=worth_assessment,
        value_score=value_score,
        md_recommendation=md_recommendation,
    )
    aga_audit_result = {}
    if str(result.get("status", "")).upper() in {"ASSESSED", "READY_FOR_OAC"}:
        aga_audit_result = _trigger_aga_audit(
            proposal_id,
            status=result.get("status", "ASSESSED"),
            source=source,
            persona_layer=result.get("persona_layer_source", "fallback_scan"),
            persona_alignment=result.get("persona_alignment", "LOW [none]"),
        )
    detail = (
        f"{result.get('proposal_id')}: status {result.get('previous_status')} -> {result.get('status')}; "
        f"md_recommendation={result.get('md_recommendation')}; "
        f"persona_alignment={result.get('persona_alignment')}; "
        f"persona_layer={result.get('persona_layer_source')}; "
        f"worth_and_value={result.get('worth_and_value')}"
    )
    _log_external_tool_injection(
        action_type="md_design_assessment",
        target=f"design_proposal:{proposal_id}",
        status=result.get("status", "ASSESSED"),
        detail=detail,
        source=source,
        authorized=True,
    )
    return {"updated": True, "aga_audit": aga_audit_result, **result}


def _build_oac_design_harmonize_directive(payload):
    bundle = _build_oac_design_harmonization_payload(payload)
    return str(bundle.get("directive", ""))


def _extract_primary_target_file(target_files):
    raw = _normalize_one_line(target_files, "")
    if not raw:
        return ""
    parts = [part.strip() for part in re.split(r"[,;]", raw) if part and part.strip()]
    for part in parts:
        lowered = part.lower()
        if lowered in {"(not specified)", "not specified", "(none)", "none"}:
            continue
        return part
    return ""


def _build_low_adventure_next_step(target_files, proposal_summary):
    primary_target = _extract_primary_target_file(target_files)
    if primary_target:
        return (
            f"Apply one deterministic edit in `{primary_target}`, then run "
            f"`git diff -- {primary_target}` to confirm scope before any broader change."
        )
    summary_hint = _compact_excerpt(_normalize_one_line(proposal_summary, ""), limit=96)
    if summary_hint:
        return (
            "Run one deterministic local check tied to this proposal summary, then take a single "
            f"surgical edit: \"{summary_hint}\"."
        )
    return "Run `git status --short`, then perform one targeted local verification before making any code edit."


def _build_oac_design_harmonization_payload(payload):
    item = payload if isinstance(payload, dict) else {}
    proposal_id = _normalize_one_line(item.get("proposal_id", ""), "").upper()
    if not proposal_id:
        raise ValueError("proposal_id is required")
    summary = _normalize_one_line(item.get("summary", ""), "(no summary provided)")
    target_files = _normalize_one_line(item.get("target_files", ""), "(not specified)")
    design_payload_excerpt = _normalize_one_line(item.get("design_payload_excerpt", ""), "(none provided)")
    status = _normalize_one_line(item.get("status", ""), "ASSESSED").upper()
    worth_and_value = _normalize_one_line(item.get("worth_and_value", ""), "")
    parsed = _extract_latest_design_assessment_metrics(worth_and_value)
    worth_assessment = _normalize_one_line(item.get("worth_assessment", ""), "") or parsed.get("worth_assessment", "")
    md_recommendation = _normalize_one_line(item.get("md_recommendation", ""), "").upper() or parsed.get("md_recommendation", "")
    persona_alignment = _normalize_one_line(item.get("persona_alignment", ""), "") or parsed.get("persona_alignment", "")
    surgical_impact = _normalize_one_line(item.get("surgical_impact", ""), "").upper() or parsed.get("surgical_impact", "")
    persona_layer = _normalize_one_line(item.get("persona_layer", ""), "") or parsed.get("persona_layer", "")
    value_score = item.get("value_score")
    if value_score in (None, ""):
        value_score = parsed.get("value_score")
    try:
        value_score_int = max(1, min(10, int(value_score))) if value_score is not None else None
    except (TypeError, ValueError):
        value_score_int = None
    calmness_score = item.get("calmness_score")
    if calmness_score in (None, ""):
        calmness_score = parsed.get("calmness_score")
    try:
        calmness_score_int = max(1, min(10, int(calmness_score))) if calmness_score is not None else None
    except (TypeError, ValueError):
        calmness_score_int = None

    value_line = f"{value_score_int}/10" if value_score_int is not None else "(not provided)"
    calmness_line = f"{calmness_score_int}/10" if calmness_score_int is not None else "(not provided)"
    recommendation_line = md_recommendation or "INTERVIEW_USER"
    surgical_line = surgical_impact or "MEDIUM"
    persona_line = persona_alignment or "LOW [none]"
    layer_line = persona_layer or "fallback_scan"
    worth_line = worth_assessment or "Assessment detail not provided. Use low-adventure review."
    next_step = _build_low_adventure_next_step(target_files, summary)
    commit_helper_note = "One-click commit helper remains conservative: local commit only (`push: false`)."

    directive = "\n".join(
        [
            "OAC HARMONIZATION DIRECTIVE",
            f"- Proposal ID: {proposal_id}",
            f"- Summary: {summary}",
            f"- Status Gate: {status}",
            f"- MD Worth & Value: {worth_line}",
            f"- MD Recommendation: {recommendation_line}",
            f"- Surgical Impact: {surgical_line}",
            f"- Calmness Score: {calmness_line}",
            f"- Persona Alignment: {persona_line} (layer: {layer_line})",
            f"- Value Score: {value_line}",
            f"- Target Files: {target_files}",
            f"- Design Payload Excerpt: {design_payload_excerpt}",
            f"- Suggested Low-Adventure Next Step: {next_step}",
            f"- Commit Helper: {commit_helper_note}",
            "",
            "Execution Plan (deterministic):",
            "1. Confirm current repo state and keep changes surgical.",
            "2. Execute only the suggested low-adventure next step above.",
            "3. Run one deterministic local verification step.",
            "4. Log outcome in G-Codex-brain before proposing harmonization.",
            "5. Keep commit local by default; push remains explicit and human-confirmed.",
        ]
    )
    return {
        "proposal_id": proposal_id,
        "summary": summary,
        "status": status,
        "md_recommendation": recommendation_line,
        "surgical_impact": surgical_line,
        "calmness_score": calmness_line,
        "value_score": value_line,
        "worth_assessment": worth_line,
        "persona_alignment": persona_line,
        "persona_layer": layer_line,
        "target_files": target_files,
        "design_payload_excerpt": design_payload_excerpt,
        "suggested_next_step": next_step,
        "commit_helper_note": commit_helper_note,
        "directive": directive,
    }


def _append_oac_harmonization_directive_block(bundle, initiated_by="Dashboard Human", action_mode="directive"):
    item = bundle if isinstance(bundle, dict) else {}
    block = "\n".join(
        [
            "## OAC_HARMONIZATION_DIRECTIVE",
            f"- timestamp: {_now_iso()}",
            f"- proposal_id: {_normalize_one_line(item.get('proposal_id', ''), 'UNKNOWN')}",
            f"- action_mode: {_normalize_one_line(action_mode, 'directive')}",
            f"- initiated_by: {_normalize_one_line(initiated_by, 'Dashboard Human')}",
            f"- status_gate: {_normalize_one_line(item.get('status', ''), 'ASSESSED')}",
            f"- md_recommendation: {_normalize_one_line(item.get('md_recommendation', ''), 'INTERVIEW_USER')}",
            f"- surgical_impact: {_normalize_one_line(item.get('surgical_impact', ''), 'MEDIUM')}",
            f"- calmness_score: {_normalize_one_line(item.get('calmness_score', ''), '(not provided)')}",
            f"- value_score: {_normalize_one_line(item.get('value_score', ''), '(not provided)')}",
            f"- worth_assessment: {_compact_excerpt(_normalize_one_line(item.get('worth_assessment', ''), '(none)'), limit=340)}",
            f"- summary: {_compact_excerpt(_normalize_one_line(item.get('summary', ''), '(none)'), limit=260)}",
            f"- target_files: {_normalize_one_line(item.get('target_files', ''), '(not specified)')}",
            f"- suggested_next_step: {_compact_excerpt(_normalize_one_line(item.get('suggested_next_step', ''), '(none)'), limit=320)}",
            "- directive:",
            "```text",
            str(item.get("directive", "")).strip() or "(directive unavailable)",
            "```",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)


def _ingest_design_proposal(payload):
    mcp_state = _mcp_status_payload()
    if str(mcp_state.get("status", "")).upper() != MCP_AUTH_STATUS_AUTHORIZED:
        raise PermissionError("403: MD Authorization Required")

    _ensure_proposal_outcomes_file()
    existing_text = PROPOSAL_OUTCOMES_PATH.read_text(encoding="utf-8")
    existing = _parse_design_proposals(existing_text)
    proposal_id = _next_design_proposal_id(existing)
    timestamp = _now_iso()

    source_tool = _normalize_one_line(payload.get("source_tool", ""), "Google Stitch")
    session_id = _normalize_one_line(payload.get("session_id", ""), "")
    summary = _normalize_one_line(payload.get("summary", payload.get("proposal_summary", "")), "")
    if not summary:
        raise ValueError("summary is required")

    raw_targets = payload.get("target_files", "")
    if isinstance(raw_targets, list):
        normalized_targets = [_normalize_one_line(item, "") for item in raw_targets]
        target_files = ", ".join([item for item in normalized_targets if item])
    else:
        target_files = _normalize_one_line(raw_targets, "")
    target_files = target_files or "(not specified)"

    raw_excerpt = payload.get("design_payload_excerpt", payload.get("proposal_body", ""))
    design_payload_excerpt = _compact_excerpt(_normalize_one_line(raw_excerpt, "(none provided)"), limit=320)
    incoming_alignment = payload.get("persona_alignment", {})
    if isinstance(incoming_alignment, dict):
        incoming_label = _normalize_one_line(incoming_alignment.get("label", ""), "")
        incoming_nodes = ", ".join(
            [str(item).strip() for item in incoming_alignment.get("matched_nodes", []) if str(item).strip()]
        )
        incoming_source = _normalize_one_line(incoming_alignment.get("source", ""), "")
        persona_alignment_hint = _normalize_one_line(
            f"{incoming_label} [{incoming_nodes or 'none'}] ({incoming_source or 'unknown'})", ""
        )
    else:
        persona_alignment_hint = ""
    if not persona_alignment_hint:
        inferred_alignment = _calculate_persona_alignment([summary, target_files, design_payload_excerpt])
        persona_alignment_hint = _normalize_one_line(
            f"{inferred_alignment.get('summary', 'LOW [none]')} ({inferred_alignment.get('source', 'fallback_scan')})",
            "LOW [none] (fallback_scan)",
        )
    status = "HARMONIZATION_PENDING"
    worth_and_value = "PENDING"

    block = "\n".join(
        [
            "## DESIGN_PROPOSAL",
            f"- proposal_id: {proposal_id}",
            f"- source_tool: {source_tool}",
            f"- session_id: {session_id}",
            f"- status: {status}",
            f"- timestamp: {timestamp}",
            f"- summary: {summary}",
            f"- target_files: {target_files}",
            f"- design_payload_excerpt: {design_payload_excerpt}",
            f"- persona_alignment_hint: {persona_alignment_hint}",
            f"- worth_and_value: {worth_and_value}",
            "",
        ]
    )
    with PROPOSAL_OUTCOMES_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n" + block)

    return {
        "proposal_id": proposal_id,
        "source_tool": source_tool,
        "session_id": session_id,
        "status": status,
        "timestamp": timestamp,
        "summary": summary,
        "target_files": target_files,
        "design_payload_excerpt": design_payload_excerpt,
        "persona_alignment_hint": persona_alignment_hint,
        "worth_and_value": worth_and_value,
        "message": f"Proposal [{proposal_id}] received and queued for MD review in PROPOSAL_OUTCOMES.md.",
    }



def _append_proposal_outcome_row(item, reviewer, outcome, notes):
    _ensure_proposal_outcomes_file()
    ts = _now_iso()
    proposal_id = _normalize_one_line(item.get("proposal_id", ""), "UNKNOWN")
    director = _normalize_one_line(item.get("managing_director", ""), "UNKNOWN")
    feature_slice = _normalize_one_line(item.get("feature_slice", ""), "(not specified)")
    reviewer_name = _normalize_one_line(reviewer, "Lead Executor")
    note_text = _normalize_one_line(notes, "-")

    existing = PROPOSAL_OUTCOMES_PATH.read_text(encoding="utf-8")
    if proposal_id != "UNKNOWN" and f"| {proposal_id} |" in existing:
        return False

    row = f"| {ts} | {proposal_id} | {director} | {feature_slice} | {outcome} | {reviewer_name} | {note_text} |"
    with PROPOSAL_OUTCOMES_PATH.open("a", encoding="utf-8") as handle:
        handle.write(row + "\n")
    return True


def _append_harmonized_proposal_entry(item, reviewer, notes):
    proposal_id = _normalize_one_line(item.get("proposal_id", ""), "")
    if not proposal_id:
        return False

    path = _dynamic_memory_path()
    current = path.read_text(encoding="utf-8")
    block_pattern = re.compile(r"(^## MD_HARMONIZED_ENTRY\n(?:.*?)(?=^## |\Z))", flags=re.MULTILINE | re.DOTALL)
    for match in block_pattern.finditer(current):
        block = match.group(1)
        if re.search(rf"^- proposal_id:\s*{re.escape(proposal_id)}$", block, flags=re.MULTILINE):
            return False

    timestamp = _now_iso()
    reviewer_name = _normalize_one_line(reviewer, "Lead Executor")
    note_text = _normalize_one_line(notes, "-")
    feature_slice = _normalize_one_line(item.get("feature_slice", ""), "(not specified)")
    director = _normalize_one_line(item.get("managing_director", ""), "UNKNOWN")
    done_summary = _normalize_one_line(item.get("done_summary", ""), "(none provided)")
    integration_suggestion = _normalize_one_line(item.get("integration_suggestion", ""), "(none provided)")
    harmonized_summary = _normalize_one_line(item.get("harmonized_summary", ""), "")

    block = "\n".join(
        [
            "## MD_HARMONIZED_ENTRY",
            f"- timestamp: {timestamp}",
            f"- proposal_id: {proposal_id}",
            f"- managing_director: {director}",
            f"- feature_slice: {feature_slice}",
            f"- harmonized_by: {reviewer_name}",
            "- accepted_status: ACCEPTED",
            f"- harmonized_summary: {harmonized_summary or done_summary}",
            f"- integration_summary: {done_summary}",
            f"- integration_suggestion: {integration_suggestion}",
            f"- harmonized_notes: {note_text}",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)
    return True


def _build_proposal_patterns(limit=3):
    _ensure_proposal_outcomes_file()
    lines = PROPOSAL_OUTCOMES_PATH.read_text(encoding="utf-8").splitlines()
    rows = [line for line in lines if line.startswith("|") and "---" not in line]
    agent_counts = {}
    for row in rows:
        parts = [part.strip() for part in row.strip("|").split("|")]
        if len(parts) < 7:
            continue
        outcome = parts[4]
        director = parts[2]
        if outcome != "ACCEPTED":
            continue
        agent_counts[director] = agent_counts.get(director, 0) + 1
    ordered = sorted(agent_counts.items(), key=lambda pair: pair[1], reverse=True)
    hints = [f"{agent}: {count} accepted proposal(s)" for agent, count in ordered[:limit]]
    if not hints:
        hints = ["No accepted proposal patterns yet. Accept a proposal to start the learning loop."]
    return hints


def _build_low_adventure_slice_suggestion(item):
    feature = _normalize_one_line(item.get("feature_slice", ""), "recent proposal slice")
    friction = _normalize_one_line(item.get("friction_removed", ""), "")
    creativity = _normalize_one_line(item.get("creativity_added", ""), "")

    if friction and friction.lower() not in {"(none provided)", "none", "-"}:
        return (
            f"Low-adventure follow-up: add one focused regression check for '{feature}' to guard against "
            f"'{friction}'."
        )
    if creativity and creativity.lower() not in {"(none provided)", "none", "-"}:
        return (
            f"Low-adventure follow-up: add one concise doc/example update to make '{creativity}' repeatable in "
            f"'{feature}'."
        )
    return f"Low-adventure follow-up: add one deterministic smoke check for '{feature}' and log the outcome."


def _short_commit_slice_title(feature_slice, fallback="harmonized slice", max_len=72):
    raw = _normalize_one_line(feature_slice, fallback)
    cleaned = re.sub(r"[\r\n\t]+", " ", raw).strip(" -_.")
    if not cleaned:
        cleaned = fallback
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _build_md_harmonized_summary(item, review_notes):
    proposal_id = _normalize_one_line(item.get("proposal_id", ""), "proposal")
    feature_slice = _short_commit_slice_title(item.get("feature_slice", "harmonized slice"), max_len=64)
    done_summary = _normalize_one_line(item.get("done_summary", ""), "")
    friction = _normalize_one_line(item.get("friction_removed", ""), "")
    notes = _normalize_one_line(review_notes, "")
    done_clean = done_summary.rstrip(" .;:")
    friction_clean = friction.rstrip(" .;:")

    base_parts = [f"MD harmonized {proposal_id}: {feature_slice}."]
    if done_clean and done_clean.lower() not in {"(summary not provided)", "(none provided)", "none", "-"}:
        base_parts.append(f"Outcome: {_compact_excerpt(done_clean, limit=90)}.")
    if friction_clean and friction_clean.lower() not in {"(none provided)", "none", "-"}:
        base_parts.append(f"Safeguard: {_compact_excerpt(friction_clean, limit=70)}.")

    relevance_query = " ".join([feature_slice, done_clean, friction_clean, notes]).strip()
    cli_events = _recent_cli_output_events(limit=4)
    cli_match = _select_relevant_cli_context(
        latest_human=relevance_query,
        focus="report",
        cli_events=cli_events,
    )
    include_cli = False
    if cli_match:
        event = cli_match.get("event", {}) if isinstance(cli_match.get("event"), dict) else {}
        return_code = event.get("return_code")
        relevance_lower = relevance_query.lower()
        include_cli = bool(
            return_code not in {None, 0}
            or any(token in relevance_lower for token in ("test", "verify", "regression", "error", "failure", "cli", "terminal", "log"))
        )
        if include_cli:
            base_parts.append(f"CLI context: {cli_match.get('summary_line', '')}.")

    summary = _compact_excerpt(" ".join(part for part in base_parts if part).strip(), limit=180)
    if not summary:
        summary = "MD harmonized proposal with a calm low-adventure integration step."
    return summary


def _build_harmonized_commit_metadata(item, review_notes):
    proposal_id = _normalize_one_line(item.get("proposal_id", ""), "")
    feature_slice = _short_commit_slice_title(item.get("feature_slice", "harmonized slice"))
    done_summary = _normalize_one_line(item.get("done_summary", ""), "(summary not provided)")
    friction = _normalize_one_line(item.get("friction_removed", ""), "(none provided)")
    creativity = _normalize_one_line(item.get("creativity_added", ""), "(none provided)")
    notes = _normalize_one_line(review_notes, "-")
    md_summary = _build_md_harmonized_summary(item, review_notes)

    title = f"feat: harmonize MD proposal {proposal_id} — {feature_slice}"
    body_lines = [
        f"Proposal-ID: {proposal_id}",
        f"Harmonization-Summary: {md_summary}",
        f"Harmonization-Detail: {done_summary}",
        f"Friction-Removed: {friction}",
        f"Creativity-Added: {creativity}",
        f"Review-Notes: {notes}",
        f"Changelog: {CHANGELOG_PATH.relative_to(ROOT)}",
    ]
    body = "\n".join(body_lines)
    command = (
        f"./scripts/conductor.sh git-safe-commit {shlex.quote(title)} "
        f"--proposal-id {shlex.quote(proposal_id)} "
        f"--summary {shlex.quote(md_summary)} "
        "--auto-stage-safe"
    )
    return {
        "title": title,
        "body": body,
        "command": command,
        "md_harmonized_summary": md_summary,
    }


def _extract_harmonization_summary(commit_body):
    text = str(commit_body or "")
    for line in text.splitlines():
        if line.startswith("Harmonization-Summary:"):
            return _normalize_one_line(line.split(":", 1)[1], "")
    return ""


def _is_accepted_proposal(proposal_id):
    pid = _normalize_one_line(proposal_id, "")
    if not pid:
        return False
    text = _dynamic_memory_path().read_text(encoding="utf-8")
    for item in _parse_md_proposals_with_spans(text):
        if _normalize_one_line(item.get("proposal_id", ""), "") != pid:
            continue
        return _normalize_one_line(item.get("status", ""), "").upper() == "ACCEPTED"
    return False


def _run_command_capture(command, timeout_sec=600):
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )
    output = "\n".join(
        [
            str(result.stdout or "").strip(),
            str(result.stderr or "").strip(),
        ]
    ).strip()
    return {
        "returncode": result.returncode,
        "output": output,
    }


class GitWorkflowError(Exception):
    def __init__(self, message, phase="commit", output="", snapshot_created=False):
        super().__init__(message)
        self.phase = phase
        self.output = output
        self.snapshot_created = snapshot_created


def _run_git_commit_push(payload):
    description = _normalize_one_line(payload.get("description", ""), "")
    proposal_id = _normalize_one_line(payload.get("proposal_id", ""), "")
    summary = _normalize_one_line(payload.get("summary", ""), "")
    branch_name = _normalize_one_line(payload.get("branch", ""), "")
    push_after_commit = _to_bool(payload.get("push", False), default=False)
    reviewed_by = _normalize_one_line(payload.get("reviewed_by", ""), "Lead Executor")
    auto_stage_safe = _to_bool(payload.get("auto_stage_safe", True), default=True)
    major_change = _to_bool(payload.get("major_change", False), default=False)

    if not description:
        raise ValueError("description is required")
    if not CONDUCTOR.exists():
        raise ValueError(f"missing conductor script: {CONDUCTOR}")
    if MAJOR_CHANGE_HINT_RE.search(description or ""):
        major_change = True
    if major_change and not proposal_id:
        raise ValueError(
            "major repo-shaping commit requires accepted harmonization (proposal_id) before commit/push"
        )
    if proposal_id and not _is_accepted_proposal(proposal_id):
        raise ValueError(f"proposal must be ACCEPTED before commit & push: {proposal_id}")

    commit_command = [str(CONDUCTOR), "git-safe-commit", description]
    if proposal_id:
        commit_command.extend(["--proposal-id", proposal_id])
    if summary:
        commit_command.extend(["--summary", summary])
    if branch_name:
        commit_command.extend(["--branch", branch_name])
    if auto_stage_safe:
        commit_command.append("--auto-stage-safe")

    commit_result = _run_command_capture(commit_command, timeout_sec=900)
    commit_output = str(commit_result.get("output", ""))
    snapshot_created = "Safety snapshot created:" in commit_output
    if commit_result["returncode"] != 0:
        if snapshot_created:
            raise GitWorkflowError(
                "Snapshot created but commit failed — check console output.",
                phase="commit",
                output=commit_output,
                snapshot_created=True,
            )
        raise GitWorkflowError(
            "Commit failed before snapshot completion — check console output.",
            phase="commit",
            output=commit_output or f"exit code {commit_result['returncode']}",
            snapshot_created=False,
        )

    push_result = {"returncode": 0, "output": ""}
    if push_after_commit:
        push_command = [str(CONDUCTOR), "push"]
        push_result = _run_command_capture(push_command, timeout_sec=900)
        if push_result["returncode"] != 0:
            raise GitWorkflowError(
                "Commit completed but push failed — check remote/private configuration.",
                phase="push",
                output=str(push_result.get("output", "")) or f"exit code {push_result['returncode']}",
                snapshot_created=snapshot_created,
            )

    if proposal_id:
        action_label = "Committed and pushed" if push_after_commit else "Committed"
        _append_brain_changelog(
            what_changed=f"{action_label} harmonized MD proposal {proposal_id}.",
            agent=reviewed_by,
            why=(
                "Operator confirmed one-click safety flow to snapshot, commit, and sync private/main."
                if push_after_commit
                else "Operator confirmed one-click safety flow to snapshot and commit harmonized proposal locally."
            ),
        )

    head_sha = ""
    try:
        head_sha = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        head_sha = ""

    return {
        "proposal_id": proposal_id,
        "description": description,
        "summary": summary,
        "branch": branch_name,
        "head_sha": head_sha,
        "snapshot_created": snapshot_created,
        "commit_output": commit_output,
        "push_output": push_result["output"],
        "pushed": bool(push_after_commit),
    }


def _create_md_assignment(payload):
    timestamp = _now_iso()
    managing_director = _normalize_one_line(payload.get("managing_director", ""))
    feature_slice = _normalize_one_line(payload.get("feature_slice", ""))
    assigned_by = _normalize_one_line(payload.get("assigned_by", "Lead Executor"), "Lead Executor")
    sandbox_proposal = _to_bool(payload.get("sandbox_proposal", True), default=True)
    if not managing_director:
        raise ValueError("managing_director is required")
    if not feature_slice:
        raise ValueError("feature_slice is required")

    isolation_note = (
        "Working in isolated sandbox proposal mode before main-brain harmonization."
        if sandbox_proposal
        else "Working in isolated proposal mode before main-brain harmonization."
    )

    block = "\n".join(
        [
            "## MD_ASSIGNMENT",
            f"- timestamp: {timestamp}",
            f"- managing_director: {managing_director}",
            f"- feature_slice: {feature_slice}",
            f"- assigned_by: {assigned_by}",
            f"- sandbox_proposal: {'true' if sandbox_proposal else 'false'}",
            "- status: ACTIVE",
            f"- isolation_note: {isolation_note}",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)
    return {
        "timestamp": timestamp,
        "managing_director": managing_director,
        "feature_slice": feature_slice,
        "assigned_by": assigned_by,
        "sandbox_proposal": sandbox_proposal,
    }


def _create_md_proposal(payload):
    timestamp = _now_iso()
    path = _dynamic_memory_path()
    text = path.read_text(encoding="utf-8")
    existing = _parse_md_proposals_with_spans(text)
    proposal_id = _next_md_proposal_id(existing)

    managing_director = _normalize_one_line(payload.get("managing_director", ""))
    feature_slice = _normalize_one_line(payload.get("feature_slice", ""))
    done_summary = _normalize_one_line(payload.get("done_summary", ""))
    friction_removed = _normalize_one_line(payload.get("friction_removed", ""))
    creativity_added = _normalize_one_line(payload.get("creativity_added", ""))
    integration_suggestion = _normalize_one_line(payload.get("integration_suggestion", ""))

    if not managing_director:
        raise ValueError("managing_director is required")
    if not feature_slice:
        raise ValueError("feature_slice is required")
    if not done_summary:
        raise ValueError("done_summary is required")

    block = "\n".join(
        [
            "## MD_PROPOSAL",
            f"- proposal_id: {proposal_id}",
            f"- timestamp: {timestamp}",
            "- status: PENDING",
            f"- managing_director: {managing_director}",
            f"- feature_slice: {feature_slice}",
            f"- done_summary: {done_summary}",
            f"- friction_removed: {friction_removed or '(none provided)'}",
            f"- creativity_added: {creativity_added or '(none provided)'}",
            f"- integration_suggestion: {integration_suggestion or '(none provided)'}",
            "- harmonized_summary:",
            f"- repo: {ROOT.name}",
            "- review_action:",
            "- reviewed_by:",
            "- reviewed_at:",
            "- review_notes:",
            "",
        ]
    )
    _append_dynamic_memory_entry(block)

    return {
        "proposal_id": proposal_id,
        "timestamp": timestamp,
        "status": "PENDING",
        "managing_director": managing_director,
        "feature_slice": feature_slice,
        "done_summary": done_summary,
        "friction_removed": friction_removed,
        "creativity_added": creativity_added,
        "integration_suggestion": integration_suggestion,
        "harmonized_summary": "",
        "review_action": "",
        "reviewed_by": "",
        "reviewed_at": "",
        "review_notes": "",
    }
def _review_md_proposal(payload):
    proposal_id = _normalize_one_line(payload.get("proposal_id", ""))
    decision = _normalize_one_line(payload.get("decision", "")).lower()
    notes = _normalize_one_line(payload.get("notes", ""), "-")
    reviewer = _normalize_one_line(payload.get("reviewed_by", ""), "Lead Executor")

    if not proposal_id:
        raise ValueError("proposal_id is required")

    decision_map = {
        "accept": "ACCEPTED",
        "reject": "REJECTED",
        "refine": "REFINE_REQUESTED",
    }
    if decision not in decision_map:
        raise ValueError("decision must be one of: accept, reject, refine")

    path = _dynamic_memory_path()
    text = path.read_text(encoding="utf-8")
    proposals = _parse_md_proposals_with_spans(text)
    target = None
    for item in proposals:
        if item.get("proposal_id") == proposal_id:
            target = item
            break
    if not target:
        raise ValueError(f"proposal not found: {proposal_id}")

    reviewed_at = _now_iso()
    status_value = decision_map[decision]
    harmonized_summary_for_block = ""
    if status_value == "ACCEPTED":
        _create_brain_snapshot(
            reason=f"Pre-harmonization snapshot for accepted proposal {proposal_id}.",
            actor=reviewer,
        )
        harmonized_summary_for_block = _build_md_harmonized_summary(dict(target), notes)

    def set_field(block_text, key, value):
        pattern = re.compile(rf"^- {re.escape(key)}:\s*.*$", flags=re.MULTILINE)
        line = f"- {key}: {value}"
        if pattern.search(block_text):
            return pattern.sub(line, block_text)
        return block_text + "\n" + line

    updated_block = target["_block"]
    updated_block = set_field(updated_block, "status", status_value)
    updated_block = set_field(updated_block, "review_action", decision.upper())
    updated_block = set_field(updated_block, "reviewed_by", reviewer)
    updated_block = set_field(updated_block, "reviewed_at", reviewed_at)
    updated_block = set_field(updated_block, "review_notes", notes)
    updated_block = set_field(updated_block, "harmonized_summary", harmonized_summary_for_block)

    start, end = target["_span"]
    updated_text = text[:start] + updated_block + text[end:]
    path.write_text(updated_text, encoding="utf-8")

    refreshed = _parse_md_proposals_with_spans(updated_text)
    final_item = None
    for item in refreshed:
        if item.get("proposal_id") == proposal_id:
            final_item = item
            break

    next_slice_suggestion = ""
    harmonized_commit = {}
    if final_item and status_value == "ACCEPTED":
        harmonized_item = dict(final_item)
        harmonized_summary = _normalize_one_line(
            harmonized_item.get("harmonized_summary", ""),
            "",
        ) or _build_md_harmonized_summary(harmonized_item, notes)
        harmonized_item["harmonized_summary"] = harmonized_summary
        _append_proposal_outcome_row(harmonized_item, reviewer, "ACCEPTED", notes)
        _append_harmonized_proposal_entry(harmonized_item, reviewer, notes)
        feature_slice = _normalize_one_line(final_item.get("feature_slice", ""), "(not specified)")
        friction = _normalize_one_line(final_item.get("friction_removed", ""), "(none provided)")
        creativity = _normalize_one_line(final_item.get("creativity_added", ""), "(none provided)")
        _append_brain_changelog(
            what_changed=f"Harmonized accepted MD proposal {proposal_id}: {feature_slice}.",
            agent=reviewer,
            why=f"Supportive merge: friction removed '{friction}', creativity added '{creativity}'.",
        )
        next_slice_suggestion = _build_low_adventure_slice_suggestion(final_item)
        harmonized_commit = _build_harmonized_commit_metadata(harmonized_item, notes)

    return {
        "proposal": _proposal_to_payload(final_item or target),
        "next_slice_suggestion": next_slice_suggestion,
        "harmonized_commit": harmonized_commit,
    }


def _list_md_proposals():
    path = _dynamic_memory_path()
    text = path.read_text(encoding="utf-8")
    proposals = _parse_md_proposals_with_spans(text)
    for item in proposals:
        item.pop("_span", None)
        item.pop("_block", None)
    proposals.sort(key=lambda item: _to_epoch(item.get("timestamp", "")), reverse=True)
    pending = [item for item in proposals if item.get("status") in {"PENDING", "REFINE_REQUESTED"}]
    _ensure_proposal_outcomes_file()
    proposal_outcomes_text = PROPOSAL_OUTCOMES_PATH.read_text(encoding="utf-8")
    design_items = _parse_design_proposals(proposal_outcomes_text)
    design_items.sort(key=lambda item: _to_epoch(item.get("timestamp", "")), reverse=True)
    design_pending = [
        item
        for item in design_items
        if str(item.get("status", "")).upper() in {"HARMONIZATION_PENDING", "ASSESSED", "READY_FOR_OAC", "REJECTED"}
    ]
    return {
        "pending": [_proposal_to_payload(item) for item in pending],
        "recent": [_proposal_to_payload(item) for item in proposals[:12]],
        "design_pending": [_design_proposal_to_payload(item) for item in design_pending[:20]],
        "patterns": _build_proposal_patterns(limit=3),
    }


def _write_clean_brain_state(reason="Manual clean-slate reset"):
    timestamp = _now_iso()
    short_date = timestamp.split("T", 1)[0]
    repo_name = ROOT.name
    truth_anchor = _truth_anchor_status()
    truth_anchor_line = (
        f"- Truth Anchor: `{truth_anchor['path']}` is canonical and present."
        if truth_anchor["exists"]
        else f"- {truth_anchor['warning']} Regenerate ingress/roadmap to restore canonical truth."
    )

    (BRAIN / "03_ACTIVE_NOW.md").write_text(
        "\n".join(
            [
                "# 03 ACTIVE NOW",
                "",
                "## Active State: Clean Bootstrap",
                "",
                f"- Repository: {repo_name}",
                "- Description: Bootstrapped with G-Codex living brain template.",
                "- Current Phase: Phase 0 — Fresh Bootstrap",
                "- Status: Clean slate initialized; no inherited template activity history.",
                truth_anchor_line,
                "",
                "## Immediate Next Steps",
                "",
                "1. Launch `./scripts/conductor.sh dashboard`.",
                "2. Start bridge watcher with `./scripts/conductor.sh watch start`.",
                "3. Review `G-Codex-brain/ROADMAP.md` before dispatching a slice.",
                "4. Dispatch your first low-adventure slice from Control Room.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (BRAIN / "MERGE_LOG.md").write_text(
        "\n".join(
            [
                "# MERGE LOG",
                "",
                "| Date | Description | Commit | Author |",
                "|---|---|---|---|",
                f"| {short_date} | {reason} for {repo_name} | local-bootstrap | scripts/bootstrap-brain.sh |",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (BRAIN / "DYNAMIC_MEMORY.md").write_text(
        "\n".join(
            [
                "# DYNAMIC MEMORY",
                "",
                "## SESSION_LOG_ENTRY",
                f"- timestamp: {timestamp}",
                "- agent: scripts/bootstrap-brain.sh",
                f"- repo: {repo_name}",
                "- branch: main",
                "- objective: Initialize clean G-Codex memory for this repository.",
                "- actions:",
                "  - Generated fresh `03_ACTIVE_NOW.md`, `MERGE_LOG.md`, `DYNAMIC_MEMORY.md`, and `PROPOSAL_OUTCOMES.md`.",
                "  - Removed inherited template activity history for a clean start.",
                "- outputs:",
                "  - G-Codex-brain/03_ACTIVE_NOW.md",
                "  - G-Codex-brain/MERGE_LOG.md",
                "  - G-Codex-brain/DYNAMIC_MEMORY.md",
                "  - G-Codex-brain/PROPOSAL_OUTCOMES.md",
                "  - G-Codex-brain/AGENT_ROLES.md",
                "  - G-Codex-brain/02_FIRST_HANDOFF.md",
                "- verification:",
                "  - Clean-slate brain files were regenerated during bootstrap/reset.",
                "- status: DONE",
                "- blockers: none",
                "- next_step: Open Control Room and begin the first project slice.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    _ensure_proposal_outcomes_file()
    _reset_md_core_state()

    for path in _iter_swarm_packet_paths():
        try:
            path.unlink()
        except OSError:
            continue

    _write_agent_roles("OAC")
    _regenerate_first_handoff("OAC")


def _archive_brain_state():
    if not BRAIN.exists():
        return None
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive_root = ROOT / "G-Codex-brain-archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / f"brain-{stamp}"
    if target.exists():
        target = archive_root / f"brain-{stamp}-{os.getpid()}"
    shutil.copytree(BRAIN, target)
    return str(target.relative_to(ROOT))


def _renew_brain(mode):
    normalized = (mode or "clean").strip().lower()
    if normalized not in {"clean", "archive", "keep"}:
        normalized = "clean"

    archived_path = None
    snapshot_path = None
    if normalized == "keep":
        return {"mode": "keep", "archived_path": None, "snapshot_path": None, "changed": False}
    snapshot_path = _create_brain_snapshot(
        reason=f"Pre-renew snapshot ({normalized} mode).",
        actor="Lead Executor",
    )
    if normalized == "archive":
        archived_path = _archive_brain_state()
        _write_clean_brain_state(reason="Dashboard Renew Brain (archive + renew)")
        _append_brain_changelog(
            what_changed="Renewed brain in archive mode and regenerated clean working state.",
            agent="Lead Executor",
            why="Reset context safely while preserving recoverable history for future reference.",
        )
    else:
        _write_clean_brain_state(reason="Dashboard Renew Brain (clean slate)")
        _append_brain_changelog(
            what_changed="Renewed brain in clean mode and regenerated baseline operational docs.",
            agent="Lead Executor",
            why="Removed drift and restored a deterministic clean-slate operating state.",
        )
    _touch_activity_refresh()
    return {"mode": normalized, "archived_path": archived_path, "snapshot_path": snapshot_path, "changed": True}


def _prepare_make_pure_transition(triggered_by="Lead Executor"):
    if not BRAIN.exists():
        return None
    snapshot_path = _create_brain_snapshot(
        reason="Pre-make-pure snapshot before removing G-Codex brain files.",
        actor=triggered_by,
    )
    _append_brain_changelog(
        what_changed="Initiated Make Pure Repo workflow.",
        agent=triggered_by,
        why="Created safety snapshot before removing template brain artifacts from the repository.",
    )
    return snapshot_path


def _clear_activity_history(reason="Dashboard Clear Feed"):
    timestamp = _now_iso()
    short_date = timestamp.split("T", 1)[0]
    repo_name = ROOT.name
    BRAIN.mkdir(parents=True, exist_ok=True)

    (BRAIN / "DYNAMIC_MEMORY.md").write_text(
        "\n".join(
            [
                "# DYNAMIC MEMORY",
                "",
                "## SESSION_LOG_ENTRY",
                f"- timestamp: {timestamp}",
                "- agent: scripts/brain_server.py",
                f"- repo: {repo_name}",
                "- branch: main",
                "- objective: Reset live activity feed to a clean state.",
                "- actions:",
                "  - Cleared previous dynamic memory entries from the live feed view.",
                "  - Removed swarm packet artifacts in repository root.",
                "- outputs:",
                "  - G-Codex-brain/DYNAMIC_MEMORY.md",
                "- verification:",
                "  - Activity feed now contains only this reset entry.",
                "- status: DONE",
                "- blockers: none",
                "- next_step: Continue dispatching slices and bridge injections.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    merge_log_path = BRAIN / "MERGE_LOG.md"
    if merge_log_path.exists():
        current = merge_log_path.read_text(encoding="utf-8")
        row = f"| {short_date} | {reason} in {repo_name} | local-runtime | scripts/brain_server.py |"
        if row not in current:
            with merge_log_path.open("a", encoding="utf-8") as handle:
                if not current.endswith("\n"):
                    handle.write("\n")
                handle.write(f"{row}\n")

    for path in _iter_swarm_packet_paths():
        try:
            path.unlink()
        except OSError:
            continue
    _reset_md_core_state()


def _pid_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _list_listening_pids(port):
    pids = set()

    if which("lsof"):
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
        for token in result.stdout.split():
            if token.isdigit():
                pids.add(int(token))

    if not pids and which("fuser"):
        result = subprocess.run(
            ["fuser", "-n", "tcp", str(port)],
            capture_output=True,
            text=True,
            check=False,
        )
        for token in result.stdout.split():
            if token.isdigit():
                pids.add(int(token))

    pids.discard(os.getpid())
    return pids


def _terminate_pids(pids):
    if not pids:
        return

    sigterm = getattr(signal, "SIGTERM", None)
    if sigterm is not None:
        for pid in sorted(pids):
            try:
                os.kill(pid, sigterm)
            except ProcessLookupError:
                continue
            except PermissionError:
                continue

    deadline = time.monotonic() + PORT_KILL_TIMEOUT_SEC
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if _pid_exists(pid)}
        if remaining:
            time.sleep(PORT_KILL_POLL_SEC)

    sigkill = getattr(signal, "SIGKILL", sigterm)
    if sigkill is None:
        return

    for pid in sorted(remaining):
        try:
            os.kill(pid, sigkill)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue


def _free_port(port):
    pids = _list_listening_pids(port)
    if pids:
        print(f"Port {port} is in use by PID(s): {', '.join(str(pid) for pid in sorted(pids))}. Stopping old server...")
        _terminate_pids(pids)


class BrainHTTPServer(HTTPServer):
    allow_reuse_address = True


def _create_server_with_retry():
    last_error = None
    for attempt in range(1, STARTUP_RETRIES + 1):
        _free_port(PORT)
        try:
            return BrainHTTPServer((HOST, PORT), Handler)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
            last_error = exc
            if attempt < STARTUP_RETRIES:
                time.sleep(STARTUP_RETRY_DELAY_SEC)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected startup failure")


class Handler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _launch_conductor(self, *args):
        if not CONDUCTOR.exists():
            return False
        subprocess.Popen(
            [str(CONDUCTOR), *args],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True

    def _schedule_conductor(self, *args, delay=0.15):
        def _runner():
            time.sleep(delay)
            self._launch_conductor(*args)

        threading.Thread(target=_runner, daemon=True).start()

    def _schedule_make_pure(self, delay=0.35):
        def _runner():
            time.sleep(delay)
            if not REMOVE_GCODEX.exists():
                return
            subprocess.Popen(
                [str(REMOVE_GCODEX), "--yes"],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        threading.Thread(target=_runner, daemon=True).start()

    def _launch_oac_terminal(self, prompt_text):
        safe_prompt = (prompt_text or "").strip()
        prompt_cache_path = ROOT / ".gcodex_oac_prompt.txt"
        prompt_cache_path.write_text(safe_prompt, encoding="utf-8")

        shell_cmd = (
            f"cd {shlex.quote(str(ROOT))}; "
            "HANDOFF_FILE='G-Codex-brain/02_FIRST_HANDOFF.md'; "
            "PROMPT_FILE='.gcodex_oac_prompt.txt'; "
            "if [ -f \"$HANDOFF_FILE\" ]; then PROMPT_CONTENT=\"$(cat \"$HANDOFF_FILE\")\"; "
            "elif [ -f \"$PROMPT_FILE\" ]; then PROMPT_CONTENT=\"$(cat \"$PROMPT_FILE\")\"; "
            "else PROMPT_CONTENT='Continue from current repository context.'; fi; "
            "echo 'Launching OAC Codex session...'; "
            "if command -v codex >/dev/null 2>&1; then "
            "  codex \"$PROMPT_CONTENT\"; "
            "else "
            "  echo 'codex CLI not found. Prompt for manual handoff:'; "
            "  echo '-----'; printf '%s\\n' \"$PROMPT_CONTENT\"; echo '-----'; "
            "  echo 'Install codex with: npm install -g @openai/codex'; "
            "  exec bash; "
            "fi"
        )

        return self._launch_shell_in_terminal(shell_cmd)

    def _launch_ggc_terminal(self, helper_packet_text):
        safe_helper = (helper_packet_text or "").strip()
        helper_cache_path = ROOT / ".gcodex_ggc_helper.txt"
        helper_cache_path.write_text(safe_helper, encoding="utf-8")

        shell_cmd = (
            f"cd {shlex.quote(str(ROOT))}; "
            "HELPER_FILE='.gcodex_ggc_helper.txt'; "
            "PROMPT_FILE='.gcodex_ggc_prompt.txt'; "
            "if [ -f \"$HELPER_FILE\" ]; then "
            "  PROMPT_CONTENT=\"$(awk '/^=== BEGIN GGC PROMPT ===/{flag=1;next}/^=== END GGC PROMPT ===/{flag=0}flag' \"$HELPER_FILE\")\"; "
            "  if [ -z \"$PROMPT_CONTENT\" ]; then PROMPT_CONTENT=\"$(cat \"$HELPER_FILE\")\"; fi; "
            "else "
            "  PROMPT_CONTENT='Please propose the next calm, low-adventure step for this repository.'; "
            "fi; "
            "printf '%s\\n' \"$PROMPT_CONTENT\" > \"$PROMPT_FILE\"; "
            "SHORT_RUNTIME_PROMPT=\"$(printf '%s' \"$PROMPT_CONTENT\" | tr '\\n' ' ' | sed 's/[[:space:]]\\+/ /g' | sed 's/^ //; s/ $//')\"; "
            "SHORT_RUNTIME_PROMPT=\"${SHORT_RUNTIME_PROMPT:0:720}\"; "
            "if [ -z \"$SHORT_RUNTIME_PROMPT\" ]; then SHORT_RUNTIME_PROMPT='Please propose the next calm, low-adventure step for this repository.'; fi; "
            "echo 'GGC terminal opened with MD context.'; "
            "echo 'Visible Gemini output and actions will appear below. Terminal stays open.'; "
            "echo 'Tip: persistent project context comes from repo-level GEMINI.md when present.'; "
            "if command -v gemini >/dev/null 2>&1; then "
            "  if gemini -i \"$SHORT_RUNTIME_PROMPT\"; then "
            "    :; "
            "  elif gemini \"$SHORT_RUNTIME_PROMPT\"; then "
            "    :; "
            "  elif gemini -r \"latest\"; then "
            "    :; "
            "  else "
            "    echo 'Gemini launch failed. Prompt for manual handoff:'; "
            "    echo '-----'; cat \"$PROMPT_FILE\"; echo '-----'; "
            "  fi; "
            "  echo 'Gemini process ended. Terminal remains open for continued interaction.'; "
            "  exec bash; "
            "elif command -v ggc >/dev/null 2>&1; then "
            "  if ggc -i \"$SHORT_RUNTIME_PROMPT\"; then "
            "    :; "
            "  elif ggc \"$SHORT_RUNTIME_PROMPT\"; then "
            "    :; "
            "  elif ggc -r \"latest\"; then "
            "    :; "
            "  else "
            "    echo 'GGC launch failed. Prompt for manual handoff:'; "
            "    echo '-----'; cat \"$PROMPT_FILE\"; echo '-----'; "
            "  fi; "
            "  echo 'GGC process ended. Terminal remains open for continued interaction.'; "
            "  exec bash; "
            "else "
            "  echo 'gemini CLI not found. Prompt for manual handoff:'; "
            "  echo '-----'; cat \"$PROMPT_FILE\"; echo '-----'; "
            "  echo 'Install Gemini CLI and ensure `gemini` is on PATH.'; "
            "  exec bash; "
            "fi"
        )

        return self._launch_shell_in_terminal(shell_cmd)

    def _launch_shell_in_terminal(self, shell_cmd):
        launchers = [
            ["x-terminal-emulator", "-e", "bash", "-lc", shell_cmd],
            ["gnome-terminal", "--", "bash", "-lc", shell_cmd],
            ["konsole", "-e", "bash", "-lc", shell_cmd],
            ["xterm", "-e", "bash", "-lc", shell_cmd],
        ]

        for launcher in launchers:
            if not which(launcher[0]):
                continue
            try:
                subprocess.Popen(
                    launcher,
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True, launcher[0]
            except OSError:
                continue
        return False, "no-terminal-launcher"

    def _resolve_repo_target(self, relative_path):
        raw = str(relative_path or "").strip()
        if raw in {"", ".", "./"}:
            target = ROOT.resolve()
            normalized = "."
        else:
            target = (ROOT / raw).resolve()
            normalized = raw
        try:
            target.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ValueError("path must stay inside repository root") from exc
        return target, normalized

    def _launch_terminal_at(self, target):
        shell_cmd = f"cd {shlex.quote(str(target))}; exec bash"
        launchers = [
            ["x-terminal-emulator", "-e", "bash", "-lc", shell_cmd],
            ["gnome-terminal", "--", "bash", "-lc", shell_cmd],
            ["konsole", "-e", "bash", "-lc", shell_cmd],
            ["xterm", "-e", "bash", "-lc", shell_cmd],
        ]
        for launcher in launchers:
            if not which(launcher[0]):
                continue
            try:
                subprocess.Popen(
                    launcher,
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True, launcher[0], launcher
            except OSError:
                continue
        return False, "no-terminal-launcher", []

    def _open_roadmap_target(self, relative_path, mode="explorer", dry_run=False):
        target, normalized = self._resolve_repo_target(relative_path)
        if not target.exists():
            return {
                "ok": False,
                "error": "target does not exist",
                "relative_path": normalized,
                "resolved_path": str(target),
            }
        if not target.is_dir():
            return {
                "ok": False,
                "error": "target is not a directory",
                "relative_path": normalized,
                "resolved_path": str(target),
            }

        selected_mode = str(mode or "explorer").strip().lower()
        if selected_mode not in {"explorer", "terminal"}:
            selected_mode = "explorer"

        if selected_mode == "terminal":
            launched, launcher, command = self._launch_terminal_at(target)
            if dry_run:
                launched = False
            return {
                "ok": launched or dry_run,
                "mode": "terminal",
                "launched": launched and not dry_run,
                "launcher": launcher,
                "command_preview": command,
                "relative_path": normalized,
                "resolved_path": str(target),
            }

        # Explorer mode (default)
        command = None
        launcher = ""
        if sys.platform.startswith("darwin"):
            command = ["open", str(target)]
            launcher = "open"
        elif os.name == "nt":
            command = ["explorer", str(target)]
            launcher = "explorer"
        elif which("xdg-open"):
            command = ["xdg-open", str(target)]
            launcher = "xdg-open"

        if not command:
            return {
                "ok": False,
                "mode": "explorer",
                "error": "no explorer launcher available",
                "relative_path": normalized,
                "resolved_path": str(target),
            }

        launched = True
        if not dry_run:
            try:
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                launched = False
        else:
            launched = False

        return {
            "ok": launched or dry_run,
            "mode": "explorer",
            "launched": launched and not dry_run,
            "launcher": launcher,
            "command_preview": command,
            "relative_path": normalized,
            "resolved_path": str(target),
        }

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        global NOTIFY_ENABLED

        if self.path == "/mcp/heartbeat":
            mcp_state = _mcp_heartbeat()
            self._json(
                {
                    "ok": True,
                    "mcp": mcp_state,
                }
            )
            return

        if self.path == "/mcp/session/reset":
            mcp_state = _mcp_reset_session()
            self._json(
                {
                    "ok": True,
                    "mcp": mcp_state,
                }
            )
            return

        if self.path == "/mcp/request":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            requested_by = _normalize_one_line(payload.get("requested_by", payload.get("source", "")), "External Tool")
            request_reason = _normalize_one_line(
                payload.get("request_reason", payload.get("reason", "")),
                "External tool requested design interview context.",
            )
            mcp_state = _mcp_mark_request_pending(requested_by, request_reason)
            _log_external_tool_injection(
                action_type="mcp_request",
                target="/mcp/request",
                status=mcp_state.get("status", MCP_AUTH_STATUS_PENDING),
                detail=f"{requested_by}: {request_reason}",
                source=requested_by,
                authorized=bool(mcp_state.get("context_release_allowed")),
            )
            _touch_activity_refresh()
            self._json(
                {
                    "ok": True,
                    "mcp": mcp_state,
                }
            )
            return

        if self.path == "/mcp/authorize":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            actor = _normalize_one_line(payload.get("authorized_by", payload.get("actor", "")), "Dashboard Human")
            mcp_state = _mcp_authorize_design_interview(actor)
            _log_external_tool_injection(
                action_type="mcp_authorize",
                target="/mcp/authorize",
                status=mcp_state.get("status", MCP_AUTH_STATUS_AUTHORIZED),
                detail=f"Authorization granted by {actor}.",
                source=actor,
                authorized=True,
            )
            _touch_activity_refresh()
            self._json(
                {
                    "ok": True,
                    "mcp": mcp_state,
                }
            )
            return

        if self.path == "/mcp/revoke":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            actor = _normalize_one_line(payload.get("revoked_by", payload.get("actor", "")), "Dashboard Human")
            mcp_state = _mcp_revoke_design_interview(actor)
            _log_external_tool_injection(
                action_type="mcp_revoke",
                target="/mcp/revoke",
                status=mcp_state.get("status", MCP_AUTH_STATUS_REVOKED),
                detail=f"Authorization revoked by {actor}.",
                source=actor,
                authorized=False,
            )
            _touch_activity_refresh()
            self._json(
                {
                    "ok": True,
                    "mcp": mcp_state,
                }
            )
            return

        if self.path == "/mcp/design-ingress":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            source_tool = _normalize_one_line(payload.get("source_tool", payload.get("source", "")), "External Tool")
            try:
                result = _ingest_design_proposal(payload)
            except PermissionError as exc:
                _log_external_tool_injection(
                    action_type="mcp_design_ingress",
                    target="/mcp/design-ingress",
                    status="DENIED",
                    detail=str(exc),
                    source=source_tool,
                    authorized=False,
                )
                self._json({"ok": False, "error": str(exc)}, 403)
                return
            except ValueError as exc:
                _log_external_tool_injection(
                    action_type="mcp_design_ingress",
                    target="/mcp/design-ingress",
                    status="INVALID",
                    detail=str(exc),
                    source=source_tool,
                    authorized=bool(_mcp_status_payload().get("context_release_allowed")),
                )
                self._json({"ok": False, "error": str(exc)}, 400)
                return

            _log_external_tool_injection(
                action_type="mcp_design_ingress",
                target="/mcp/design-ingress",
                status="QUEUED",
                detail=f"{result.get('proposal_id', '')}: {_normalize_one_line(result.get('summary', ''), '')}",
                source=source_tool,
                authorized=True,
            )
            _touch_activity_refresh()
            proposal_data = _list_md_proposals()
            self._json(
                {
                    "ok": True,
                    "proposal": result,
                    "message": result.get("message", ""),
                    "pending": proposal_data["pending"],
                    "recent": proposal_data["recent"],
                    "design_pending": proposal_data["design_pending"],
                    "patterns": proposal_data["patterns"],
                    "refresh_token": ACTIVITY_REFRESH_TOKEN,
                    "refreshed_at": ACTIVITY_REFRESH_AT,
                }
            )
            return

        if self.path == "/mcp/github/list-prs":
            try:
                mcp_script = ROOT / "scripts" / "mcp_server.py"
                cmd = [sys.executable, str(mcp_script), "--list-prs"]
                mcp_status = _mcp_status_payload()
                if mcp_status.get("authorized") or mcp_status.get("status") == "AUTHORIZED":
                    cmd.append("--bootstrap-authorized")

                proc = subprocess.run(
                    cmd,
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                try:
                    result = json.loads(proc.stdout.strip())
                except json.JSONDecodeError:
                    err = proc.stderr.strip() or "MCP proxy failed"
                    self._json({"ok": False, "error": f"MCP proxy error: {err}"}, 500)
                    return

                if result.get("status") == "OK":
                    self._json({"ok": True, "prs": result.get("prs", [])})
                else:
                    self._json({"ok": False, "error": result.get("message")}, 403 if result.get("status") == "DENIED" else 500)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if self.path == "/mcp/github/pr-details":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(raw) if raw else {}
                number = _normalize_one_line(str(payload.get("number", "")), "")
                if not number:
                    raise ValueError("number is required")

                mcp_script = ROOT / "scripts" / "mcp_server.py"
                cmd = [sys.executable, str(mcp_script), "--pr-details", number]
                mcp_status = _mcp_status_payload()
                if mcp_status.get("authorized") or mcp_status.get("status") == "AUTHORIZED":
                    cmd.append("--bootstrap-authorized")

                proc = subprocess.run(
                    cmd,
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                try:
                    result = json.loads(proc.stdout.strip())
                except json.JSONDecodeError:
                    err = proc.stderr.strip() or "MCP proxy failed"
                    self._json({"ok": False, "error": f"MCP proxy error: {err}"}, 500)
                    return

                if result.get("status") == "OK":
                    self._json({"ok": True, "pr": result.get("pr", {})})
                else:
                    self._json({"ok": False, "error": result.get("message")}, 403 if result.get("status") == "DENIED" else 500)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if self.path == "/mcp/github/post-pr-comment":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(raw) if raw else {}
                number = _normalize_one_line(str(payload.get("number", "")), "")
                body = str(payload.get("body", "")).strip()
                if not number or not body:
                    raise ValueError("number and body are required")

                mcp_script = ROOT / "scripts" / "mcp_server.py"
                cmd = [sys.executable, str(mcp_script), "--post-pr-comment", number, "--body", body]
                
                mcp_status = _mcp_status_payload()
                if mcp_status.get("authorized") or mcp_status.get("status") == "AUTHORIZED":
                    cmd.append("--bootstrap-authorized")

                proc = subprocess.run(
                    cmd,
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                try:
                    result = json.loads(proc.stdout.strip())
                except json.JSONDecodeError:
                    err = proc.stderr.strip() or "MCP proxy failed"
                    self._json({"ok": False, "error": f"MCP proxy error: {err}"}, 500)
                    return

                if result.get("status") == "OK":
                    self._json({"ok": True, "message": result.get("message"), "url": result.get("url")})
                else:
                    self._json({"ok": False, "error": result.get("message")}, 403 if result.get("status") == "DENIED" else 500)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if self.path == "/mcp/github/enriched-pr-prompt":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(raw) if raw else {}
                if not payload.get("number"):
                    raise ValueError("PR details (number) required")
                
                enriched = _build_enriched_pr_review_prompt(payload)
                
                # Log the enriched prompt for transparency
                block = "\n".join([
                    "## MD_PR_REVIEW",
                    f"- timestamp: {_now_iso()}",
                    f"- pr_number: {payload.get('number')}",
                    f"- persona_influence: {enriched.get('persona_influence', 'none')}",
                    f"- attuned: {'TRUE' if enriched.get('attuned') else 'FALSE'}",
                    "- enriched_prompt_excerpt:",
                    "```text",
                    _compact_excerpt(enriched.get("prompt", ""), limit=400),
                    "```",
                    ""
                ])
                _append_dynamic_memory_entry(block)
                
                self._json({"ok": True, "prompt": enriched["prompt"], "attuned": enriched["attuned"]})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if self.path == "/mcp/sight/screenshot-lite":
            try:
                # Direct CDP capture (Phase 23 Lite)
                result = _capture_screenshot_lite()
                if result.get("ok"):
                    self._json({"ok": True, "filename": result.get("filename"), "path": result.get("path"), "title": result.get("title")})
                else:
                    self._json({"ok": False, "error": result.get("error")}, 500)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if self.path == "/mcp/github/meta-scan":
            try:
                mcp_script = ROOT / "scripts" / "mcp_server.py"
                cmd = [sys.executable, str(mcp_script), "--meta-scan"]
                
                mcp_status = _mcp_status_payload()
                if mcp_status.get("authorized") or mcp_status.get("status") == "AUTHORIZED":
                    cmd.append("--bootstrap-authorized")

                proc = subprocess.run(
                    cmd,
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                try:
                    result = json.loads(proc.stdout.strip())
                except json.JSONDecodeError:
                    err = proc.stderr.strip() or "MCP proxy failed"
                    self._json({"ok": False, "error": f"MCP proxy error: {err}"}, 500)
                    return

                if result.get("status") == "OK":
                    meta_scan = result.get("meta_scan")
                    if meta_scan:
                        with GITHUB_STATUS_LOCK:
                            GITHUB_META_SCAN_CACHE["checked_at"] = time.time()
                            GITHUB_META_SCAN_CACHE["payload"] = meta_scan
                    self._json({"ok": True, "meta_scan": meta_scan})
                else:
                    self._json({"ok": False, "error": result.get("message")}, 403 if result.get("status") == "DENIED" else 500)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if self.path == "/mcp/github/create-issue":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(raw) if raw else {}
                title = _normalize_one_line(payload.get("title", ""), "")
                body = str(payload.get("body", "")).strip()
                labels = _normalize_one_line(payload.get("labels", "low-adventure,md-proposal"), "low-adventure,md-proposal")
                milestone = _normalize_one_line(payload.get("milestone", ""), "")

                if not title or not body:
                    raise ValueError("title and body are required")

                # Proxy call to mcp_server.py (Sovereign Source of Truth)
                mcp_script = ROOT / "scripts" / "mcp_server.py"
                cmd = [
                    sys.executable,
                    str(mcp_script),
                    "--create-github-issue",
                    "--title", title,
                    "--body", body,
                    "--labels", labels,
                ]
                if milestone:
                    cmd.extend(["--milestone", milestone])

                # If MD authorized in brain, pass it to the child MCP process
                mcp_status = _mcp_status_payload()
                if mcp_status.get("authorized") or mcp_status.get("status") == "AUTHORIZED":
                    cmd.append("--bootstrap-authorized")

                proc = subprocess.run(
                    cmd,
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                
                # mcp_server.py returns a JSON result on stdout
                try:
                    result = json.loads(proc.stdout.strip())
                except json.JSONDecodeError:
                    err = proc.stderr.strip() or "MCP proxy failed"
                    self._json({"ok": False, "error": f"MCP proxy error: {err}"}, 500)
                    return

                if result.get("status") == "OK":
                    self._json({"ok": True, "issue_url": result.get("issue_url"), "message": result.get("message")})
                else:
                    self._json({"ok": False, "error": result.get("message")}, 403 if result.get("status") == "DENIED" else 500)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if self.path == "/oac/harmonize-directive":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            harmonize_action = _normalize_one_line(payload.get("harmonize_action", payload.get("action", "")), "directive").lower()
            try:
                directive_bundle = _build_oac_design_harmonization_payload(payload)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            directive = str(directive_bundle.get("directive", "") or "").strip()
            if not directive:
                self._json({"ok": False, "error": "directive generation failed"}, 500)
                return
            proposal_id = _normalize_one_line(payload.get("proposal_id", ""), "").upper()
            md_recommendation = _normalize_one_line(payload.get("md_recommendation", ""), "").upper()
            persona_alignment = _normalize_one_line(payload.get("persona_alignment", ""), "")
            persona_layer = _normalize_one_line(payload.get("persona_layer", ""), "")
            _append_oac_harmonization_directive_block(
                directive_bundle,
                initiated_by="Dashboard Human",
                action_mode=harmonize_action,
            )
            detail = (
                f"Directive generated for {proposal_id}; action={harmonize_action}; "
                f"md_recommendation={md_recommendation or directive_bundle.get('md_recommendation') or 'INTERVIEW_USER'}; "
                f"persona_alignment={persona_alignment or directive_bundle.get('persona_alignment') or 'LOW [none]'}; "
                f"persona_layer={persona_layer or directive_bundle.get('persona_layer') or 'fallback_scan'}."
            )
            _log_external_tool_injection(
                action_type="oac_harmonize_directive",
                target=f"design_proposal:{proposal_id}",
                status="READY",
                detail=detail,
                source="Dashboard Human",
                authorized=True,
            )
            _touch_activity_refresh()
            self._json(
                {
                    "ok": True,
                    "proposal_id": proposal_id,
                    "directive": directive,
                    "message": f"OAC harmonization directive generated for {proposal_id}. Local commit helper stays conservative (`push: false`).",
                    "commit_helper": {
                        "mode": "local_commit_only",
                        "push": False,
                        "note": directive_bundle.get("commit_helper_note", "One-click commit helper remains conservative: local commit only (`push: false`)."),
                    },
                    "refresh_token": ACTIVITY_REFRESH_TOKEN,
                    "refreshed_at": ACTIVITY_REFRESH_AT,
                }
            )
            return

        if self.path == "/dispatch":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            slice_text = payload.get("slice", "").strip()
            risk_level = payload.get("risk_level", "LOW ADVENTURE").strip().upper()

            if not slice_text:
                self._json({"error": "slice is required"}, 400)
                return
            if risk_level not in ALLOWED_RISK_LEVELS:
                self._json({"error": "invalid risk_level"}, 400)
                return

            timestamp = _now_iso()
            context_summary = _extract_active_now_excerpt()
            packet = (
                "# G-Codex Swarm Packet\n"
                f"Timestamp: {timestamp}\n"
                f"Repo: {ROOT.name}\n"
                f"Risk Level: {risk_level}\n"
                f"Slice: {slice_text}\n"
                f"Context Summary: {context_summary}\n"
                "---\n"
                "Ready for Triad of Truth execution.\n"
            )
            SWARM_PACKET_PATH.write_text(packet, encoding="utf-8")
            self._json({
                "ok": True,
                "packet_path": str(SWARM_PACKET_PATH.relative_to(ROOT)),
                "packet": packet,
            })
            _touch_activity_refresh()
            return

        if self.path == "/notify-control":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            NOTIFY_ENABLED = bool(payload.get("enabled", True))
            _write_notify_enabled(NOTIFY_ENABLED)
            self._json({
                "ok": True,
                "notify_enabled": NOTIFY_ENABLED,
            })
            return

        if self.path == "/activity":
            _run_md_core(trigger="ACTIVITY_SIGNAL", force=False)
            _touch_activity_refresh()
            self._json({
                "ok": True,
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
                "md_status": _md_status_payload(),
            })
            return

        if self.path == "/md/talk":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            message = str(payload.get("message", "")).strip()
            source = str(payload.get("source", "Human")).strip() or "Human"
            requested_design_proposal_id = _normalize_one_line(payload.get("design_proposal_id", ""), "")
            if not message:
                self._json({"ok": False, "error": "message is required"}, 400)
                return
            try:
                injected_at = _append_human_injection(message, source=source)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            md_result = _run_md_core(trigger="HUMAN_INJECTION", force=False, reason="Talk to Managing Director")
            md_status = _md_status_payload()
            design_assessment = _apply_design_assessment_from_md(
                guidance_text=md_status.get("guidance", ""),
                requested_proposal_id=requested_design_proposal_id,
                source=source or "Human",
            )
            if design_assessment.get("updated"):
                _touch_activity_refresh()
            proposal_data = _list_md_proposals()
            self._json(
                {
                    "ok": True,
                    "injected_at": injected_at,
                    "md_report": md_result,
                    "md_status": md_status,
                    "design_assessment": design_assessment,
                    "pending": proposal_data["pending"],
                    "recent": proposal_data["recent"],
                    "design_pending": proposal_data["design_pending"],
                    "patterns": proposal_data["patterns"],
                    "md_reply": {
                        "md_brain_engine": str(md_status.get("md_brain_engine", DEFAULT_MD_BRAIN_ENGINE)).strip(),
                        "sentiment": str(md_status.get("sentiment", "")).strip(),
                        "guidance": str(md_status.get("guidance", "")).strip(),
                        "next_mission": str(md_status.get("next_mission", "")).strip(),
                        "suggested_mission": str(md_status.get("suggested_mission", "")).strip(),
                        "complexity_flag": bool(md_status.get("complexity_flag", False)),
                        "complexity_reason": str(md_status.get("complexity_reason", "")).strip(),
                        "complexity_note": str(md_status.get("complexity_note", "")).strip(),
                        "matched_route": str(md_status.get("matched_route", "")).strip(),
                        "matched_route_note": str(md_status.get("matched_route_note", "")).strip(),
                        "project_personality_summary": str(md_status.get("project_personality_summary", "")).strip(),
                        "project_personality_active": bool(md_status.get("project_personality_active", False)),
                        "persona_influence": str(md_status.get("persona_influence", "")).strip(),
                        "persona_attuned": bool(md_status.get("persona_attuned", False)),
                        "oac_handoff_target": "OAC",
                        "oac_handoff": str(md_status.get("oac_handoff", "")).strip(),
                    },
                    "refresh_token": ACTIVITY_REFRESH_TOKEN,
                    "refreshed_at": ACTIVITY_REFRESH_AT,
                }
            )
            return

        if self.path == "/md/report":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            reason = _normalize_one_line(payload.get("reason", ""), "")
            md_result = _run_md_core(trigger="MANUAL_REQUEST", force=True, reason=reason or "Manual report request")
            self._json(
                {
                    "ok": True,
                    "md_report": md_result,
                    "md_status": _md_status_payload(),
                    "refresh_token": ACTIVITY_REFRESH_TOKEN,
                    "refreshed_at": ACTIVITY_REFRESH_AT,
                }
            )
            return

        if self.path == "/md/suggestion/review":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            try:
                result = _review_md_suggestion(payload)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return

            _touch_activity_refresh()
            proposal_data = _list_md_proposals()
            self._json(
                {
                    "ok": True,
                    **result,
                    "md_status": _md_status_payload(),
                    "pending": proposal_data["pending"],
                    "recent": proposal_data["recent"],
                    "design_pending": proposal_data["design_pending"],
                    "patterns": proposal_data["patterns"],
                    "refresh_token": ACTIVITY_REFRESH_TOKEN,
                    "refreshed_at": ACTIVITY_REFRESH_AT,
                }
            )
            return

        if self.path == "/managing-director/assign":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            try:
                assignment = _create_md_assignment(payload)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            _run_md_core(trigger="MD_ASSIGNMENT", force=False, reason="Managing Director assignment updated")
            _touch_activity_refresh()
            self._json({
                "ok": True,
                "assignment": assignment,
                "md_status": _md_status_payload(),
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/proposals/create":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            try:
                proposal = _create_md_proposal(payload)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            _touch_activity_refresh()
            proposal_data = _list_md_proposals()
            self._json({
                "ok": True,
                "proposal": proposal,
                "pending": proposal_data["pending"],
                "recent": proposal_data["recent"],
                "design_pending": proposal_data["design_pending"],
                "patterns": proposal_data["patterns"],
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/proposals/review":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            try:
                review_result = _review_md_proposal(payload)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            reviewed_status = str(review_result.get("proposal", {}).get("status", "")).upper()
            if reviewed_status == "ACCEPTED":
                _run_md_core(trigger="PROPOSAL_ACCEPTED", force=True, reason="Proposal accepted and harmonized")
            else:
                _run_md_core(trigger="PROPOSAL_REVIEW", force=False)
            _touch_activity_refresh()
            proposal_data = _list_md_proposals()
            self._json({
                "ok": True,
                "proposal": review_result["proposal"],
                "next_slice_suggestion": review_result.get("next_slice_suggestion", ""),
                "harmonized_commit": review_result.get("harmonized_commit", {}),
                "md_status": _md_status_payload(),
                "pending": proposal_data["pending"],
                "recent": proposal_data["recent"],
                "design_pending": proposal_data["design_pending"],
                "patterns": proposal_data["patterns"],
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/git/commit":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            try:
                result = _run_git_commit_push(payload)
            except GitWorkflowError as exc:
                self._json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "phase": exc.phase,
                        "snapshot_created": exc.snapshot_created,
                        "output": exc.output,
                    },
                    400,
                )
                return
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            except (OSError, subprocess.SubprocessError) as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
                return

            _touch_activity_refresh()
            proposal_data = _list_md_proposals()
            self._json({
                "ok": True,
                **result,
                "pending": proposal_data["pending"],
                "recent": proposal_data["recent"],
                "design_pending": proposal_data["design_pending"],
                "patterns": proposal_data["patterns"],
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/backups/restore":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            snapshot = payload.get("snapshot", "")
            restored_by = _normalize_one_line(payload.get("restored_by", ""), "Lead Executor")
            try:
                result = _restore_brain_snapshot(snapshot, restored_by=restored_by)
            except (ValueError, OSError, zipfile.BadZipFile) as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            _touch_activity_refresh()
            proposal_data = _list_md_proposals()
            self._json({
                "ok": True,
                **result,
                "pending": proposal_data["pending"],
                "recent": proposal_data["recent"],
                "design_pending": proposal_data["design_pending"],
                "patterns": proposal_data["patterns"],
                "backups": _list_brain_snapshots(limit=12),
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/roles/promote":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            requested = payload.get("agent", "")
            lead = _normalize_lead_agent(requested)
            if not lead:
                self._json({"ok": False, "error": "invalid agent"}, 400)
                return
            lead = _write_agent_roles(lead)
            handoff = _regenerate_first_handoff(lead)
            role_state = _read_agent_roles()
            resolved_lead = handoff.get("lead_executor", lead)
            _touch_activity_refresh()
            self._json({
                "ok": True,
                "lead_executor": resolved_lead,
                "lead_executor_role": _role_description_for(resolved_lead, role_state),
                "roles_path": str(AGENT_ROLES_PATH.relative_to(ROOT)),
                "handoff_path": handoff["handoff_path"],
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/roadmap/open":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            relative_path = payload.get("relative_path", ".")
            mode = payload.get("mode", "explorer")
            dry_run = bool(payload.get("dry_run", False))
            try:
                result = self._open_roadmap_target(relative_path, mode=mode, dry_run=dry_run)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            status = 200 if result.get("ok") else 400
            self._json(result, status=status)
            return

        if self.path == "/activity/clear":
            _clear_activity_history()
            _reset_md_core_state()
            _touch_activity_refresh()
            self._json({
                "ok": True,
                "accepted": True,
                "action": "activity-clear",
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/watch/start":
            self._json({"ok": True, "accepted": True, "action": "watch-start"})
            self._schedule_conductor("watch", "start")
            return

        if self.path == "/agent/launch":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            agent = str(payload.get("agent", "")).strip().upper()
            prompt = str(payload.get("prompt", "")).strip()
            helper_packet = str(payload.get("helper_packet", "")).strip()
            if agent == "OAC":
                launched, launcher = self._launch_oac_terminal(prompt)
                normalized_agent = "OAC"
            elif agent in {"GGC", "GEMINI", "GEMINI 3"}:
                launch_text = helper_packet or prompt
                launched, launcher = self._launch_ggc_terminal(launch_text)
                normalized_agent = "GGC"
            else:
                self._json({"ok": False, "error": "agent launch endpoint supports OAC and GGC only"}, 400)
                return
            self._json({
                "ok": True,
                "agent": normalized_agent,
                "launched": launched,
                "launcher": launcher,
            })
            return

        if self.path == "/brain/renew":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            mode = str(payload.get("mode", "clean")).strip().lower()
            result = _renew_brain(mode)
            self._json({"ok": True, **result})
            return

        if self.path == "/make-pure":
            snapshot_path = _prepare_make_pure_transition(triggered_by="Lead Executor")
            self._json({"ok": True, "accepted": True, "action": "make-pure", "snapshot_path": snapshot_path})
            self._schedule_make_pure()
            return

        if self.path == "/start-fresh":
            snapshot_path = _create_brain_snapshot(
                reason="Pre-start-fresh snapshot before clean reset.",
                actor="Lead Executor",
            )
            _write_clean_brain_state(reason="Dashboard Start Fresh reset")
            _reset_md_core_state()
            _append_brain_changelog(
                what_changed="Executed Start Fresh reset and regenerated clean brain state.",
                agent="Lead Executor",
                why="Cleared prior local memory state to begin a deterministic fresh bootstrap cycle.",
            )
            _touch_activity_refresh()
            self._json({"ok": True, "accepted": True, "action": "start-fresh", "snapshot_path": snapshot_path})
            return

        if self.path in ("/start", "/stop", "/restart"):
            action_map = {
                "/start": "start-server",
                "/stop": "stop-server",
                "/restart": "restart-server",
            }
            action = action_map[self.path]
        elif self.path == "/server/control":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            payload = json.loads(raw) if raw else {}
            action = payload.get("action", "")
        else:
            self._json({"error": "not found"}, 404)
            return

        if action == "start-server":
            # This endpoint is only reachable while a server is already running.
            self._json({"ok": True, "status": "running", "detail": "already-running"})
            return

        if action == "stop-server":
            self._json({"ok": True, "accepted": True, "action": action})
            self._schedule_conductor("stop-server")
            return

        if action == "restart-server":
            self._json({"ok": True, "accepted": True, "action": action})
            self._schedule_conductor("start-server")
            return

        if action == "watch-start":
            self._json({"ok": True, "accepted": True, "action": action})
            self._schedule_conductor("watch", "start")
            return

        if action == "activity-clear":
            _clear_activity_history()
            _reset_md_core_state()
            _touch_activity_refresh()
            self._json({
                "ok": True,
                "accepted": True,
                "action": action,
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if action == "start-fresh":
            snapshot_path = _create_brain_snapshot(
                reason="Pre-start-fresh snapshot before clean reset.",
                actor="Lead Executor",
            )
            _write_clean_brain_state(reason="Dashboard Start Fresh reset")
            _reset_md_core_state()
            _append_brain_changelog(
                what_changed="Executed Start Fresh reset and regenerated clean brain state.",
                agent="Lead Executor",
                why="Cleared prior local memory state to begin a deterministic fresh bootstrap cycle.",
            )
            _touch_activity_refresh()
            self._json({"ok": True, "accepted": True, "action": action, "snapshot_path": snapshot_path})
            return

        if action == "make-pure":
            snapshot_path = _prepare_make_pure_transition(triggered_by="Lead Executor")
            self._json({"ok": True, "accepted": True, "action": action, "snapshot_path": snapshot_path})
            self._schedule_make_pure()
            return

        if action == "brain-renew":
            mode = str(payload.get("mode", "clean")).strip().lower()
            result = _renew_brain(mode)
            self._json({"ok": True, "accepted": True, "action": action, **result})
            return

        self._json({"error": "invalid action"}, 400)

    def do_GET(self):
        if self.path == "/notify-control":
            self._json({
                "notify_enabled": NOTIFY_ENABLED,
                "notify_file": str(NOTIFY_ENABLED_FILE.relative_to(ROOT)),
            })
            return

        if self.path == "/health":
            local_reasoning_status = _local_reasoning_status_payload(trigger_warmup=True)
            github_status = _collect_github_status_payload(force=False)
            self._json(
                {
                    "ok": True,
                    "status": "healthy",
                    "generated_at": _now_iso(),
                    "local_reasoning_status": local_reasoning_status,
                    "github_status": github_status,
                }
            )
            return

        if self.path == "/mcp/status":
            source = _normalize_one_line(self.headers.get("X-GCodex-Source", ""), "external-tool")
            mcp_state = _mcp_status_payload()
            local_reasoning_status = mcp_state.get("local_reasoning_status", {})
            github_status = mcp_state.get("github_status", {})
            if source.lower() != "dashboard":
                _log_external_tool_injection(
                    action_type="mcp_status",
                    target="/mcp/status",
                    status=mcp_state.get("status", MCP_AUTH_STATUS_IDLE),
                    detail=f"Gatekeeper status requested by {source}.",
                    source=source,
                    authorized=bool(mcp_state.get("context_release_allowed")),
                )
            self._json(
                {
                    "ok": True,
                    "mcp": mcp_state,
                    "local_reasoning_status": local_reasoning_status,
                    "github_status": github_status,
                    "generated_at": _now_iso(),
                }
            )
            return

        if self.path == "/roles":
            role_data = _read_agent_roles()
            self._json({
                "lead_executor": role_data["lead_executor"],
                "md_brain_engine": role_data.get("md_brain_engine", DEFAULT_MD_BRAIN_ENGINE),
                "agents": role_data["agents"],
                "roles": role_data["roles"],
                "roles_path": str(AGENT_ROLES_PATH.relative_to(ROOT)),
            })
            return

        if self.path == "/activity/pulse":
            self._json({
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/activity":
            _run_md_core(trigger="ACTIVITY_SIGNAL", force=False)
            entries = _build_activity_feed(limit=5)
            bridge_status = _watcher_status_payload()
            self._json({
                "entries": entries,
                "last_bridge_injection_at": bridge_status.get("last_bridge_injection_at", ""),
                "md_status": _md_status_payload(),
                "generated_at": _now_iso(),
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/md/status":
            self._json({
                "ok": True,
                "md_status": _md_status_payload(),
                "generated_at": _now_iso(),
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/watch/status":
            payload = _watcher_status_payload()
            payload["generated_at"] = _now_iso()
            self._json(payload)
            return

        if self.path == "/watch-folder/status":
            payload = _ambient_watch_status_payload()
            payload["generated_at"] = _now_iso()
            self._json(payload)
            return

        if self.path == "/proposals":
            proposal_data = _list_md_proposals()
            self._json({
                "pending": proposal_data["pending"],
                "recent": proposal_data["recent"],
                "design_pending": proposal_data["design_pending"],
                "patterns": proposal_data["patterns"],
                "generated_at": _now_iso(),
                "refresh_token": ACTIVITY_REFRESH_TOKEN,
                "refreshed_at": ACTIVITY_REFRESH_AT,
            })
            return

        if self.path == "/backups" or self.path.startswith("/backups?"):
            self._json({
                "backups": _list_brain_snapshots(limit=12),
                "generated_at": _now_iso(),
            })
            return

        if self.path.split('?')[0] == '/dashboard':
            dashboard_path = ROOT / "scripts" / "named_agent_dashboard.html"
            if dashboard_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(dashboard_path.read_bytes())
            else:
                self._json({"error": "dashboard file not found"}, 404)
            return

        if self.path != "/context":
            self._json({"error": "not found"}, 404)
            return
        
        data = {}
        for path in CONTEXT_FILES:
            rel_path = str(path.relative_to(ROOT))
            if path.exists():
                data[rel_path] = path.read_text(encoding="utf-8")
            else:
                data[rel_path] = "FILE_NOT_FOUND"
        
        self._json({
            "repo": {
                "name": ROOT.name,
                "path": str(ROOT),
                "git_status": get_git_status(),
                "posture": _repo_posture_payload(),
            },
            "context": data
        })


if __name__ == "__main__":
    print(f"Starting G-Codex Shared Brain Server on {HOST}:{PORT}...")
    server = _create_server_with_retry()
    server.serve_forever()
