#!/usr/bin/env python3
"""
grimoire_api.py - a small command-line client for the Grimoire REST API.

Standard library only. Connect once and the connection is saved (in
~/.config/grimoire/config.json, readable only by you); the key is never printed.

    grimoire_api.py login --url https://grimoire.example.com            # sign in with your browser
    grimoire_api.py login --url https://grimoire.example.com --api-key  # or paste/pipe an API key
    grimoire_api.py login --url http://nas:9481 --profile nas --no-browser   # browser on another machine
    grimoire_api.py profiles                  # saved libraries
    grimoire_api.py use nas                   # make one the default
    grimoire_api.py --profile nas systems     # or pick one per command
    grimoire_api.py logout [--profile nas]

GRIMOIRE_URL + GRIMOIRE_API_KEY (or GRIMOIRE_TOKEN) in the environment, or
--url/--key, override the saved connection. --insecure (or "insecure" saved by
login) accepts a self-signed TLS certificate; SSL_CERT_FILE names a private CA.

Reading the library:

    grimoire_api.py check                     # who am I, and what can this key do
    grimoire_api.py systems                   # game systems, containers, book counts
    grimoire_api.py tree books --depth 3      # the folder layout under books/
    grimoire_api.py browse "books/Pathfinder 2e/Adventures"
    grimoire_api.py lookups                   # valid genres, licenses, families, ...
    grimoire_api.py books --system 12 --missing authors publisher year
    grimoire_api.py book 345                  # one book's full metadata
    grimoire_api.py find "books/Mothership/Core/Player's Survival Guide.pdf"
    grimoire_api.py page-text 345 3           # text of page 3
    grimoire_api.py thumbnail 345 cover.webp  # cover image, to look at
    grimoire_api.py download 345 book.pdf

Changing it (admin key with files/library/books write):

    grimoire_api.py mkdir "books/Dungeons & Dragons" --container parent
    grimoire_api.py mkdir "books/Mothership/Adventures/Gradient Descent"   # makes parents too
    grimoire_api.py scaffold "books/Mothership"
    grimoire_api.py upload file.pdf "books/Mothership/Core" --name "Player's Survival Guide.pdf"
    grimoire_api.py move "books/Inbox/x.pdf" --to "books/Mothership/Core"
    grimoire_api.py rename "books/Mothership/Core/x.pdf" "Warden's Operations Manual.pdf"
    grimoire_api.py rescan --scope "books/Mothership" --wait
    grimoire_api.py patch 345 '{"authors": ["Sean McCoy"], "year": 2021}'
    grimoire_api.py tag 345 346 --tags "Missing pages"

Metadata lookups (Grimoire Codex DB and installed add-ons):

    grimoire_api.py sources 345
    grimoire_api.py lookup 345 --source grimoire-codex [--query "..."]
    grimoire_api.py fetch 345 --source grimoire-codex --identity <id> [--query "..."]

Reading for questions and session prep:

    grimoire_api.py search "grappling" [--system ID] [--book ID]
    grimoire_api.py pages 345 12 14           # text of pages 12-14 (up to 10)
    grimoire_api.py campaigns
    grimoire_api.py campaign <id>             # overview, members, resources
    grimoire_api.py wiki <campaign-id> [<page-id>]
    grimoire_api.py wiki-search <campaign-id> "the baron"
    grimoire_api.py notes                     # your saved notes about this library

Applying a reviewed organisation plan (see references/plan-format.md):

    grimoire_api.py apply plan.json --dry-run
    grimoire_api.py apply plan.json

Every command prints JSON on stdout; errors go to stderr with a non-zero exit.
"""
from __future__ import annotations

import argparse
import getpass
import hmac
import json
import mimetypes
import os
import secrets
import socket
import ssl
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterator, Optional

CHUNK = 1 << 20
UPLOAD_TIMEOUT = 3600
# Fields PATCH /api/books/:id accepts that a plan may set. `category` is left
# out on purpose: changing it moves the file, and in a plan the folder already
# decides the category.
BOOK_FIELDS = {
    "title", "description", "authors", "artists", "genres", "publisher", "urls", "isbn",
    "product_code", "version", "language", "license", "year", "month", "day",
    "is_explicit", "codex_id", "access_level",
}
LIST_FIELDS = {"authors", "artists", "genres", "urls"}


class ApiError(Exception):
    def __init__(self, status: int, detail: Any, method: str, path: str) -> None:
        super().__init__(f"{method} {path} -> {status}: {detail}")
        self.status, self.detail = status, detail


# ------------------------------------------------------------------- client --


