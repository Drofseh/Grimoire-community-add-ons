import json
import pytest


class TestMetadataRules:
    def test_clean_metadata_drops_empties_category_and_unknowns(self, api):
        out = api.clean_metadata({"title": "T", "category": "core", "authors": "A", "isbn": "",
                                  "artists": [], "bogus": 1, "year": 1999})
        assert out == {"title": "T", "authors": ["A"], "year": 1999}

    def test_fill_only_keeps_existing_values(self, api):
        meta = {"title": "Real", "publisher": "P", "year": 2001}
        current = {"title": "Already Set", "publisher": "", "year": None}
        assert api.fill_only(meta, current) == {"publisher": "P", "year": 2001}

    def test_fill_only_replaces_a_filename_title(self, api):
        current = {"title": "Ars Magica 4e   core v2"}
        assert api.fill_only({"title": "Ars Magica"}, current, "Ars_Magica-4e - core-v2") == {
            "title": "Ars Magica"
        }


class FakeClient:
    """In-memory stand-in for the Grimoire API, enough for apply_plan."""

    def __init__(self):
        self.dirs = {"books"}
        self.files = {}  # path -> {"size", "record_id"}
        self.calls = []
        self.patches = {}
        self.tags = []
        self.next_id = 1

    def ensure_dir(self, path, container_kind="", nsfw=False, dry_run=False):
        parts = path.split("/")
        made = []
        for i in range(2, len(parts) + 1):
            p = "/".join(parts[:i])
            if p not in self.dirs:
                made.append(p)
                if not dry_run:
                    self.dirs.add(p)
        return made

    def upload(self, file, dest_dir, name=None, on_conflict="skip"):
        target = f"{dest_dir}/{name or file.name}"
        if target in self.files:
            raise _api().ApiError(409, "exists", "POST", "/api/files/upload")
        self.files[target] = {"size": file.stat().st_size, "record_id": None}
        self.calls.append(("upload", target))
        return {"path": target}

    def exists(self, path):
        f = self.files.get(path)
        return {"name": path.rsplit("/", 1)[1], "size": f["size"]} if f else None

    def browse(self, path):
        entries = [
            {"name": p.rsplit("/", 1)[1], "record_id": f["record_id"]}
            for p, f in self.files.items() if p.rsplit("/", 1)[0] == path
        ]
        return {"entries": entries}

    def rescan(self, scope, metadata_mode="new", wait=True):
        self.calls.append(("rescan", scope))
        for p, f in self.files.items():
            if p.startswith(scope + "/") and not f["record_id"]:
                f["record_id"] = f"id-{self.next_id}"
                self.next_id += 1
        return {"status": "scan_started"}

    def post(self, endpoint, body=None, **params):
        if endpoint == "/api/books/bulk/tags":
            self.tags.append((body["tags"][0], sorted(body["ids"])))
            return {"updated": len(body["ids"])}
        if endpoint == "/api/files/move":
            src = body["sources"][0]
            dest = f"{body['destination']}/{src.rsplit('/', 1)[1]}"
            self.files[dest] = self.files.pop(src)
            self.calls.append(("move", dest))
            return {"moved": [dest], "skipped": []}
        if endpoint == "/api/files/rename":
            f = self.files.pop(body["path"])
            self.files[body["path"].rsplit("/", 1)[0] + "/" + body["new_name"]] = f
            return {}
        raise AssertionError(endpoint)

    def request(self, method, endpoint, body=None, **kw):
        assert method == "PATCH"
        self.patches[endpoint.rsplit("/", 1)[1]] = body
        return {}

    def get(self, endpoint, **params):
        return {"title": "old name", "publisher": "Kept Publisher"}


def _api():
    import grimoire_api

    return grimoire_api


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "pile"
    (root / "a").mkdir(parents=True)
    (root / "a" / "one.pdf").write_bytes(b"%PDF one")
    (root / "a" / "two.pdf").write_bytes(b"%PDF two!")
    return root


def write_plan(tmp_path, root, items, folders=()):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"version": 1, "source": {"kind": "local", "root": str(root)},
                                "folders": list(folders), "items": items}))
    return plan


