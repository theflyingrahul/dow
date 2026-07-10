"""Man page + version surface: guard the roff generator and `dow --version`.

Regression coverage for two defects found during a v2.0.2 install verification:

1. A wrapped doc line beginning with ``'`` or ``.`` is a roff control line, so
   troff silently dropped it (e.g. init.txt's "'dow commit' to capture v1 ..."
   sentence vanished from `man dow`). `_roff` now protects such lines with a
   leading zero-width ``\\&``.
2. There was no ``dow --version`` flag even though the version feeds the man
   page header; it is now a top-level eager option.
"""
from typer.testing import CliRunner

from dow.cli import _dow_version, _render_manpage, _roff, app

runner = CliRunner()


def test_roff_protects_leading_control_characters():
    # Lines that begin with a roff control char get a zero-width guard.
    assert _roff("'dow commit' to capture v1").startswith("\\&'")
    assert _roff(".PP is not a real macro here").startswith("\\&.")
    # Ordinary prose is untouched (apart from hyphen/backslash escaping).
    assert _roff("ordinary line") == "ordinary line"
    # Multi-line text is guarded line by line.
    out = _roff("first line\n'second starts with quote")
    assert out.splitlines()[1].startswith("\\&'")


def test_manpage_has_no_unprotected_control_line_from_prose():
    page = _render_manpage()
    # The init sentence that troff used to swallow must survive, guarded.
    assert "'dow commit' to capture v1" in page
    assert "\\&'dow commit' to capture v1" in page
    # No line may start with an apostrophe followed by a letter (that is the
    # exact shape troff misreads as an undefined macro call).
    for line in page.splitlines():
        assert not (line[:1] == "'" and line[1:2].isalpha()), line


def test_version_flag_prints_version():
    for flag in ("--version", "-V"):
        result = runner.invoke(app, [flag])
        assert result.exit_code == 0
        assert _dow_version() in result.stdout
