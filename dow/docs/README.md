# Command documentation & the `dow` man page

This folder holds the **single source** for every `dow` command's prose
documentation. The same text drives:

- `dow help <command>` — the in-terminal help, and
- `man dow` — the Unix manual page,

so the two can never drift apart. Options and arguments are read from each
command's own definition in code, so they stay correct without being repeated
here.

## Layout

```
dow/docs/
  commit.txt     # one file per command, named exactly after the command
  compare.txt
  ...
  man.txt
  README.md      # this guide (not a command doc, not shipped in the wheel)
```

## File format

Each `<command>.txt` is plain text:

```
<one-line summary>

<optional longer description — any number of paragraphs>

@examples
dow <command> ...
dow <command> ...
```

- Everything **before** the `@examples` line is the description. Its first line is
  used as the short summary in the `dow help` overview; the full text appears in
  `dow help <command>` and in the man page.
- Everything **after** `@examples` is one example invocation per line. Omit the
  `@examples` section entirely when a command has no examples.
- Write plain prose — **no roff or markup**. The man page generator escapes and
  formats it automatically.

Example — `commit.txt`:

```
Run your spec and capture its behavior as a new version.

Executes every input in the spec and stores the outputs together with the full
runtime capture as an automatically named version (v1, v2, ...).

@examples
dow commit
dow commit -m "lower temperature"
dow commit --from v1
```

## How it is wired up

- `dow/cli.py` loads each file with `_doc("<name>")` and passes it to the command
  decorator: `@app.command(**_doc("commit"))`. This sets the command's `help`
  (description) and `epilog` (examples).
- `dow help` is rendered by Typer from those values.
- `man dow` is produced by `_render_manpage()`, which walks the live commands and
  reads the same `help` / `epilog` plus each command's options and arguments.

## Add documentation for a new command

1. Add the command in `dow/cli.py`, decorated with `@app.command(**_doc("<name>"))`.
2. Create `dow/docs/<name>.txt` using the format above.
3. Done — `dow help <name>` and `man dow` pick it up automatically.

## Update an existing command's docs

Edit its `dow/docs/<command>.txt`. No code changes are needed; both `dow help`
and `man dow` reflect the change immediately.

## The man page

- `dow man` — print the man page (roff) to stdout. Pipe it anywhere, e.g.
  `dow man | less`.
- `dow man --install` — write `dow.1` into `~/.local/share/man/man1` (override the
  target with `--dir`) so `man dow` works.
- After editing any doc file, refresh the committed page that ships with the
  package:

  ```
  dow man --install --dir man
  ```

  This rewrites `man/dow.1`, which is kept in version control.

## Packaging

`pyproject.toml` ships both pieces:

```toml
[tool.setuptools.package-data]
dow = ["docs/*.txt"]              # so dow help / dow man work when installed

[tool.setuptools.data-files]
"share/man/man1" = ["man/dow.1"]  # so `pip install` puts `man dow` on the path
```

## Platform notes

- **Linux, macOS, WSL, Git Bash:** `man dow` works after a normal `pip install`,
  or after running `dow man --install` once (required for editable installs,
  which skip `data-files`).
- **Windows PowerShell:** `man` is an alias for `Get-Help` and will **not** render
  this page. Use WSL or Git Bash for `man dow`, or read it directly with `dow man`.

## Quick reference

| Task | Command / file |
| --- | --- |
| Edit a command's docs | `dow/docs/<command>.txt` |
| Preview in the terminal | `dow help <command>` |
| Preview the man page | `dow man` (or `man dow` on Unix) |
| Refresh committed `man/dow.1` | `dow man --install --dir man` |
| Install so `man dow` works | `dow man --install` |
