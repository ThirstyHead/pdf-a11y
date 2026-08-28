"""Report enrichment with official WCAG criterion text.

Two sources, in order:
  1. ``--enrich`` : spawn the locally installed ``wcag-guidelines-mcp`` over
     stdio and call ``get-criterion`` (full W3C Understanding docs).
  2. bundled cache : ``sc_cache.json`` shipped in this package — same shape,
     captured offline from the same server. Used whenever the server is not
     available (default mode), keeping enrichment deterministic and
     dependency-free (no node required for normal runs).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

BUNDLED_CACHE = Path(__file__).resolve().parent / "sc_cache.json"
SERVER_PATH_ENV = "WCAG_MCP_PATH"
SERVER_TOOL = "get-criterion"
PROTOCOL_VERSION = "2025-03-26"


def find_server() -> Optional[Path]:
    """Locate the wcag-guidelines-mcp entrypoint.

    Order: $WCAG_MCP_PATH, npm global install, common user locations.
    """
    env = os.environ.get(SERVER_PATH_ENV)
    if env and Path(env).exists():
        return Path(env)
    if shutil.which("wcag-guidelines-mcp"):
        which_path = shutil.which("wcag-guidelines-mcp")
        if which_path:
            return Path(which_path)
    home = Path(os.path.expanduser("~"))
    candidates = [
        home / ".local/lib/node_modules/wcag-guidelines-mcp/src/index.js",
        Path("/usr/local/lib/node_modules/wcag-guidelines-mcp/src/index.js"),
        Path("/opt/homebrew/lib/node_modules/wcag-guidelines-mcp/src/index.js"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def parse_criterion(text: Optional[str]) -> dict:
    """Parse get-criterion markdown into structured fields (best effort)."""
    out = {
        "num": "", "handle": "", "level": "", "principle": "", "guideline": "",
        "in_brief": "", "description": "", "intent": "", "raw_len": len(text or ""),
    }
    if not text:
        return out
    m = re.match(r"^# (\d+\.\d+\.\d+) (.+)$", text, re.M)
    if m:
        out["num"], out["handle"] = m.group(1), m.group(2).strip()
    for key, pat in (
        ("level", r"^\*\*Level:\*\* (\S+)"),
        ("principle", r"^\*\*Principle:\*\* (.+)$"),
        ("guideline", r"^\*\*Guideline:\*\* (.+)$"),
    ):
        m = re.search(pat, text, re.M)
        if m:
            out[key] = m.group(1).strip()

    def section(name):
        m = re.search(rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        return m.group(1).strip() if m else ""

    out["in_brief"] = section("In Brief")
    out["description"] = section("Description")
    out["intent"] = section("Intent")
    return out


def _parse_jsonl_line(line: str) -> Optional[dict]:
    try:
        return json.loads(line)
    except (ValueError, TypeError):
        return None


def fetch_via_server(server: Path, sc: str, timeout: float = 20.0) -> Optional[str]:
    """Call get-criterion over stdio. Returns text or None (never raises)."""
    try:
        proc = subprocess.Popen(
            ["node", str(server)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return None
    if proc.stdin is None or proc.stdout is None:
        return None
    try:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "pdf-a11y", "version": "0.1.0"}}}
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": SERVER_TOOL, "arguments": {"ref_id": sc}}}
        initn = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        proc.stdin.write(json.dumps(init) + "\n")
        line = proc.stdout.readline()
        _parse_jsonl_line(line)
        proc.stdin.write(json.dumps(initn) + "\n")
        proc.stdin.write(json.dumps(call) + "\n")
        proc.stdin.close()
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            msg = _parse_jsonl_line(line)
            if msg and msg.get("id") == 2:
                content = msg.get("result", {}).get("content", [])
                for c in content:
                    if c.get("type") == "text":
                        return c.get("text")
                return None
    except Exception:
        return None
    finally:
        try:
            proc.kill()
        except Exception:
            pass


class Cache:
    """In-memory criterion cache (bundled + optional live lookups)."""

    def __init__(self, live: bool = False, timeout: float = 20.0):
        self.live = live
        self.timeout = timeout
        self._data = {}
        if BUNDLED_CACHE.exists():
            try:
                self._data = json.loads(BUNDLED_CACHE.read_text())
            except (ValueError, OSError):
                self._data = {}
        self._server = find_server() if live else None

    def get(self, sc: str) -> Optional[str]:
        if sc in self._data:
            return self._data[sc]
        if self.live and self._server is not None:
            text = fetch_via_server(self._server, sc, self.timeout)
            if text:
                self._data[sc] = text
            return text
        return None

    @property
    def source(self) -> str:
        if self.live and self._server is not None:
            return "wcag-guidelines-mcp (live stdio)"
        return "bundled sc_cache.json (offline)"


def get_criterion_text(sc: str, live: bool = False) -> Optional[str]:
    return Cache(live=live).get(sc)


def build_enrichment(result: dict, live: bool = False) -> tuple:
    """Build {sc: parsed-criterion} for every SC referenced in an audit result.

    Returns (enrichment_dict, source_label). Only fetches the SCs actually
    present in the findings, so reports stay focused. Deterministic for a
    given source: offline mode reads the bundled cache, live mode queries the
    locally installed wcag-guidelines-mcp over stdio.
    """
    scs = sorted({f["sc"] for f in result.get("findings", []) if f.get("sc")})
    cache = Cache(live=live)
    enrichment = {}
    for sc in scs:
        text = cache.get(sc)
        if text:
            enrichment[sc] = parse_criterion(text)
    return enrichment, cache.source


def load_cache_json() -> dict:
    if BUNDLED_CACHE.exists():
        try:
            return json.loads(BUNDLED_CACHE.read_text())
        except (ValueError, OSError):
            return {}
    return {}