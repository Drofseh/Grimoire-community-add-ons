import json

import pytest

from skillhelpers import make_book

fitz = pytest.importorskip("fitz")


def codes(rec, severity=None):
    return {i["code"] for i in rec["issues"] if severity is None or i["severity"] == severity}


class TestSniffing:
    def test_recognises_formats(self, health):
        assert health.sniff_type(b"%PDF-1.7\n") == "pdf"
        assert health.sniff_type(b"PK\x03\x04rest") == "zip"
        assert health.sniff_type(b"Rar!\x1a\x07") == "rar"
        assert health.sniff_type(b"  <!DOCTYPE html><html>") == "html"
        assert health.sniff_type(b"\x00" * 4096) == "zero-filled"
        assert health.sniff_type(b"") == "empty"
        assert health.sniff_type(b"hello world") == "unknown"

    def test_pdf_header_may_follow_junk(self, health):
        assert health.sniff_type(b"garbage" * 10 + b"%PDF-1.4") == "pdf"


class TestPageNumberGaps:
    def test_no_gap_in_continuous_numbering(self, health):
        assert health.page_number_gaps([{n} for n in range(1, 30)]) == []

    def test_finds_a_jump(self, health):
        numbers = [{n} for n in range(1, 11)] + [{n} for n in range(14, 25)]
        (gap,) = health.page_number_gaps(numbers)
        assert gap["printed_from"] == 10 and gap["printed_to"] == 14
        assert gap["missing"] == 3
        assert gap["after_pdf_page"] == 10

    def test_ignores_stray_numbers_without_a_neighbour(self, health):
        numbers = [{n} for n in range(1, 20)]
        numbers[7] = {8, 1987}  # a year in the footer
        assert health.page_number_gaps(numbers) == []

    def test_restart_is_not_a_gap(self, health):
        numbers = [{n} for n in range(1, 15)] + [{n} for n in range(1, 10)]
        assert health.page_number_gaps(numbers) == []

    def test_two_page_spreads_are_allowed_for(self, health):
        numbers = [{2 * i, 2 * i + 1} for i in range(1, 20)]
        assert health.page_number_gaps(numbers) == []

    def test_long_unnumbered_stretch_is_not_compared(self, health):
        numbers = [{n} for n in range(1, 8)] + [set()] * 10 + [{n} for n in range(40, 50)]
        assert health.page_number_gaps(numbers) == []


