#!/usr/bin/env python3
"""
inventory.py - sort a pile of files into what Grimoire can take and what it cannot.

    python3 inventory.py ~/Downloads/unsorted --out inventory.json

Walks the folder (read-only) and buckets every file by what it is: books, images
(map, token or cover - decided later), audio, 3D models, archives, formats
Grimoire refuses, unfinished downloads, sidecars, Grimoire marker files, and
junk. Prints a summary and writes the full lists as JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

BUCKETS = {
    "books": {".pdf", ".epub", ".djvu", ".xps", ".cbz", ".cbr", ".cb7", ".cbt", ".txt", ".md", ".rtf"},
    "images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg", ".avif"},
    "video": {".webm", ".mp4", ".m4v"},
    "vtt": {".uvtt", ".dd2vtt", ".df2vtt"},
    "audio": {".mp3", ".ogg", ".opus", ".flac", ".wav", ".m4a", ".m4b", ".aac"},
    "models": {".stl", ".obj", ".ply", ".3mf", ".glb", ".gltf", ".lys", ".ctb", ".cbddlp", ".pwmx", ".photon"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".tbz2"},
    "unsupported_documents": {".doc", ".docx", ".odt", ".pages", ".mobi", ".azw", ".azw3", ".fb2",
                              ".lit", ".ppt", ".pptx", ".xls", ".xlsx", ".ods", ".psd", ".ai", ".indd"},
    "incomplete_downloads": {".part", ".crdownload", ".download", ".partial", ".!qb", ".aria2", ".tmp"},
    "sidecars": {".opf", ".nfo"},
}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini", ".localized"}
JUNK_EXTS = {".url", ".lnk", ".webloc", ".torrent", ".sfv", ".md5", ".sha1", ".log", ".ini", ".db"}
GRIMOIRE_MARKERS = {
    ".parent-system-container", ".one-page-container", ".system-agnostic-container",
    ".system-family-container", ".publisher-container", ".container", ".nsfw",
    ".no-auto-category", ".frames-container", ".grimoireignore", "tags.json",
}
EXT_TO_BUCKET = {ext: bucket for bucket, exts in BUCKETS.items() for ext in exts}


def bucket_for(path: Path) -> str:
    name = path.name.lower()
    if name in GRIMOIRE_MARKERS:
        return "grimoire_markers"
    if name in JUNK_NAMES or name.startswith("._"):
        return "junk"
    suffix = path.suffix.lower()
    if name.endswith((".tar.gz", ".tar.bz2")):
        return "archives"
    if name.endswith((".cover.jpg", ".grimoire.json", ".grimoire.yaml")):
        return "sidecars"
    if suffix in EXT_TO_BUCKET:
        return EXT_TO_BUCKET[suffix]
    if suffix in JUNK_EXTS:
        return "junk"
    return "unknown"


def inventory(root: Path) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    per_folder: dict[str, Counter[str]] = defaultdict(Counter)
    sizes: Counter[str] = Counter()
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        b = bucket_for(f)
        size = f.stat().st_size
        buckets[b].append({"path": str(rel), "size": size})
        sizes[b] += size
        top = rel.parts[0] if len(rel.parts) > 1 else "."
        per_folder[top][b] += 1
    return {
        "root": str(root),
        "counts": {b: len(v) for b, v in sorted(buckets.items())},
        "size_mb": {b: round(s / 1_048_576, 1) for b, s in sorted(sizes.items())},
        "top_folders": {k: dict(v) for k, v in sorted(per_folder.items())},
        "files": dict(sorted(buckets.items())),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--out", help="write the full inventory JSON here")
    args = ap.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 1
    inv = inventory(root)
    if args.out:
        Path(args.out).write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{root}")
    for bucket, count in inv["counts"].items():
        print(f"  {bucket:<24} {count:>6}  ({inv['size_mb'][bucket]} MB)")
    for bucket in ("unsupported_documents", "incomplete_downloads", "unknown", "grimoire_markers"):
        files = inv["files"].get(bucket, [])
        if files:
            print(f"\n{bucket}:")
            for f in files[:15]:
                print(f"  {f['path']}")
            if len(files) > 15:
                print(f"  ... and {len(files) - 15} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