class Client:
    def __init__(self, url: str, key: Optional[str], token: Optional[str] = None,
                 insecure: bool = False) -> None:
        if not url or not (key or token):
            raise SystemExit(
                "not connected to a Grimoire library - run: grimoire_api.py login --url <address>"
            )
        self.base = url.rstrip("/")
        # A self-signed homelab certificate needs verification off; anything
        # else (a private CA) is better served by SSL_CERT_FILE.
        self.ssl = ssl._create_unverified_context() if insecure else None
        self.headers = {"Accept": "application/json", "User-Agent": "grimoire-skills/1"}
        if key:
            self.headers["X-API-Key"] = key
        else:
            self.headers["Authorization"] = f"Bearer {token}"

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        params: Optional[dict[str, Any]] = None,
        raw: bool = False,
        data: Any = None,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 120,
        retries: int = 2,
    ) -> Any:
        url = self.base + path
        if params:
            query = {k: v for k, v in params.items() if v is not None}
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        hdrs = dict(self.headers)
        if body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update(headers)
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=self.ssl) as resp:
                    payload = resp.read()
                    if raw:
                        return payload
                    ctype = resp.headers.get("Content-Type", "")
                    if "json" not in ctype:
                        if payload.lstrip().startswith(b"<"):
                            raise ApiError(
                                resp.status,
                                "got a web page instead of JSON - is GRIMOIRE_URL the Grimoire "
                                "address, and is nothing (a login proxy) in front of the API?",
                                method,
                                path,
                            )
                        return payload.decode(errors="replace")
                    return json.loads(payload) if payload else None
            except urllib.error.HTTPError as exc:
                text = exc.read().decode(errors="replace")
                try:
                    detail = json.loads(text).get("detail", text)
                except (ValueError, AttributeError):
                    detail = text[:300]
                replayable = data is None or isinstance(data, bytes)
                if exc.code in {429, 502, 503, 504} and replayable and attempt < retries:
                    attempt += 1
                    time.sleep(2 * attempt)
                    continue
                raise ApiError(exc.code, detail, method, path) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if attempt < retries and (data is None or isinstance(data, bytes)):
                    attempt += 1
                    time.sleep(2 * attempt)
                    continue
                raise ApiError(0, f"cannot reach {self.base}: {exc}", method, path) from None

    # ``endpoint``, not ``path``: several routes take a ``path`` query parameter.
    def get(self, endpoint: str, **params: Any) -> Any:
        return self.request("GET", endpoint, params=params)

    def post(self, endpoint: str, body: Any = None, **params: Any) -> Any:
        return self.request("POST", endpoint, body=body if body is not None else {}, params=params)

    # ---------------------------------------------------------- files ----

    def browse(self, path: str) -> dict[str, Any]:
        return self.get("/api/files/browse", path=path, limit=2000)

    def exists(self, path: str) -> Optional[dict[str, Any]]:
        """The browse entry for a library path, or None when nothing is there."""
        parent, _, name = path.rstrip("/").rpartition("/")
        try:
            listing = self.browse(parent)
        except ApiError as exc:
            if exc.status in {400, 404}:
                return None
            raise
        return next((e for e in listing["entries"] if e["name"] == name), None)

    def ensure_dir(self, path: str, container_kind: str = "", nsfw: bool = False,
                   dry_run: bool = False) -> list[str]:
        """Create a folder and any missing parents. Returns the folders created."""
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) < 2:
            raise SystemExit(f"refusing to create a top-level collection folder: {path!r}")
        created: list[str] = []
        current = parts[0]
        for i, name in enumerate(parts[1:], start=1):
            target = f"{current}/{name}"
            last = i == len(parts) - 1
            entry = self.exists(target)
            if entry is None:
                body = {"parent": current, "name": name, "container_kind": "", "nsfw": False}
                if last:
                    body.update(container_kind=container_kind, nsfw=nsfw)
                if not dry_run:
                    self.post("/api/files/folder", body)
                created.append(target)
            elif not entry.get("is_dir"):
                raise ApiError(409, f"{target} exists and is a file", "POST", "/api/files/folder")
            elif last and (container_kind or nsfw):
                have_kind = entry.get("container_kind") or ""
                if have_kind != container_kind or (nsfw and not entry.get("nsfw")):
                    if not dry_run:
                        self.request(
                            "PUT",
                            "/api/files/folder/markers",
                            body={"path": target, "container_kind": container_kind, "nsfw": nsfw or bool(entry.get("nsfw"))},
                        )
                    created.append(f"{target} (markers updated)")
            current = target
        return created

    def upload(self, file: Path, dest_dir: str, name: Optional[str] = None,
               on_conflict: str = "skip") -> dict[str, Any]:
        """Stream one file into a library folder as multipart/form-data."""
        boundary = uuid.uuid4().hex
        filename = name or file.name
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        quoted = filename.replace("\\", "\\\\").replace('"', '\\"')

        def field(key: str, value: str) -> bytes:
            return (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n"
            ).encode()

        head = field("destination", dest_dir) + field("on_conflict", on_conflict)
        head += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{quoted}\"; filename*=UTF-8''{urllib.parse.quote(filename)}\r\n"
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode()
        tail = f"\r\n--{boundary}--\r\n".encode()
        size = file.stat().st_size

        def body() -> Iterator[bytes]:
            yield head
            with file.open("rb") as fh:
                for block in iter(lambda: fh.read(CHUNK), b""):
                    yield block
            yield tail

        return self.request(
            "POST",
            "/api/files/upload",
            data=body(),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(head) + size + len(tail)),
            },
            timeout=UPLOAD_TIMEOUT,
            retries=0,
        )

    # ----------------------------------------------------------- scans ----

    def wait_for_scan(self, timeout: float = 7200, quiet: bool = False) -> dict[str, Any]:
        started = time.monotonic()
        last = ""
        status: dict[str, Any] = {}
        while time.monotonic() - started < timeout:
            status = self.get("/api/scan-status")
            if not status.get("running"):
                return status
            line = f"{status.get('phase')} {status.get('processed', '')}/{status.get('total', '')}"
            if line != last and not quiet:
                print(f"  scan: {line}", file=sys.stderr)
                last = line
            time.sleep(3)
        raise ApiError(0, f"scan still running after {timeout:.0f}s", "GET", "/api/scan-status")

    def rescan(self, scope: Optional[str], metadata_mode: str = "new", wait: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {"metadata_mode": metadata_mode}
        if scope:
            body["scope"] = scope
        for _ in range(240):
            result = self.post("/api/rescan", body)
            if result.get("status") != "already_running":
                break
            self.wait_for_scan(quiet=True)
        if wait:
            time.sleep(1)
            result["final"] = self.wait_for_scan()
        return result


# ----------------------------------------------------------- plan applying --


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"items": {}, "folders": []}


