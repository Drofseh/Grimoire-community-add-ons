#!/usr/bin/env python3
"""
pdf_health.py - find broken, incomplete and padded books before they reach a library.

Checks every file it is given (directories are walked recursively) and writes one
JSON object per file. Nothing is modified: repaired copies are only written when
--repair-out is passed, and always to a separate folder.

    python3 pdf_health.py ~/Downloads/unsorted --out health.jsonl
    python3 pdf_health.py book.pdf                      # one file, JSON to stdout
    python3 pdf_health.py inbox/ --quick --jobs 8       # sample pages, faster
    python3 pdf_health.py inbox/ --repair-out fixed/    # rebuild damaged-but-readable PDFs

What it catches:

  * files that are not what their extension says - an HTML error page saved as
    .pdf, a zip renamed to .pdf, a zero-byte or zero-filled (unfinished) download
  * PDFs that will not open, need a password, or crash the PDF engine
  * truncated files (no end-of-file marker) and damaged cross-reference tables
  * pages that fail to render
  * blank pages, long runs of them, and consecutive duplicate pages
  * missing pages, from jumps in the printed page numbers and from bookmarks that
    point past the last page
  * scans with no text layer (informational - Grimoire OCRs these itself)

Each file gets a verdict: ok, warn (usable but damaged or padded), broken (do
not import), locked (password required) or skipped (not a format checked here).

Deep checks need PyMuPDF (`pip install pymupdf`). Without it only the structural
checks run, and the summary says so. Every file is opened in a separate worker
process, so a file that crashes or hangs the PDF engine costs only that file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import re
import sys
import time
import zipfile
from collections import Counter
from multiprocessing.connection import wait as mp_wait
from pathlib import Path
from typing import Any, Optional

try:
    import fitz  # PyMuPDF

    HAVE_FITZ = True
except ImportError:  # pragma: no cover - exercised only on machines without it
    fitz = None
    HAVE_FITZ = False

BOOK_EXTS = {".pdf", ".epub", ".djvu", ".cbz", ".cbr", ".cb7", ".cbt", ".xps"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z"}
CHECKED_EXTS = BOOK_EXTS | ARCHIVE_EXTS
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# Pixel value under which a grayscale pixel counts as ink.
INK_LEVEL = 200
# A page whose inked fraction is below this, and that carries no real text, is blank.
BLANK_INK_RATIO = 0.004
# Width in pixels each page is rendered at for the blank/duplicate checks.
THUMB_WIDTH = 96
# A page needs this many characters of extracted text to count as having a text layer.
TEXT_CHARS = 25
# Thresholds that turn blank pages from a note into a warning. Books carry a
# few deliberate blanks (inside covers, versos before chapters), so a short
# handout with one empty back page must not read as damage.
BLANK_RUN_WARN = 3
BLANK_RATIO_WARN = 0.15
BLANK_COUNT_WARN = 4
# Anchored page numbers further apart than this are not compared: a long stretch
# without readable numbers is usually a restart (appendix, new section) rather
# than a hole, and guessing across it produced phantom gaps.
GAP_MAX_SPAN = 3

_INK_TABLE = bytes(1 if i < INK_LEVEL else 0 for i in range(256))
_SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2}


# ----------------------------------------------------------------- sniffing --


def sniff_type(head: bytes) -> str:
    """Name the real format of a file from its first bytes."""
    if not head:
        return "empty"
    if b"%PDF-" in head[:1024]:
        return "pdf"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    if head.startswith(b"Rar!"):
        return "rar"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if head.startswith(b"AT&TFORM"):
        return "djvu"
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"GIF8"):
        return "gif"
    if head.startswith(b"\x1f\x8b"):
        return "gzip"
    if len(head) > 262 and head[257:262] == b"ustar":
        return "tar"
    if not head.strip(b"\x00"):
        return "zero-filled"
    lowered = head[:2048].lstrip().lower()
    if lowered.startswith(b"<") and (b"<html" in lowered or b"<!doctype" in lowered):
        return "html"
    if lowered.startswith(b"<?xml"):
        return "xml"
    return "unknown"


EXPECTED_TYPES = {
    ".pdf": {"pdf"},
    ".epub": {"zip"},
    ".cbz": {"zip"},
    ".zip": {"zip"},
    ".cbr": {"rar"},
    ".rar": {"rar"},
    ".cb7": {"7z"},
    ".7z": {"7z"},
    ".djvu": {"djvu"},
    ".cbt": {"tar"},
    ".xps": {"zip"},
}


def zero_filled_regions(path: Path, size: int, chunk: int = 65536) -> list[str]:
    """Which of the head, middle and tail of the file are nothing but zero bytes.

    An unfinished download (torrent, sync client, interrupted copy) is often a
    file of the right size whose missing parts were never written.
    """
    if size < chunk * 3:
        return []
    found = []
    with path.open("rb") as fh:
        for label, offset in (("start", 0), ("middle", size // 2), ("end", size - chunk)):
            fh.seek(offset)
            if not fh.read(chunk).strip(b"\x00"):
                found.append(label)
    return found


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------- page checks --


def page_ink(page: Any) -> tuple[float, bool, bytes]:
    """Render a page small and return (ink ratio, is solid colour, pixel digest)."""
    zoom = THUMB_WIDTH / max(page.rect.width, 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, alpha=False)
    samples = bytes(pix.samples)
    if not samples:
        return 0.0, True, b""
    ink = samples.translate(_INK_TABLE).count(1) / len(samples)
    solid = (max(samples) - min(samples)) < 12
    return ink, solid, hashlib.md5(samples).digest()


_NUM_LINE = re.compile(r"^(?:page\s+)?(\d{1,4})$", re.IGNORECASE)
_NUM_EDGE = re.compile(r"^(\d{1,4})\s+\S|\S\s+(\d{1,4})$")


def printed_numbers(page: Any) -> set[int]:
    """Candidate printed page numbers from a page's header and footer bands."""
    height = page.rect.height or 1
    found: set[int] = set()
    for block in page.get_text("blocks"):
        y0, y1, text = block[1], block[3], block[4]
        if not (y1 < height * 0.10 or y0 > height * 0.90):
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) > 48:
                continue
            m = _NUM_LINE.match(line)
            if m:
                found.add(int(m.group(1)))
                continue
            m = _NUM_EDGE.search(line)
            if m:
                found.add(int(m.group(1) or m.group(2)))
    return {n for n in found if 0 < n < 5000}


