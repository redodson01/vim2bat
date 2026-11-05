# Contributing to vim2bat

## Development

vim2bat is a Python package that uses only the standard library. The code is in
`src/vim2bat/cli.py`, and `src/vim2bat/share/` holds two Vim scripts and two
tables. You need Vim, bat and [uv](https://docs.astral.sh/uv/) (`brew install
uv`). uv uses Python 3.11 or newer and downloads one if none is installed, and
it installs the dev tools (pytest, mypy, ruff and pre-commit) at the versions in
`uv.lock`.

```bash
uv sync                    # creates .venv with an editable install of vim2bat and the dev tools
uv run pre-commit install  # installs the git hook described below
uv run pytest              # unit tests, plus integration tests when vim and bat are installed
uv run mypy                # type checks src and tests in strict mode
uv run ruff check          # lints (add --fix to apply the safe fixes)
uv run ruff format         # formats
```

`uv run` brings `.venv` up to date with `uv.lock` before it runs a command, and
because the install is editable, changes under `src/` take effect without
reinstalling.

The pre-commit hook runs on the files you commit. It lints them with
`ruff check --fix`, formats them with `ruff format`, runs `uv lock` when
`pyproject.toml` or `uv.lock` changes, trims trailing whitespace, fixes final
newlines, checks YAML and TOML syntax, and rejects large files. It doesn't run
mypy or the tests.

The integration tests build themes from the test colorschemes in
`tests/fixtures/colors`, in a scratch home, bat config and cache, and compare
the strict themes with the files in `tests/golden`. After an intended change to
the output, regenerate those files and check their diff:

```bash
UPDATE_GOLDEN=1 uv run pytest
```

## Measuring a change

`uv run vim2bat compare THEME FILE...` measures a theme against Vim. Before and
after a change to the tables, rebuild the theme with `uv run vim2bat SCHEME`,
which uses your checkout, and measure it on a representative set of your own
code. Keep those files out of the repository.

## The tables

`src/vim2bat/share/strict.tsv` maps each of Vim's standard groups to the
TextMate scopes with the same meaning, one row per group: `GROUP<TAB>SCOPES`.

`src/vim2bat/share/loose.tsv` adds language-specific rows:
`FILETYPE<TAB>GROUP<TAB>SCOPES`. vim-solarized8's language-specific coloring
decides which languages and tokens are in scope. A new row follows these rules:

1. Map scopes that bat already assigns to the Vim group that Vim gives the same
   tokens, by meaning.
2. Use the first group in the token's link chain (as `vim2bat compare` lists
   it) that exists in Table 1 (the groups vim2bat records from Vim), or
   `Normal` for tokens that Vim leaves plain. When one scope covers tokens with
   different chains, use the first group they all share.
3. The filetype column is the Vim filetype whose syntax file defines the group.
4. Qualify every selector by language: a language-suffixed scope, or the
   language's root scope plus exactly one other scope. No selector combines two
   non-root scopes, and none uses exclusions.
5. Don't rely on the order of rows with equal specificity.
6. Stop when every remaining kind of mismatch is under 1% of characters, or
   would need a rule that depends on context.
7. Don't fit rows to particular files.

## Pull requests

- Keep PRs focused on a single change
- Ensure `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` and
  `uv run pytest` pass (CI runs all four, checks that `uv.lock` is current, and
  runs the tests on macOS and Linux with Python 3.11 through 3.15)
- Update `CHANGELOG.md` under `[Unreleased]` when making a notable change
- Use atomic, logically-ordered commits
- Follow the commit message style of the existing history

## Versioning

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **MAJOR** for incompatible CLI changes or theme names
- **MINOR** for backwards-compatible new features
- **PATCH** for backwards-compatible bug fixes

## Releasing

1. Run `uv version --bump patch` (or `minor` or `major`). It sets the new
   version in `pyproject.toml` and `uv.lock`, and `vim2bat --version` reads it
   from the installed package.
2. In `CHANGELOG.md`, move the `[Unreleased]` entries under a new
   `## [X.Y.Z] - YYYY-MM-DD` heading, change the `[Unreleased]` link to compare
   `vX.Y.Z...HEAD`, and add an `[X.Y.Z]` link that compares the previous tag
   with `vX.Y.Z`.
3. Commit and push, then push a `vX.Y.Z` tag for the new version.

The release workflow checks that the tag matches the version in
`pyproject.toml`, builds the sdist and wheel with `uv build`, and publishes them
to PyPI through trusted publishing. It then creates the GitHub release with the
built files attached, and updates the formula in
[redodson01/homebrew-tap](https://github.com/redodson01/homebrew-tap) using the
`HOMEBREW_TAP_TOKEN` secret. Each job runs only after the one before it
succeeds, so a tag that doesn't match the version publishes nothing.

### One-time setup

Before the first release:

1. Create redodson01/vim2bat on GitHub as a public repository and push `main`.
   The tap update downloads the tag's source tarball without credentials, and
   Dependabot's pre-commit updates work only in public repositories.
2. On PyPI, add a pending trusted publisher on the GitHub tab of your account's
   [Publishing](https://pypi.org/manage/account/publishing/) page:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `vim2bat` |
   | Owner | `redodson01` |
   | Repository name | `vim2bat` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   A pending publisher doesn't reserve the name, and it stops working if
   someone else registers vim2bat first. The first upload turns it into a
   normal publisher.
3. Optionally, create the `pypi` environment on GitHub (Settings, Environments)
   and add yourself as a required reviewer, so that each PyPI upload waits for
   your approval. Do this before the first tag, because a release run otherwise
   creates the environment with no protection rules. On the Free plan, required
   reviewers work only in public repositories.
4. Add a repository secret named `HOMEBREW_TAP_TOKEN` (Settings, Secrets and
   variables, Actions). It holds a fine-grained personal access token limited
   to redodson01/homebrew-tap, with Contents set to read and write. Without it,
   the release skips the tap update.
