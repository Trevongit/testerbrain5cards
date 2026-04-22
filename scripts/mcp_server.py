#!/usr/bin/env python3
"""G-Codex MCP Extension Module (Phase 1 foundation).

Sovereign defaults:
- Local-first transport (stdio primary)
- Read-only resources
- MD gatekeeping required for every resource/tool call
- Total recall logging under ## EXTERNAL_TOOL_INJECTION
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - runtime dependency check
    FastMCP = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
BRAIN = ROOT / "G-Codex-brain"
DYNAMIC_MEMORY_PATH = BRAIN / "DYNAMIC_MEMORY.md"
ROADMAP_PATH = BRAIN / "ROADMAP.md"
ACTIVE_NOW_PATH = BRAIN / "03_ACTIVE_NOW.md"
USER_DOMAIN_NODES_PATH = BRAIN / "user_domain_nodes.json"
NODE_MANIFEST_PATH = BRAIN / "NODE_MANIFEST.json"
PERSONALITY_STATE_PATH = ROOT / ".md_core_state.json"
DASHBOARD_PATH = ROOT / "scripts" / "named_agent_dashboard.html"
BRAIN_SERVER_PATH = ROOT / "scripts" / "brain_server.py"
PROPOSAL_OUTCOMES_PATH = BRAIN / "PROPOSAL_OUTCOMES.md"
BRAIN_SERVER_BASE_URL = os.environ.get("GCODEX_BRAIN_SERVER_URL", "http://127.0.0.1:8765").rstrip("/")
ANTIGRAVITY_CONFIG_PATH = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
ANTIGRAVITY_CLIENT_NAME = os.environ.get("GCODEX_MCP_CLIENT_NAME", "Antigravity")
ANTIGRAVITY_AGENT_NAME = "AGa"
ANTIGRAVITY_LOG_SOURCE = "Antigravity"

MD_GATEKEEPER_DENIED = "403: MD Authorization Required"

DOMAIN_SCAN_HINTS = {
    "isan_study": (
        "isan",
        "thai",
        "teacher",
        "grammar",
        "dialect",
    ),
    "marine_systems": (
        "marine",
        "reef",
        "reefsys",
        "aqua one",
        "aquarium",
        "water chemistry",
    ),
}
DOMAIN_SCAN_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".log",
    ".py",
}
DOMAIN_SCAN_SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".cache",
    "dist",
    "build",
    "target",
}
DEFAULT_USER_DOMAIN_NODES = ("isan_study", "marine_systems")
GITHUB_MCP_IMAGE = "ghcr.io/github/github-mcp-server"
GITHUB_READ_ONLY_TOOLSETS = "repos,issues,pull_requests"
GITHUB_STATUS_TTL_SEC = 45.0
GITHUB_META_SCAN_TTL_SEC = 21600.0
GITHUB_LOG_COOLDOWN_SEC = 60.0


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compact(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(1, limit - 3)].rstrip()}..."


def _normalize_domain_node(value: Any) -> str:
    key = _compact(str(value or ""), limit=120).lower()
    key = re.sub(r"[^a-z0-9_]+", "_", key).strip("_")
    return key


def _safe_datetime(value: str) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _humanize_timestamp(value: str) -> str:
    parsed = _safe_datetime(value)
    if not parsed:
        return "unavailable"
    delta = dt.datetime.now(dt.timezone.utc) - parsed
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    return parsed.strftime("%Y-%m-%d")


def _run_git_cmd(repo_root: Path, args: list[str], timeout_sec: float = 2.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return int(proc.returncode), (proc.stdout or "").strip()


def _parse_github_repo_slug(remote_url: str) -> str:
    raw = str(remote_url or "").strip()
    if not raw:
        return ""
    match = re.search(
        r"github\.com[:/](?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$",
        raw,
    )
    if not match:
        return ""
    return f"{match.group('owner')}/{match.group('repo')}"


def _detect_preferred_remote(repo_root: Path) -> str:
    code, upstream_ref = _run_git_cmd(
        repo_root,
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        timeout_sec=2.0,
    )
    if code == 0 and upstream_ref and "/" in upstream_ref:
        return upstream_ref.split("/", 1)[0].strip()
    return ""


def _detect_github_repo_binding(repo_root: Path) -> dict[str, str]:
    preferred_remote = _detect_preferred_remote(repo_root)
    remote_order: list[str] = []
    if preferred_remote:
        remote_order.append(preferred_remote)
    remote_order.extend(["origin", "private", "upstream"])
    code, remote_list = _run_git_cmd(repo_root, ["git", "remote"], timeout_sec=2.0)
    if code == 0 and remote_list:
        for name in remote_list.splitlines():
            item = name.strip()
            if item:
                remote_order.append(item)

    seen: set[str] = set()
    for remote_name in remote_order:
        if remote_name in seen:
            continue
        seen.add(remote_name)
        code, remote_url = _run_git_cmd(repo_root, ["git", "remote", "get-url", remote_name], timeout_sec=2.0)
        if code != 0 or not remote_url:
            continue
        slug = _parse_github_repo_slug(remote_url)
        if slug:
            return {"repo_slug": slug, "remote_name": remote_name}

    return {"repo_slug": "", "remote_name": preferred_remote}


def _ensure_user_domain_nodes_file() -> None:
    USER_DOMAIN_NODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if USER_DOMAIN_NODES_PATH.exists():
        return
    USER_DOMAIN_NODES_PATH.write_text(json.dumps(list(DEFAULT_USER_DOMAIN_NODES), indent=2) + "\n", encoding="utf-8")


def _read_user_domain_nodes() -> dict[str, Any]:
    _ensure_user_domain_nodes_file()
    source = "user_domain_nodes.json"
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

    nodes: list[str] = []
    for raw in raw_nodes if isinstance(raw_nodes, list) else []:
        normalized = _normalize_domain_node(raw)
        if not normalized or normalized in nodes:
            continue
        nodes.append(normalized)

    if not nodes:
        nodes = list(DEFAULT_USER_DOMAIN_NODES)
        source = "fallback_scan"

    return {
        "nodes": nodes,
        "source": source,
        "path": str(USER_DOMAIN_NODES_PATH.relative_to(ROOT)),
    }


@dataclass
class AccessDecision:
    allowed: bool
    reason: str


class GcodexContextService:
    """Business logic for resource and tool exposure (Phase 1 read-only)."""

    def __init__(self, bootstrap_authorized: bool = False, session_id: str | None = None) -> None:
        self._authorized = bool(bootstrap_authorized)
        self._session_id = session_id or f"mcp-{uuid.uuid4().hex[:10]}"
        self._lock = threading.Lock()
        # Keep AGa access logging deterministic for dashboard status parsing.
        self._client_source = ANTIGRAVITY_LOG_SOURCE
        self._github_status_cache: dict[str, Any] = {"checked_at": 0.0, "payload": {}}
        self._github_meta_scan_cache: dict[str, Any] = {"checked_at": 0.0, "payload": {}}
        self._compact_log_state: dict[str, float] = {}
        self._notify_brain_server_connected()

    # ---------- MD Gatekeeping ----------
    def check_md_auth(self) -> AccessDecision:
        if self._authorized:
            return AccessDecision(True, "MCP_AUTHORIZATION granted for this server session.")
        state = self._mcp_gatekeeper_status()
        session_state = str(state.get("session_state") or state.get("status", "UNAVAILABLE")).upper()
        if session_state == "AUTHORIZED":
            return AccessDecision(True, "MCP_AUTHORIZATION granted by MD gatekeeper.")
        return AccessDecision(False, f"{MD_GATEKEEPER_DENIED} (session_state={session_state})")

    def _log_external_injection(
        self,
        *,
        action_type: str,
        target: str,
        status: str,
        detail: str,
        authorized: bool,
        source: str = "",
    ) -> None:
        source_name = _compact(source or self._client_source, limit=80) or ANTIGRAVITY_LOG_SOURCE
        block = "\n".join(
            [
                "## EXTERNAL_TOOL_INJECTION",
                f"- timestamp: {_utc_now()}",
                f"- source: {source_name}",
                f"- session_id: {self._session_id}",
                f"- action_type: {action_type}",
                f"- target: {target}",
                f"- status: {status}",
                f"- authorized: {'true' if authorized else 'false'}",
                f"- detail: {_compact(detail, limit=360) or '(none)'}",
            ]
        )
        self._append_dynamic_memory_entry(block)

    def _append_dynamic_memory_entry(self, block: str) -> None:
        with self._lock:
            DYNAMIC_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            if DYNAMIC_MEMORY_PATH.exists():
                current = DYNAMIC_MEMORY_PATH.read_text(encoding="utf-8")
            else:
                current = "# DYNAMIC MEMORY\n\n"
            if current and not current.endswith("\n"):
                current += "\n"
            current += "\n" + block.strip() + "\n"
            DYNAMIC_MEMORY_PATH.write_text(current, encoding="utf-8")

    # ---------- Internal helpers ----------
    def _guard(self, action_type: str, target: str) -> AccessDecision:
        decision = self.check_md_auth()
        if not decision.allowed:
            self._log_external_injection(
                action_type=action_type,
                target=target,
                status="DENIED",
                detail=decision.reason,
                authorized=False,
            )
        return decision

    def _read_text_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _brain_server_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout_sec: float = 6.0,
    ) -> tuple[dict[str, Any], int]:
        url = f"{BRAIN_SERVER_BASE_URL}{path}"
        body = b""
        headers = {"Content-Type": "application/json", "X-GCodex-Source": "mcp-server"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url=url, data=body if method.upper() != "GET" else None, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                status_code = int(getattr(response, "status", 200))
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as err:
            status_code = int(getattr(err, "code", 500))
            raw = err.read().decode("utf-8") if hasattr(err, "read") else ""
        except (urllib.error.URLError, TimeoutError):
            return {"ok": False, "error": "brain_server_unreachable"}, 0

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": "brain_server_invalid_json"}
        return parsed if isinstance(parsed, dict) else {"ok": False, "error": "brain_server_invalid_payload"}, status_code

    def _mcp_gatekeeper_status(self) -> dict[str, Any]:
        payload, status = self._brain_server_json(method="GET", path="/mcp/status")
        if status != 200:
            return {"status": "UNAVAILABLE", "context_release_allowed": False}
        mcp = payload.get("mcp")
        if isinstance(mcp, dict):
            return mcp
        return {"status": "UNAVAILABLE", "context_release_allowed": False}

    def _notify_brain_server_connected(self) -> None:
        # Heartbeat to notify brain server that an MCP client process has started and connected.
        self._brain_server_json(method="POST", path="/mcp/heartbeat")

    def _run_cmd(self, args: list[str], *, timeout_sec: float = 4.0) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                args,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except (OSError, subprocess.SubprocessError):
            return 1, "", ""
        return int(proc.returncode), (proc.stdout or "").strip(), (proc.stderr or "").strip()

    def _resolve_github_token(self) -> str:
        for env_name in ("GITHUB_PERSONAL_ACCESS_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            value = str(os.environ.get(env_name, "") or "").strip()
            if value:
                return value
        if not shutil.which("gh"):
            return ""
        rc, out, _err = self._run_cmd(["gh", "auth", "token"], timeout_sec=2.5)
        if rc != 0:
            return ""
        return out.strip()

    def _git_last_commit(self) -> tuple[str, str, str]:
        rc, out, _err = self._run_cmd(["git", "log", "-1", "--pretty=format:%H%n%s%n%cI"], timeout_sec=3.0)
        if rc != 0 or not out:
            return "", "", ""
        lines = out.splitlines()
        commit_sha = (lines[0].strip() if lines else "")[:7]
        commit_msg = _compact(lines[1].strip() if len(lines) > 1 else "", limit=120)
        commit_iso = lines[2].strip() if len(lines) > 2 else ""
        return commit_sha, commit_msg, commit_iso

    def _git_default_branch(self, remote_name: str = "") -> str:
        preferred_remote = _compact(remote_name, 64)
        remote_candidates = [item for item in (preferred_remote, "origin", "private") if item]
        checked: set[str] = set()
        for remote in remote_candidates:
            if remote in checked:
                continue
            checked.add(remote)
            rc, out, _err = self._run_cmd(
                ["git", "symbolic-ref", f"refs/remotes/{remote}/HEAD"],
                timeout_sec=2.0,
            )
            if rc == 0 and out:
                ref = out.strip().split("/")[-1]
                if ref:
                    return ref
        rc, out, _err = self._run_cmd(["git", "branch", "--show-current"], timeout_sec=2.0)
        if rc == 0:
            return _compact(out, 80)
        rc, out, _err = self._run_cmd(["git", "symbolic-ref", "--short", "HEAD"], timeout_sec=2.0)
        if rc == 0:
            return _compact(out, 80)
        return ""

    def _git_ahead_behind(self) -> dict[str, int] | None:
        rc, out, _err = self._run_cmd(["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"], timeout_sec=2.5)
        if rc != 0 or not out:
            return None
        parts = out.split()
        if len(parts) != 2:
            return None
        try:
            ahead = int(parts[0])
            behind = int(parts[1])
        except ValueError:
            return None
        return {"ahead": ahead, "behind": behind}

    def _gh_repo_status(self, repo_slug: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if not repo_slug or not shutil.which("gh"):
            return result

        rc, out, _err = self._run_cmd(
            ["gh", "repo", "view", repo_slug, "--json", "defaultBranchRef,pushedAt"],
            timeout_sec=3.5,
        )
        if rc == 0 and out:
            try:
                payload = json.loads(out)
            except json.JSONDecodeError:
                payload = {}
            default_ref = payload.get("defaultBranchRef")
            if isinstance(default_ref, dict):
                result["default_branch"] = _compact(str(default_ref.get("name", "") or ""), 80)
            pushed_at = _compact(str(payload.get("pushedAt", "") or ""), 80)
            if pushed_at:
                result["last_pushed_iso"] = pushed_at

        rc, out, _err = self._run_cmd(["gh", "api", f"repos/{repo_slug}", "--jq", ".open_issues_count"], timeout_sec=3.5)
        if rc == 0 and out:
            try:
                result["open_issues_count"] = int(str(out).strip())
            except ValueError:
                pass
        return result

    def _github_meta_toolset_scan(self, *, force: bool = False) -> dict[str, Any]:
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        cached_at = float(self._github_meta_scan_cache.get("checked_at") or 0.0)
        if not force and (now - cached_at) <= GITHUB_META_SCAN_TTL_SEC:
            cached_payload = self._github_meta_scan_cache.get("payload", {})
            return cached_payload if isinstance(cached_payload, dict) else {}

        scan = {
            "repo": "github/github-mcp-server",
            "checked_at": _utc_now(),
            "scan_status": "UNAVAILABLE",
            "requested_toolsets": GITHUB_READ_ONLY_TOOLSETS,
            "found_toolsets": [],
        }
        readme_url = "https://raw.githubusercontent.com/github/github-mcp-server/main/README.md"
        try:
            with urllib.request.urlopen(readme_url, timeout=3.5) as response:
                body = response.read(96_000).decode("utf-8", errors="ignore").lower()
        except (urllib.error.URLError, TimeoutError):
            body = ""

        if body:
            found: list[str] = []
            if "repos" in body:
                found.append("repos")
            if "issues" in body:
                found.append("issues")
            if "pull_requests" in body or "pull requests" in body:
                found.append("pull_requests")
            scan["scan_status"] = "OK"
            scan["found_toolsets"] = found
        else:
            scan["scan_status"] = "UNAVAILABLE"
            scan["found_toolsets"] = []

        self._github_meta_scan_cache = {"checked_at": now, "payload": scan}
        return scan

    def _should_emit_compact_log(self, key: str) -> bool:
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        last = float(self._compact_log_state.get(key) or 0.0)
        if now - last < GITHUB_LOG_COOLDOWN_SEC:
            return False
        self._compact_log_state[key] = now
        return True

    def _github_status_payload(self, *, force: bool = False) -> dict[str, Any]:
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        cached_at = float(self._github_status_cache.get("checked_at") or 0.0)
        if not force and (now - cached_at) <= GITHUB_STATUS_TTL_SEC:
            cached_payload = self._github_status_cache.get("payload", {})
            return cached_payload if isinstance(cached_payload, dict) else {}

        binding = _detect_github_repo_binding(ROOT)
        repo_slug = _compact(binding.get("repo_slug", ""), 160)
        remote_name = _compact(binding.get("remote_name", ""), 64)
        commit_sha, commit_message, commit_iso = self._git_last_commit()
        default_branch = self._git_default_branch(remote_name=remote_name)
        ahead_behind = self._git_ahead_behind()
        open_issues_count = None
        pushed_iso = commit_iso
        gh_data: dict[str, Any] = {}
        if repo_slug:
            gh_data = self._gh_repo_status(repo_slug)
            default_branch = _compact(str(gh_data.get("default_branch", "") or default_branch), 80)
            pushed_iso = _compact(str(gh_data.get("last_pushed_iso", "") or pushed_iso), 80)
            issues_value = gh_data.get("open_issues_count")
            if isinstance(issues_value, int):
                open_issues_count = issues_value

        docker_available = bool(shutil.which("docker"))
        gh_available = bool(shutil.which("gh"))
        token_available = bool(self._resolve_github_token())
        if docker_available and token_available:
            active_path = "docker_mcp"
        elif gh_available:
            active_path = "gh_cli_fallback"
        else:
            active_path = "unavailable"

        meta_scan = self._github_meta_toolset_scan(force=False)
        local_repo_recognized = bool((ROOT / ".git").exists())
        repo_field = repo_slug if repo_slug else (f"local:{ROOT.name}" if local_repo_recognized else None)
        payload = {
            "default_branch": default_branch or None,
            "last_commit_sha": commit_sha or None,
            "last_commit_message": _compact(commit_message, limit=120) if commit_message else None,
            "last_pushed_at": _humanize_timestamp(pushed_iso),
            "ahead_behind": ahead_behind,
            "open_issues_count": open_issues_count,
            "active_path": active_path,
            "repo": repo_field,
            "remote_name": remote_name or None,
            "meta_toolset_scan": {
                "repo": meta_scan.get("repo", "github/github-mcp-server"),
                "scan_status": meta_scan.get("scan_status", "UNAVAILABLE"),
                "found_toolsets": meta_scan.get("found_toolsets", []),
                "checked_at": meta_scan.get("checked_at", ""),
            },
        }
        self._github_status_cache = {"checked_at": now, "payload": payload}
        return payload

    def _extract_blocks(self, text: str, *, headers: set[str], limit: int = 8) -> list[dict[str, str]]:
        lines = text.splitlines()
        blocks: list[tuple[str, list[str]]] = []
        current_header = ""
        current_lines: list[str] = []
        for line in lines:
            if line.startswith("## "):
                if current_header:
                    blocks.append((current_header, current_lines))
                current_header = line[3:].strip()
                current_lines = []
            elif current_header:
                current_lines.append(line)
        if current_header:
            blocks.append((current_header, current_lines))

        selected = [item for item in blocks if item[0] in headers][-limit:]
        result: list[dict[str, str]] = []
        for header, payload_lines in selected:
            payload = "\n".join(payload_lines).strip()
            ts_match = re.search(r"-\s*timestamp:\s*(.+)", payload)
            result.append(
                {
                    "header": header,
                    "timestamp": ts_match.group(1).strip() if ts_match else "",
                    "summary": _compact(payload, limit=260),
                }
            )
        return result

    def _domain_node_registry(self) -> dict[str, Any]:
        return _read_user_domain_nodes()

    def _domain_hint_terms(self, node_key: str) -> tuple[str, ...]:
        normalized = _normalize_domain_node(node_key)
        static_hints = tuple(DOMAIN_SCAN_HINTS.get(normalized, ()))
        if static_hints:
            return static_hints
        split_hints = tuple(part for part in normalized.replace("-", "_").split("_") if part)
        return split_hints or (normalized,)

    def _persona_alignment(self, text_parts: list[str] | tuple[str, ...], registry: dict[str, Any] | None = None) -> dict[str, Any]:
        effective_registry = registry if isinstance(registry, dict) else self._domain_node_registry()
        active_nodes = [str(item) for item in effective_registry.get("nodes", []) if str(item).strip()]
        source = _compact(str(effective_registry.get("source", "") or "fallback_scan"), 80)
        combined = " ".join(_compact(item, 400) for item in text_parts if item).lower()

        matched_nodes: list[str] = []
        for node in active_nodes:
            hints = self._domain_hint_terms(node)
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

        return {
            "label": label,
            "score": int(score),
            "matched_nodes": matched_nodes,
            "active_nodes": active_nodes,
            "source": source or "fallback_scan",
            "summary": f"{label} [{', '.join(matched_nodes) if matched_nodes else 'none'}]",
        }

    def _collect_domain_context(self, domain_key: str) -> dict[str, Any]:
        registry = self._domain_node_registry()
        hints = self._domain_hint_terms(domain_key)
        files: list[dict[str, str]] = []
        max_files = 16
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [name for name in dirnames if name not in DOMAIN_SCAN_SKIP_DIRS]
            for filename in filenames:
                candidate = Path(dirpath) / filename
                suffix = candidate.suffix.lower()
                if suffix and suffix not in DOMAIN_SCAN_EXTENSIONS:
                    continue
                try:
                    if candidate.stat().st_size > 512_000:
                        continue
                    content = candidate.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                rel_path = str(candidate.relative_to(ROOT))
                searchable = f"{rel_path} {content[:6000]}".lower()
                if hints and not any(hint in searchable for hint in hints):
                    continue
                excerpt = _compact(content, limit=240)
                files.append(
                    {
                        "path": rel_path,
                        "excerpt": excerpt or "(empty text content)",
                    }
                )
                if len(files) >= max_files:
                    break
            if len(files) >= max_files:
                break
        return {
            "session_id": self._session_id,
            "domain": domain_key,
            "registered_domain_nodes": registry.get("nodes", []),
            "files_found": len(files),
            "files": files,
        }

    def _personality_payload(self) -> dict[str, Any]:
        registry = self._domain_node_registry()
        profile = {}
        summary = ""
        if PERSONALITY_STATE_PATH.exists():
            try:
                payload = json.loads(PERSONALITY_STATE_PATH.read_text(encoding="utf-8"))
                profile = payload.get("project_personality_profile", {}) or {}
                summary = str(payload.get("project_personality_summary", "") or "").strip()
            except Exception:
                profile = {}
                summary = ""
        if not isinstance(profile, dict):
            profile = {}
        alignment = self._persona_alignment([summary, json.dumps(profile, ensure_ascii=True)], registry=registry)
        return {
            "session_id": self._session_id,
            "project_personality_profile": profile,
            "project_personality_summary": summary,
            "source": str(PERSONALITY_STATE_PATH.relative_to(ROOT)),
            "registered_domain_nodes": registry.get("nodes", []),
            "persona_alignment": alignment,
        }

    def _triad_payload(self) -> dict[str, Any]:
        registry = self._domain_node_registry()
        triad_files = {
            "ROADMAP.md": ROADMAP_PATH,
            "DYNAMIC_MEMORY.md": DYNAMIC_MEMORY_PATH,
            "03_ACTIVE_NOW.md": ACTIVE_NOW_PATH,
        }
        triad: dict[str, dict[str, Any]] = {}
        for label, path in triad_files.items():
            exists = path.exists()
            triad[label] = {
                "path": str(path.relative_to(ROOT)),
                "exists": exists,
                "content": path.read_text(encoding="utf-8") if exists else "",
                "last_modified_utc": dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if exists else "",
            }
        alignment_inputs = []
        for label, item in triad.items():
            alignment_inputs.append(label)
            alignment_inputs.append(_compact(str(item.get("content", "")), limit=800))
        alignment = self._persona_alignment(alignment_inputs, registry=registry)
        return {
            "session_id": self._session_id,
            "deep_sea_mode": {
                "local_first": True,
                "ollama_cli_detected": bool(shutil.which("ollama")),
            },
            "registered_domain_nodes": registry.get("nodes", []),
            "persona_alignment": alignment,
            "triad": triad,
        }

    def _styles_payload(self) -> dict[str, Any]:
        html = self._read_text_file(DASHBOARD_PATH)
        css_vars = sorted(
            {
                f"--{name.strip()}": value.strip()
                for name, value in re.findall(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+);", html)
            }.items(),
            key=lambda item: item[0],
        )
        js_functions = sorted(set(re.findall(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", html)))
        return {
            "session_id": self._session_id,
            "path": str(DASHBOARD_PATH.relative_to(ROOT)),
            "css_variables": [{"name": name, "value": value} for name, value in css_vars],
            "js_entry_points": js_functions,
        }

    def _live_activity_payload(self) -> dict[str, Any]:
        registry = self._domain_node_registry()
        text = self._read_text_file(DYNAMIC_MEMORY_PATH)
        blocks = self._extract_blocks(
            text,
            headers={
                "CLI_OUTPUT",
                "GCODEX_BRIDGE_INJECTION",
                "EXTERNAL_TOOL_INJECTION",
                "SESSION_LOG_ENTRY",
            },
            limit=12,
        )
        alignment = self._persona_alignment(
            [item.get("summary", "") for item in blocks],
            registry=registry,
        )
        return {
            "session_id": self._session_id,
            "path": str(DYNAMIC_MEMORY_PATH.relative_to(ROOT)),
            "registered_domain_nodes": registry.get("nodes", []),
            "persona_alignment": alignment,
            "events": blocks,
        }

    # ---------- MCP Resources ----------
    def resource_dashboard(self) -> str:
        target = "/repository/dashboard"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return MD_GATEKEEPER_DENIED
        payload = self._read_text_file(DASHBOARD_PATH)
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail="Read-only dashboard HTML returned.",
            authorized=True,
        )
        return payload

    def resource_brain_server(self) -> str:
        target = "/repository/brain_server"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return MD_GATEKEEPER_DENIED
        payload = self._read_text_file(BRAIN_SERVER_PATH)
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail="Read-only brain_server.py source returned.",
            authorized=True,
        )
        return payload

    def resource_context_personality(self) -> dict[str, Any]:
        target = "/context/personality"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}
        payload = self._personality_payload()
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail="Read-only project personality payload returned.",
            authorized=True,
        )
        return payload

    def resource_context_triad(self) -> dict[str, Any]:
        target = "/context/triad"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}
        payload = self._triad_payload()
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail="Read-only Triad of Truth payload returned.",
            authorized=True,
        )
        return payload

    def resource_repository_styles(self) -> dict[str, Any]:
        target = "/repository/styles"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}
        payload = self._styles_payload()
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail="Read-only dashboard style dictionary returned.",
            authorized=True,
        )
        return payload

    def resource_live_activity(self) -> dict[str, Any]:
        target = "/context/live_activity"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}
        payload = self._live_activity_payload()
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail="Read-only live activity payload returned.",
            authorized=True,
        )
        return payload

    def resource_context_isan_study(self) -> dict[str, Any]:
        target = "/context/isan_study"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}
        payload = self._collect_domain_context("isan_study")
        payload["persona_alignment"] = self._persona_alignment(
            [item.get("excerpt", "") for item in payload.get("files", [])],
            registry=self._domain_node_registry(),
        )
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail=f"Read-only Isan study context returned ({payload.get('files_found', 0)} files).",
            authorized=True,
        )
        return payload

    def resource_context_marine_systems(self) -> dict[str, Any]:
        target = "/context/marine_systems"
        decision = self._guard("resource_read", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}
        payload = self._collect_domain_context("marine_systems")
        payload["persona_alignment"] = self._persona_alignment(
            [item.get("excerpt", "") for item in payload.get("files", [])],
            registry=self._domain_node_registry(),
        )
        self._log_external_injection(
            action_type="resource_read",
            target=target,
            status="ALLOWED",
            detail=f"Read-only marine systems context returned ({payload.get('files_found', 0)} files).",
            authorized=True,
        )
        return payload

    def resource_github_status(self) -> dict[str, Any]:
        target = "/github/status"
        decision = self.check_md_auth()
        if not decision.allowed:
            self._log_external_injection(
                action_type="resource_read",
                target=target,
                status="DENIED",
                detail=decision.reason,
                authorized=False,
                source="GitHub MCP",
            )
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        payload = self._github_status_payload(force=False)
        detail = (
            f"path={payload.get('active_path') or 'unavailable'}; "
            f"repo={payload.get('repo') or 'unknown'}; "
            f"branch={payload.get('default_branch') or 'unknown'}; "
            f"commit={payload.get('last_commit_sha') or 'unknown'}; "
            f"push={payload.get('last_pushed_at') or 'unavailable'}"
        )
        if self._should_emit_compact_log(f"github_status:{payload.get('active_path')}:{payload.get('last_commit_sha')}"):
            self._log_external_injection(
                action_type="resource_read",
                target=target,
                status="ALLOWED",
                detail=detail,
                authorized=True,
                source="GitHub MCP",
            )
        meta_scan = payload.get("meta_toolset_scan", {})
        if isinstance(meta_scan, dict):
            scan_key = (
                f"github_meta_scan:{meta_scan.get('scan_status')}:{','.join(meta_scan.get('found_toolsets', []))}"
            )
            if self._should_emit_compact_log(scan_key):
                self._log_external_injection(
                    action_type="github_meta_scan",
                    target="repo:github/github-mcp-server",
                    status=str(meta_scan.get("scan_status") or "UNAVAILABLE"),
                    detail=(
                        f"Minimal discovery check complete. Found toolsets: "
                        f"{', '.join(meta_scan.get('found_toolsets', [])) or 'none'}."
                    ),
                    authorized=True,
                    source="GitHub MCP",
                )
        return payload

    # ---------- MCP Tools ----------
    def run_health_check(self) -> dict[str, Any]:
        target = "tool:run_health_check"
        decision = self._guard("tool_call", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        git_dirty = False
        git_summary = ""
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            git_summary = proc.stdout.strip()
            git_dirty = bool(git_summary)
        except Exception:
            git_summary = "git status unavailable"

        triad_exists = all(path.exists() for path in (ROADMAP_PATH, DYNAMIC_MEMORY_PATH, ACTIVE_NOW_PATH))
        health = "green" if triad_exists and not git_dirty else "yellow" if triad_exists else "red"
        payload = {
            "status": "OK",
            "health": health,
            "triad_present": triad_exists,
            "git_dirty": git_dirty,
            "git_summary_excerpt": _compact(git_summary, 280),
        }
        self._log_external_injection(
            action_type="tool_call",
            target=target,
            status="ALLOWED",
            detail=f"Health check returned {health}.",
            authorized=True,
        )
        return payload

    def get_mission_templates(self) -> dict[str, Any]:
        target = "tool:get_mission_templates"
        decision = self._guard("tool_call", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        active_now = self._read_text_file(ACTIVE_NOW_PATH)
        suggested = [
            "Calm visual polish pass in scripts/named_agent_dashboard.html",
            "Low-adventure reliability pass in scripts/brain_server.py",
            "Surgical docs sync for first-run guidance",
        ]
        for line in active_now.splitlines():
            stripped = line.strip()
            if re.match(r"^\d+\.\s+", stripped):
                suggested.append(re.sub(r"^\d+\.\s+", "", stripped))
        payload = {
            "status": "OK",
            "templates": suggested[:8],
            "source": str(ACTIVE_NOW_PATH.relative_to(ROOT)),
        }
        self._log_external_injection(
            action_type="tool_call",
            target=target,
            status="ALLOWED",
            detail="Mission templates returned for low-adventure planning.",
            authorized=True,
        )
        return payload

    def audit_layout(self) -> dict[str, Any]:
        target = "tool:audit_layout"
        decision = self._guard("tool_call", target)
        if not decision.allowed:
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}
        payload = {
            "status": "PENDING_WIRING",
            "message": "AGa visual pass pending wiring in a later phase.",
        }
        self._log_external_injection(
            action_type="tool_call",
            target=target,
            status="ALLOWED_STUB",
            detail="audit_layout returned safe stub response.",
            authorized=True,
        )
        return payload

    def propose_design(
        self,
        proposal_summary: str,
        proposal_body: str = "",
        source_tool: str = "Google Stitch",
        target_files: str = "",
        design_payload_excerpt: str = "",
    ) -> dict[str, Any]:
        target = "tool:propose_design"
        mcp_state = self._mcp_gatekeeper_status()
        session_state = str(mcp_state.get("session_state") or mcp_state.get("status", "UNAVAILABLE")).upper()
        if session_state != "AUTHORIZED":
            denied_message = "403: MD Authorization Required"
            self._log_external_injection(
                action_type="tool_call",
                target=target,
                status="DENIED",
                detail=f"propose_design blocked: {denied_message} (session_state={session_state})",
                authorized=False,
            )
            return {
                "status": "DENIED",
                "message": denied_message,
                "session_state": session_state,
            }

        ingress_payload = {
            "source_tool": _compact(source_tool, 80) or "Google Stitch",
            "session_id": self._session_id,
            "summary": _compact(proposal_summary, 260),
            "target_files": target_files,
            "design_payload_excerpt": _compact(design_payload_excerpt or proposal_body, 420),
            "proposal_body": _compact(proposal_body, 420),
        }
        persona_alignment = self._persona_alignment(
            [
                ingress_payload["summary"],
                ingress_payload["target_files"],
                ingress_payload["design_payload_excerpt"],
                ingress_payload["proposal_body"],
            ],
            registry=self._domain_node_registry(),
        )
        ingress_payload["persona_alignment"] = persona_alignment
        ingress_response, ingress_status = self._brain_server_json(
            method="POST",
            path="/mcp/design-ingress",
            payload=ingress_payload,
        )
        if ingress_status != 200 or not bool(ingress_response.get("ok")):
            message = str(ingress_response.get("error", "design ingress failed")).strip() or "design ingress failed"
            self._log_external_injection(
                action_type="tool_call",
                target=target,
                status="ERROR",
                detail=f"Design ingress failed: {message}",
                authorized=True,
            )
            return {
                "status": "ERROR",
                "message": message,
            }

        proposal = ingress_response.get("proposal") if isinstance(ingress_response.get("proposal"), dict) else {}
        confirmation = str(
            ingress_response.get("message")
            or proposal.get("message")
            or f"Proposal [{proposal.get('proposal_id', '(unknown)')}] received and queued for MD review in PROPOSAL_OUTCOMES.md."
        ).strip()
        payload = {
            "status": "QUEUED",
            "message": confirmation,
            "proposal_id": proposal.get("proposal_id", ""),
            "proposal_outcomes_path": str(PROPOSAL_OUTCOMES_PATH.relative_to(ROOT)),
            "session_state": session_state,
        }
        self._log_external_injection(
            action_type="tool_call",
            target=target,
            status="QUEUED",
            detail=f"{confirmation} Persona alignment: {persona_alignment.get('summary', 'LOW [none]')} ({persona_alignment.get('source', 'fallback_scan')}).",
            authorized=True,
        )
        return payload

    def resource_github_create_issue(
        self,
        title: str,
        body: str,
        labels: str = "low-adventure,md-proposal",
        milestone: str = "",
    ) -> dict[str, Any]:
        target = "/github/create-issue"
        decision = self.check_md_auth()
        if not decision.allowed:
            self._log_external_injection(
                action_type="github_issue_creation",
                target=target,
                status="DENIED",
                detail=decision.reason,
                authorized=False,
                source="GitHub MCP",
            )
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        cmd = ["gh", "issue", "create", "--title", title, "--body", body]
        if labels:
            for label in [l.strip() for l in labels.split(",") if l.strip()]:
                cmd.extend(["--label", label])
        if milestone:
            cmd.extend(["--milestone", milestone])

        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or "Unknown gh error"
                self._log_external_injection(
                    action_type="github_issue_creation",
                    target=target,
                    status="ERROR",
                    detail=f"Failed to create issue: {err}",
                    authorized=True,
                    source="GitHub MCP",
                )
                return {"status": "ERROR", "message": f"GitHub issue creation failed: {err}"}

            issue_url = proc.stdout.strip()
            self._log_external_injection(
                action_type="github_issue_creation",
                target=target,
                status="CREATED",
                detail=f"Issue created: {issue_url}",
                authorized=True,
                source="GitHub MCP",
            )
            return {
                "status": "OK",
                "issue_url": issue_url,
                "message": f"GitHub issue created successfully: {issue_url}",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Subprocess error: {e}"}

    def resource_github_list_prs(self) -> dict[str, Any]:
        target = "/github/list-prs"
        decision = self.check_md_auth()
        if not decision.allowed:
            self._log_external_injection(
                action_type="github_pr_list",
                target=target,
                status="DENIED",
                detail=decision.reason,
                authorized=False,
                source="GitHub MCP",
            )
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        cmd = ["gh", "pr", "list", "--state", "open", "--json", "number,title,author,url,createdAt,state"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or "Unknown gh error"
                return {"status": "ERROR", "message": f"GitHub PR list failed: {err}"}

            prs = json.loads(proc.stdout.strip())
            self._log_external_injection(
                action_type="github_pr_list",
                target=target,
                status="OK",
                detail=f"Found {len(prs)} open PRs.",
                authorized=True,
                source="GitHub MCP",
            )
            return {
                "status": "OK",
                "prs": prs,
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Subprocess error: {e}"}

    def resource_github_pr_details(self, number: str) -> dict[str, Any]:
        target = f"/github/pr-details?number={number}"
        decision = self.check_md_auth()
        if not decision.allowed:
            self._log_external_injection(
                action_type="github_pr_details",
                target=target,
                status="DENIED",
                detail=decision.reason,
                authorized=False,
                source="GitHub MCP",
            )
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        cmd = ["gh", "pr", "view", number, "--json", "number,title,body,baseRefName,headRefName,state,url,createdAt"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or "Unknown gh error"
                return {"status": "ERROR", "message": f"GitHub PR details failed: {err}"}

            pr_details = json.loads(proc.stdout.strip())
            self._log_external_injection(
                action_type="github_pr_details",
                target=target,
                status="OK",
                detail=f"PR #{number} details retrieved.",
                authorized=True,
                source="GitHub MCP",
            )
            return {
                "status": "OK",
                "pr": pr_details,
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Subprocess error: {e}"}

    def resource_github_post_pr_comment(self, pr_number: str, body: str) -> dict[str, Any]:
        target = f"/github/post-pr-comment?number={pr_number}"
        decision = self.check_md_auth()
        if not decision.allowed:
            self._log_external_injection(
                action_type="github_pr_comment",
                target=target,
                status="DENIED",
                detail=decision.reason,
                authorized=False,
                source="GitHub MCP",
            )
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        signature = "✦ Sovereign Assessment by G-Codex MD"
        final_body = str(body or "").strip()
        if signature not in final_body:
            final_body = f"{final_body}\n\n{signature}"

        cmd = ["gh", "pr", "comment", pr_number, "--body", final_body]
        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or "Unknown gh error"
                self._log_external_injection(
                    action_type="github_pr_comment",
                    target=target,
                    status="ERROR",
                    detail=f"Failed to post comment: {err}",
                    authorized=True,
                    source="GitHub MCP",
                )
                return {"status": "ERROR", "message": f"GitHub PR comment failed: {err}"}

            output = proc.stdout.strip()
            self._log_external_injection(
                action_type="github_pr_comment",
                target=target,
                status="OK",
                detail=f"Comment posted to PR #{pr_number}.",
                authorized=True,
                source="GitHub MCP",
            )
            return {
                "status": "OK",
                "message": f"Comment posted to PR #{pr_number}.",
                "url": output,
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Subprocess error: {e}"}

    def resource_github_meta_scan(self) -> dict[str, Any]:
        target = "/github/meta-scan"
        decision = self.check_md_auth()
        if not decision.allowed:
            self._log_external_injection(
                action_type="github_meta_scan",
                target=target,
                status="DENIED",
                detail=decision.reason,
                authorized=False,
                source="GitHub MCP",
            )
            return {"status": "DENIED", "message": MD_GATEKEEPER_DENIED}

        scan = self._github_meta_toolset_scan(force=True)
        self._log_external_injection(
            action_type="github_meta_scan",
            target=target,
            status="OK",
            detail=f"Official repo scan complete. Toolsets: {', '.join(scan.get('found_toolsets', []))}",
            authorized=True,
            source="GitHub MCP",
        )
        return {
            "status": "OK",
            "meta_scan": scan,
        }

    def sync_agent_state(
        self,
        *,
        agent_name: str,
        focus: str,
        source_tool: str = "Antigravity",
        session_label: str = "",
        next_action: str = "",
        files_touched: str = "",
    ) -> dict[str, Any]:
        target = "tool:sync_agent_state"
        mcp_state = self._mcp_gatekeeper_status()
        session_state = str(mcp_state.get("session_state") or mcp_state.get("status", "UNAVAILABLE")).upper()
        if session_state != "AUTHORIZED":
            denied_message = MD_GATEKEEPER_DENIED
            self._log_external_injection(
                action_type="tool_call",
                target=target,
                status="DENIED",
                detail=f"sync_agent_state blocked: {denied_message} (session_state={session_state})",
                authorized=False,
            )
            return {
                "status": "DENIED",
                "message": denied_message,
                "session_state": session_state,
            }

        detail = (
            f"agent={_compact(agent_name, 80) or 'unknown'}; "
            f"focus={_compact(focus, 220) or '(none)'}; "
            f"next_action={_compact(next_action, 160) or '(none)'}; "
            f"files_touched={_compact(files_touched, 180) or '(none)'}; "
            f"session_label={_compact(session_label, 80) or '(none)'}; "
            f"source_tool={_compact(source_tool, 80) or 'Antigravity'}"
        )
        persona_alignment = self._persona_alignment(
            [focus, next_action, files_touched, session_label, source_tool],
            registry=self._domain_node_registry(),
        )
        self._log_external_injection(
            action_type="tool_call",
            target=target,
            status="SYNCED",
            detail=(
                f"{detail}; persona_alignment={persona_alignment.get('summary', 'LOW [none]')}; "
                f"persona_layer={persona_alignment.get('source', 'fallback_scan')}"
            ),
            authorized=True,
        )
        return {
            "status": "SYNCED",
            "message": "Agent state synced to DYNAMIC_MEMORY.md under EXTERNAL_TOOL_INJECTION.",
            "session_id": self._session_id,
            "session_state": session_state,
            "persona_alignment": persona_alignment,
        }


def _build_antigravity_mcp_config(repo_root: Path) -> dict[str, Any]:
    scripts_path = repo_root / "scripts"
    mcp_server_path = scripts_path / "mcp_server.py"
    binding = _detect_github_repo_binding(repo_root)
    repo_slug = _compact(binding.get("repo_slug", ""), 160)
    github_fallback_args = ["repo", "view"]
    if repo_slug:
        github_fallback_args.append(repo_slug)
    github_fallback_args.extend(["--json", "defaultBranchRef,pushedAt"])

    github_server = {
        "command": "docker",
        "args": [
            "run",
            "-i",
            "--rm",
            "-e",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            GITHUB_MCP_IMAGE,
            "stdio",
            "--toolsets",
            GITHUB_READ_ONLY_TOOLSETS,
        ],
        "env": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}",
        },
        "mode": "read_only",
        "toolsets": GITHUB_READ_ONLY_TOOLSETS,
        "fallback": {
            "mode": "gh_cli_read_only",
            "command": "gh",
            "args": github_fallback_args,
            "note": "Used by /github/status when Docker MCP is unavailable.",
        },
    }
    return {
        "mcpServers": {
            "g-codex-brain": {
                "command": "python3",
                "args": [str(mcp_server_path)],
                "env": {
                    "PYTHONPATH": str(scripts_path),
                    "DEEP_SEA_MODE": "true",
                    "GCODEX_MCP_CLIENT_NAME": _compact(ANTIGRAVITY_CLIENT_NAME, limit=80) or "Antigravity",
                    "GCODEX_MCP_CLIENT_AGENT": ANTIGRAVITY_AGENT_NAME,
                },
                "client": {
                    "name": _compact(ANTIGRAVITY_CLIENT_NAME, limit=80) or "Antigravity",
                    "agent": ANTIGRAVITY_AGENT_NAME,
                    "authorization": "MD gatekeeper required",
                    "access_mode": "read_only_resources_until_authorized",
                    "allowed_resources": [
                        "/context/triad",
                        "/context/personality",
                        "/context/live_activity",
                        "/context/isan_study",
                        "/context/marine_systems",
                        "/github/status",
                        "/repository/dashboard",
                        "/repository/styles",
                    ],
                },
            },
            "github": github_server,
        }
    }


def _write_antigravity_mcp_config(config_path: Path, repo_root: Path) -> Path:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_antigravity_mcp_config(repo_root)
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config_path


def build_mcp_app(service: GcodexContextService):
    if FastMCP is None:
        raise RuntimeError("Missing dependency: install `mcp` Python package to run MCP server.")

    app = FastMCP("g-codex-sovereign-context-server")

    @app.resource("gcodex://repository/dashboard", name="/repository/dashboard", mime_type="text/html")
    def repository_dashboard() -> str:
        return service.resource_dashboard()

    @app.resource("gcodex://repository/brain_server", name="/repository/brain_server", mime_type="text/x-python")
    def repository_brain_server() -> str:
        return service.resource_brain_server()

    @app.resource("gcodex://context/triad", name="/context/triad", mime_type="application/json")
    def context_triad() -> dict[str, Any]:
        return service.resource_context_triad()

    @app.resource("gcodex://context/personality", name="/context/personality", mime_type="application/json")
    def context_personality() -> dict[str, Any]:
        return service.resource_context_personality()

    @app.resource("gcodex://repository/styles", name="/repository/styles", mime_type="application/json")
    def repository_styles() -> dict[str, Any]:
        return service.resource_repository_styles()

    @app.resource("gcodex://context/live_activity", name="/context/live_activity", mime_type="application/json")
    def context_live_activity() -> dict[str, Any]:
        return service.resource_live_activity()

    @app.resource("gcodex://context/isan_study", name="/context/isan_study", mime_type="application/json")
    def context_isan_study() -> dict[str, Any]:
        return service.resource_context_isan_study()

    @app.resource("gcodex://context/marine_systems", name="/context/marine_systems", mime_type="application/json")
    def context_marine_systems() -> dict[str, Any]:
        return service.resource_context_marine_systems()

    @app.resource("gcodex://github/status", name="/github/status", mime_type="application/json")
    def github_status() -> dict[str, Any]:
        return service.resource_github_status()

    @app.resource(
        "gcodex://github/create-issue?title={title}&body={body}&labels={labels}&milestone={milestone}",
        name="/github/create-issue",
        mime_type="application/json",
    )
    def github_create_issue(
        title: str,
        body: str,
        labels: str = "low-adventure,md-proposal",
        milestone: str = "",
    ) -> dict[str, Any]:
        return service.resource_github_create_issue(
            title=title,
            body=body,
            labels=labels,
            milestone=milestone,
        )

    @app.resource(
        "gcodex://github/list-prs",
        name="/github/list-prs",
        mime_type="application/json",
    )
    def github_list_prs() -> dict[str, Any]:
        return service.resource_github_list_prs()

    @app.resource(
        "gcodex://github/pr-details?number={number}",
        name="/github/pr-details",
        mime_type="application/json",
    )
    def github_pr_details(number: str) -> dict[str, Any]:
        return service.resource_github_pr_details(number=number)

    @app.resource(
        "gcodex://github/post-pr-comment?number={number}&body={body}",
        name="/github/post-pr-comment",
        mime_type="application/json",
    )
    def github_post_pr_comment(number: str, body: str) -> dict[str, Any]:
        return service.resource_github_post_pr_comment(pr_number=number, body=body)

    @app.resource(
        "gcodex://github/meta-scan",
        name="/github/meta-scan",
        mime_type="application/json",
    )
    def github_meta_scan() -> dict[str, Any]:
        return service.resource_github_meta_scan()

    @app.tool(name="run_health_check")
    def run_health_check() -> dict[str, Any]:
        return service.run_health_check()

    @app.tool(name="get_mission_templates")
    def get_mission_templates() -> dict[str, Any]:
        return service.get_mission_templates()

    @app.tool(name="audit_layout")
    def audit_layout() -> dict[str, Any]:
        return service.audit_layout()

    @app.tool(name="propose_design")
    def propose_design(
        proposal_summary: str,
        proposal_body: str = "",
        source_tool: str = "Google Stitch",
        target_files: str = "",
        design_payload_excerpt: str = "",
    ) -> dict[str, Any]:
        return service.propose_design(
            proposal_summary=proposal_summary,
            proposal_body=proposal_body,
            source_tool=source_tool,
            target_files=target_files,
            design_payload_excerpt=design_payload_excerpt,
        )

    @app.tool(name="sync_agent_state")
    def sync_agent_state(
        agent_name: str,
        focus: str,
        source_tool: str = "Antigravity",
        session_label: str = "",
        next_action: str = "",
        files_touched: str = "",
    ) -> dict[str, Any]:
        return service.sync_agent_state(
            agent_name=agent_name,
            focus=focus,
            source_tool=source_tool,
            session_label=session_label,
            next_action=next_action,
            files_touched=files_touched,
        )

    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="G-Codex MCP sovereign context server (Phase 1 foundation).")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.environ.get("GCODEX_MCP_TRANSPORT", "stdio"),
        help="MCP transport mode. stdio is sovereignty-first default.",
    )
    parser.add_argument(
        "--mount-path",
        default=os.environ.get("GCODEX_MCP_MOUNT_PATH", "/mcp"),
        help="Mount path for streamable-http transport.",
    )
    parser.add_argument(
        "--bootstrap-authorized",
        action="store_true",
        default=os.environ.get("GCODEX_MCP_BOOTSTRAP_AUTH", "").lower() in {"1", "true", "yes"},
        help="Testing helper only. Enables MD authorization at startup for this process.",
    )
    parser.add_argument(
        "--session-id",
        default=os.environ.get("GCODEX_MCP_SESSION_ID", ""),
        help="Optional explicit session id for deterministic verification.",
    )
    parser.add_argument(
        "--write-antigravity-config",
        action="store_true",
        help="Write ~/.gemini/antigravity/mcp_config.json for the current repository root and exit.",
    )
    parser.add_argument(
        "--create-github-issue",
        action="store_true",
        help="Sovereign issue creation (proxied for dashboard). Requires MD auth.",
    )
    parser.add_argument("--title", help="GitHub issue title.")
    parser.add_argument("--body", help="GitHub issue body.")
    parser.add_argument("--labels", help="Comma-separated GitHub labels.")
    parser.add_argument("--milestone", help="GitHub milestone.")
    parser.add_argument(
        "--list-prs",
        action="store_true",
        help="Sovereign PR list (proxied for dashboard). Requires MD auth.",
    )
    parser.add_argument(
        "--pr-details",
        help="Sovereign PR details by number (proxied for dashboard). Requires MD auth.",
    )
    parser.add_argument(
        "--post-pr-comment",
        help="Sovereign PR comment by number (proxied for dashboard). Requires MD auth.",
    )
    parser.add_argument(
        "--meta-scan",
        action="store_true",
        help="Sovereign discovery of new official GitHub MCP capabilities (proxied for dashboard). Requires MD auth.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.write_antigravity_config:
        written = _write_antigravity_mcp_config(ANTIGRAVITY_CONFIG_PATH, ROOT)
        print(f"Wrote Antigravity MCP config: {written}")
        return 0

    service = GcodexContextService(
        bootstrap_authorized=bool(args.bootstrap_authorized),
        session_id=(args.session_id.strip() or None),
    )

    if args.list_prs:
        result = service.resource_github_list_prs()
        print(json.dumps(result))
        return 0 if result.get("status") == "OK" else 1

    if args.pr_details:
        result = service.resource_github_pr_details(number=args.pr_details)
        print(json.dumps(result))
        return 0 if result.get("status") == "OK" else 1

    if args.post_pr_comment:
        if not args.body:
            print(json.dumps({"status": "ERROR", "message": "body is required"}))
            return 1
        result = service.resource_github_post_pr_comment(pr_number=args.post_pr_comment, body=args.body)
        print(json.dumps(result))
        return 0 if result.get("status") == "OK" else 1

    if args.meta_scan:
        result = service.resource_github_meta_scan()
        print(json.dumps(result))
        return 0 if result.get("status") == "OK" else 1

    if args.create_github_issue:
        if not args.title or not args.body:
            print(json.dumps({"status": "ERROR", "message": "title and body are required"}))
            return 1
        result = service.resource_github_create_issue(
            title=args.title,
            body=args.body,
            labels=(args.labels or "low-adventure,md-proposal"),
            milestone=(args.milestone or ""),
        )
        print(json.dumps(result))
        return 0 if result.get("status") == "OK" else 1

    if FastMCP is None:
        import sys
        print("Missing dependency: install `mcp` package (pip install mcp).", file=sys.stderr)
        return 2

    app = build_mcp_app(service)

    if args.transport == "stdio":
        app.run(transport="stdio")
        return 0
    if args.transport in {"sse", "streamable-http"}:
        app.run(transport=args.transport, mount_path=args.mount_path)
        return 0

    print(f"Unsupported transport: {args.transport}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