def page_number_gaps(numbers: list[set[int]]) -> list[dict[str, int]]:
    """Find places where the printed page numbers jump further than the PDF does.

    A number only counts once a neighbouring page agrees with it (page i shows n
    and page i±1 shows n±1), which discards years, stat values and other stray
    digits in the margins. Scans of two-page spreads (two printed pages per PDF
    page) are detected and allowed for. A drop in the numbering is a new section
    or appendix, not damage, and is ignored.
    """
    anchored: dict[int, int] = {}
    for i, cands in enumerate(numbers):
        prev_c = numbers[i - 1] if i > 0 else set()
        next_c = numbers[i + 1] if i + 1 < len(numbers) else set()
        agreed = [n for n in cands if (n - 1) in prev_c or (n + 1) in next_c]
        if agreed:
            anchored[i] = max(agreed)
    if len(anchored) < 4:
        return []
    order = sorted(anchored)
    steps = [
        anchored[b] - anchored[a] for a, b in zip(order, order[1:]) if b - a == 1
    ]
    per_page = 2 if steps and Counter(steps).most_common(1)[0][0] == 2 else 1
    gaps = []
    for a, b in zip(order, order[1:]):
        if b - a > GAP_MAX_SPAN:
            continue
        printed = anchored[b] - anchored[a]
        expected = (b - a) * per_page
        missing = printed - expected
        if printed <= 0 or missing <= 0 or missing > 60:
            continue
        gaps.append(
            {
                "after_pdf_page": a + 1,
                "before_pdf_page": b + 1,
                "printed_from": anchored[a],
                "printed_to": anchored[b],
                "missing": missing,
            }
        )
    return gaps


def runs(pages: list[int]) -> list[list[int]]:
    """Collapse sorted 1-based page numbers into [first, last] runs."""
    out: list[list[int]] = []
    for p in pages:
        if out and p == out[-1][1] + 1:
            out[-1][1] = p
        else:
            out.append([p, p])
    return out


