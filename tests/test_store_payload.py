"""Upgrade B: heavy per-item ``payload`` is offloaded to a git-ignored,
content-addressed artifact and rehydrated (with integrity checks) on read - the
version JSON in git stays light."""
import json
import os

from dow.store import Store


def _record(payload):
    """A minimal but complete run record (what ``runner.execute`` produces)."""
    return {
        "spec_name": "s",
        "spec_fingerprint": "fp0",
        "run_id": "2024-01-01T00:00:00Z",
        "input": "x",
        "config": {"evaluation": {}},
        "runtime": {},
        "samples": [{"output": "o"}],
        "metrics": {"stability": 1.0},
        "payload": payload,
    }


def _disk_payload(root, vid):
    path = root / ".dow" / "versions" / "s" / f"{vid}.json"
    return json.loads(path.read_text(encoding="utf-8")).get("payload")


def test_payload_is_externalized_and_rehydrated(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    vid = st.add_version("s", _record({"labels": [1, 2, 3]}))

    # On disk (and therefore in git) the version holds only a reference.
    disk = _disk_payload(tmp_path, vid)
    assert set(disk) == {"__artifact__", "sha256", "bytes"}
    assert "labels" not in json.dumps(disk)

    # get_record transparently rehydrates the real payload.
    rec = st.get_record("s", vid)
    assert rec["payload"] == {"labels": [1, 2, 3]}


def test_artifacts_are_git_ignored(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    ignored = (tmp_path / ".dow" / ".gitignore").read_text(encoding="utf-8").split()
    assert "artifacts/" in ignored          # heavy payload blobs stay out of git
    assert "*.tmp" in ignored               # atomic-write crash residue stays out too
    st.add_version("s", _record({"labels": [1, 2, 3]}))
    tracked = st.git._run("ls-files", check=False)
    assert "artifacts/" not in tracked
    # The blob really exists on disk, just untracked.
    assert list((tmp_path / ".dow" / "artifacts").glob("*.json"))


def test_content_addressed_dedup(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    st.add_version("s", _record({"labels": [1, 2, 3]}))
    st.add_version("s", _record({"labels": [1, 2, 3]}))  # identical payload
    assert len(list((tmp_path / ".dow" / "artifacts").glob("*.json"))) == 1


def test_integrity_mismatch_is_flagged(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    vid = st.add_version("s", _record({"labels": [1, 2, 3]}))
    ref = _disk_payload(tmp_path, vid)["__artifact__"]
    (tmp_path / ".dow" / "artifacts" / ref).write_text('{"labels": [9]}', encoding="utf-8")
    rec = st.get_record("s", vid)
    assert rec.get("_payload_integrity") == "sha256-mismatch"


def test_missing_artifact_is_flagged(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    vid = st.add_version("s", _record({"labels": [1, 2, 3]}))
    ref = _disk_payload(tmp_path, vid)["__artifact__"]
    os.remove(tmp_path / ".dow" / "artifacts" / ref)
    rec = st.get_record("s", vid)
    assert rec["payload"] is None
    assert rec.get("_payload_missing")


def test_no_payload_is_left_untouched(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    rec = _record(None)
    del rec["payload"]
    vid = st.add_version("s", rec)
    assert _disk_payload(tmp_path, vid) is None
    assert st.get_record("s", vid).get("payload") is None
