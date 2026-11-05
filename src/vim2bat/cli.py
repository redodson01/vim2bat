"""Builds bat themes from Vim colorschemes.

vim2bat runs Vim with your vimrc, records the colors and attributes a
colorscheme gives each highlight group (Table 1), and writes bat themes that
map TextMate scopes to them: share/strict.tsv (Table 2) for Vim's standard
groups, and share/loose.tsv (Table 3) for language-specific groups. vim2bat
compare measures a theme against Vim with share/vim-slots.vim.
"""

import argparse
import fcntl
import os
import plistlib
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, suppress
from importlib.metadata import version
from pathlib import Path
from types import FrameType
from typing import IO, NamedTuple, NoReturn, NotRequired, TypedDict
from xml.parsers.expat import ExpatError

SHARE = Path(__file__).with_name("share")
BACKGROUNDS = ("dark", "light")
# A scheme that resets 'background' to Vim's guess, such as default, gets the
# guess from the background color in COLORFGBG.
COLORFGBG = {"dark": "15;0", "light": "0;15"}
# bat themes support only these attributes.
ATTRIBUTES = ("bold", "italic", "underline")
SGR = re.compile(r"\x1b\[([0-9;]*)m")


class Directories(NamedTuple):
    themes: Path
    cache: Path


class Rule(TypedDict):
    # A theme's first rule, which holds its global colors, has no name or scope.
    name: NotRequired[str]
    scope: NotRequired[str]
    settings: dict[str, str]


class Theme(TypedDict):
    name: str
    comment: str
    settings: list[Rule]


class Failure(Exception):
    """Stops vim2bat with exit status 1, after printing the message if any."""