def sample_indices(count: int) -> list[int]:
    """Pages read in --quick mode: the ends of the book plus an even spread."""
    if count <= 60:
        return list(range(count))
    picked = set(range(15)) | set(range(count - 15, count))
    step = max(1, count // 30)
    picked |= set(range(0, count, step))
    return sorted(picked)


# ------------------------------------------------------------ format checks --


def check_pdf(path: Path, rec: dict[str, Any], quick: bool) -> None:
    fitz.TOOLS.mupdf_warnings()  # clear anything left from a previous file
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001 - any open failure means unreadable
        issue(rec, "unreadable", "error", f"PDF engine could not open it: {exc}")
        return
    with doc:
        if doc.needs_pass:
            issue(rec, "password_required", "error", "the PDF needs a password to open")
            rec["locked"] = True
            return
        if doc.is_repaired:
            issue(
                rec,
                "xref_repaired",
                "warn",
                "the cross-reference table is damaged and had to be rebuilt to open it",
            )
        count = doc.page_count
        rec["pages"] = count
        if count == 0:
            issue(rec, "no_pages", "error", "the document has no pages")
            return
        rec["form_fields"] = bool(doc.is_form_pdf)

        try:
            toc = doc.get_toc(simple=True)
        except Exception:  # noqa: BLE001 - a broken outline is reported, not fatal
            toc = []
            issue(rec, "toc_unreadable", "info", "the bookmarks could not be read")
        past_end = [t for t in toc if t[2] > count]
        unresolved = [t for t in toc if t[2] < 1]
        if past_end:
            issue(
                rec,
                "toc_points_past_end",
                "warn",
                f"{len(past_end)} bookmark(s) point past the last page ({count}), e.g. "
                f"{past_end[0][1]!r} -> page {past_end[0][2]}; pages are probably missing "
                f"from the end",
            )
        # Bookmarks into pages that were cut from the file resolve to nothing.
        # Scattered dead bookmarks are ordinary sloppiness; a dead *tail* after
        # bookmarks that work is what a book missing its last pages looks like.
        tail = 0
        for entry in reversed(toc):
            if entry[2] >= 1:
                break
            tail += 1
        if 2 <= tail < len(toc):
            issue(
                rec,
                "toc_tail_unresolved",
                "warn",
                f"the last {tail} bookmark(s) lead nowhere, starting at {toc[-tail][1]!r}; "
                f"pages are probably missing from the end",
            )
        elif toc and len(unresolved) > max(3, len(toc) // 5):
            issue(
                rec,
                "toc_unresolved",
                "info",
                f"{len(unresolved)} of {len(toc)} bookmarks lead nowhere",
            )

        indices = sample_indices(count) if quick else list(range(count))
        rec["pages_checked"] = len(indices)
        blank: list[int] = []
        bad: list[int] = []
        dupes: list[list[int]] = []
        with_text = 0
        numbers: list[set[int]] = []
        last_digest: Optional[bytes] = None
        last_index = -2
        for i in indices:
            try:
                page = doc.load_page(i)
                text = page.get_text("text")
                ink, solid, digest = page_ink(page)
            except Exception:  # noqa: BLE001 - one bad page must not stop the rest
                bad.append(i + 1)
                numbers.append(set())
                last_digest = None
                continue
            has_text = len(text.strip()) >= TEXT_CHARS
            with_text += has_text
            if not has_text and (ink < BLANK_INK_RATIO or solid):
                blank.append(i + 1)
                last_digest = None
            else:
                if digest and digest == last_digest and i == last_index + 1:
                    dupes.append([i, i + 1])
                last_digest = digest
            last_index = i
            if not quick:
                try:
                    numbers.append(printed_numbers(page))
                except Exception:  # noqa: BLE001
                    numbers.append(set())

        warnings = fitz.TOOLS.mupdf_warnings()
        if warnings and not bad:
            rec["engine_warnings"] = warnings.splitlines()[:5]

    if bad:
        sev = "error" if len(bad) > max(2, len(indices) // 20) else "warn"
        issue(
            rec,
            "unreadable_pages",
            sev,
            f"{len(bad)} page(s) fail to render: {short_list(bad)}",
        )
        rec["unreadable_pages"] = bad

    rec["text_layer"] = (
        "none" if with_text == 0 else "full" if with_text >= len(indices) * 0.6 else "partial"
    )
    if with_text == 0:
        issue(
            rec,
            "no_text_layer",
            "info",
            "no page has a text layer - a scan; Grimoire will OCR it after import",
        )

    if blank:
        rec["blank_pages"] = blank
        rec["blank_runs"] = [r for r in runs(blank) if r[1] - r[0] + 1 >= 2]
        ratio = len(blank) / len(indices)
        rec["blank_ratio"] = round(ratio, 3)
        longest = max(r[1] - r[0] + 1 for r in runs(blank))
        if (ratio >= BLANK_RATIO_WARN and len(blank) >= BLANK_COUNT_WARN) or longest >= BLANK_RUN_WARN:
            issue(
                rec,
                "blank_pages",
                "warn",
                f"{len(blank)} blank page(s) ({ratio:.0%}), longest run {longest}: "
                f"{short_list(blank)}",
            )
        else:
            issue(rec, "blank_pages", "info", f"{len(blank)} blank page(s): {short_list(blank)}")

    if dupes:
        # Informational only: card decks repeat their backs and handout packs
        # repeat sheets on purpose, and a doubled scan page loses no content.
        rec["duplicate_pages"] = dupes
        issue(
            rec,
            "duplicate_pages",
            "info",
            f"{len(dupes)} page(s) identical to the page before: "
            + ", ".join(f"{a}={b}" for a, b in dupes[:8]),
        )

    if not quick:
        gaps = page_number_gaps(numbers)
        if gaps:
            rec["page_number_gaps"] = gaps
            total = sum(g["missing"] for g in gaps)
            first = max(gaps, key=lambda g: g["missing"])
            # A lone one-page skip is most often a blank verso the publisher
            # left out of the digital edition, not a lost page.
            severity = "info" if all(g["missing"] == 1 for g in gaps) and len(gaps) == 1 else "warn"
            issue(
                rec,
                "missing_pages",
                severity,
                f"printed page numbers skip {total} page(s) in {len(gaps)} place(s), e.g. "
                f"printed {first['printed_from']} -> {first['printed_to']} between PDF pages "
                f"{first['after_pdf_page']} and {first['before_pdf_page']}",
            )


def check_zip(path: Path, rec: dict[str, Any], ext: str) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            broken = zf.testzip()
            names = [n for n in zf.namelist() if not n.endswith("/")]
    except (zipfile.BadZipFile, OSError) as exc:
        issue(rec, "archive_corrupt", "error", f"the archive cannot be read: {exc}")
        return
    except Exception as exc:  # noqa: BLE001 - zlib errors surface as several types
        issue(rec, "archive_corrupt", "error", f"the archive is damaged: {exc}")
        return
    if broken:
        issue(rec, "archive_corrupt", "error", f"damaged member in the archive: {broken}")
    rec["members"] = len(names)
    if ext == ".epub" and "META-INF/container.xml" not in names:
        issue(rec, "epub_invalid", "error", "not a valid EPUB (no META-INF/container.xml)")
    if ext == ".cbz":
        images = [n for n in names if re.search(r"\.(jpe?g|png|gif|webp|avif|bmp)$", n, re.I)]
        rec["pages"] = len(images)
        if not images:
            issue(rec, "no_pages", "error", "the comic archive holds no images")
    if ext == ".zip":
        inner = Counter(Path(n).suffix.lower() for n in names)
        rec["contents"] = dict(inner.most_common(8))


def check_file(path_str: str, quick: bool, want_hash: bool) -> dict[str, Any]:
    """Run every applicable check on one file. Runs inside a worker process."""
    path = Path(path_str)
    ext = path.suffix.lower()
    rec: dict[str, Any] = {"path": path_str, "ext": ext, "issues": []}
    try:
        size = path.stat().st_size
    except OSError as exc:
        issue(rec, "unreadable", "error", f"cannot stat the file: {exc}")
        return finish(rec)
    rec["size"] = size
    if size == 0:
        issue(rec, "empty_file", "error", "the file is empty (0 bytes)")
        return finish(rec)
    with path.open("rb") as fh:
        head = fh.read(4096)
    kind = sniff_type(head)
    rec["detected_type"] = kind
    expected = EXPECTED_TYPES.get(ext)
    if expected and kind not in expected:
        hint = {
            "html": "it is a web page - usually a failed or login-walled download",
            "zero-filled": "it is all zero bytes - an unfinished download",
            "zip": "it is a zip archive with the wrong extension",
        }.get(kind, f"it looks like {kind}")
        issue(rec, "wrong_type", "error", f"named {ext} but {hint}")
        return finish(rec)
    zeros = zero_filled_regions(path, size)
    if zeros:
        issue(
            rec,
            "zero_filled",
            "error",
            f"the {', '.join(zeros)} of the file is zero bytes - an unfinished download",
        )
    if want_hash:
        rec["sha256"] = sha256_of(path)

    if ext == ".pdf":
        with path.open("rb") as fh:
            fh.seek(max(0, size - 2048))
            tail = fh.read()
        if b"%%EOF" not in tail:
            issue(
                rec,
                "truncated",
                "warn",
                "no end-of-file marker - the file may be cut short",
            )
        if HAVE_FITZ:
            check_pdf(path, rec, quick)
        else:
            rec["deep_check"] = False
    elif ext in {".epub", ".cbz", ".zip"}:
        check_zip(path, rec, ext)
        if ext == ".epub" and HAVE_FITZ and not rec["issues"]:
            try:
                with fitz.open(str(path)) as doc:
                    rec["pages"] = doc.page_count
            except Exception as exc:  # noqa: BLE001
                issue(rec, "unreadable", "error", f"EPUB will not open: {exc}")
    return finish(rec)


def issue(rec: dict[str, Any], code: str, severity: str, detail: str) -> None:
    rec["issues"].append({"code": code, "severity": severity, "detail": detail})


def finish(rec: dict[str, Any]) -> dict[str, Any]:
    worst = max((_SEVERITY_RANK[i["severity"]] for i in rec["issues"]), default=0)
    if rec.get("locked"):
        rec["verdict"] = "locked"
    elif worst == 2:
        rec["verdict"] = "broken"
    elif worst == 1:
        rec["verdict"] = "warn"
    else:
        rec["verdict"] = "ok"
    rec.pop("locked", None)
    return rec


def short_list(pages: list[int], limit: int = 12) -> str:
    parts = [f"{a}-{b}" if a != b else str(a) for a, b in runs(pages)]
    text = ", ".join(parts[:limit])
    return text + (f", ... (+{len(parts) - limit} more)" if len(parts) > limit else "")


# ---------------------------------------------------------------- repairing --


def write_repaired(rec: dict[str, Any], src_root: Optional[Path], out_dir: Path, drop_blank: bool) -> None:
    """Write a rebuilt copy of a damaged-but-readable PDF. The original is untouched."""
    if not HAVE_FITZ or rec.get("ext") != ".pdf" or rec["verdict"] in {"locked"}:
        return
    codes = {i["code"] for i in rec["issues"]}
    fixable = codes & {"xref_repaired", "truncated", "blank_pages", "unreadable_pages"}
    if not fixable or codes & {"wrong_type", "empty_file", "zero_filled", "unreadable"}:
        return
    src = Path(rec["path"])
    rel = src.relative_to(src_root) if src_root and src.is_relative_to(src_root) else Path(src.name)
    dest = out_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with fitz.open(str(src)) as doc:
            removed = []
            if drop_blank and rec.get("blank_pages"):
                removed = sorted(rec["blank_pages"])
                doc.delete_pages([p - 1 for p in removed])
            doc.save(str(dest), garbage=3, deflate=True)
        rec["repaired_copy"] = str(dest)
        if removed:
            rec["repaired_dropped_pages"] = removed
    except Exception as exc:  # noqa: BLE001
        rec["repair_failed"] = str(exc)


# ------------------------------------------------------------------ workers --


def _worker(conn: Any, quick: bool, want_hash: bool) -> None:
    # MuPDF prints its complaints about damaged files from C, straight to file
    # descriptor 1, which would corrupt the JSON on stdout. Point it at stderr.
    os.dup2(2, 1)
    if HAVE_FITZ:
        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)
    while True:
        try:
            path = conn.recv()
        except EOFError:
            return
        if path is None:
            return
        try:
            conn.send(check_file(path, quick, want_hash))
        except Exception as exc:  # noqa: BLE001 - report, never kill the worker silently
            rec = {"path": path, "issues": []}
            issue(rec, "checker_error", "error", f"the checker failed on this file: {exc}")
            conn.send(finish(rec))


class Pool:
    """Worker processes that survive the files that kill them.

    A PDF that segfaults MuPDF or hangs it forever takes down only its own
    worker; the file is recorded as broken and a fresh worker replaces it.
    """

    def __init__(self, jobs: int, quick: bool, want_hash: bool, timeout: float) -> None:
        self.ctx = mp.get_context("spawn")
        self.quick, self.want_hash, self.timeout = quick, want_hash, timeout
        self.idle: list[Any] = [self._spawn() for _ in range(jobs)]
        self.busy: dict[Any, tuple[Any, str, float]] = {}

    def _spawn(self) -> tuple[Any, Any]:
        parent, child = self.ctx.Pipe()
        proc = self.ctx.Process(target=_worker, args=(child, self.quick, self.want_hash), daemon=True)
        proc.start()
        child.close()
        return proc, parent

    def run(self, paths: list[str]):
        pending = list(reversed(paths))
        while pending or self.busy:
            while pending and self.idle:
                proc, conn = self.idle.pop()
                path = pending.pop()
                conn.send(path)
                self.busy[conn] = (proc, path, time.monotonic())
            ready = mp_wait(list(self.busy), timeout=1.0)
            for conn in ready:
                proc, path, _ = self.busy.pop(conn)
                try:
                    yield conn.recv()
                    self.idle.append((proc, conn))
                except (EOFError, OSError):
                    rec = {"path": path, "issues": []}
                    issue(rec, "crashed", "error", "the file crashed the PDF engine")
                    yield finish(rec)
                    proc.join(1)
                    self.idle.append(self._spawn())
            now = time.monotonic()
            for conn, (proc, path, started) in list(self.busy.items()):
                if now - started > self.timeout:
                    self.busy.pop(conn)
                    proc.kill()
                    proc.join(1)
                    rec = {"path": path, "issues": []}
                    issue(rec, "timeout", "error", f"checking took longer than {self.timeout:.0f}s")
                    yield finish(rec)
                    self.idle.append(self._spawn())

    def close(self) -> None:
        for proc, conn in self.idle:
            try:
                conn.send(None)
            except OSError:
                pass
            proc.join(2)


# --------------------------------------------------------------------- main --


def collect(paths: list[str], include_all: bool) -> tuple[list[str], Optional[Path]]:
    files: list[str] = []
    root: Optional[Path] = None
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            root = root or p
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.name not in SKIP_NAMES and not f.name.startswith("._"):
                    if include_all or f.suffix.lower() in CHECKED_EXTS:
                        files.append(str(f))
        elif p.is_file():
            files.append(str(p))
        else:
            print(f"not found: {raw}", file=sys.stderr)
    return files, root


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="files or folders to check")
    ap.add_argument("--out", help="write JSON Lines here instead of stdout")
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--timeout", type=float, default=300, help="seconds allowed per file")
    ap.add_argument("--quick", action="store_true", help="sample pages instead of reading all")
    ap.add_argument("--hash", action="store_true", help="add a SHA-256 (finds exact duplicates)")
    ap.add_argument("--all-files", action="store_true", help="check every file, not just books/archives")
    ap.add_argument("--repair-out", help="write rebuilt copies of damaged-but-readable PDFs here")
    ap.add_argument("--drop-blank", action="store_true", help="with --repair-out, also remove blank pages")
    args = ap.parse_args(argv)

    files, root = collect(args.paths, args.all_files)
    if not files:
        print("no files to check", file=sys.stderr)
        return 1
    if not HAVE_FITZ:
        print(
            "PyMuPDF is not installed - only structural checks will run "
            "(pip install pymupdf for page-level checks)",
            file=sys.stderr,
        )
    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    repair_dir = Path(args.repair_out).expanduser().resolve() if args.repair_out else None
    verdicts: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    hashes: dict[str, list[str]] = {}
    pool = Pool(min(args.jobs, len(files)), args.quick, args.hash, args.timeout)
    started = time.monotonic()
    try:
        for n, rec in enumerate(pool.run(files), 1):
            if repair_dir:
                write_repaired(rec, root, repair_dir, args.drop_blank)
            verdicts[rec["verdict"]] += 1
            codes.update(i["code"] for i in rec["issues"] if i["severity"] != "info")
            if rec.get("sha256"):
                hashes.setdefault(rec["sha256"], []).append(rec["path"])
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if args.out and (n % 25 == 0 or n == len(files)):
                print(f"  checked {n}/{len(files)}", file=sys.stderr)
    finally:
        pool.close()
        if args.out:
            out.close()

    dupes = [paths for paths in hashes.values() if len(paths) > 1]
    print(
        f"\n{len(files)} file(s) in {time.monotonic() - started:.0f}s: "
        + ", ".join(f"{v} {k}" for k, v in sorted(verdicts.items())),
        file=sys.stderr,
    )
    if codes:
        print("issues: " + ", ".join(f"{c} x{n}" for c, n in codes.most_common()), file=sys.stderr)
    if dupes:
        print(f"exact duplicates: {len(dupes)} group(s)", file=sys.stderr)
        for group in dupes[:20]:
            print("  = " + " | ".join(group), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
