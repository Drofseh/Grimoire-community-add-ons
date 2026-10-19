"""Shared helpers for the library-skill script tests.

The skill scripts are standalone files (each skill is installed on its own),
not a package, so tests load them by path.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent


def load(skill: str, script: str):
    # A plain import by name, not a spec loaded from a path: pdf_health's
    # worker processes are spawned, and a spawned child re-imports the worker
    # function's module by name using the parent's sys.path.
    scripts = str(SKILLS / skill / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module(script)


@pytest.fixture(scope="session")
def health():
    return load("grimoire", "pdf_health")


@pytest.fixture(scope="session")
def evidence():
    return load("grimoire", "extract_evidence")


@pytest.fixture(scope="session")
def api():
    return load("grimoire", "grimoire_api")


@pytest.fixture(scope="session")
def inventory():
    return load("grimoire", "inventory")
