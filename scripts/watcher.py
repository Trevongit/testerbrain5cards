#!/usr/bin/env python3
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from shutil import which

POLL_SECONDS = 2.0
CLIPBOARD_DEBOUNCE_SECONDS = 0.35
INJECTION_HEADER = "### 🧠 G-CODEX INJECTION:"
ACTIVITY_URL = "http://127.0.0.1:8765/activity"
NOTIFY_CONTROL_URL = "http://127.0.0.1:8765/notify-control"

ROOT = Path(__file__).resolve().parents[1]
DYNAMIC_MEMORY_PATH = ROOT / "G-Codex-brain" / "DYNAMIC_MEMORY.md"
NOTIFY_ENABLED_FILE = ROOT / ".notify_enabled"
BRIDGE_HASH_PATTERN = re.compile(r"^- bridge_hash:\s*([a-f0-9]{32})\s*$", flags=re.MULTILINE)


def now_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def normalize_source(raw_source):
    value = (raw_source or "").strip()
    lower = value.lower()
    if "gemini" in lower:
        return "Gemini 3"
    if "grok" in lower:
        return "Grok"
    if "chatgpt" in lower:
        return "ChatGPT"
    if "claude" in lower:
        return "Claude"
    if "human" in lower:
        return "Human"
    return value if value else "Human"


def normalize_metadata_line(line):
    trimmed = (line or "").strip()
    while trimmed.startswith(("-", "*", "•")):
        trimmed = trimmed[1:].strip()
    return trimmed


def parse_injection_block(clipboard_text):
    if not clipboard_text:
        return None

    stripped = clipboard_text.strip()
    if not stripped.startswith(INJECTION_HEADER):
        return None

    payload = stripped[len(INJECTION_HEADER):].lstrip()
    lines = payload.splitlines()
    source = "Human"
    body_lines = []
    content_lines = []
    in_content = False

    for line in lines:
        trimmed = normalize_metadata_line(line)
        lower = trimmed.lower()

        if lower.startswith("source:"):
            source = normalize_source(trimmed.split(":", 1)[1])
            continue
        if lower.startswith("model:"):
            source = normalize_source(trimmed.split(":", 1)[1])
            continue
        if lower.startswith("timestamp:"):
            continue
        if lower.startswith("content:"):
            in_content = True
            remainder = line.split(":", 1)[1].strip()
            if remainder:
                content_lines.append(remainder)
            continue

        if in_content:
            content_lines.append(line.rstrip())
        else:
            body_lines.append(line.rstrip())

    if not content_lines:
        content_lines = body_lines

    clean_content = "\n".join(content_lines).strip()
    if not clean_content:
        return None

    return {
        "source": source,
        "content": clean_content,
        "content_hash": hashlib.md5(clean_content.encode("utf-8")).hexdigest(),
    }


def read_clipboard():
    proc = subprocess.run(
        ["xclip", "-selection", "clipboard", "-o"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "xclip clipboard read failed")
    return proc.stdout


def last_hashes(limit=5):
    if not DYNAMIC_MEMORY_PATH.exists():
        return []
    text = DYNAMIC_MEMORY_PATH.read_text(encoding="utf-8")
    matches = BRIDGE_HASH_PATTERN.findall(text)
    return matches[-limit:]


def append_injection(entry):
    timestamp = now_iso()
    record = (
        "\n\n## GCODEX_BRIDGE_INJECTION\n"
        f"- timestamp: {timestamp}\n"
        f"- source: {entry['source']}\n"
        f"- bridge_hash: {entry['content_hash']}\n"
        "- content:\n"
        "```text\n"
        f"{entry['content']}\n"
        "```\n"
    )
    with DYNAMIC_MEMORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(record)


def _notify_enabled_from_file():
    if not NOTIFY_ENABLED_FILE.exists():
        return True
    raw = NOTIFY_ENABLED_FILE.read_text(encoding="utf-8").strip().lower()
    return raw not in {"0", "off", "false", "calm", "no"}


def _notify_enabled():
    request = urllib.request.Request(NOTIFY_CONTROL_URL, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=1.2) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if "notify_enabled" in payload:
                return bool(payload["notify_enabled"])
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    return _notify_enabled_from_file()


def send_notification():
    if not _notify_enabled():
        return False
    subprocess.run(["notify-send", "G-Codex sensed an injection."], check=False)
    return True


def post_activity_refresh():
    payload = json.dumps({"source": "watcher", "timestamp": now_iso()}).encode("utf-8")
    request = urllib.request.Request(
        ACTIVITY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1.5):
            pass
    except (urllib.error.URLError, TimeoutError):
        # Feed polling still catches updates, so this remains best-effort.
        pass


def main():
    if not DYNAMIC_MEMORY_PATH.exists():
        print(f"Missing required memory file: {DYNAMIC_MEMORY_PATH}", file=sys.stderr)
        return 1

    if which("xclip") is None:
        print("xclip is required for watcher mode. Install xclip and retry.", file=sys.stderr)
        return 2

    candidate_hash = ""
    candidate_text = ""
    candidate_since = 0.0
    handled_hash = ""
    print("G-Codex watcher active. Polling clipboard every 2 seconds...")

    while True:
        try:
            clipboard_text = read_clipboard()
        except RuntimeError as err:
            print(f"[watcher] clipboard read failed: {err}", file=sys.stderr)
            time.sleep(POLL_SECONDS)
            continue

        block_hash = hashlib.md5(clipboard_text.encode("utf-8")).hexdigest()
        now_mono = time.monotonic()

        if block_hash != candidate_hash:
            candidate_hash = block_hash
            candidate_text = clipboard_text
            candidate_since = now_mono
            time.sleep(POLL_SECONDS)
            continue

        if now_mono - candidate_since < CLIPBOARD_DEBOUNCE_SECONDS:
            time.sleep(POLL_SECONDS)
            continue

        if block_hash == handled_hash:
            time.sleep(POLL_SECONDS)
            continue

        handled_hash = block_hash
        injection = parse_injection_block(candidate_text)
        if not injection:
            time.sleep(POLL_SECONDS)
            continue

        recent_hashes = last_hashes(limit=5)
        if injection["content_hash"] in recent_hashes:
            notified = send_notification()
            post_activity_refresh()
            if not notified:
                print(f"[watcher] notification suppressed (calm mode) for duplicate from {injection['source']}")
            print(f"[watcher] duplicate injection ignored from {injection['source']} at {now_iso()}")
            time.sleep(POLL_SECONDS)
            continue

        append_injection(injection)
        notified = send_notification()
        post_activity_refresh()
        if not notified:
            print(f"[watcher] notification suppressed (calm mode) for injection from {injection['source']}")
        print(f"[watcher] injection accepted from {injection['source']} at {now_iso()}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
