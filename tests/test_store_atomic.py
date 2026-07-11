"""Durability: store writes are atomic, so a torn write never corrupts the store.

dow persists its version history as plain JSON files under ``.dow`` (``index.json``,
per-version records, aggregation bundles, content-addressed artifacts). A crash -
or a Dropbox/NFS sync landing mid-write - must never leave a half-written file: a
truncated ``index.json`` would break the whole history, and a truncated artifact
would fail its later sha256 check. Every durable write therefore goes through
:func:`dow.store._atomic_write_bytes` (temp in the same dir -> fsync -> ``os.replace``).
"""
import json

from dow.store import Store, _atomic_write_bytes, _atomic_write_text

_RECORD = {
    "spec_name": "s", "spec_fingerprint": "fp", "run_id": "2024-01-01T00:00:00Z",
    "input": "x", "config": {"evaluation": {}}, "runtime": {},
    "samples": [{"output": "o"}], "metrics": {"stability": 1.0}, "payload": {"k": [1, 2, 3]},
}


def test_atomic_write_roundtrip_and_no_temp_residue(tmp_path):
    target = tmp_path / "sub" / "index.json"   # parent auto-created
    _atomic_write_text(target, '{"specs": {}}')
    assert json.loads(target.read_text(encoding="utf-8")) == {"specs": {}}
    _atomic_write_bytes(target, b'{"specs": {"s": 1}}')  # overwrite
    assert json.loads(target.read_text(encoding="utf-8")) == {"specs": {"s": 1}}
    assert not list(tmp_path.rglob("*.tmp")), "atomic write left a temp file behind"


def test_failure_during_replace_leaves_original_intact(tmp_path, monkeypatch):
    """The whole point: if the write fails, the previous good bytes survive and no
    truncated temp file is left behind."""
    target = tmp_path / "index.json"
    good = '{"specs": {"good": {"counter": 1, "versions": []}}}'
    target.write_text(good, encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated crash at rename")

    monkeypatch.setattr("dow.store.os.replace", boom)
    try:
        _atomic_write_text(target, '{"specs": {"TORN')   # would corrupt if not atomic
        assert False, "expected the simulated failure to propagate"
    except OSError:
        pass

    assert target.read_text(encoding="utf-8") == good      # original untouched
    assert not list(tmp_path.glob("*.tmp"))                # temp cleaned up


def test_store_operations_leave_no_temp_and_gitignore_covers_them(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    vid = st.add_version("s", dict(_RECORD))
    st.save_eval("s", vid, {"metrics": {"score": 1.0}})
    st.save_aggregation("s", {"members": [vid], "aggregators": {"x": 1.0}})

    dow_dir = tmp_path / ".dow"
    assert not list(dow_dir.rglob("*.tmp")), "a store write left a temp file behind"

    # The record (with an externalized payload artifact) round-trips intact.
    rec = st.get_record("s", vid)
    assert rec["payload"] == {"k": [1, 2, 3]}
    assert "_payload_integrity" not in rec and "_payload_missing" not in rec

    # index.json is valid and the gitignore keeps crash-residue temps out of git.
    assert json.loads((dow_dir / "index.json").read_text(encoding="utf-8"))["specs"]
    gitignore = (dow_dir / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.tmp" in gitignore and "artifacts/" in gitignore


def test_ensure_adds_tmp_ignore_to_a_preexisting_gitignore(tmp_path):
    """An older store (whose .gitignore only lists artifacts/) gains the *.tmp rule
    without losing any user-added lines."""
    st = Store(tmp_path)
    dow_dir = tmp_path / ".dow"
    dow_dir.mkdir()
    (dow_dir / ".gitignore").write_text("artifacts/\nmy-custom-line\n", encoding="utf-8")
    st.ensure()
    lines = (dow_dir / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count("artifacts/") == 1          # not duplicated
    assert "my-custom-line" in lines               # preserved
    assert "*.tmp" in lines                         # added