class Stop(BaseException):
    """Raised by a signal handler, so that vim2bat can stop Vim before exiting."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


# Vim processes still running, which vim2bat kills when it is stopped.
_running: set[subprocess.Popen[bytes]] = set()
_running_lock = threading.Lock()
_stopping = threading.Event()


@contextmanager
def vim_error_file() -> Iterator[IO[bytes]]:
    """Yields a temporary file to give Vim as its stderr."""
    with tempfile.TemporaryFile() as errors:
        # Vim writes some messages, such as a vimrc's errors, to its stderr
        # directly. On Linux, the Vim scripts' writes through /dev/stderr keep
        # their own offset, so without O_APPEND each would overwrite the other.
        flags = fcntl.fcntl(errors, fcntl.F_GETFL)
        fcntl.fcntl(errors, fcntl.F_SETFL, flags | os.O_APPEND)
        yield errors


def run_vim(
    arguments: list[str], environment: dict[str, str], stderr: IO[bytes] | None = None
) -> int:
    """Runs Vim with your vimrc on a pseudo-terminal and returns its status.

    Vim without a terminal numbers named cterm colors (such as DarkBlue)
    differently from a terminal, so it gets one, as xterm-256color. What Vim
    draws there is discarded, including most error messages, so the Vim
    scripts write their errors to stderr.
    """
    if stderr is None:
        # On Linux, /dev/stderr opens a redirected stderr's file anew, so
        # vim2bat's own writes to a file opened with 2> would overwrite Vim's.
        with vim_error_file() as errors:
            try:
                return run_vim(arguments, environment, errors)
            finally:
                errors.seek(0)
                sys.stderr.write(errors.read().decode("utf-8", "replace"))
    if _stopping.is_set():
        raise Failure("")
    controller, terminal = os.openpty()
    # -n skips the swap file, whose warning for a file open in another Vim
    # would count as an error. nomore keeps Vim from pausing at -- More --
    # after a screenful of messages, which the Enter below would page through
    # one line at a time.
    command = [
        "vim",
        "-N",
        "-i",
        "NONE",
        "-n",
        "--cmd",
        "set nomore",
        *arguments,
        "-c",
        "qa!",
    ]
    # Its own session keeps Ctrl-C from interrupting Vim's script, which would
    # leave Vim waiting for input instead of reaching qa!. vim2bat stops it
    # instead.
    try:
        process = subprocess.Popen(
            command,
            stdin=terminal,
            stdout=terminal,
            stderr=stderr,
            env={**os.environ, "TERM": "xterm-256color", **environment},
            start_new_session=True,
        )
    except BaseException:
        os.close(controller)
        raise
    finally:
        os.close(terminal)
    with _running_lock:
        _running.add(process)
        if _stopping.is_set():
            process.kill()
    try:
        # A command the vimrc started in the background with :! can hold the
        # terminal open after Vim exits.
        while process.poll() is None:
            if not select.select([controller], [], [], 0.5)[0]:
                # Vim waits for a key at a prompt, such as the one after an
                # error message, so an idle half second gets an Enter. If Vim
                # was busy instead, it never reads the Enter, because it quits
                # at the -c 'qa!' that ends its arguments.
                try:
                    os.write(controller, b"\r")
                except OSError:
                    break
                continue
            try:
                if not os.read(controller, 65536):
                    break
            # Some systems report the closed terminal as an error rather than
            # end of file.
            except OSError:
                break
        return process.wait()
    except BaseException:
        process.kill()
        raise
    finally:
        os.close(controller)
        with _running_lock:
            _running.discard(process)


def stop_vims() -> None:
    with _running_lock:
        _stopping.set()
        for process in _running:
            process.kill()


def bat_config_dir() -> Path:
    result = subprocess.run(
        ["bat", "--config-dir"], capture_output=True, text=True, check=True
    )
    folder = result.stdout.strip()
    if not os.path.isabs(folder):
        raise Failure(
            f"bat's config folder {folder!r} isn't an absolute path; check "
            "BAT_CONFIG_DIR"
        )
    return Path(folder)


def cache_dir() -> Path:
    # The XDG Base Directory spec says to ignore a relative path.
    base = os.environ.get("XDG_CACHE_HOME", "")
    return (Path(base) if os.path.isabs(base) else Path.home() / ".cache") / "vim2bat"


def ask_vim(expression: str) -> list[str]:
    """Returns the lines of a list or string that Vim evaluates with your vimrc."""
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "out"
        status = run_vim(
            ["-c", f"call writefile(flatten([{expression}]), $OUTFILE)"],
            {"OUTFILE": str(out)},
        )
        if status != 0 or not out.exists():
            raise Failure(f"Vim couldn't evaluate {expression}")
        return out.read_text(encoding="utf-8").splitlines()


def color(value: str) -> str:
    """Returns a Table 1 color as a bat theme color.

    bat reads a color whose alpha is 00 as a palette slot number, and one whose
    alpha is 01 as the terminal's default. Table 1 holds #rrggbb colors under
    'termguicolors'.
    """
    if not value:
        return "#00000001"
    if value.startswith("#"):
        return value
    return f"#{int(value):02X}000000"


def read_table(path: Path) -> dict[str, tuple[str, str, str]]:
    """Returns Table 1 as {group: (foreground, background, font style)}."""
    groups = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        group, foreground, background, attributes = line.split("\t")
        style = " ".join(a for a in attributes.split(",") if a in ATTRIBUTES)
        groups[group] = (foreground, background, style)
    return groups


def read_rules(strict: bool) -> list[tuple[str, str, bool]]:
    """Returns (group, scopes, loose) for Table 2 and, unless strict, Table 3."""
    rows = [(group, scopes, False) for group, scopes in tsv(SHARE / "strict.tsv", 2)]
    if not strict:
        rows += [
            (group, scopes, True)
            for _filetype, group, scopes in tsv(SHARE / "loose.tsv", 3)
        ]
    return rows


def tsv(path: Path, fields: int) -> list[list[str]]:
    return [
        line.split("\t", fields - 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def rule(
    groups: dict[str, tuple[str, str, str]], group: str, scopes: str, loose: bool
) -> Rule:
    foreground, _background, style = groups[group]
    # bat keeps the color of a less specific rule that also matches when this
    # one has no foreground, so a loose rule always writes one, taking Normal's
    # when its group has none.
    if loose and not foreground:
        foreground = groups["Normal"][0]
    settings = {}
    if foreground or loose:
        settings["foreground"] = color(foreground)
    # Written even when empty, so that a rule nested inside another doesn't
    # inherit the outer rule's bold or italic.
    settings["fontStyle"] = style
    return {"name": group, "scope": scopes, "settings": settings}


def theme(
    name: str,
    comment: str,
    groups: dict[str, tuple[str, str, str]],
    rules: list[tuple[str, str, bool]],
) -> Theme:
    globals_ = {
        "foreground": color(groups["Normal"][0]),
        # bat's --highlight-line, which fzf.vim's preview uses to mark the
        # matched line, draws with lineHighlight.
        "lineHighlight": color(groups["CursorLine"][1]),
    }
    # A group from a newer Vim can't color anything in this one, so it gets no
    # rule.
    scoped = [rule(groups, *row) for row in rules if row[0] in groups]
    return {
        "name": name,
        # vim2bat compare reads the options a theme was built with from here.
        "comment": comment,
        "settings": [{"settings": globals_}, *scoped],
    }


def theme_names(scheme: str, backgrounds: Sequence[str]) -> dict[str, str]:
    """Names the themes: the background is part of the name only when the
    scheme has both."""
    if len(backgrounds) > 1:
        return {background: f"vim-{scheme}-{background}" for background in backgrounds}
    return {background: f"vim-{scheme}" for background in backgrounds}


def build_comment(scheme: str, options: argparse.Namespace) -> str:
    words = ["vim2bat"]
    if options.strict:
        words.append("-s")
    if options.truecolor:
        words.append("-t")
    if options.palette:
        words += ["-p", options.palette]
    if scheme.startswith("-"):
        words.append("--")
    return shlex.join([*words, scheme])


def vim_environment(
    scheme: str, background: str, options: argparse.Namespace
) -> dict[str, str]:
    return {
        "SCHEME": scheme,
        "BACKGROUND": background,
        "COLORFGBG": COLORFGBG[background],
        "T_CO": options.palette or "",
        "TERMGUICOLORS": "1" if options.truecolor else "",
    }


def build(
    scheme: str,
    options: argparse.Namespace,
    directories: Directories,
    stderr: IO[bytes] | None = None,
) -> None:
    """Writes the themes for one scheme."""
    tables = directories.cache / "tables" / scheme
    tables.mkdir(parents=True, exist_ok=True)
    found = []
    for background in BACKGROUNDS:
        table = tables / f"vim-groups-{background}.tsv"
        environment = {
            **vim_environment(scheme, background, options),
            "OUTFILE": str(table),
        }
        table.unlink(missing_ok=True)
        # vim-groups.vim prints why it failed.
        status = run_vim(["-S", str(SHARE / "vim-groups.vim")], environment, stderr)
        if status != 0:
            raise Failure(f"Vim exited with status {status}")
        if not table.exists():
            raise Failure(f"Vim wrote no table for {scheme}")
        # vim-groups.vim writes an empty table for a background the scheme lacks.
        if table.stat().st_size:
            found.append(background)
    rules = read_rules(options.strict)
    comment = build_comment(scheme, options)
    directories.themes.mkdir(parents=True, exist_ok=True)
    for background, name in theme_names(scheme, found).items():
        groups = read_table(tables / f"vim-groups-{background}.tsv")
        # Two schemes can build the same name in parallel, such as one with both
        # backgrounds and another with its name plus -dark, so each write gets
        # its own temporary file.
        descriptor, temporary = tempfile.mkstemp(dir=directories.themes, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as f:
                plistlib.dump(theme(name, comment, groups, rules), f, sort_keys=False)
            os.chmod(temporary, 0o644)
            os.replace(temporary, directories.themes / f"{name}.tmTheme")
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


def build_quietly(
    scheme: str, options: argparse.Namespace, directories: Directories
) -> tuple[bool, str]:
    """Builds one scheme for --all and returns (succeeded, its error output)."""
    with vim_error_file() as errors:
        message = ""
        try:
            build(scheme, options, directories, errors)
            succeeded = True
        except Failure as failure:
            succeeded = False
            if str(failure):
                message = f"vim2bat: {failure}\n"
        errors.seek(0)
        return succeeded, errors.read().decode("utf-8", "replace") + message


def build_all(options: argparse.Namespace, directories: Directories) -> list[str]:
    """Builds every scheme Vim lists, one per CPU at a time, and returns the
    ones that failed."""
    schemes = ask_vim('getcompletion("", "color")')
    failed = []
    with ThreadPoolExecutor(os.cpu_count() or 1) as pool:
        try:
            futures = {
                pool.submit(build_quietly, scheme, options, directories): scheme
                for scheme in schemes
            }
            for count, future in enumerate(as_completed(futures), 1):
                scheme = futures[future]
                succeeded, errors = future.result()
                # Each scheme's errors follow its progress line, so that errors
                # from schemes building at the same time don't interleave.
                print(f"vim2bat: [{count}/{len(schemes)}] {scheme}", file=sys.stderr)
                sys.stderr.write(errors)
                if not succeeded:
                    failed.append(scheme)
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            stop_vims()
            raise
    return failed


def build_cache() -> None:
    # bat reads cache as a file name instead of its subcommand when the current
    # folder has an entry named cache.
    with tempfile.TemporaryDirectory() as empty:
        result = subprocess.run(
            ["bat", "cache", "--build"],
            cwd=empty,
            capture_output=True,
            text=True,
            check=True,
        )
    # bat reports a theme it can't parse on stdout and still exits 0, so only
    # the lines a clean build prints are dropped.
    for line in result.stdout.splitlines():
        if not line.endswith(" ... okay") and not line.startswith(
            "No syntaxes were found"
        ):
            print(line, file=sys.stderr)
    sys.stderr.write(result.stderr)


def generate_parser(
    parser_class: type[argparse.ArgumentParser] = argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    parser = parser_class(
        prog="vim2bat",
        description=(
            "Builds bat themes from a Vim colorscheme, as Vim shows it with your "
            "vimrc in a 256-color terminal. A scheme with both backgrounds gets "
            "vim-SCHEME-dark and vim-SCHEME-light; one with a single background "
            "gets vim-SCHEME. Then it rebuilds bat's cache."
        ),
        epilog=(
            "To measure a theme against Vim, run vim2bat compare THEME FILE... "
            "(see vim2bat compare --help). To build a scheme named compare, run "
            "vim2bat -- compare."
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("scheme", nargs="?", help="the colorscheme to build")
    target.add_argument(
        "-a", "--all", action="store_true", help="build every colorscheme Vim lists"
    )
    parser.add_argument(
        "-c",
        "--clean",
        action="store_true",
        help="first delete vim2bat's cache and the whole bat themes folder",
    )
    parser.add_argument(
        "-s",
        "--strict",
        action="store_true",
        help="map only Vim's standard groups (strict.tsv)",
    )
    parser.add_argument(
        "-t",
        "--truecolor",
        action="store_true",
        help="turn on 'termguicolors' to use the scheme's 24-bit colors",
    )
    parser.add_argument(
        "-p",
        "--palette",
        choices=("16", "256"),
        help="override your vimrc's 't_Co' with 16 or 256 colors",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('vim2bat')}"
    )
    return parser


def generate(argv: list[str]) -> None:
    parser = generate_parser()
    options = parser.parse_args(argv)
    # vim-groups.vim passes the name to :colorscheme, which reads a blank name,
    # or one that starts with | or ", as no name and keeps the vimrc's scheme.
    if options.scheme is not None and re.match(r'\s*($|["|])', options.scheme):
        parser.error("the scheme name is empty")
    # The scheme name becomes part of a theme's file name.
    if "/" in (options.scheme or ""):
        parser.error("a scheme name can't contain /")
    directories = Directories(bat_config_dir() / "themes", cache_dir())
    if options.clean:
        folders = (directories.cache, directories.themes)
        for folder in folders:
            if folder.is_symlink():
                raise Failure(
                    f"{folder} is a symbolic link; -c deletes only a real folder"
                )
        for folder in folders:
            with suppress(FileNotFoundError):
                shutil.rmtree(folder)
    if options.all:
        failed = build_all(options, directories)
        # This runs even when some schemes failed, so that the rest are usable.
        build_cache()
        if failed:
            raise Failure(f"failed: {' '.join(failed)}")
        return
    build(options.scheme, options, directories)
    build_cache()


def compare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vim2bat compare",
        description=(
            "Reports how often a bat theme that vim2bat built shows each character "
            "of FILE in the same color as Vim does, with the options the theme was "
            "built with. To measure strict.tsv alone, build the theme with -s first, "
            "since both builds use the same name."
        ),
    )
    parser.add_argument("theme", metavar="THEME")
    parser.add_argument("files", metavar="FILE", nargs="+")
    return parser


def bat_colors(text: str) -> dict[tuple[int, int], str | None]:
    """Returns {(line, index): color} for each character of bat's output."""
    colors = {}
    for lnum, line in enumerate(text.split("\n"), 1):
        current, idx = None, 0
        for k, part in enumerate(SGR.split(line)):
            if k % 2:
                current = apply(current, part)
                continue
            for _ in part:
                colors[(lnum, idx)] = current
                idx += 1
    return colors


