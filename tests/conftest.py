import sys
import webbrowser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # the app's modules sit at the repo root

import actions  # noqa: E402
import guards  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_effects(monkeypatch):
    """No test reaches the real browser, Photoshop, file manager or clipboard: a test that needs one swaps in a fake."""
    def refuse(*a, **k):
        pytest.fail("a test reached a real external effect")
    monkeypatch.setattr(guards, "_browser", refuse)
    for name in ("open", "open_new", "open_new_tab"):
        monkeypatch.setattr(webbrowser, name, refuse)
    for name in ("call", "spawn", "startfile", "clipboard"):
        monkeypatch.setattr(actions, name, refuse)
