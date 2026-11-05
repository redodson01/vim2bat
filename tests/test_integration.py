"""Integration tests: these run vim2bat with Vim and bat on the test
colorschemes in fixtures/colors, in a scratch home, bat config and cache.

Set UPDATE_GOLDEN=1 to rewrite the files in golden/ after an intended change.
"""

import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from vim2bat import cli

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
GOLDEN = TESTS / "golden"
PLAIN = FIXTURES / "samples" / "plain.sample"
ALL_AGREE = re.compile(r"^100\.0%\s+\d+\s+all$", re.MULTILINE)

pytestmark = pytest.mark.skipif(
    not (shutil.which("vim") and shutil.which("bat")), reason="needs vim and bat"
)


@dataclass(frozen=True)
class Scratch:
    themes: Path
    environment: dict[str, str]

    def vim2bat(
        self, *args: str, status: int = 0, cwd: Path | None = None, **environment: str
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-m", "vim2bat", *args],
            env={**self.environment, **environment},
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == status, result.stderr
        return result

    def load(self, name: str) -> dict[str, Any]:
        theme: dict[str, Any] = plistlib.loads(
            (self.themes / f"{name}.tmTheme").read_bytes()
        )
        return theme

    def foreground(self, name: str, group: str) -> str | None:
        color: str | None = next(
            rule["settings"].get("foreground")
            for rule in self.load(name)["settings"][1:]
            if rule["name"] == group
        )
        return color


def vimrc_home(folder: Path, *lines: str) -> str:
    vimrc = [f"set runtimepath^={FIXTURES}", *lines]
    (folder / ".vimrc").write_text("".join(f"{line}\n" for line in vimrc))
    return str(folder)


@pytest.fixture(scope="module")
def scratch(tmp_path_factory: pytest.TempPathFactory) -> Scratch:
    root = tmp_path_factory.mktemp("scratch")
    home = root / "home"
    home.mkdir()
    # An inherited COLORTERM would hide a compare that doesn't set it for bat.
    ignored = ("VIMINIT", "MYVIMRC", "COLORTERM")
    return Scratch(
        themes=root / "bat" / "themes",
        environment={
            **{k: v for k, v in os.environ.items() if k not in ignored},
            "HOME": vimrc_home(home),
            "XDG_CACHE_HOME": str(root / "cache"),
            "BAT_CONFIG_DIR": str(root / "bat"),
            "BAT_CACHE_PATH": str(root / "bat-cache"),
        },
    )


def test_both_backgrounds(scratch: Scratch) -> None:
    scratch.vim2bat("testdual")
    assert scratch.load("vim-testdual-dark")["comment"] == "vim2bat testdual"
    assert (scratch.themes / "vim-testdual-light.tmTheme").exists()
    assert not (scratch.themes / "vim-testdual.tmTheme").exists()


def test_named_colors_get_the_terminal_numbers(scratch: Scratch) -> None:
    scratch.vim2bat("testdual")
    # DarkBlue and Blue are 4 and 12 in a terminal, 1 and 9 without one.
    assert scratch.foreground("vim-testdual-dark", "Comment") == "#04000000"
    assert scratch.foreground("vim-testdual-light", "Comment") == "#0C000000"


def test_one_background(scratch: Scratch) -> None:
    scratch.vim2bat("testdark")
    assert (scratch.themes / "vim-testdark.tmTheme").exists()
    assert not (scratch.themes / "vim-testdark-light.tmTheme").exists()


def test_palette(scratch: Scratch) -> None:
    scratch.vim2bat("testdual")
    assert scratch.foreground("vim-testdual-dark", "Type") == "#D0000000"
    scratch.vim2bat("-p", "16", "testdual")
    assert scratch.foreground("vim-testdual-dark", "Type") == "#03000000"
    assert scratch.load("vim-testdual-dark")["comment"] == "vim2bat -p 16 testdual"


def test_truecolor(scratch: Scratch) -> None:
    scratch.vim2bat("-t", "testhex")
    settings = scratch.load("vim-testhex")["settings"]
    assert settings[0]["settings"] == {
        "foreground": "#d0d0d0",
        "lineHighlight": "#303030",
    }
    # Statement has no 24-bit color, so Vim draws its cterm color.
    assert scratch.foreground("vim-testhex", "Statement") == "#01000000"


def test_loose_rules_follow_syntax_links(scratch: Scratch) -> None:
    scratch.vim2bat("testdual")
    # Vim's Ruby syntax links rubySymbol to Constant.
    assert scratch.foreground("vim-testdual-dark", "rubySymbol") == "#05000000"


@pytest.mark.parametrize(
    ("args", "name"),
    [
        pytest.param(["-s", "testdual"], "vim-testdual-dark", id="vim-testdual-dark"),
        pytest.param(["-s", "testdual"], "vim-testdual-light", id="vim-testdual-light"),
        pytest.param(["-s", "testdark"], "vim-testdark", id="vim-testdark"),
        pytest.param(["-s", "-t", "testhex"], "vim-testhex", id="vim-testhex"),
    ],
)
def test_strict_matches_golden(scratch: Scratch, args: list[str], name: str) -> None:
    scratch.vim2bat(*args)
    built = (scratch.themes / f"{name}.tmTheme").read_bytes()
    golden = GOLDEN / f"{name}.tmTheme"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_bytes(built)
    assert built == golden.read_bytes()


def test_compare(scratch: Scratch) -> None:
    scratch.vim2bat("testdual")
    result = scratch.vim2bat(
        "compare", "vim-testdual-dark", str(FIXTURES / "samples" / "sample.rb")
    )
    assert re.search(r"\d+\.\d%\s+\d+\s+all", result.stdout)


@pytest.mark.parametrize(
    ("args", "name"),
    [
        pytest.param(["testdual"], "vim-testdual-light", id="vim-testdual-light"),
        pytest.param(["-t", "testhex"], "vim-testhex", id="vim-testhex"),
    ],
)
def test_compare_plain_text(scratch: Scratch, args: list[str], name: str) -> None:
    # Neither Vim nor bat has a syntax for this file, so both show it all in
    # Normal.
    scratch.vim2bat(*args)
    result = scratch.vim2bat("compare", name, str(PLAIN))
    assert ALL_AGREE.search(result.stdout)


def test_compare_file_named_like_an_option(scratch: Scratch, tmp_path: Path) -> None:
    scratch.vim2bat("testdual")
    shutil.copy(PLAIN, tmp_path / "--list-languages")
    result = scratch.vim2bat(
        "compare", "vim-testdual-light", "--", "--list-languages", cwd=tmp_path
    )
    assert ALL_AGREE.search(result.stdout)


def test_compare_after_the_vimrc_changes_folder(
    scratch: Scratch, tmp_path: Path
) -> None:
    scratch.vim2bat("testdual")
    result = scratch.vim2bat(
        "compare",
        "vim-testdual-light",
        PLAIN.name,
        cwd=PLAIN.parent,
        HOME=vimrc_home(tmp_path, "cd /"),
    )
    assert ALL_AGREE.search(result.stdout)


def test_compare_after_a_bare_autocmd_in_the_vimrc(
    scratch: Scratch, tmp_path: Path
) -> None:
    scratch.vim2bat("testdark")
    sample = tmp_path / "sample.ts"
    sample.write_text("let x: number = 1;\n")
    engine = tmp_path / "engine"
    home = vimrc_home(
        tmp_path,
        "autocmd!",
        "autocmd VimLeavePre * call writefile([&regexpengine], $ENGINE)",
    )
    scratch.vim2bat(
        "compare", "vim-testdark", str(sample), HOME=home, ENGINE=str(engine)
    )
    # vim2bat's own autocmd sets 'regexpengine' to 2 for TypeScript.
    assert engine.read_text() == "2\n"


def test_compare_highlight_link_cycle(scratch: Scratch, tmp_path: Path) -> None:
    scratch.vim2bat("testdark")
    sample = tmp_path / "cycle.rb"
    sample.write_text("x = :sym\n")
    # A cycle made directly in the vimrc wouldn't survive the scheme's :hi clear.
    home = vimrc_home(
        tmp_path,
        "autocmd ColorScheme * hi link rubySymbol Cycle | hi link Cycle rubySymbol",
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "vim2bat", "compare", "vim-testdark", str(sample)],
        env={**scratch.environment, "HOME": home},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        # SIGTERM lets vim2bat kill its Vim, which would otherwise keep looping.
        process.terminate()
        process.communicate(timeout=10)
        pytest.fail("compare didn't finish")
    assert process.returncode == 0, stderr
    assert "rubySymbol>Cycle" in stdout


def test_compare_bat_error(scratch: Scratch, tmp_path: Path) -> None:
    scratch.vim2bat("testdual")
    result = scratch.vim2bat(
        "compare", "vim-testdual-light", str(tmp_path / "missing"), status=1
    )
    assert "[bat error]" in result.stderr
    assert "\x1b" not in result.stderr


def test_scheme_that_fails_to_load(scratch: Scratch) -> None:
    result = scratch.vim2bat("testbroken", status=1)
    assert "E421" in result.stderr


def test_error_hidden_by_silent(scratch: Scratch) -> None:
    scratch.vim2bat("testsilent")


def test_vimrc_error(scratch: Scratch, tmp_path: Path) -> None:
    # The error stops Vim at a hit-enter prompt, which vim2bat has to answer.
    result = scratch.vim2bat(
        "testdark", HOME=vimrc_home(tmp_path, "call NoSuchFunction()")
    )
    assert "E117" in result.stderr


def test_vimrc_error_before_a_scheme_error(scratch: Scratch, tmp_path: Path) -> None:
    # Like test_stderr_redirected_to_a_file, this can fail only on Linux.
    home = vimrc_home(tmp_path, "call NoSuchFunction()")
    result = scratch.vim2bat("no-such-scheme", status=1, HOME=home)
    assert "E117" in result.stderr
    assert "Vim(colorscheme):E185" in result.stderr


def test_background_command_from_the_vimrc(scratch: Scratch, tmp_path: Path) -> None:
    # The command holds Vim's terminal open for 20 seconds after Vim exits.
    home = vimrc_home(tmp_path, "silent !sleep 20 &")
    start = time.monotonic()
    scratch.vim2bat("testdark", HOME=home)
    assert time.monotonic() - start < 20


def test_stop_while_vim_starts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # stop_vims runs after Vim starts and before run_vim records it. It sets
    # _stopping for good, so the test gets its own.
    monkeypatch.setattr(cli, "_stopping", threading.Event())
    popen = subprocess.Popen

    def start_then_stop(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process: subprocess.Popen[bytes] = popen(*args, **kwargs)
        cli.stop_vims()
        return process

    monkeypatch.setattr(subprocess, "Popen", start_then_stop)
    status = cli.run_vim([], {"HOME": str(tmp_path), "VIMINIT": "sleep 5"})
    assert status == -signal.SIGKILL


def test_vim_errors_are_forwarded_to_stderr(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    # capsys sees what vim2bat writes to sys.stderr, but not what Vim writes to
    # its own stderr.
    viminit = "call writefile(['from Vim'], '/dev/stderr', 'a')"
    status = cli.run_vim([], {"HOME": str(tmp_path), "VIMINIT": viminit})
    assert status == 0
    assert capsys.readouterr().err == "from Vim\n"


def test_vim_failure(scratch: Scratch) -> None:
    result = scratch.vim2bat("testdark", status=1, VIMINIT="cquit")
    assert result.stderr == "vim2bat: Vim exited with status 1\n"


def test_stale_table(scratch: Scratch) -> None:
    scratch.vim2bat("testdual")
    # The build above leaves tables behind, and VIMINIT quits Vim before
    # vim-groups.vim can replace them.
    result = scratch.vim2bat("-p", "16", "testdual", status=1, VIMINIT="qa!")
    assert "Vim wrote no table for testdual" in result.stderr
    assert scratch.load("vim-testdual-dark")["comment"] == "vim2bat testdual"


def test_failed_write_leaves_no_temporary_file(
    scratch: Scratch, tmp_path: Path
) -> None:
    own = own_folders(scratch, tmp_path)
    # A folder in the theme's place makes the write fail.
    (own.themes / "vim-testdark.tmTheme").mkdir(parents=True)
    own.vim2bat("testdark", status=1)
    assert not list(own.themes.glob("*.tmp"))


def test_unknown_scheme(scratch: Scratch) -> None:
    result = scratch.vim2bat("no-such-scheme", status=1)
    assert "E185" in result.stderr


@pytest.mark.parametrize(
    ("mode", "kept"),
    [pytest.param("w", "", id="write"), pytest.param("a", "earlier\n", id="append")],
)
def test_stderr_redirected_to_a_file(
    scratch: Scratch, tmp_path: Path, mode: str, kept: str
) -> None:
    # Only Linux's /dev/stderr opens the file anew, so this can fail only there.
    log = tmp_path / "log"
    log.write_text("earlier\n")
    with log.open(mode) as stderr:
        result = subprocess.run(
            [sys.executable, "-m", "vim2bat", "no-such-scheme"],
            env=scratch.environment,
            stderr=stderr,
            timeout=120,
            check=False,
        )
    assert result.returncode == 1
    assert re.fullmatch(
        rf"{kept}.*E185.*\nvim2bat: Vim exited with status 1\n", log.read_text()
    )


@pytest.mark.parametrize("name", ["", " ", "|", '"x'])
def test_empty_scheme(scratch: Scratch, name: str) -> None:
    result = scratch.vim2bat(name, status=2)
    assert "the scheme name is empty" in result.stderr


def test_scheme_name_with_a_slash(scratch: Scratch) -> None:
    result = scratch.vim2bat("sub/nested", status=2)
    assert "a scheme name can't contain /" in result.stderr


def test_file_error(scratch: Scratch, tmp_path: Path) -> None:
    cache = tmp_path / "not-a-folder"
    cache.touch()
    result = scratch.vim2bat("testdual", status=1, XDG_CACHE_HOME=str(cache))
    assert re.search(r"\Avim2bat: .*not-a-folder.*\n\Z", result.stderr)


def test_folder_with_an_entry_named_cache(scratch: Scratch, tmp_path: Path) -> None:
    (tmp_path / "cache").mkdir()
    scratch.vim2bat("testdark", cwd=tmp_path)


def test_relative_cache_home(scratch: Scratch, tmp_path: Path) -> None:
    scratch.vim2bat("testdark", cwd=tmp_path, XDG_CACHE_HOME="cache")
    assert not (tmp_path / "cache").exists()
    assert (Path(scratch.environment["HOME"]) / ".cache" / "vim2bat").is_dir()


def own_folders(scratch: Scratch, tmp_path: Path) -> Scratch:
    # --all, --clean and broken themes would change the shared folders the other
    # tests read.
    return replace(
        scratch,
        themes=tmp_path / "bat" / "themes",
        environment={
            **scratch.environment,
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "BAT_CONFIG_DIR": str(tmp_path / "bat"),
            "BAT_CACHE_PATH": str(tmp_path / "bat-cache"),
        },
    )


def test_all(scratch: Scratch, tmp_path: Path) -> None:
    own = own_folders(scratch, tmp_path)
    lines = own.vim2bat("-a", status=1).stderr.splitlines()
    progress = [
        (i, match)
        for i, line in enumerate(lines)
        if (match := re.fullmatch(r"vim2bat: \[(\d+)/(\d+)\] (.+)", line))
    ]
    total = int(progress[0][1][2])
    assert [int(match[1]) for _, match in progress] == list(range(1, total + 1))
    # Each scheme's errors follow its own progress line.
    broken = next(i for i, match in progress if match[3] == "testbroken")
    assert "E421" in lines[broken + 1]
    assert re.fullmatch(r"vim2bat: failed: (.+ )?testbroken( .+)?", lines[-1])
    for name in (
        "vim-testdual-dark",
        "vim-testdark",
        "vim-testhex",
        "vim-testsilent-dark",
        "vim-default-dark",
        "vim-default-light",
    ):
        assert (own.themes / f"{name}.tmTheme").exists()
    # bat's cache is rebuilt even though a scheme failed.
    listed = subprocess.run(
        ["bat", "--list-themes", "--color=never"],
        env=own.environment,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "vim-testdark" in listed


def test_clean(scratch: Scratch, tmp_path: Path) -> None:
    own = own_folders(scratch, tmp_path)
    stale_theme = own.themes / "stale.tmTheme"
    stale_table = tmp_path / "cache" / "vim2bat" / "tables" / "stale"
    stale_theme.parent.mkdir(parents=True)
    stale_theme.touch()
    stale_table.mkdir(parents=True)
    own.vim2bat("-c", "testdark")
    assert not stale_theme.exists()
    assert not stale_table.exists()
    assert (own.themes / "vim-testdark.tmTheme").exists()


def test_clean_refuses_a_linked_themes_folder(scratch: Scratch, tmp_path: Path) -> None:
    own = own_folders(scratch, tmp_path)
    stale_theme = tmp_path / "dotfiles" / "stale.tmTheme"
    stale_table = tmp_path / "cache" / "vim2bat" / "tables" / "stale"
    stale_theme.parent.mkdir()
    stale_theme.touch()
    stale_table.mkdir(parents=True)
    own.themes.parent.mkdir()
    own.themes.symlink_to(stale_theme.parent)
    result = own.vim2bat("-c", "testdark", status=1)
    assert "is a symbolic link" in result.stderr
    assert stale_theme.exists()
    assert stale_table.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_clean_reports_what_it_cannot_delete(scratch: Scratch, tmp_path: Path) -> None:
    own = own_folders(scratch, tmp_path)
    locked = own.themes / "locked"
    locked.mkdir(parents=True)
    (locked / "stale.tmTheme").touch()
    locked.chmod(0o500)
    result = own.vim2bat("-c", "testdark", status=1)
    assert "Permission denied" in result.stderr


@pytest.mark.parametrize("folder", ["", "relative"])
def test_bat_config_dir_not_absolute(
    scratch: Scratch, tmp_path: Path, folder: str
) -> None:
    own = own_folders(scratch, tmp_path)
    kept = tmp_path / folder / "themes" / "kept.tmTheme"
    kept.parent.mkdir(parents=True)
    kept.touch()
    result = own.vim2bat(
        "-c", "testdark", status=1, cwd=tmp_path, BAT_CONFIG_DIR=folder
    )
    assert "isn't an absolute path" in result.stderr
    assert kept.exists()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"not a plist", id="not-a-plist"),
        pytest.param(b"<?xml version='1.0'?><plist><dict>", id="unclosed-xml"),
        pytest.param(plistlib.dumps([]), id="not-a-dict"),
        pytest.param(plistlib.dumps({"comment": 5}), id="comment-not-a-string"),
    ],
)
def test_compare_unreadable_theme(
    scratch: Scratch, tmp_path: Path, content: bytes
) -> None:
    own = own_folders(scratch, tmp_path)
    own.vim2bat("testdark")
    (own.themes / "vim-testdark.tmTheme").write_bytes(content)
    result = own.vim2bat("compare", "vim-testdark", str(PLAIN), status=1)
    assert re.fullmatch(r"vim2bat: .*vim-testdark.*\n", result.stderr)


def test_dies_by_the_signal(scratch: Scratch, tmp_path: Path) -> None:
    # VIMINIT replaces the vimrc, and keeps Vim busy until vim2bat stops it.
    pid = tmp_path / "pid"
    process = subprocess.Popen(
        [sys.executable, "-m", "vim2bat", "testdark"],
        env={
            **scratch.environment,
            "VIMINIT": "call writefile([getpid()], $PIDFILE) | sleep 30",
            "PIDFILE": str(pid),
        },
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1)
    process.send_signal(signal.SIGINT)
    # Python also dies by SIGINT when nothing handles it, but prints a traceback
    # first.
    _, stderr = process.communicate(timeout=10)
    assert process.returncode == -signal.SIGINT
    assert stderr == ""
    vim = int(pid.read_text())
    # The killed Vim stays a zombie until init reaps it.
    deadline = time.monotonic() + 5
    while True:
        try:
            os.kill(vim, 0)
        except ProcessLookupError:
            break
        assert time.monotonic() < deadline, "Vim is still running"
        time.sleep(0.1)


def test_signal_keeps_vim_output_without_a_newline(scratch: Scratch) -> None:
    # writefile()'s b flag leaves out the final newline, so the forwarded text
    # stays in stderr's buffer until vim2bat flushes it.
    process = subprocess.Popen(
        [sys.executable, "-m", "vim2bat", "testdark"],
        env={
            **scratch.environment,
            "VIMINIT": "call writefile(['early'], '/dev/stderr', 'ab') | sleep 30",
        },
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1)
    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=10)
    assert process.returncode == -signal.SIGINT
    assert stderr == "early"
