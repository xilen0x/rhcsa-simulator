from __future__ import annotations

from rhcsa_sim.ui import Ui, supports_unicode, visible_len


def test_supports_unicode_only_for_utf_encodings() -> None:
    assert supports_unicode("UTF-8") is True
    assert supports_unicode("utf8") is True
    assert supports_unicode("ascii") is False
    assert supports_unicode("latin-1") is False
    assert supports_unicode(None) is False


def test_visible_len_ignores_ansi() -> None:
    assert visible_len("\x1b[1m\x1b[36mabc\x1b[0m") == 3


def test_box_unicode_has_equal_width_lines() -> None:
    ui = Ui(unicode=True, color=False)
    lines = ui.box(["hello", "a longer line"], width=20, title="T").splitlines()
    assert lines[0].startswith("╭") and lines[-1].startswith("╰")
    assert {len(line) for line in lines} == {20}


def test_box_ascii_fallback() -> None:
    ui = Ui(unicode=False, color=False)
    text = ui.box(["hi"], width=10)
    assert text.splitlines()[0] == "+" + "-" * 8 + "+"
    assert "|" in text
    assert text.isascii()


def test_box_width_ignores_ansi_in_content() -> None:
    ui = Ui(unicode=True, color=True)
    lines = ui.box([ui.bold("hi")], width=12).splitlines()
    assert {visible_len(line) for line in lines} == {12}


def test_color_off_emits_no_escape_sequences() -> None:
    ui = Ui(unicode=True, color=False)
    out = ui.green("x") + ui.red("x") + ui.cyan("x") + ui.yellow("x") + ui.dim("x")
    assert "\x1b" not in out


def test_color_on_emits_escape_sequences() -> None:
    assert "\x1b[" in Ui(unicode=True, color=True).cyan("x")


def test_symbols_unicode_and_ascii() -> None:
    assert Ui(True, False).symbol("passed") == "✔"
    assert Ui(False, False).symbol("passed") == "OK"
    assert Ui(False, False).symbol("failed") == "KO"
    assert Ui(False, False).symbol("pending") == ".."


def test_progress_bar() -> None:
    assert Ui(False, False).progress_bar(1, 2, width=10) == "[#####-----]"
    assert Ui(True, False).progress_bar(0, 0, width=4) == "[░░░░]"
    assert Ui(True, False).progress_bar(4, 4, width=4) == "[████]"