def save_state(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def clean_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in meta.items():
        if key not in BOOK_FIELDS or value in (None, "", []):
            continue
        if key in LIST_FIELDS and isinstance(value, str):
            value = [value]
        out[key] = value
    return out


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def fill_only(meta: dict[str, Any], current: dict[str, Any], old_stem: str = "") -> dict[str, Any]:
    """Drop fields the book already has a value for.

    A title the scanner derived from the filename is not a value anyone chose,
    so it counts as empty: otherwise every book reorganised in place would keep
    "Ars Magica 4e - core_v2" as its title.
    """
    out = {}
    for key, value in meta.items():
        have = current.get(key)
        auto_title = key == "title" and old_stem and _norm(str(have or "")) == _norm(old_stem)
        if have in (None, "", [], 0) or auto_title:
            out[key] = value
    return out


def apply_plan(client: Client, plan_path: Path, dry_run: bool, overwrite: bool,
               rescan: bool) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source = plan.get("source", {})
    kind = source.get("kind", "local")
    root = Path(source.get("root", ".")).expanduser() if kind == "local" else None
    state_path = plan_path.with_name(plan_path.stem + ".state.json")
    state = load_state(state_path) if not dry_run else {"items": {}, "folders": []}
    report: dict[str, Any] = {"dry_run": dry_run, "created_folders": [], "placed": 0,
                              "patched": 0, "tagged": 0, "skipped": 0, "errors": []}

    items = [i for i in plan["items"] if i.get("action") in {"upload", "move"}]
    report["skipped"] = len(plan["items"]) - len(items)

    # 1. Folders: explicit ones first (they carry container/NSFW markers), then
    #    every destination an item needs.
    wanted: list[tuple[str, str, bool]] = [
        (f["path"], f.get("container_kind", ""), bool(f.get("nsfw"))) for f in plan.get("folders", [])
    ]
    wanted += [(i["dest_dir"], "", False) for i in items]
    seen: set[str] = set()
    for path, ck, nsfw in wanted:
        if path in seen or (path in state["folders"] and not ck and not nsfw):
            continue
        seen.add(path)
        try:
            made = client.ensure_dir(path, ck, nsfw, dry_run=dry_run)
            report["created_folders"] += made
            if not dry_run:
                state["folders"].append(path)
        except (ApiError, SystemExit) as exc:
            report["errors"].append({"folder": path, "error": str(exc)})
    if not dry_run:
        save_state(state_path, state)

    # 2. Files.
    for item in items:
        sid = str(item["id"])
        st = state["items"].setdefault(sid, {})
        if st.get("placed"):
            continue
        dest_name = item.get("dest_name") or Path(item["source"]).name
        target = f"{item['dest_dir']}/{dest_name}"
        try:
            if dry_run:
                print(f"  {item['action']}: {item['source']} -> {target}", file=sys.stderr)
                report["placed"] += 1
                continue
            if item["action"] == "upload":
                src = (root / item["source"]) if root else Path(item["source"])
                if not src.is_file():
                    raise ApiError(404, f"source file not found: {src}", "UPLOAD", item["source"])
                try:
                    result = client.upload(src, item["dest_dir"], dest_name, on_conflict="skip")
                    st["path"] = result["path"]
                except ApiError as exc:
                    if exc.status != 409:
                        raise
                    # A re-run after an interruption: the file may already be there.
                    there = client.exists(target)
                    if there and there.get("size") == src.stat().st_size:
                        st["path"] = target
                    else:
                        raise ApiError(409, f"a different file is already at {target}", "UPLOAD", target)
            else:
                moved = client.post("/api/files/move", {"sources": [item["source"]],
                                                         "destination": item["dest_dir"],
                                                         "on_conflict": "skip"})
                if moved.get("skipped"):
                    raise ApiError(409, moved["skipped"][0].get("reason"), "MOVE", item["source"])
                landed = f"{item['dest_dir']}/{Path(item['source']).name}"
                st["old_stem"] = Path(item["source"]).stem
                if dest_name != Path(item["source"]).name:
                    client.post("/api/files/rename", {"path": landed, "new_name": dest_name})
                st["path"] = target
            st["placed"] = True
            st["fresh"] = item["action"] == "upload"
            report["placed"] += 1
        except ApiError as exc:
            st["error"] = str(exc)
            report["errors"].append({"id": sid, "source": item["source"], "error": str(exc)})
        save_state(state_path, state)

    if dry_run:
        report["would_patch"] = sum(1 for i in items if clean_metadata(i.get("metadata", {})))
        return report

    # 3. Find each file's record. Moves keep theirs (the file manager relinks
    #    it); uploads have none until a scan indexes them, so rescan - one
    #    scoped rescan per top-level folder - only for what is still missing.
    placed = [i for i in items if state["items"].get(str(i["id"]), {}).get("placed")]

    def resolve() -> list[dict[str, Any]]:
        listings: dict[str, dict[str, Any]] = {}
        missing = []
        for item in placed:
            st = state["items"][str(item["id"])]
            if st.get("record_id"):
                continue
            parent, _, name = st["path"].rpartition("/")
            try:
                if parent not in listings:
                    listings[parent] = client.browse(parent)
            except ApiError as exc:
                report["errors"].append({"id": str(item["id"]), "path": st["path"], "error": str(exc)})
                continue
            entry = next((e for e in listings[parent]["entries"] if e["name"] == name), None)
            if entry and entry.get("record_id"):
                st["record_id"] = entry["record_id"]
            else:
                missing.append(item)
        return missing

    unindexed = resolve()
    if rescan and unindexed:
        scopes = sorted({"/".join(i["dest_dir"].split("/")[:2]) for i in unindexed})
        for scope in scopes:
            print(f"rescanning {scope}", file=sys.stderr)
            try:
                client.rescan(scope, wait=True)
            except ApiError as exc:
                report["errors"].append({"rescan": scope, "error": str(exc)})
        resolve()
    save_state(state_path, state)

    # 4. Metadata and health tags.
    tags_by_name: dict[str, list[str]] = {}
    for item in placed:
        sid = str(item["id"])
        st = state["items"][sid]
        if st.get("patched") and st.get("tagged", not item.get("health_tags")):
            continue
        try:
            record_id = st.get("record_id")
            if not record_id:
                raise ApiError(404, "not indexed yet - rescan, then re-run apply", "FIND", st["path"])
            meta = clean_metadata(item.get("metadata", {}))
            if meta and not st.get("patched"):
                # Fresh uploads only carry what the scanner guessed, so the plan
                # wins. Books that were already in the library keep their values.
                if not (overwrite or st.get("fresh")):
                    meta = fill_only(meta, client.get(f"/api/books/{record_id}"), st.get("old_stem", ""))
                if meta:
                    client.request("PATCH", f"/api/books/{record_id}", body=meta)
                    report["patched"] += 1
            st["patched"] = True
            for tag in item.get("health_tags", []):
                tags_by_name.setdefault(tag, []).append(record_id)
        except ApiError as exc:
            st["error"] = str(exc)
            report["errors"].append({"id": sid, "path": st.get("path"), "error": str(exc)})
        save_state(state_path, state)

    for tag, ids in tags_by_name.items():
        try:
            client.post("/api/books/bulk/tags", {"ids": ids, "tags": [tag]})
            report["tagged"] += len(ids)
            for item in placed:
                st = state["items"][str(item["id"])]
                if st.get("record_id") in ids:
                    st["tagged"] = True
        except ApiError as exc:
            report["errors"].append({"tag": tag, "error": str(exc)})
    save_state(state_path, state)
    report["state_file"] = str(state_path)
    report["records"] = {
        str(i["id"]): state["items"][str(i["id"])].get("record_id") for i in placed
    }
    return report


# ------------------------------------------------------- saved connections --

# What `login` asks for by default: everything the /grimoire workflows use.
# Grimoire offers the user only what their role can grant, and the connect
# page shows what was reduced or refused before they allow it.
ACCESS = {
    "full": "files:write,library:write,books:write,systems:read,lookups:read,search:read,campaigns:read",
    "read": "books:read,systems:read,lookups:read,search:read,campaigns:read",
}
LOGIN_TIMEOUT = 300


def config_dir() -> Path:
    explicit = os.environ.get("GRIMOIRE_CONFIG_DIR")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "grimoire"


def load_config() -> dict[str, Any]:
    path = config_dir() / "config.json"
    if not path.exists():
        return {"default_profile": None, "profiles": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("profiles", {})
    data.setdefault("default_profile", None)
    return data


def save_config(data: dict[str, Any]) -> Path:
    """Write the config readable by its owner only - it holds API keys."""
    folder = config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    path = folder / "config.json"
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def notes_path(profile: str) -> Path:
    return config_dir() / "libraries" / f"{profile}.md"


def resolve_connection(a: argparse.Namespace) -> dict[str, Any]:
    """Explicit flags, then the environment, then the chosen saved profile."""
    cfg = load_config()
    name = a.profile or os.environ.get("GRIMOIRE_PROFILE") or cfg.get("default_profile")
    saved = cfg["profiles"].get(name, {}) if name else {}
    if a.profile and not saved:
        raise SystemExit(f"no saved library called {a.profile!r} - see: grimoire_api.py profiles")
    url = a.url or os.environ.get("GRIMOIRE_URL") or saved.get("url")
    key = a.key or os.environ.get("GRIMOIRE_API_KEY")
    token = a.token or os.environ.get("GRIMOIRE_TOKEN")
    if not (key or token):
        key = saved.get("api_key")
    insecure = bool(a.insecure or os.environ.get("GRIMOIRE_INSECURE") or saved.get("insecure"))
    return {"profile": name if saved else None, "url": url, "key": key, "token": token,
            "insecure": insecure}


def mask(key: str) -> str:
    return key[:9] + "…" if key else ""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Receives the connect page's form POST on 127.0.0.1."""

    server: "_CallbackServer"

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        length = int(self.headers.get("Content-Length") or 0)
        fields = urllib.parse.parse_qs(self.rfile.read(min(length, 65536)).decode())
        get = lambda k: (fields.get(k) or [""])[0]  # noqa: E731
        if not hmac.compare_digest(get("state"), self.server.state):
            self._reply(400, "This sign-in doesn't match the one your terminal started. Start it again.")
            return
        if get("error"):
            self.server.result = {"error": get("error")}
            self._reply(200, "Cancelled - nothing was saved. You can close this tab.")
        elif get("key"):
            self.server.result = {"key": get("key")}
            self._reply(200, "Signed in - you can close this tab and go back to your terminal.")
        else:
            self._reply(400, "Nothing was received. Start the sign-in again.")

    def do_GET(self) -> None:  # noqa: N802
        self._reply(200, "Waiting for Grimoire - finish signing in in the other tab.")

    def _reply(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><meta charset=utf-8><title>Grimoire</title>"
            "<body style='font-family:system-ui;max-width:32em;margin:4em auto;line-height:1.5'>"
            f"<h1 style='font-size:1.2em'>Grimoire</h1><p>{message}</p>"
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


class _CallbackServer(HTTPServer):
    def __init__(self, state: str) -> None:
        super().__init__(("127.0.0.1", 0), _CallbackHandler)
        self.state = state
        self.result: Optional[dict[str, str]] = None


def connect_url(base: str, perms: str, client: str, callback: Optional[str] = None,
                state: Optional[str] = None) -> str:
    query = {"client": client, "perms": perms}
    if callback:
        query.update(callback=callback, state=state or "")
    return f"{base.rstrip('/')}/connect?{urllib.parse.urlencode(query)}"


def browser_login(base: str, perms: str, client: str, open_browser: bool = True,
                  timeout: float = LOGIN_TIMEOUT) -> str:
    """Open Grimoire's /connect page and wait for the key to come back."""
    state = secrets.token_urlsafe(24)
    server = _CallbackServer(state)
    callback = f"http://127.0.0.1:{server.server_address[1]}/callback"
    url = connect_url(base, perms, client, callback, state)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    thread.start()
    print(f"Finish signing in in your browser. If it did not open, visit:\n  {url}\n", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    deadline = time.monotonic() + timeout
    try:
        while server.result is None and time.monotonic() < deadline:
            time.sleep(0.2)
    finally:
        server.shutdown()
        server.server_close()
    if server.result is None:
        raise SystemExit(f"no answer from the browser within {timeout:.0f}s - run login again")
    if "error" in server.result:
        raise SystemExit("sign-in was cancelled in the browser - nothing was saved")
    return server.result["key"]


def read_key_from_user(prompt: str) -> str:
    """A key from GRIMOIRE_API_KEY, piped stdin, or a hidden prompt - never argv."""
    key = os.environ.get("GRIMOIRE_API_KEY", "").strip()
    if not key and not sys.stdin.isatty():
        key = sys.stdin.readline().strip()
    if not key:
        key = getpass.getpass(prompt).strip()
    if not key:
        raise SystemExit("no key given")
    return key


def cmd_login(a: argparse.Namespace) -> Any:
    url = (a.url or os.environ.get("GRIMOIRE_URL") or "").strip().rstrip("/")
    cfg = load_config()
    name = a.profile or os.environ.get("GRIMOIRE_PROFILE") or cfg.get("default_profile") or "default"
    if not url:
        url = cfg["profiles"].get(name, {}).get("url", "")
    if not url:
        raise SystemExit("which Grimoire? pass --url https://your-grimoire.example.com")
    if "://" not in url:
        url = "https://" + url
    perms = ACCESS[a.access]
    client_name = f"Grimoire skills on {socket.gethostname().split('.')[0]}"[:60]
    if a.api_key:
        key, method = read_key_from_user("Grimoire API key (input hidden): "), "api-key"
    elif a.no_browser:
        print(
            "Open this address in any browser signed in to Grimoire, allow access, and copy the key:"
            f"\n  {connect_url(url, perms, client_name)}\n",
            file=sys.stderr,
        )
        key, method = read_key_from_user("Paste the key here (input hidden): "), "browser"
    else:
        key, method = browser_login(url, perms, client_name, timeout=a.timeout), "browser"

    insecure = bool(a.insecure)
    report = cmd_check(Client(url, key, insecure=insecure), a)
    if not any(v is True for v in report["can_read"].values()):
        raise SystemExit(f"Grimoire rejected the key - nothing was saved: {report['can_read']}")
    cfg["profiles"][name] = {
        "url": url, "api_key": key, "insecure": insecure, "auth": method,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if not cfg.get("default_profile") or a.make_default:
        cfg["default_profile"] = name
    path = save_config(cfg)
    report.update(profile=name, default=cfg["default_profile"] == name, saved_to=str(path),
                  key=mask(key))
    return report


def cmd_profiles(a: argparse.Namespace) -> Any:
    cfg = load_config()
    return [
        {"profile": n, "url": p.get("url"), "default": n == cfg.get("default_profile"),
         "auth": p.get("auth"), "key": mask(p.get("api_key", "")),
         "notes": str(notes_path(n)) if notes_path(n).exists() else None}
        for n, p in sorted(cfg["profiles"].items())
    ]


def cmd_use(a: argparse.Namespace) -> Any:
    cfg = load_config()
    if a.name not in cfg["profiles"]:
        raise SystemExit(f"no saved library called {a.name!r}")
    cfg["default_profile"] = a.name
    save_config(cfg)
    return {"default_profile": a.name}


def cmd_logout(a: argparse.Namespace) -> Any:
    cfg = load_config()
    name = a.profile or cfg.get("default_profile")
    if not name or name not in cfg["profiles"]:
        raise SystemExit("nothing saved to log out of")
    removed = cfg["profiles"].pop(name)
    if cfg.get("default_profile") == name:
        cfg["default_profile"] = next(iter(sorted(cfg["profiles"])), None)
    save_config(cfg)
    return {
        "removed": name,
        "default_profile": cfg["default_profile"],
        "note": f"the key {mask(removed.get('api_key', ''))} still works until you revoke it in "
                "Grimoire: Settings → Account → Security → API Keys",
    }


def cmd_notes(a: argparse.Namespace) -> Any:
    name = resolve_connection(a)["profile"] or "default"
    path = notes_path(name)
    return {"profile": name, "path": str(path), "exists": path.exists(),
            "content": path.read_text(encoding="utf-8") if path.exists() else ""}


# --------------------------------------------------------------- commands --


def cmd_check(c: Client, a: argparse.Namespace) -> Any:
    # /api/auth/me refuses API keys, so the key is judged by what it can reach.
    out: dict[str, Any] = {"url": c.base}
    probes = {
        "files (browse/upload/move)": lambda: c.browse("books"),
        "library (scan status/rescan)": lambda: c.get("/api/scan-status"),
        "books": lambda: c.get("/api/books", limit=1),
        "systems": lambda: c.get("/api/systems", limit=1),
        "lookups": lambda: c.get("/api/genres"),
    }
    out["can_read"] = {}
    for label, probe in probes.items():
        try:
            probe()
            out["can_read"][label] = True
        except ApiError as exc:
            out["can_read"][label] = f"no ({exc.status}: {exc.detail})"
    try:
        out["codex"] = c.get("/api/codex/status")
    except ApiError as exc:
        # Lookups run through the Books permission either way; this status
        # route alone needs the Codex permission.
        out["codex"] = (
            "unknown - the key has no Codex permission; `sources <book-id>` lists what lookups exist"
            if exc.status == 403 else f"unavailable ({exc.status})"
        )
    if out["can_read"]["files (browse/upload/move)"] is not True:
        out["warning"] = "the file manager is unreachable: uploading and moving need an admin's key with files: write"
    out["note"] = "write access is only proven by a write; a key with read-only scopes gets 403 on the first change"
    return out


def cmd_systems(c: Client, a: argparse.Namespace) -> Any:
    data = c.get("/api/systems", include_children="true", limit=1000)
    rows = data.get("systems", data) if isinstance(data, dict) else data
    keep = ("id", "name", "container_kind", "parent_id", "book_count", "parent_system",
            "edition", "system_family", "is_system_agnostic", "is_one_page", "codex_id")
    return [{k: s.get(k) for k in keep if s.get(k) not in (None, "", False)} for s in rows]


def cmd_tree(c: Client, a: argparse.Namespace) -> Any:
    lines: list[str] = []

    def walk(path: str, depth: int, indent: str) -> None:
        listing = c.browse(path)
        dirs = [e for e in listing["entries"] if e["is_dir"]]
        files = len(listing["entries"]) - len(dirs)
        for e in dirs:
            marks = [m for m in (e.get("container_kind") and f"container:{e['container_kind']}",
                                 e.get("nsfw") and "nsfw") if m]
            label = f"{e['name']}/" + (f"  [{', '.join(marks)}]" if marks else "")
            label += f"  ({e.get('child_count')})" if e.get("child_count") is not None else ""
            lines.append(indent + label)
            if depth > 1:
                walk(e["path"], depth - 1, indent + "  ")
        if files and a.files:
            lines.append(indent + f"... {files} file(s)")

    walk(a.path, a.depth, "")
    print("\n".join(lines))
    return None


def cmd_books(c: Client, a: argparse.Namespace) -> Any:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = c.get("/api/books", system_id=a.system, category=a.category, limit=500, offset=offset)
        rows += page["books"]
        offset += 500
        if offset >= page["total"] or not page["books"]:
            break
    if a.missing:
        detailed = []
        for r in rows:
            full = c.get(f"/api/books/{r['id']}")
            gaps = [f for f in a.missing if full.get(f) in (None, "", [], 0)]
            if gaps:
                detailed.append({"id": r["id"], "title": full["title"], "path": full.get("relative_path"),
                                 "missing": gaps})
        return detailed
    # List rows carry the file name but not its folder; `book <id>` has the full path.
    return [{"id": r["id"], "title": r.get("title"), "category": r.get("category"),
             "file": r.get("filename"), "pages": r.get("page_count"),
             "system_id": r.get("game_system_id")} for r in rows]


def cmd_find(c: Client, a: argparse.Namespace) -> Any:
    entry = c.exists(a.path)
    if not entry:
        raise ApiError(404, "nothing at that path", "FIND", a.path)
    return entry


def read_json_arg(value: str) -> Any:
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # The connection options work before or after the command
    # (`--profile nas systems` and `systems --profile nas`). On the
    # subcommands they default to SUPPRESS so an option given before the
    # command is not reset by the subparser's own default.
    def connection_options(parser: argparse.ArgumentParser, default: Any) -> None:
        parser.add_argument("--profile", default=default,
                            help="saved library to use (default: the default profile)")
        parser.add_argument("--url", default=default, help="Grimoire address; overrides the saved one")
        parser.add_argument("--key", default=default,
                            help="API key; overrides the saved one (prefer GRIMOIRE_API_KEY)")
        parser.add_argument("--token", default=default, help="a JWT instead of an API key")
        parser.add_argument("--insecure", action="store_true",
                            default=False if default is None else default,
                            help="accept a self-signed TLS certificate")

    connection_options(ap, None)
    shared = argparse.ArgumentParser(add_help=False)
    connection_options(shared, argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    plain_add = sub.add_parser
    sub.add_parser = lambda *args, **kw: plain_add(*args, parents=[shared], **kw)  # type: ignore[method-assign]

    p = sub.add_parser("login", help="connect to a library and save the connection")
    how = p.add_mutually_exclusive_group()
    how.add_argument("--api-key", action="store_true", help="use an API key (env, stdin or prompt)")
    how.add_argument("--no-browser", action="store_true", help="browser on another machine: paste the key")
    p.add_argument("--access", choices=sorted(ACCESS), default="full")
    p.add_argument("--default", dest="make_default", action="store_true", help="make this the default library")
    p.add_argument("--timeout", type=float, default=LOGIN_TIMEOUT)
    sub.add_parser("logout")
    sub.add_parser("profiles")
    p = sub.add_parser("use")
    p.add_argument("name")
    sub.add_parser("notes")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--system")
    p.add_argument("--book")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("pages")
    p.add_argument("id")
    p.add_argument("start", type=int)
    p.add_argument("end", type=int, nargs="?")
    sub.add_parser("campaigns")
    p = sub.add_parser("campaign")
    p.add_argument("id")
    p = sub.add_parser("wiki")
    p.add_argument("campaign")
    p.add_argument("page", nargs="?")
    p = sub.add_parser("wiki-search")
    p.add_argument("campaign")
    p.add_argument("query")

    sub.add_parser("check")
    sub.add_parser("systems")
    sub.add_parser("lookups")
    p = sub.add_parser("tree")
    p.add_argument("path", nargs="?", default="books")
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--files", action="store_true")
    p = sub.add_parser("browse")
    p.add_argument("path", nargs="?", default="")
    p = sub.add_parser("find")
    p.add_argument("path")
    p = sub.add_parser("books")
    p.add_argument("--system")
    p.add_argument("--category")
    p.add_argument("--missing", nargs="*", help="only books with these fields empty")
    p = sub.add_parser("book")
    p.add_argument("id")
    p = sub.add_parser("page-text")
    p.add_argument("id")
    p.add_argument("page", type=int)
    p = sub.add_parser("toc")
    p.add_argument("id")
    p = sub.add_parser("thumbnail")
    p.add_argument("id")
    p.add_argument("out")
    p = sub.add_parser("page-image")
    p.add_argument("id")
    p.add_argument("page", type=int)
    p.add_argument("out")
    p.add_argument("--width", type=int, default=1000)
    p = sub.add_parser("download")
    p.add_argument("id")
    p.add_argument("out")

    p = sub.add_parser("mkdir")
    p.add_argument("path")
    p.add_argument("--container", default="", choices=["", "parent", "one-page", "agnostic", "family", "publisher", "generic"])
    p.add_argument("--nsfw", action="store_true")
    p = sub.add_parser("scaffold")
    p.add_argument("path")
    p = sub.add_parser("upload")
    p.add_argument("file")
    p.add_argument("dest")
    p.add_argument("--name")
    p.add_argument("--on-conflict", default="skip", choices=["skip", "rename", "replace"])
    p = sub.add_parser("move")
    p.add_argument("sources", nargs="+")
    p.add_argument("--to", required=True)
    p.add_argument("--on-conflict", default="skip", choices=["skip", "rename"])
    p = sub.add_parser("rename")
    p.add_argument("path")
    p.add_argument("new_name")
    p = sub.add_parser("rescan")
    p.add_argument("--scope")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--metadata-mode", default="new", choices=["new", "missing", "replace"])
    sub.add_parser("scan-status")
    p = sub.add_parser("patch")
    p.add_argument("id")
    p.add_argument("json", help="JSON object, or @file.json")
    p = sub.add_parser("tag")
    p.add_argument("ids", nargs="+")
    p.add_argument("--tags", required=True)
    p = sub.add_parser("sources")
    p.add_argument("id")
    p = sub.add_parser("lookup")
    p.add_argument("id")
    p.add_argument("--source", required=True)
    p.add_argument("--query")
    p = sub.add_parser("fetch")
    p.add_argument("id")
    p.add_argument("--source", required=True)
    p.add_argument("--identity", required=True)
    p.add_argument("--query")
    p = sub.add_parser("apply")
    p.add_argument("plan")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--overwrite", action="store_true", help="let plan metadata replace values books already had")
    p.add_argument("--no-rescan", action="store_true")
    return ap


def run(a: argparse.Namespace, c: Client) -> Any:
    cmd = a.cmd
    if cmd == "check":
        return cmd_check(c, a)
    if cmd == "systems":
        return cmd_systems(c, a)
    if cmd == "lookups":
        return {
            "genres": [g["name"] for g in c.get("/api/genres")["genres"]],
            "licenses": [x["name"] for x in c.get("/api/licenses")["licenses"]],
            "system_families": [x["name"] for x in c.get("/api/system-families")["families"]],
            "parent_systems": [x["name"] for x in c.get("/api/parent-systems")["parent_systems"]],
        }
    if cmd == "tree":
        return cmd_tree(c, a)
    if cmd == "browse":
        return c.browse(a.path)
    if cmd == "find":
        return cmd_find(c, a)
    if cmd == "books":
        return cmd_books(c, a)
    if cmd == "book":
        return c.get(f"/api/books/{a.id}")
    if cmd == "page-text":
        return c.get(f"/api/books/{a.id}/page/{a.page}/text")
    if cmd == "toc":
        return c.get(f"/api/books/{a.id}/toc")
    if cmd in {"thumbnail", "page-image", "download"}:
        path = {
            "thumbnail": f"/api/books/{a.id}/thumbnail",
            "page-image": f"/api/books/{a.id}/page/{getattr(a, 'page', 1)}",
            "download": f"/api/books/{a.id}/file",
        }[cmd]
        params = {"width": a.width} if cmd == "page-image" else None
        data = c.request("GET", path, params=params, raw=True, timeout=UPLOAD_TIMEOUT)
        Path(a.out).write_bytes(data)
        return {"saved": a.out, "bytes": len(data)}
    if cmd == "mkdir":
        return {"created": c.ensure_dir(a.path, a.container, a.nsfw)}
    if cmd == "scaffold":
        return c.post("/api/files/folder/scaffold", {"path": a.path})
    if cmd == "upload":
        return c.upload(Path(a.file), a.dest, a.name, a.on_conflict)
    if cmd == "move":
        return c.post("/api/files/move", {"sources": a.sources, "destination": a.to, "on_conflict": a.on_conflict})
    if cmd == "rename":
        return c.post("/api/files/rename", {"path": a.path, "new_name": a.new_name})
    if cmd == "rescan":
        return c.rescan(a.scope, a.metadata_mode, wait=a.wait)
    if cmd == "scan-status":
        return c.get("/api/scan-status")
    if cmd == "patch":
        body = read_json_arg(a.json)
        body = {k: v for k, v in body.items() if k != "category"} if not isinstance(body, list) else body
        return c.request("PATCH", f"/api/books/{a.id}", body=body)
    if cmd == "tag":
        return c.post("/api/books/bulk/tags", {"ids": a.ids, "tags": [t.strip() for t in a.tags.split(",") if t.strip()]})
    if cmd == "sources":
        return c.get(f"/api/books/{a.id}/metadata-sources")
    if cmd == "lookup":
        return c.post(f"/api/books/{a.id}/metadata-search", {"source_id": a.source, "query": a.query or ""})
    if cmd == "fetch":
        body = {"source_id": a.source, "identity": a.identity}
        if a.query:
            body["query"] = a.query
        return c.post(f"/api/books/{a.id}/metadata-fetch", body)
    if cmd == "apply":
        return apply_plan(c, Path(a.plan), a.dry_run, a.overwrite, not a.no_rescan)
    if cmd == "search":
        return c.get("/api/search", q=a.query, system_id=a.system, book_id=a.book, limit=a.limit)
    if cmd == "pages":
        end = min(a.end or a.start, a.start + 9)
        return [{"page": n, "text": c.get(f"/api/books/{a.id}/page/{n}/text").get("text", "")}
                for n in range(a.start, end + 1)]
    if cmd == "campaigns":
        return c.get("/api/campaigns")
    if cmd == "campaign":
        return c.get(f"/api/campaigns/{a.id}")
    if cmd == "wiki":
        if a.page:
            return c.get(f"/api/campaigns/{a.campaign}/wiki/{a.page}")
        return c.get(f"/api/campaigns/{a.campaign}/wiki")
    if cmd == "wiki-search":
        return c.get(f"/api/campaigns/{a.campaign}/wiki/search", q=a.query)
    raise SystemExit(f"unknown command {cmd}")


LOCAL_COMMANDS = {"login": cmd_login, "logout": cmd_logout, "profiles": cmd_profiles,
                  "use": cmd_use, "notes": cmd_notes}


def main(argv: Optional[list[str]] = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        if a.cmd in LOCAL_COMMANDS:
            result = LOCAL_COMMANDS[a.cmd](a)
        else:
            conn = resolve_connection(a)
            c = Client(conn["url"], conn["key"], conn["token"], conn["insecure"])
            result = run(a, c)
            if a.cmd == "check":
                result["profile"] = conn["profile"]
    except ApiError as exc:
        print(json.dumps({"error": str(exc), "status": exc.status}), file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