class TestApplyPlan:
    ITEMS = [
        {"id": "1", "source": "a/one.pdf", "action": "upload", "dest_dir": "books/Game/Core",
         "dest_name": "One.pdf", "metadata": {"title": "One", "category": "core", "year": 2001},
         "health_tags": ["Health: missing pages"]},
        {"id": "2", "source": "a/two.pdf", "action": "upload", "dest_dir": "books/Game/Adventures",
         "metadata": {"title": "Two"}},
        {"id": "3", "source": "a/bad.pdf", "action": "quarantine", "reason": "broken"},
    ]

    def test_dry_run_changes_nothing(self, api, tmp_path, source):
        fake = FakeClient()
        plan = write_plan(tmp_path, source, self.ITEMS)
        report = api.apply_plan(fake, plan, dry_run=True, overwrite=False, rescan=True)
        assert report["placed"] == 2 and report["skipped"] == 1
        assert fake.files == {} and fake.dirs == {"books"}
        assert not (tmp_path / "plan.state.json").exists()

    def test_uploads_rescans_patches_and_tags(self, api, tmp_path, source):
        fake = FakeClient()
        plan = write_plan(tmp_path, source, self.ITEMS,
                          folders=[{"path": "books/Game", "container_kind": ""}])
        report = api.apply_plan(fake, plan, dry_run=False, overwrite=False, rescan=True)
        assert report["errors"] == []
        assert set(fake.files) == {"books/Game/Core/One.pdf", "books/Game/Adventures/two.pdf"}
        assert ("rescan", "books/Game") in fake.calls
        rid = report["records"]["1"]
        # Fresh uploads take the plan's values; category never reaches the API.
        assert fake.patches[rid] == {"title": "One", "year": 2001}
        assert fake.tags == [("Health: missing pages", [rid])]

    def test_rerun_resumes_without_repeating(self, api, tmp_path, source):
        fake = FakeClient()
        plan = write_plan(tmp_path, source, self.ITEMS)
        api.apply_plan(fake, plan, dry_run=False, overwrite=False, rescan=True)
        fake.calls.clear()
        fake.patches.clear()
        report = api.apply_plan(fake, plan, dry_run=False, overwrite=False, rescan=True)
        assert fake.calls == [] and fake.patches == {}
        assert report["placed"] == 0

    def test_interrupted_upload_is_recognised(self, api, tmp_path, source):
        fake = FakeClient()
        fake.files["books/Game/Core/One.pdf"] = {"size": len(b"%PDF one"), "record_id": None}
        plan = write_plan(tmp_path, source, self.ITEMS[:1])
        report = api.apply_plan(fake, plan, dry_run=False, overwrite=False, rescan=True)
        assert report["errors"] == [] and report["placed"] == 1

    def test_different_file_with_same_name_is_an_error(self, api, tmp_path, source):
        fake = FakeClient()
        fake.files["books/Game/Core/One.pdf"] = {"size": 999, "record_id": "x"}
        plan = write_plan(tmp_path, source, self.ITEMS[:1])
        report = api.apply_plan(fake, plan, dry_run=False, overwrite=False, rescan=True)
        assert report["placed"] == 0
        assert "different file" in report["errors"][0]["error"]

    def test_library_moves_keep_existing_values(self, api, tmp_path):
        fake = FakeClient()
        fake.files["books/Inbox/old name.pdf"] = {"size": 1, "record_id": "rec-9"}
        plan = tmp_path / "plan.json"
        plan.write_text(json.dumps({"version": 1, "source": {"kind": "library", "root": "books/Inbox"},
                                    "items": [{"id": "m", "source": "books/Inbox/old name.pdf",
                                               "action": "move", "dest_dir": "books/Game/Core",
                                               "dest_name": "New.pdf",
                                               "metadata": {"title": "New", "publisher": "Other"}}]}))
        report = api.apply_plan(fake, plan, dry_run=False, overwrite=False, rescan=True)
        assert "books/Game/Core/New.pdf" in fake.files
        assert not any(c[0] == "rescan" for c in fake.calls)  # the record moved with the file
        # The filename-derived title is replaced; a publisher someone set is kept.
        assert fake.patches["rec-9"] == {"title": "New"}
        assert report["records"] == {"m": "rec-9"}


class TestInventory:
    def test_buckets(self, inventory, tmp_path):
        for name in ["a/book.PDF", "a/map.jpg", "a/notes.docx", "a/x.part", "a/.DS_Store",
                     "a/.parent-system-container", "a/b.opf", "a/song.mp3", "a/mini.stl",
                     "a/pack.tar.gz", "a/weird.xyz"]:
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        inv = inventory.inventory(tmp_path)
        assert inv["counts"] == {
            "archives": 1, "audio": 1, "books": 1, "grimoire_markers": 1, "images": 1,
            "incomplete_downloads": 1, "junk": 1, "models": 1, "sidecars": 1,
            "unknown": 1, "unsupported_documents": 1,
        }
        assert inv["top_folders"]["a"]["books"] == 1
