"""Unit tests: none of these runs Vim or bat."""

import argparse
import os
import shlex
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from vim2bat import cli as vim2bat


def options(
    *, strict: bool = False, truecolor: bool = False, palette: str | None = None
) -> argparse.Namespace:
    return argparse.Namespace(strict=strict, truecolor=truecolor, palette=palette)


def test_color_palette_slot() -> None:
    assert vim2bat.color("3") == "#03000000"
    assert vim2bat.color("208") == "#D0000000"


def test_color_terminal_default() -> None:
    assert vim2bat.color("") == "#00000001"


def test_color_hex() -> None:
    assert vim2bat.color("#a1b2c3") == "#a1b2c3"


def test_theme_names_both_backgrounds() -> None:
    assert vim2bat.theme_names("x", ["dark", "light"]) == {
        "dark": "vim-x-dark",
        "light": "vim-x-light",
    }


def test_theme_names_one_background() -> None:
    assert vim2bat.theme_names("x", ["light"]) == {"light": "vim-x"}


def test_theme_names_no_background() -> None:
    assert vim2bat.theme_names("x", []) == {}


def test_comment_plain() -> None:
    assert vim2bat.build_comment("habamax", options()) == "vim2bat habamax"


def test_comment_options() -> None:
    comment = vim2bat.build_comment(
        "habamax", options(strict=True, truecolor=True, palette="16")
    )
    assert comment == "vim2bat -s -t -p 16 habamax"


@pytest.mark.parametrize("scheme", ["my scheme", "-a", "compare"])
def test_comment_round_trip(scheme: str) -> None:
    comment = vim2bat.build_comment(scheme, options(palette="256"))
    parsed = vim2bat.generate_parser().parse_args(shlex.split(comment)[1:])
    assert parsed.scheme == scheme
    assert parsed.palette == "256"


def test_read_table(tmp_path: Path) -> None:
    path = tmp_path / "table.tsv"
    path.write_text(
        "Normal\t14\t\t\nError\t1\t\tbold,reverse\nComment\t10\t0\titalic\n"
    )
    groups = vim2bat.read_table(path)
    assert groups["Normal"] == ("14", "", "")
    assert groups["Error"] == ("1", "", "bold")
    assert groups["Comment"] == ("10", "0", "italic")


def test_rules_files_parse() -> None:
    strict = vim2bat.read_rules(strict=True)
    loose = vim2bat.read_rules(strict=False)
    assert strict
    assert len(loose) > len(strict)
    assert all(len(row) == 3 and row[0] and row[1] for row in loose)


def test_css_rules_apply_outside_html() -> None:
    css = [
        scopes
        for group, scopes, _loose in vim2bat.read_rules(strict=False)
        if group.startswith("css")
    ]
    assert css
    assert not any("text.html" in scopes for scopes in css)


GROUPS = {
    "Normal": ("14", "", ""),
    "CursorLine": ("", "0", ""),
    "Comment": ("10", "", "italic"),
    "Plain": ("", "", ""),
}


def test_strict_rule_without_color_omits_foreground() -> None:
    rule = vim2bat.rule(GROUPS, "Plain", "x", False)
    assert rule["settings"] == {"fontStyle": ""}


def test_loose_rule_without_color_takes_normal() -> None:
    rule = vim2bat.rule(GROUPS, "Plain", "x", True)
    assert rule["settings"] == {"foreground": "#0E000000", "fontStyle": ""}


def test_rule_with_color() -> None:
    rule = vim2bat.rule(GROUPS, "Comment", "comment", False)
    assert rule == {
        "name": "Comment",
        "scope": "comment",
        "settings": {"foreground": "#0A000000", "fontStyle": "italic"},
    }


def test_group_missing_from_this_vim_gets_no_rule() -> None:
    theme = vim2bat.theme("vim-x", "vim2bat x", GROUPS, [("Missing", "x", True)])
    assert len(theme["settings"]) == 1


def test_theme_globals() -> None:
    theme = vim2bat.theme("vim-x", "vim2bat x", GROUPS, [("Comment", "comment", False)])
    assert theme["name"] == "vim-x"
    assert theme["comment"] == "vim2bat x"
    assert theme["settings"][0] == {
        "settings": {"foreground": "#0E000000", "lineHighlight": "#00000000"}
    }
    assert len(theme["settings"]) == 2


def test_built_with_accepts_its_own_names() -> None:
    assert vim2bat.built_with("vim-x-dark", "vim2bat -p 16 x").palette == "16"
    assert vim2bat.built_with("vim-x", "vim2bat x").scheme == "x"


@pytest.mark.parametrize(
    ("name", "comment"),
    [
        ("vim-x-dark", "Based on Ethan Schoonover's Solarized"),
        ("vim-x-dark", "vim2bat"),
        ("vim-x-dark", "vim2bat --bogus x"),
        ("vim-x-dark-copy", "vim2bat x"),
    ],
)
def test_built_with_rejects_other_themes(name: str, comment: str) -> None:
    with pytest.raises(vim2bat.Failure):
        vim2bat.built_with(name, comment)


def test_sgr() -> None:
    assert vim2bat.apply(None, "38;5;12") == "12"
    assert vim2bat.apply(None, "31") == "1"
    assert vim2bat.apply(None, "1;38;2;1;2;255") == "#0102ff"
    assert vim2bat.apply("3", "0") is None
    assert vim2bat.apply("3", "") is None
    assert vim2bat.apply("3", "1") == "3"


def test_bat_colors_characters() -> None:
    text = "\x1b[31mab\x1b[0m c\n\x1b[38;5;12md"
    assert vim2bat.bat_colors(text) == {
        (1, 0): "1",
        (1, 1): "1",
        (1, 2): None,
        (1, 3): None,
        (2, 0): "12",
    }


def run_vim2bat(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "vim2bat", *args],
        # argparse on Python 3.14 and newer colors its output when FORCE_COLOR
        # is set, even into a pipe.
        env={**os.environ, "PYTHON_COLORS": "0"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_help() -> None:
    result = run_vim2bat("--help")
    assert result.returncode == 0
    assert "usage: vim2bat" in result.stdout


def test_version() -> None:
    result = run_vim2bat("--version")
    assert result.stdout.strip() == f"vim2bat {version('vim2bat')}"


def test_scheme_required() -> None:
    result = run_vim2bat()
    assert result.returncode == 2
    assert "-a/--all is required" in result.stderr


def test_scheme_with_all() -> None:
    result = run_vim2bat("-a", "habamax")
    assert result.returncode == 2


def test_palette_choices() -> None:
    result = run_vim2bat("-p", "8", "habamax")
    assert result.returncode == 2


def test_compare_arguments() -> None:
    result = run_vim2bat("compare", "vim-x")
    assert result.returncode == 2
