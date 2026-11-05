# vim2bat

[![CI](https://github.com/redodson01/vim2bat/actions/workflows/ci.yml/badge.svg)](https://github.com/redodson01/vim2bat/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/release/redodson01/vim2bat)](https://github.com/redodson01/vim2bat/releases/latest)
[![Release Date](https://img.shields.io/github/release-date/redodson01/vim2bat)](https://github.com/redodson01/vim2bat/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/redodson01/vim2bat/blob/main/LICENSE)

Builds [bat](https://github.com/sharkdp/bat) themes from Vim colorschemes, so
that bat, and tools that use it such as fzf.vim's previews and delta, color code
the way Vim does.

## The problem

bat ships its own themes, and most of them use 24-bit colors. If you use a Vim
colorscheme, especially one built on your terminal's palette like solarized8
with `g:solarized_use16`, the previews and diffs that bat colors look different
from the code you edit in Vim. A matching bat theme means mapping Vim's
highlight groups to TextMate scopes by hand, for each scheme and background.

vim2bat asks Vim which colors a colorscheme gives each highlight group, with
your vimrc, and writes bat themes that use the same palette slots, or the same
24-bit colors.

## Install

### Homebrew (macOS and Linux)

```bash
brew install redodson01/tap/vim2bat
```

### PyPI

```bash
uv tool install vim2bat   # or: pipx install vim2bat
```

### From source

```bash
git clone https://github.com/redodson01/vim2bat.git
cd vim2bat
uv tool install .   # or: uv tool install --editable . to follow edits to the checkout
```

The PyPI and source installs put the `vim2bat` command in `~/.local/bin` by
default. Make sure that folder is on your `$PATH` (`uv tool update-shell` or
`pipx ensurepath` adds it).

## Runtime requirements

- Vim 9.1 or newer, with the colorschemes you want to convert
- bat (0.25 or newer for the `--theme-dark` and `--theme-light` settings below)
- Python 3.11 or newer

Debian and Ubuntu install bat as `batcat`. vim2bat runs `bat`, so link it:
`ln -s /usr/bin/batcat ~/.local/bin/bat`.

## Usage

```bash
vim2bat retrobox     # builds vim-retrobox-dark and vim-retrobox-light
vim2bat --all        # builds every colorscheme Vim lists
bat --theme=vim-retrobox-dark file.rb
```

| Option | Effect |
|---|---|
| `-a`, `--all` | Builds every colorscheme Vim lists, several at a time |
| `-c`, `--clean` | First deletes vim2bat's cache and the whole bat themes folder |
| `-s`, `--strict` | Maps only Vim's standard highlight groups, such as `Comment` and `String` |
| `-t`, `--truecolor` | Turns on `termguicolors`, so the themes use the scheme's 24-bit colors |
| `-p`, `--palette 16\|256` | Overrides your vimrc's `t_Co` |

vim2bat rebuilds bat's cache when it finishes, so the themes are available right
away.

### Theme names

A scheme that supports both backgrounds gets `vim-SCHEME-dark` and
`vim-SCHEME-light`. A scheme that supports a single background, by setting
`background` itself, gets `vim-SCHEME`.

### What decides the colors

Vim runs with your vimrc in a 256-color terminal, so your vimrc decides what the
themes look like: a scheme's own options (such as `g:solarized_use16`), `t_Co`
and `termguicolors` all apply. `-p` and `-t` override `t_Co` and
`termguicolors` for one run. Each theme records the options it was built with in
its `comment` entry. `-p` has no effect while `termguicolors` is on, whether
from `-t` or your vimrc.

With `-t`, bat prints the exact colors only when `COLORTERM` is `truecolor` or
`24bit`. Otherwise it rounds them to the nearest of 256.

## Using the themes

### bat

Add these lines to bat's config file, whose path `bat --config-file` prints:

```
--theme-dark="vim-retrobox-dark"
--theme-light="vim-retrobox-light"
--italic-text=always
```

bat's default, `--theme=auto`, picks between them by asking the terminal for its
background. It doesn't ask when its output goes to a pipe, as in fzf.vim's
previews, and then uses its own default theme. On macOS, `--theme="auto:system"`
follows the system appearance instead, and works in pipes too.

bat leaves out italics unless `--italic-text` is `always`.

### delta

delta takes a single syntax theme:

```ini
[delta]
    syntax-theme = vim-retrobox-dark
```

On macOS, git's pager command can pick the theme from the system appearance:

```ini
[core]
    pager = delta --syntax-theme=vim-retrobox-$(defaults read -g AppleInterfaceStyle 2>/dev/null | grep -qx Dark && echo dark || echo light)
```

## Measuring a theme

`vim2bat compare THEME FILE...` reports how often the theme gives each
character the color Vim does, per file and per language, then the most common
mismatches:

```bash
vim2bat compare vim-retrobox-dark app/models/*.rb
```

Expect 85 to 90 percent on real code in the languages Table 3 covers (see
below): bat's syntax definitions don't split code exactly the way Vim's do.
Other languages get only Table 2 and score lower.

## How it works

1. For each background, vim2bat runs Vim with your vimrc on a pseudo-terminal,
   loads the scheme, and records each highlight group's colors and attributes
   (Table 1, cached in `$XDG_CACHE_HOME/vim2bat/tables`, or
   `~/.cache/vim2bat/tables`). Vim gets a terminal because
   without one it numbers named colors such as `DarkBlue` differently.
2. `src/vim2bat/share/strict.tsv` (Table 2) maps Vim's standard groups, such
   as `Comment` and `String`, to the TextMate scopes with the same meaning.
3. `src/vim2bat/share/loose.tsv` (Table 3) maps language-specific scopes to the
   Vim syntax groups that Vim gives the same tokens, for Ruby, ERB, HTML, CSS
   and SCSS, TypeScript and TSX, JavaScript and JSX, YAML, Vim script, git
   commit messages and diffs. The languages and tokens follow what
   vim-solarized8 colors.
4. Palette colors use bat's palette notation, where `#0E000000` means slot 14,
   and the terminal's default color is `#00000001`.

## Known limits

- bat doesn't paint a scheme's background color, so a scheme with its own
  background, such as habamax, sits on your terminal's.
- bat themes support only bold, italic and underline, so reverse and undercurl
  are dropped.
- `-c` deletes the whole bat themes folder, including themes vim2bat didn't
  build.
- A single-background scheme whose own name ends in `-dark` or `-light` gets a
  name that looks like another scheme's background variant.
- Colorschemes in a subfolder of `colors/`, whose names contain `/`, aren't
  supported. vim2bat rejects those names.

## Uninstall

```bash
brew uninstall vim2bat   # or: uv tool uninstall vim2bat, or pipx uninstall vim2bat
rm "$(bat --config-dir)"/themes/vim-*.tmTheme && (cd / && bat cache --build)
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/vim2bat"
```

## Development

Development uses [uv](https://docs.astral.sh/uv/) (`brew install uv`).

```bash
git clone https://github.com/redodson01/vim2bat.git
cd vim2bat
uv sync                    # creates .venv with vim2bat and the dev tools
uv run pre-commit install  # runs ruff and file checks before each commit
uv run pytest              # unit tests, plus integration tests when vim and bat are installed
uv run mypy                # type checks src and tests
uv run ruff check          # lints
uv run ruff format         # formats
```

[CONTRIBUTING.md](https://github.com/redodson01/vim2bat/blob/main/CONTRIBUTING.md)
covers the golden files, measuring a change, the rules for the tables, and
releasing.

## License

[MIT](https://github.com/redodson01/vim2bat/blob/main/LICENSE)