class TestCheckFile:
    def test_healthy_book(self, health, tmp_path):
        rec = health.check_file(str(make_book(tmp_path / "good.pdf")), False, True)
        assert rec["verdict"] == "ok"
        assert rec["pages"] == 20
        assert rec["text_layer"] == "full"
        assert len(rec["sha256"]) == 64

    def test_missing_pages(self, health, tmp_path):
        rec = health.check_file(str(make_book(tmp_path / "m.pdf", 30, skip=(12, 13, 14))), False, False)
        assert rec["verdict"] == "warn"
        assert "missing_pages" in codes(rec, "warn")
        assert rec["page_number_gaps"][0]["missing"] == 3

    def test_single_page_skip_is_only_info(self, health, tmp_path):
        rec = health.check_file(str(make_book(tmp_path / "m.pdf", 30, skip=(12,))), False, False)
        assert rec["verdict"] == "ok"
        assert "missing_pages" in codes(rec, "info")

    def test_blank_run(self, health, tmp_path):
        rec = health.check_file(str(make_book(tmp_path / "b.pdf", 30, blank=(10, 11, 12, 13))), False, False)
        assert rec["verdict"] == "warn"
        assert rec["blank_pages"] == [11, 12, 13, 14]
        assert rec["blank_runs"] == [[11, 14]]

    def test_one_blank_page_in_a_short_handout_is_fine(self, health, tmp_path):
        rec = health.check_file(str(make_book(tmp_path / "h.pdf", 6, blank=(5,))), False, False)
        assert rec["verdict"] == "ok"

    def test_duplicate_page_is_informational(self, health, tmp_path):
        rec = health.check_file(str(make_book(tmp_path / "d.pdf", 12, dupe_of_prev=(6,))), False, False)
        assert rec["duplicate_pages"] == [[6, 7]]
        assert rec["verdict"] == "ok"

    def test_html_saved_as_pdf(self, health, tmp_path):
        f = tmp_path / "x.pdf"
        f.write_text("<!DOCTYPE html><html><body>Please log in</body></html>")
        rec = health.check_file(str(f), False, False)
        assert rec["verdict"] == "broken"
        assert "web page" in rec["issues"][0]["detail"]

    def test_empty_file(self, health, tmp_path):
        f = tmp_path / "e.pdf"
        f.write_bytes(b"")
        assert health.check_file(str(f), False, False)["verdict"] == "broken"

    def test_zero_filled_middle(self, health, tmp_path):
        good = make_book(tmp_path / "g.pdf", 5).read_bytes()
        f = tmp_path / "z.pdf"
        f.write_bytes(good[:1000] + b"\x00" * 300_000 + good[1000:])
        rec = health.check_file(str(f), False, False)
        assert "zero_filled" in codes(rec, "error")
        assert rec["verdict"] == "broken"

    def test_password_locked(self, health, tmp_path):
        src = make_book(tmp_path / "g.pdf", 3)
        locked = tmp_path / "l.pdf"
        with fitz.open(str(src)) as doc:
            doc.save(str(locked), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="a", owner_pw="b")
        assert health.check_file(str(locked), False, False)["verdict"] == "locked"

    def test_truncated(self, health, tmp_path):
        raw = make_book(tmp_path / "g.pdf", 10).read_bytes()
        f = tmp_path / "t.pdf"
        f.write_bytes(raw[: len(raw) // 2])
        rec = health.check_file(str(f), False, False)
        assert "truncated" in codes(rec)
        assert rec["verdict"] in {"warn", "broken"}

    def test_corrupt_zip(self, health, tmp_path):
        f = tmp_path / "c.cbz"
        f.write_bytes(b"PK\x03\x04" + b"\x01" * 200)
        assert health.check_file(str(f), False, False)["verdict"] == "broken"

    def test_quick_mode_samples(self, health, tmp_path):
        rec = health.check_file(str(make_book(tmp_path / "big.pdf", 120)), True, False)
        assert rec["pages"] == 120
        assert rec["pages_checked"] < 120
        assert "page_number_gaps" not in rec


class TestCli:
    def test_end_to_end_writes_jsonl_and_repairs(self, health, tmp_path, capsys):
        src = tmp_path / "src"
        src.mkdir()
        make_book(src / "good.pdf", 8)
        make_book(src / "blank.pdf", 12, blank=(3, 4, 5))
        (src / "bad.pdf").write_text("<html>nope</html>")
        (src / ".DS_Store").write_bytes(b"junk")
        out = tmp_path / "report.jsonl"
        fixed = tmp_path / "fixed"
        rc = health.main([str(src), "--out", str(out), "--jobs", "2", "--hash",
                          "--repair-out", str(fixed), "--drop-blank"])
        assert rc == 0
        recs = {json.loads(line)["path"].rsplit("/", 1)[-1]: json.loads(line)
                for line in out.read_text().splitlines()}
        assert set(recs) == {"good.pdf", "blank.pdf", "bad.pdf"}
        assert recs["good.pdf"]["verdict"] == "ok"
        assert recs["bad.pdf"]["verdict"] == "broken"
        repaired = recs["blank.pdf"]["repaired_copy"]
        with fitz.open(repaired) as doc:
            assert doc.page_count == 9
        assert (src / "blank.pdf").exists()  # the original is untouched
        assert "3 file(s)" in capsys.readouterr().err

    def test_no_files(self, health, tmp_path):
        assert health.main([str(tmp_path)]) == 1
