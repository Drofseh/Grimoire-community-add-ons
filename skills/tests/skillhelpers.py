"""Helpers for the library-skill script tests (kept out of conftest.py so the
name cannot collide with backend/tests/conftest.py when both suites run)."""
from pathlib import Path


def make_book(path: Path, pages: int = 20, skip=(), blank=(), dupe_of_prev=(), extra=None):
    """Write a PDF whose pages carry body text and a printed page number.

    ``skip`` lists printed numbers left out (a page lost from the middle),
    ``blank`` PDF page indexes left empty, ``dupe_of_prev`` indexes that repeat
    the previous page exactly, and ``extra`` maps an index to text added to it.
    """
    import fitz

    doc = fitz.open()
    printed = 1
    last = None
    for i in range(pages):
        while printed in skip:
            printed += 1
        page = doc.new_page()
        if i in blank:
            continue
        if i in dupe_of_prev and last is not None:
            body, number = last
        else:
            body, number = f"Body text for printed page {printed}. " * 3, printed
            printed += 1
        page.insert_text((72, 100), body, fontsize=11)
        page.insert_text((72, 130), "Lorem ipsum dolor sit amet consectetur " * 2, fontsize=9)
        page.insert_text((300, 820), str(number), fontsize=10)
        if extra and i in extra:
            page.insert_text((72, 200), extra[i], fontsize=10)
        last = (body, number)
    doc.save(str(path))
    return path