def apply(current: str | None, params: str) -> str | None:
    """Returns the foreground color after one SGR sequence."""
    codes = params.split(";") if params else ["0"]
    k = 0
    while k < len(codes):
        code = codes[k]
        if code == "38" and codes[k + 1] == "2":
            current = "#" + "".join(f"{int(c):02x}" for c in codes[k + 2 : k + 5])
            k += 5
            continue
        if code == "38":
            current = codes[k + 2]
            k += 3
            continue
        if code in ("0", "39"):
            current = None
        elif code.isdigit() and 30 <= int(code) <= 37:
            current = str(int(code) - 30)
        k += 1
    return current


class CommentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def built_with(theme_name: str, comment: str) -> argparse.Namespace:
    """Returns the options in a theme's comment, if vim2bat built the theme
    under its own name."""
    options: argparse.Namespace | None
    try:
        words = shlex.split(comment)
        if words[:1] != ["vim2bat"]:
            raise ValueError
        options = generate_parser(CommentParser).parse_args(words[1:])
    except ValueError:
        options = None
    if (
        options is None
        or options.scheme is None
        or theme_name
        not in (
            f"vim-{options.scheme}",
            *theme_names(options.scheme, BACKGROUNDS).values(),
        )
    ):
        raise Failure(f"{theme_name} wasn't built by vim2bat under that name")
    return options


