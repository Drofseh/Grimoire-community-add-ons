#!/usr/bin/env python3
"""
extract_evidence.py - gather everything a book says about itself, for identifying it.

Reads each file's embedded metadata, the text of its title, credits and legal
pages, its bookmarks, page size and count, and clues in its filename and folder
path, and writes one JSON object per file. It decides nothing: the output is
evidence for whoever (or whatever) does the identifying.

    python3 extract_evidence.py ~/Downloads/unsorted --out evidence.jsonl
    python3 extract_evidence.py inbox/ --out ev.jsonl --digest digest.md --covers covers/
    python3 extract_evidence.py inbox/ --skip-broken health.jsonl   # skip files pdf_health.py failed

--digest writes a compact Markdown table (one row per file) that is quick to read
before diving into the full records. --covers renders each book's first page as a
PNG, for when the text is not enough - a scan with no text layer, a cover whose
title is artwork.

Purchase watermarks ("Jane Doe (order #1234567)") are stripped from the extracted
text and only reported as present, so a buyer's name never travels further.

Needs PyMuPDF (`pip install pymupdf`) for PDF/EPUB/CBZ/XPS contents; without it
only the filename, path and sidecar clues are extracted.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Optional

try:
    import fitz  # PyMuPDF

    HAVE_FITZ = True
except ImportError:  # pragma: no cover
    fitz = None
    HAVE_FITZ = False

DOC_EXTS = {".pdf", ".epub", ".xps", ".cbz", ".fb2", ".mobi"}
BOOK_EXTS = DOC_EXTS | {".djvu", ".cbr", ".cb7", ".cbt", ".txt", ".md", ".rtf"}
# Formats people keep beside books that Grimoire does not index.
UNSUPPORTED_DOC_EXTS = {".doc", ".docx", ".odt", ".pages", ".mobi", ".azw", ".azw3", ".fb2", ".lit"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# ------------------------------------------------------------------ patterns --

# Publisher product-code formats. A match is a strong hint, not proof - always
# confirm against the book's own credits/legal page or a metadata lookup.
PRODUCT_CODES = [
    (r"PZO\s?\d{4,5}[A-Z]?", "Paizo"),
    (r"CHA\s?\d{4,5}[A-Z]?", "Chaosium"),
    (r"CB7\s?\d{3,5}", "Cubicle 7"),
    (r"MUH\d{5,7}", "Modiphius"),
    (r"S2P\d{5}", "Pinnacle Entertainment Group"),
    (r"PEG\s?\d{4,5}", "Pinnacle Entertainment Group"),
    (r"GMG\s?\d{3,5}", "Goodman Games"),
    (r"MGP\s?\d{3,5}", "Mongoose Publishing"),
    (r"EHP\d{3,5}", "Evil Hat Productions"),
    (r"CAT\s?\d{5}[A-Z]?", "Catalyst Game Labs"),
    (r"WW\s?\d{4,5}", "White Wolf"),
    (r"GRR\s?\d{4}", "Green Ronin"),
    (r"MCG\s?\d{3}", "Monte Cook Games"),
    (r"TSR\s?\d{4,5}", "TSR"),
    (r"AG\s?\d{4}", "Atlas Games"),
    (r"EDN\s?\d{4}", "Eden Studios"),
    (r"AEG\s?\d{4}", "Alderac Entertainment Group"),
    (r"SJG\s?\d{2}-\d{4}", "Steve Jackson Games"),
    (r"FLF[-\s]?[A-Z]{2,4}\d{2,3}", "Free League"),
    (r"FAS\s?\d{4,5}", "FASA"),
    (r"WEG\s?\d{5}", "West End Games"),
    (r"ICE\s?\d{4}", "Iron Crown Enterprises"),
    (r"GDW\s?\d{3,4}", "Game Designers' Workshop"),
]
_CODE_RES = [(re.compile(rf"(?<![A-Za-z0-9]){p}(?![0-9])"), pub) for p, pub in PRODUCT_CODES]

_EDITION_RES = [
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)[\s._-]*ed(?:ition|\.)?\b", re.I),
    re.compile(r"\b(first|second|third|fourth|fifth|sixth|seventh)\s+edition\b", re.I),
    re.compile(r"(?<![A-Za-z0-9])(\d(?:\.\d)?)\s?e(?![A-Za-z])", re.I),
    re.compile(r"\b(revised|anniversary|deluxe|remastered|legacy|redux|reloaded|classic)\b(?:\s+edition)?", re.I),
    re.compile(r"\((19[7-9]\d|20[0-4]\d)\)"),
]
_VERSION_RE = re.compile(r"(?<![A-Za-z])v(?:er(?:sion)?)?[\s._-]?(\d+(?:\.\d+){0,3})\b", re.I)
_VARIANT_RE = re.compile(
    r"\b(printer[\s_-]?friendly|print(?:[\s_-]?(?:version|ready))?|for[\s_-]print|low[\s_-]?ink|"
    r"no[\s_-]?art|no[\s_-]?background|screen|digital(?:[\s_-]edition)?|web|letter|a4|a5|"
    r"spreads?|single[\s_-]?pages?|panels|gatefold|b&w|bw|black[\s_-]and[\s_-]white|"
    r"greyscale|grayscale|colou?r|mono|hyperlinked|bookmarked|lite|compressed|"
    r"rescan|ocr|scan(?:ned)?|fillable|form[\s_-]?fillable|editable)\b",
    re.I,
)
# The variant words that never belong in a title, so the title guess can drop
# them. "Screen", "Digital" and "Colour" stay: they start real titles (GM Screen).
_TITLE_STRIP_RE = re.compile(
    r"(?<![A-Za-z])(printer[\s_-]?friendly|print(?:[\s_-]?(?:version|ready))?|for[\s_-]print|"
    r"low[\s_-]?ink|no[\s_-]?art|spreads|single[\s_-]?pages?|compressed|hyperlinked|"
    r"bookmarked|letter|a4|a5|rescan|ocr)(?![A-Za-z])",
    re.I,
)
_STATUS_RE = re.compile(
    r"\b(preview|quick[\s_-]?start|quickstart|ashcan|playtest|beta|alpha|draft|"
    r"preview[\s_-]edition|free[\s_-]rpg[\s_-]day|frpgd|sampler|demo|teaser)\b",
    re.I,
)
_SERIES_RE = re.compile(
    r"\b(part|pt|vol(?:ume)?|book|issue|no|chapter|episode|#)\.?\s*(\d{1,4})\b", re.I
)
_NOISE_RE = re.compile(
    r"\[(?:[^\]]*)\]|\((?:dtrpg|drivethru(?:rpg)?|watermarked|ocr|\d)\)|"
    r"\b(?:drivethru(?:rpg)?|dtrpg|rpgnow|itch\.io|final|copy|hq|lq|optimized|opt)\b",
    re.I,
)
_ISBN_RE = re.compile(r"(?:ISBN(?:-1[03])?:?\s*)?((?:97[89][\s-]?)?(?:\d[\s-]?){9}[\dXx])\b")
_YEAR_RE = re.compile(r"(?:©|\(c\)|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19[6-9]|20[0-4])\d)", re.I)
_WATERMARK_RE = re.compile(
    r"order\s*#\s*\d{4,}|purchased by|licensed to|exclusive use of|this copy (?:is|was) "
    r"(?:made|prepared|purchased)|watermark",
    re.I,
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LEGAL_RE = re.compile(
    r"isbn|©|copyright|all rights reserved|published by|printed in|credits|written by|"
    r"writ(?:ing|ers?)\b|design(?:ed|er|ers)?\b|developer|editor|layout|cover art|"
    r"illustrat|artwork|art direction|open game license|trademark",
    re.I,
)
_CREDIT_LABEL_RE = re.compile(
    r"^\s*(?:lead\s+)?(written by|writing|writers?|authors?|by|design(?:ed by|ers?)?|"
    r"game design|developer|development|edit(?:ed by|ing|ors?)|cover(?: art(?:ist)?| "
    r"illustration)?|interior (?:art|illustrations?)|art(?:ists?|work)?|illustrat\w*|"
    r"cartograph\w*|maps?|layout|graphic design|publisher|line developer)\s*[:\-–]?\s*(.*)$",
    re.I,
)

# Phrases that name a licence or a system's third-party programme. Each is
# evidence for the licence field, for the system, or for "this is community
# content" (homebrew) - the identifier decides which.
LICENSE_HINTS = {
    "Open Game License": r"open game licen[sc]e|\bOGL\b",
    "ORC License": r"\bORC licen[sc]e|open rpg creative",
    "Creative Commons": r"creative commons|\bCC[-\s]BY",
    "Dungeon Masters Guild": r"dungeon ?masters ?guild|\bDMs ?Guild\b",
    "Pathfinder Infinite": r"pathfinder infinite",
    "Starfinder Infinite": r"starfinder infinite",
    "Storytellers Vault": r"storytellers vault",
    "Chronicle System": r"chronicle system",
    "Miskatonic Repository": r"miskatonic repository",
    "Jonstown Compendium": r"jonstown compendium",
    "Explorer's Society": r"explorer'?s society",
    "Free League Workshop": r"free league workshop",
    "Cypher System Open License": r"cypher system open licen[sc]e|cypher system creator",
    "Mörk Borg Third Party": r"m[öo]rk borg third party|not affiliated with ockult",
    "Powered by the Apocalypse": r"powered by the apocalypse|\bPbtA\b",
    "Forged in the Dark": r"forged in the dark",
    "Carved from Brindlewood": r"carved from brindlewood",
    "Year Zero Engine": r"year zero engine|\bYZE\b",
    "Savage Worlds fan/licence": r"savage worlds (?:adventure edition )?(?:fan|licen[sc]e)|savage worlds is",
    "Belonging Outside Belonging": r"belonging outside belonging|no dice no masters",
    "Black Hack / OSR": r"black hack|old[- ]school (?:revival|renaissance)|\bOSR\b",
    "Old-School Essentials": r"old[- ]school essentials|\bOSE\b",
    "Shadowdark third-party": r"shadowdark rpg third[- ]party|designed for use with shadowdark",
    "Mothership Third Party": r"mothership.*third party|third party.*mothership|tuesday knight games",
    "Basic Roleplaying ORC": r"basic roleplaying|\bBRP\b",
}
_LICENSE_RES = {k: re.compile(v, re.I) for k, v in LICENSE_HINTS.items()}

# Stopwords for a cheap language guess (ISO 639-1 code -> words).
STOPWORDS = {
    "en": "the and of to in is that for with you your are this be as on",
    "de": "der die und das ist nicht mit sich ein eine auf für dem den zu",
    "fr": "le la les et des est une pour dans que qui sur pas vous avec",
    "es": "el la los las y que del en por una para con como es se",
    "it": "il di che la per una del sono con non nel della gli le è",
    "pt": "o a os as que de do da em um uma para com não é se",
    "nl": "de het een en van is dat op te zijn met voor niet",
    "sv": "och att det som en på är för med av till den har inte",
    "pl": "i w na się z że do nie jest to jak od po",
}
_STOP = {lang: set(words.split()) for lang, words in STOPWORDS.items()}
LANGUAGE_NAMES = {
    "en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
}

# Printed page sizes in inches (width, height), portrait.
PAGE_SIZES = {
    "US Letter": (8.5, 11.0),
    "A4": (8.27, 11.69),
    "A5": (5.83, 8.27),
    "Digest": (5.5, 8.5),
    "US Trade": (6.0, 9.0),
    "B5": (6.93, 9.84),
    "Royal": (6.14, 9.21),
    "US Legal": (8.5, 14.0),
    "Tabloid": (11.0, 17.0),
    "A6": (4.13, 5.83),
}

_JUNK_META_RE = re.compile(
    r"^(untitled|document\d*|layout\s*\d*|book\d*|print|title|cover|pdf|indd|"
    r"microsoft (word|powerpoint)\b.*|adobe .*|.*\.(docx?|indd|pdf|qxd|pub|rtf|odt|ps|tif)|"
    r"\d+|[a-f0-9-]{16,}|[\W_]*)$",
    re.I,
)


# ------------------------------------------------------------------- helpers --


def isbn_valid(raw: str) -> Optional[str]:
    digits = re.sub(r"[\s-]", "", raw).upper()
    if len(digits) == 10 and re.fullmatch(r"\d{9}[\dX]", digits):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
        return digits if total % 11 == 0 else None
    if len(digits) == 13 and digits.isdigit() and digits[:3] in {"978", "979"}:
        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits))
        return digits if total % 10 == 0 else None
    return None


def find_isbns(text: str) -> list[str]:
    out = []
    for m in _ISBN_RE.finditer(text):
        ok = isbn_valid(m.group(1))
        if ok and ok not in out:
            out.append(ok)
    return out


def product_codes(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for rx, pub in _CODE_RES:
        for m in rx.finditer(text):
            code = re.sub(r"\s", "", m.group(0)).upper()
            if not any(f["code"] == code for f in found):
                found.append({"code": code, "publisher_hint": pub})
    return found


def split_camel(s: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)


def filename_clues(stem: str) -> dict[str, Any]:
    """What a filename says, and a cleaned-up guess at the title inside it."""
    clues: dict[str, Any] = {}
    codes = product_codes(stem.upper())
    if codes:
        clues["product_codes"] = codes
    isbns = find_isbns(stem)
    if isbns:
        clues["isbn"] = isbns
    editions = sorted({m.group(0).strip() for rx in _EDITION_RES for m in rx.finditer(stem)})
    if editions:
        clues["edition"] = editions
    v = _VERSION_RE.search(stem)
    if v:
        clues["version"] = v.group(1)
    variants = sorted({m.group(0).lower() for m in _VARIANT_RE.finditer(stem.replace("_", " "))})
    if variants:
        clues["variant"] = variants
    status = sorted({m.group(0).lower() for m in _STATUS_RE.finditer(stem.replace("_", " "))})
    if status:
        clues["status"] = status
    series = [f"{m.group(1)} {m.group(2)}" for m in _SERIES_RE.finditer(stem.replace("_", " "))]
    if series:
        clues["series"] = series

    # Names that went through a web page arrive as "Art &amp Magic" or "Art &amp; Magic".
    title = html.unescape(re.sub(r"&(amp|quot|apos|lt|gt)(?!;)", r"&\1;", stem))
    # Underscores are word characters, so "_FINAL" would hide from \b-anchored noise words.
    title = title.replace("_", " ")
    title = _NOISE_RE.sub(" ", title)
    for c in codes:
        pattern = re.sub(r"(?<=[A-Z])(?=\d)", r"[\\s_-]?", c["code"])
        title = re.sub(pattern, " ", title, flags=re.I)
    title = _VERSION_RE.sub(" ", title)
    title = _TITLE_STRIP_RE.sub(" ", title)
    title = split_camel(title)
    title = re.sub(r"[_.]+", " ", title)
    title = re.sub(r"\s*[-–]\s*$|^\s*[-–]\s*", "", title)
    title = re.sub(r"\s{2,}", " ", title).strip(" -–_")
    clues["title_guess"] = title
    return clues


def folder_hints(path: Path, root: Optional[Path]) -> list[str]:
    try:
        parts = path.parent.relative_to(root).parts if root else path.parent.parts[-3:]
    except ValueError:
        parts = path.parent.parts[-3:]
    return [p for p in parts if p not in {".", ""}]


def is_junk_meta(value: str, stem: str) -> bool:
    v = value.strip()
    return (
        len(v) < 3
        or bool(_JUNK_META_RE.match(v))
        or v.lower() == stem.lower()
        or v.lower().replace(" ", "_") == stem.lower()
    )


def clean_text(text: str) -> tuple[str, bool]:
    """Drop purchase-watermark lines and e-mail addresses; say if any were found."""
    kept, marked = [], False
    for line in text.splitlines():
        if _WATERMARK_RE.search(line):
            marked = True
            continue
        kept.append(_EMAIL_RE.sub("[email]", line))
    joined = "\n".join(kept)
    joined = re.sub(r"[ \t]+", " ", joined)
    joined = re.sub(r"\n\s*\n+", "\n", joined)
    return joined.strip(), marked


def guess_language(text: str) -> Optional[dict[str, Any]]:
    words = re.findall(r"[a-zà-ÿäöüßåøæ]+", text.lower())
    if len(words) < 40:
        return None
    counts = Counter(words)
    scores = {lang: sum(counts[w] for w in stop) for lang, stop in _STOP.items()}
    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    if scores[best] < 8:
        return None
    return {"code": best, "name": LANGUAGE_NAMES[best], "confidence": round(scores[best] / total, 2)}


def page_size(width_pt: float, height_pt: float) -> dict[str, Any]:
    w, h = width_pt / 72, height_pt / 72
    landscape = w > h * 1.05
    pw, ph = (h, w) if landscape else (w, h)
    name = None
    for label, (sw, sh) in PAGE_SIZES.items():
        if abs(pw - sw) < 0.2 and abs(ph - sh) < 0.25:
            name = label
            break
    info: dict[str, Any] = {"inches": [round(w, 2), round(h, 2)], "landscape": landscape}
    if name:
        info["name"] = name
    if landscape:
        for label, (sw, sh) in PAGE_SIZES.items():
            if abs(w - 2 * sw) < 0.4 and abs(h - sh) < 0.3:
                info["spreads_of"] = label  # two portrait pages side by side
                break
    return info


def credit_lines(text: str, limit: int = 14) -> list[str]:
    out = []
    for line in text.splitlines():
        if _CREDIT_LABEL_RE.match(line) and 4 < len(line) < 160:
            out.append(line.strip())
            if len(out) >= limit:
                break
    return out


def parse_xmp(xml: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tag, key in (("dc:title", "title"), ("dc:creator", "creators"), ("dc:publisher", "publisher"),
                     ("dc:description", "description"), ("dc:subject", "subjects"),
                     ("dc:identifier", "identifier"), ("dc:language", "language")):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.S)
        if m:
            items = re.findall(r"<rdf:li[^>]*>(.*?)</rdf:li>", m.group(1), re.S) or [m.group(1)]
            items = [re.sub(r"<[^>]+>", "", i).strip() for i in items]
            items = [i for i in items if i]
            if items:
                out[key] = items if key in {"creators", "subjects"} else items[0]
    m = re.search(r"<xmp:CreatorTool>(.*?)</xmp:CreatorTool>", xml)
    if m:
        out["creator_tool"] = m.group(1).strip()
    return out


def read_opf(path: Path) -> Optional[dict[str, Any]]:
    candidates = [path.with_suffix(".opf"), path.parent / "metadata.opf"]
    for opf in candidates:
        if not opf.is_file():
            continue
        try:
            root = ET.parse(opf).getroot()
        except ET.ParseError:
            return {"file": opf.name, "error": "unparseable"}
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        get = lambda tag: [e.text.strip() for e in root.iter(f"{{{ns['dc']}}}{tag}") if e.text]  # noqa: E731
        return {
            "file": opf.name,
            "title": next(iter(get("title")), None),
            "creators": get("creator"),
            "publisher": next(iter(get("publisher")), None),
            "date": next(iter(get("date")), None),
            "identifiers": get("identifier"),
            "subjects": get("subject"),
            "language": next(iter(get("language")), None),
            "description": (next(iter(get("description")), "") or "")[:600] or None,
        }
    return None


# -------------------------------------------------------------- extraction --


def document_evidence(path: Path, rec: dict[str, Any], args: argparse.Namespace) -> None:
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001
        rec["open_error"] = str(exc)
        return
    with doc:
        if doc.needs_pass:
            rec["open_error"] = "password required"
            return
        stem = path.stem
        meta = {k: v for k, v in (doc.metadata or {}).items() if v and k != "format"}
        if meta:
            junk = [k for k in ("title", "author", "subject") if k in meta and is_junk_meta(meta[k], stem)]
            m = re.match(r"D:(\d{4})", meta.get("creationDate", ""))
            if m:
                meta["created_year"] = int(m.group(1))
            for k in ("creationDate", "modDate"):
                meta.pop(k, None)
            if junk:
                meta["junk_fields"] = junk
            rec["embedded_metadata"] = meta
        try:
            xmp = doc.get_xml_metadata()
            if xmp:
                parsed = parse_xmp(xmp)
                if parsed:
                    rec["xmp"] = parsed
        except Exception:  # noqa: BLE001
            pass

        count = doc.page_count
        rec["pages"] = count
        if count == 0:
            return
        first = doc.load_page(0)
        rec["page_size"] = page_size(first.rect.width, first.rect.height)
        if path.suffix.lower() == ".pdf":
            rec["form_fields"] = bool(doc.is_form_pdf)
        try:
            toc = doc.get_toc(simple=True)
        except Exception:  # noqa: BLE001
            toc = []
        if toc:
            rec["toc"] = [[lvl, title.strip()[:90], pg] for lvl, title, pg in toc if lvl <= 2][: args.toc]
            rec["toc_entries"] = len(toc)

        texts: dict[int, str] = {}
        watermarked = False

        def text_of(i: int) -> str:
            nonlocal watermarked
            if i not in texts:
                try:
                    raw = doc.load_page(i).get_text("text")
                except Exception:  # noqa: BLE001
                    raw = ""
                cleaned, marked = clean_text(raw)
                watermarked |= marked
                texts[i] = cleaned
            return texts[i]

        limit = args.text_chars
        opening = [i for i in range(min(3, count))]
        legal = [i for i in range(3, min(10, count)) if _LEGAL_RE.search(text_of(i))][:3]
        closing = [i for i in range(max(min(10, count), count - 3), count) if _LEGAL_RE.search(text_of(i))][:2]
        pages_out = []
        for i in opening + legal + closing:
            t = text_of(i)
            if t:
                pages_out.append({"page": i + 1, "text": t[:limit]})
        rec["text_layer"] = any(len(text_of(i)) > 40 for i in range(min(count, 12)))
        if pages_out:
            rec["page_text"] = pages_out

        scanned = "\n".join(text_of(i) for i in sorted(set(opening + legal + closing + list(range(min(8, count))))))
        isbns = find_isbns(scanned)
        if isbns:
            rec["isbn_in_text"] = isbns
        codes = product_codes(scanned)
        if codes:
            rec["product_codes_in_text"] = codes
        years = sorted({int(y) for y in _YEAR_RE.findall(scanned)})
        if years:
            rec["copyright_years"] = years
        credits = credit_lines(scanned)
        if credits:
            rec["credit_lines"] = credits
        licenses = sorted(k for k, rx in _LICENSE_RES.items() if rx.search(scanned))
        if licenses:
            rec["license_or_program_hints"] = licenses
        lang = guess_language(scanned)
        if lang:
            rec["language_guess"] = lang
        if watermarked:
            rec["purchase_watermark"] = True

        if args.covers:
            try:
                out_dir = Path(args.covers)
                out_dir.mkdir(parents=True, exist_ok=True)
                name = hashlib.sha1(str(path).encode()).hexdigest()[:12] + ".png"
                zoom = args.cover_width / max(first.rect.width, 1)
                first.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).save(str(out_dir / name))
                rec["cover_image"] = str(out_dir / name)
            except Exception as exc:  # noqa: BLE001
                rec["cover_error"] = str(exc)


def evidence_for(path: Path, root: Optional[Path], args: argparse.Namespace) -> dict[str, Any]:
    ext = path.suffix.lower()
    rec: dict[str, Any] = {
        "path": str(path),
        "rel_path": str(path.relative_to(root)) if root and path.is_relative_to(root) else path.name,
        "folders": folder_hints(path, root),
        "file": path.name,
        "ext": ext,
        "size_mb": round(path.stat().st_size / 1_048_576, 2),
        "filename": filename_clues(path.stem),
    }
    if ext in UNSUPPORTED_DOC_EXTS - DOC_EXTS:
        rec["unsupported"] = f"Grimoire does not index {ext} files - convert to PDF or leave out"
    opf = read_opf(path)
    if opf:
        rec["sidecar_opf"] = opf
    if HAVE_FITZ and ext in DOC_EXTS | {".cbz"}:
        document_evidence(path, rec, args)
    elif ext in {".txt", ".md"}:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[: args.text_chars]
            rec["page_text"] = [{"page": 1, "text": clean_text(head)[0]}]
        except OSError as exc:
            rec["open_error"] = str(exc)
    return rec


def digest_row(rec: dict[str, Any]) -> str:
    meta = rec.get("embedded_metadata", {})
    junk = set(meta.get("junk_fields", []))
    title = meta.get("title") if "title" in meta and "title" not in junk else ""
    author = meta.get("author") if "author" in meta and "author" not in junk else ""
    first = ""
    for p in rec.get("page_text", []):
        first = " / ".join(line for line in p["text"].splitlines()[:4] if line.strip())
        break
    hints = []
    fn = rec["filename"]
    for key in ("product_codes",):
        hints += [c["code"] for c in fn.get(key, [])]
    hints += [c["code"] for c in rec.get("product_codes_in_text", []) if c["code"] not in hints]
    if rec.get("isbn_in_text"):
        hints.append("ISBN " + rec["isbn_in_text"][0])
    hints += fn.get("edition", []) + fn.get("variant", []) + fn.get("status", [])
    hints += rec.get("license_or_program_hints", [])[:3]
    if rec.get("form_fields"):
        hints.append("fillable form")
    size = rec.get("page_size", {})
    if size.get("landscape"):
        hints.append("landscape" + (f" spreads ({size['spreads_of']})" if size.get("spreads_of") else ""))
    if rec.get("text_layer") is False:
        hints.append("no text layer")
    if rec.get("unsupported"):
        hints.append("UNSUPPORTED FORMAT")
    cells = [
        rec["rel_path"],
        str(rec.get("pages", "")),
        (title or "")[:60],
        (author or "")[:40],
        first[:110],
        ", ".join(dict.fromkeys(hints))[:140],
    ]
    return "| " + " | ".join(c.replace("|", "/").replace("\n", " ") for c in cells) + " |"


def collect(paths: list[str], skip: set[str]) -> tuple[list[Path], Optional[Path]]:
    files: list[Path] = []
    root: Optional[Path] = None
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            root = root or p
            for f in sorted(p.rglob("*")):
                if (
                    f.is_file()
                    and f.name not in SKIP_NAMES
                    and not f.name.startswith(".")
                    and f.suffix.lower() in BOOK_EXTS | UNSUPPORTED_DOC_EXTS
                    and str(f) not in skip
                ):
                    files.append(f)
        elif p.is_file() and str(p) not in skip:
            files.append(p)
    return files, root


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", help="JSON Lines output (default stdout)")
    ap.add_argument("--digest", help="also write a one-row-per-file Markdown table here")
    ap.add_argument("--covers", help="render each first page as a PNG into this folder")
    ap.add_argument("--cover-width", type=int, default=480)
    ap.add_argument("--text-chars", type=int, default=1200, help="max characters kept per page")
    ap.add_argument("--toc", type=int, default=40, help="max bookmark entries kept")
    ap.add_argument("--skip-broken", help="pdf_health.py JSONL; files it judged broken are skipped")
    args = ap.parse_args(argv)

    skip: set[str] = set()
    if args.skip_broken:
        for line in Path(args.skip_broken).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("verdict") in {"broken", "locked"}:
                    skip.add(r["path"])
    files, root = collect(args.paths, skip)
    if not files:
        print("no files to read", file=sys.stderr)
        return 1
    if not HAVE_FITZ:
        print("PyMuPDF is not installed - only filename/path clues will be extracted", file=sys.stderr)
    if HAVE_FITZ:
        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    rows = []
    try:
        for n, f in enumerate(files, 1):
            try:
                rec = evidence_for(f, root, args)
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
                rec = {"path": str(f), "file": f.name, "rel_path": f.name, "filename": {}, "error": str(exc)}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(digest_row(rec))
            if args.out and (n % 25 == 0 or n == len(files)):
                print(f"  read {n}/{len(files)}", file=sys.stderr)
    finally:
        if args.out:
            out.close()
    if args.digest:
        header = (
            "| file | pages | embedded title | embedded author | opening text | clues |\n"
            "|---|---|---|---|---|---|\n"
        )
        Path(args.digest).write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    if skip:
        print(f"skipped {len(skip)} broken/locked file(s) from the health report", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
