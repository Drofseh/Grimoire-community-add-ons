import json

import pytest

from skillhelpers import make_book


class TestIdentifiers:
    def test_isbn_checksums(self, evidence):
        assert evidence.isbn_valid("1-887801-55-3") == "1887801553"
        assert evidence.isbn_valid("9780306406157") == "9780306406157"
        assert evidence.isbn_valid("9780306406158") is None
        assert evidence.isbn_valid("1234567890") is None
        assert evidence.isbn_valid("080442957X") == "080442957X"

    def test_find_isbns_in_text(self, evidence):
        text = "Printed in USA. ISBN 978-0-306-40615-7. Stock AG0256. ISBN 0000000000"
        assert evidence.find_isbns(text) == ["9780306406157", "0000000000"]

    def test_product_codes(self, evidence):
        found = evidence.product_codes("PZO 2101 and CHA23137, also AG0813")
        assert [(f["code"], f["publisher_hint"]) for f in found] == [
            ("PZO2101", "Paizo"),
            ("CHA23137", "Chaosium"),
            ("AG0813", "Atlas Games"),
        ]

    def test_codes_need_their_boundaries(self, evidence):
        assert evidence.product_codes("BIGPZO21015") == []


class TestFilenameClues:
    def test_cleans_store_noise_and_keeps_clues(self, evidence):
        clues = evidence.filename_clues("PZO2101 Pathfinder Core Rulebook_print v1.2")
        assert clues["title_guess"] == "Pathfinder Core Rulebook"
        assert clues["version"] == "1.2"
        assert clues["variant"] == ["print"]
        assert clues["product_codes"][0]["code"] == "PZO2101"

    def test_keeps_real_title_words(self, evidence):
        assert evidence.filename_clues("GM Screen Inserts")["title_guess"] == "GM Screen Inserts"

    def test_unescapes_web_mangled_names(self, evidence):
        clues = evidence.filename_clues("Wonders of Art &amp Magic")
        assert clues["title_guess"] == "Wonders of Art & Magic"

    def test_edition_status_and_series(self, evidence):
        clues = evidence.filename_clues("Ars Magica 4e - Quickstart Part 2")
        assert "4e" in clues["edition"]
        assert clues["status"] == ["quickstart"]
        assert clues["series"] == ["Part 2"]

    def test_bracketed_tags_dropped(self, evidence):
        assert evidence.filename_clues("Alien [US88025] Card Deck")["title_guess"] == "Alien Card Deck"


class TestHelpers:
    def test_watermark_lines_are_removed(self, evidence):
        text, marked = evidence.clean_text("Title\nJane Doe (order #1234567)\nmail me@x.com now")
        assert marked
        assert "Jane" not in text and "1234567" not in text
        assert "[email]" in text

    def test_junk_metadata(self, evidence):
        assert evidence.is_junk_meta("Microsoft Word - draft.doc", "x")
        assert evidence.is_junk_meta("Untitled", "x")
        assert evidence.is_junk_meta("my_file", "my_file")
        assert not evidence.is_junk_meta("The Drowned Spire", "ds")

    def test_page_sizes(self, evidence):
        assert evidence.page_size(612, 792)["name"] == "US Letter"
        assert evidence.page_size(595, 842)["name"] == "A4"
        spread = evidence.page_size(1224, 792)
        assert spread["landscape"] and spread["spreads_of"] == "US Letter"

    def test_language_guess(self, evidence):
        english = "the and of to in is that for with you your are this be as on " * 5
        assert evidence.guess_language(english)["code"] == "en"
        german = "der die und das ist nicht mit sich ein eine auf für dem den zu " * 5
        assert evidence.guess_language(german)["code"] == "de"
        assert evidence.guess_language("too short") is None

    def test_credit_lines(self, evidence):
        lines = evidence.credit_lines("Written by: Jane Writer\nCover Art: Sam Painter\nChapter 1")
        assert lines == ["Written by: Jane Writer", "Cover Art: Sam Painter"]

    def test_reads_opf_sidecar(self, evidence, tmp_path):
        book = tmp_path / "b.pdf"
        book.write_bytes(b"%PDF-1.4")
        (tmp_path / "b.opf").write_text(
            '<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata>'
            "<dc:title>Real Title</dc:title><dc:creator>A. Writer</dc:creator>"
            "</metadata></package>"
        )
        opf = evidence.read_opf(book)
        assert opf["title"] == "Real Title" and opf["creators"] == ["A. Writer"]


class TestExtraction:
    def test_pdf_evidence_end_to_end(self, evidence, tmp_path):
        pytest.importorskip("fitz")
        src = tmp_path / "src" / "Example Game" / "core"
        src.mkdir(parents=True)
        legal = (
            "Credits\nWritten by: Jane Writer\nCover Art: Sam Painter\n"
            "Copyright 2019 Example Press. ISBN 978-0-306-40615-7. Product EXP2001\n"
            "Released under the Open Game License"
        )
        make_book(src / "EG_core_FINAL(1).pdf", 12, extra={2: legal, 4: "Reader (order #998877)"})
        (src / "notes.docx").write_bytes(b"PK")
        out = tmp_path / "ev.jsonl"
        digest = tmp_path / "digest.md"
        covers = tmp_path / "covers"
        rc = evidence.main([str(tmp_path / "src"), "--out", str(out), "--digest", str(digest),
                            "--covers", str(covers)])
        assert rc == 0
        recs = {json.loads(line)["file"]: json.loads(line) for line in out.read_text().splitlines()}
        rec = recs["EG_core_FINAL(1).pdf"]
        assert rec["folders"] == ["Example Game", "core"]
        assert rec["pages"] == 12
        assert rec["isbn_in_text"] == ["9780306406157"]
        assert rec["copyright_years"] == [2019]
        assert "Written by: Jane Writer" in rec["credit_lines"]
        assert "Open Game License" in rec["license_or_program_hints"]
        assert rec["purchase_watermark"] is True
        assert "998877" not in out.read_text()
        assert rec["filename"]["title_guess"] == "EG core"
        assert (covers / rec["cover_image"].rsplit("/", 1)[-1]).exists()
        assert "unsupported" in recs["notes.docx"]
        assert "EG_core_FINAL(1).pdf" in digest.read_text()

    def test_skip_broken_uses_health_report(self, evidence, tmp_path):
        pytest.importorskip("fitz")
        good = make_book(tmp_path / "good.pdf", 3)
        bad = tmp_path / "bad.pdf"
        bad.write_text("<html>")
        report = tmp_path / "health.jsonl"
        report.write_text(json.dumps({"path": str(bad.resolve()), "verdict": "broken"}) + "\n")
        out = tmp_path / "ev.jsonl"
        evidence.main([str(tmp_path), "--out", str(out), "--skip-broken", str(report)])
        files = [json.loads(line)["file"] for line in out.read_text().splitlines()]
        assert files == [good.name]