def compare(argv: list[str]) -> None:
    args = compare_parser().parse_args(argv)
    # bat falls back to its default theme for an unknown name instead of failing.
    listed = subprocess.run(
        ["bat", "--list-themes", "--color=never"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if args.theme not in listed:
        raise Failure(f"no bat theme named {args.theme}")
    path = bat_config_dir() / "themes" / f"{args.theme}.tmTheme"
    if not path.exists():
        raise Failure(
            f"{path} doesn't exist; vim2bat compare measures only themes that "
            "vim2bat built"
        )
    try:
        data = plistlib.loads(path.read_bytes())
    except (ValueError, ExpatError) as error:
        raise Failure(f"can't read {path}: {error}") from None
    comment = data.get("comment") if isinstance(data, dict) else None
    options = built_with(args.theme, comment if isinstance(comment, str) else "")
    scheme = options.scheme
    suffix = args.theme[len(f"vim-{scheme}") :]
    # A scheme with one background sets 'background' itself.
    background = suffix[1:] if suffix else "dark"
    totals: Counter[str] = Counter()
    agrees: Counter[str] = Counter()
    mismatches: Counter[tuple[str, str, str, str | None]] = Counter()
    with tempfile.TemporaryDirectory() as directory:
        for index, name in enumerate(args.files):
            out = Path(directory) / f"{index}.tsv"
            environment = {
                **vim_environment(scheme, background, options),
                "TARGET": os.path.join(os.getcwd(), name),
                "OUTFILE": str(out),
            }
            # The backtracking regex engine, which macOS's Vim uses by default,
            # stalls on the TypeScript syntax. Other syntaxes keep the default
            # because the NFA engine highlights some of them, such as ERB,
            # differently. The autocmd gets its own group, which a bare
            # autocmd! in your vimrc doesn't clear.
            status = run_vim(
                [
                    "--cmd",
                    "augroup vim2bat | augroup END",
                    "--cmd",
                    (
                        "autocmd vim2bat FileType typescript,typescriptreact "
                        "set regexpengine=2"
                    ),
                    "-S",
                    str(SHARE / "vim-slots.vim"),
                ],
                environment,
            )
            if status != 0:
                print(f"vim2bat: Vim reported an error on {name}", file=sys.stderr)
            # vim-slots.vim writes nothing when the scheme fails to load.
            if not out.exists():
                raise Failure("")
            # Without COLORTERM, bat rounds #rrggbb colors to the nearest of 256.
            bat = subprocess.run(
                [
                    "bat",
                    f"--theme={args.theme}",
                    "--color=always",
                    "--style=plain",
                    "--tabs=0",
                    "--wrap=never",
                    "--",
                    name,
                ],
                capture_output=True,
                check=True,
                env={**os.environ, "COLORTERM": "truecolor"},
            )
            got = bat_colors(bat.stdout.decode("utf-8"))
            lines = out.read_text(encoding="utf-8").splitlines()
            lang = lines[0].removeprefix("#ft=") if lines else ""
            total = agree = 0
            for row in lines[1:]:
                lnum, idx, vim, chain = row.split("\t")
                bat_color = got.get((int(lnum), int(idx)))
                total += 1
                # Vim has no color for text in a Normal without a foreground,
                # which bat draws in the terminal's default.
                if bat_color == (vim or None):
                    agree += 1
                else:
                    mismatches[(lang, chain or "(no syntax item)", vim, bat_color)] += 1
            print(f"{100 * agree / max(total, 1):5.1f}%  {total:6}  {lang:16} {name}")
            for key in (lang, "all"):
                totals[key] += total
                agrees[key] += agree
    print()
    for key in sorted(totals, key=lambda key: key == "all"):
        print(
            f"{100 * agrees[key] / max(totals[key], 1):5.1f}%  {totals[key]:6}  {key}"
        )
    print("\nchars  language  Vim syntax item>links  Vim color  bat color")
    for (lang, chain, vim, bat_color), n in mismatches.most_common(30):
        print(
            f"{n:5}  {lang}  {chain}  {vim or 'default'}  "
            f"{'default' if bat_color is None else bat_color}"
        )


def stop(signum: int, _frame: FrameType | None) -> NoReturn:
    raise Stop(signum)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, stop)
    try:
        if argv[:1] == ["compare"]:
            compare(argv[1:])
        else:
            generate(argv)
    except Stop as stopped:
        stop_vims()
        # A shell running vim2bat in a loop stops the loop on Ctrl-C only when
        # vim2bat dies by the signal, not when it exits with 130. Dying skips the
        # flush of stdout and stderr that exiting does.
        sys.stdout.flush()
        sys.stderr.flush()
        signal.signal(stopped.signum, signal.SIG_DFL)
        os.kill(os.getpid(), stopped.signum)
        return 128 + stopped.signum
    except Failure as failure:
        if str(failure):
            print(f"vim2bat: {failure}", file=sys.stderr)
        return 1
    except FileNotFoundError as error:
        print(f"vim2bat: {error.filename} not found", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"vim2bat: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"vim2bat: {shlex.join(error.cmd)} failed", file=sys.stderr)
        reason = (
            error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr
        )
        sys.stderr.write(SGR.sub("", reason or ""))
        return 1
    return 0
