# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-05

### Added

- `vim2bat SCHEME` builds bat themes from a Vim colorscheme as Vim shows it with
  your vimrc: `vim-SCHEME-dark` and `vim-SCHEME-light`, or `vim-SCHEME` for a
  scheme with one background
- `--all` builds every colorscheme Vim lists, several at a time
- `--strict`, `--truecolor`, `--palette 16|256` and `--clean`
- `vim2bat compare THEME FILE...` measures a theme against Vim
- Support for Python 3.11 or newer
- Homebrew install via `brew install redodson01/tap/vim2bat`
- PyPI package, installed with `uv tool install vim2bat` or
  `pipx install vim2bat`
- Source install via `uv tool install .`
- CI that runs ruff, the format check and mypy, and runs the tests on macOS
  and Linux for Python 3.11 through 3.15
- pre-commit hooks for ruff, the uv lockfile and basic file checks
- Release workflow that, on tag push, checks the tag against the package
  version, publishes to PyPI through trusted publishing, creates a GitHub
  release with the built files and updates the redodson01/homebrew-tap formula
- Dependabot config for keeping GitHub Actions, uv dependencies and pre-commit
  hooks current

[Unreleased]: https://github.com/redodson01/vim2bat/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/redodson01/vim2bat/releases/tag/v0.1.0
