"""Security boundaries dow must uphold.

dow deliberately treats a shared *spec* as code: ``provider: python`` and
evaluator/comparator/aggregator/plot refs (``file.py:function``) execute local
Python by design. These tests pin the boundaries that must hold *regardless* of
that model - the ones an attacker could otherwise reach without writing a ``.py``
file, e.g. through the read-only MCP surface:

* store ids/names are single path components (no ``..`` traversal out of ``.dow``);
* ``service.docs`` only serves the packaged help files, never arbitrary paths;
* artifact references rehydrated from a record cannot read outside the store;
* git is driven as an argv list, so messages/tags/refs cannot inject a shell;
* specs are parsed with ``yaml.safe_load`` (no object construction / code exec).
"""
import json

import pytest

from dow import service
from dow.gitstore import GitError, GitStore
from dow.spec import InferenceSpec
from dow.store import Store, _safe_component

TRAVERSALS = [
    "..",
    ".",
    "",
    "../secret",
    "../../../../etc/passwd",
    "a/b",
    "a\\b",
    "/abs",
    "sha\x00.json",
]

LEGIT_SLUGS = ["a1", "a12", "v1", "v300", "summarization", "my.spec", "a-b_c", "sha256"]


# --- component guard -------------------------------------------------------- #

@pytest.mark.parametrize("bad", TRAVERSALS)
def test_safe_component_rejects_traversal(bad):
    with pytest.raises(ValueError):
        _safe_component(bad, "id")


@pytest.mark.parametrize("ok", LEGIT_SLUGS)
def test_safe_component_accepts_plain_slugs(ok):
    assert _safe_component(ok, "id") == ok


# --- Alert 1: aggregation-id traversal (HIGH) ------------------------------- #

def _make_store_with_aggregation(root):
    st = Store(root)
    st.ensure()
    st.save_aggregation("s", {"members": ["v1"], "aggregators": {"n_raters": 1.0}})
    return st


def test_get_aggregation_blocks_traversal(tmp_path):
    st = _make_store_with_aggregation(tmp_path)
    # A real, high-value JSON file outside the store the attacker would target.
    secret = tmp_path / "creds.json"
    secret.write_text(json.dumps({"token": "s3cr3t"}), encoding="utf-8")

    assert st.get_aggregation("s", "a1")["aggregators"]["n_raters"] == 1.0  # legit read

    for bad in ["../../../creds", "../../creds", "..", "a/b", "/abs"]:
        with pytest.raises(ValueError):
            st.get_aggregation("s", bad)
    # A traversal in the spec name is refused too.
    with pytest.raises(ValueError):
        st.get_aggregation("../../..", "a1")


def test_service_get_aggregation_surfaces_clean_error(tmp_path):
    _make_store_with_aggregation(tmp_path)
    # service scaffolds the example spec name lookup via need_spec; a traversal
    # id must come back as a user-facing DowError, never leak a file.
    with pytest.raises(service.DowError):
        service.get_aggregation(tmp_path, name="s", agg_id="../../../creds")


# --- Alert 1 sibling: version-id traversal ---------------------------------- #

def test_get_record_blocks_traversal(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    vid = st.add_version(
        "s",
        {
            "spec_name": "s",
            "spec_fingerprint": "fp",
            "run_id": "2024-01-01T00:00:00Z",
            "input": "x",
            "config": {"evaluation": {}},
            "runtime": {},
            "samples": [{"output": "o"}],
            "metrics": {},
            "payload": None,
        },
    )
    assert st.get_record("s", vid)["spec_name"] == "s"  # legit read
    for bad in ["../../../../etc/passwd", "..", "a/b"]:
        with pytest.raises(ValueError):
            st.get_record("s", bad)


# --- Alert 1 sibling: traversal on the WRITE path --------------------------- #

_RECORD = {
    "spec_name": "s", "spec_fingerprint": "fp", "run_id": "2024-01-01T00:00:00Z",
    "input": "x", "config": {"evaluation": {}}, "runtime": {},
    "samples": [{"output": "o"}], "metrics": {}, "payload": None,
}


@pytest.mark.parametrize("bad", ["../../../../tmp/escape", "..", "a/b", "a\\b", "/abs", ""])
def test_store_writes_block_traversal_spec_name(tmp_path, bad):
    """A traversal *spec name* must never let a write escape the ``.dow`` store.

    Reads are already guarded; the write methods (add_version / save_eval /
    save_aggregation) build ``.dow/versions/<name>/…`` and ``.dow/aggregations/
    <name>/…`` paths too, so an unsanitized name here would write files anywhere
    on disk. Through the service layer ``find_spec_name`` stems the name, but the
    store is the documented security boundary and must self-defend.
    """
    st = Store(tmp_path)
    st.ensure()
    before = {p.resolve() for p in tmp_path.rglob("*")}

    with pytest.raises(ValueError):
        st.add_version(bad, dict(_RECORD))
    with pytest.raises(ValueError):
        st.save_aggregation(bad, {"members": ["v1"], "aggregators": {"x": 1.0}})

    # A legit version to target save_eval's version-id sanitization too.
    vid = st.add_version("s", dict(_RECORD))
    with pytest.raises(ValueError):
        st.save_eval(bad, vid, {"metrics": {}})
    with pytest.raises(ValueError):
        st.save_eval("s", bad, {"metrics": {}})

    # Nothing was created outside the store (only the legit "s" version dir).
    after = {p.resolve() for p in tmp_path.rglob("*")}
    escaped = {p for p in (after - before) if ".dow" not in p.parts}
    assert not escaped, f"write escaped the store: {escaped}"


@pytest.mark.parametrize("bad", ["../../../../tmp/escape", "..", "a/b", "a\\b", "/abs", ""])
def test_store_writes_block_traversal_suite_name(tmp_path, bad):
    """A traversal *suite name* must never let a suite bundle escape ``.dow``.

    ``save_suite_aggregation``/``get_suite_aggregation`` build ``.dow/aggregations/
    _suites/<name>/…`` paths; the store must self-defend on both write and read.
    """
    st = Store(tmp_path)
    st.ensure()
    before = {p.resolve() for p in tmp_path.rglob("*")}

    with pytest.raises(ValueError):
        st.save_suite_aggregation(bad, {"members": ["s:v1"], "aggregators": {"x": 1.0}})
    with pytest.raises(ValueError):
        st.get_suite_aggregation(bad, "a1")

    after = {p.resolve() for p in tmp_path.rglob("*")}
    escaped = {p for p in (after - before) if ".dow" not in p.parts}
    assert not escaped, f"suite write escaped the store: {escaped}"


# --- hardening: poisoned artifact reference --------------------------------- #
def test_internalize_refuses_traversal_artifact_ref(tmp_path):
    st = Store(tmp_path)
    st.ensure()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"leak": True}), encoding="utf-8")

    poisoned = {
        "payload": {"__artifact__": "../../outside.json", "sha256": "x", "bytes": 1}
    }
    rec = st._internalize(poisoned)
    assert rec["payload"] is None
    assert rec["_payload_integrity"] == "invalid-artifact-ref"


# --- Alert 2: docs path traversal (read-only surface) ----------------------- #

def test_docs_serves_only_packaged_help(tmp_path):
    # A legit command returns its packaged help text.
    assert service.docs("compare")["command"] == "compare"
    # Overview lists the commands.
    assert "commands" in service.docs()

    for bad in ["../../requirements", "../__init__", "../../pyproject", "a/b", ".."]:
        with pytest.raises(service.DowError):
            service.docs(bad)


def test_mcp_docs_resource_does_not_leak(tmp_path):
    pytest.importorskip("mcp")
    from dow import mcp_server as M

    try:
        out = M.command_docs_resource("../../requirements")
    except Exception:
        return  # blocked by raising - acceptable
    # If it returned anything, it must not be the out-of-tree requirements file.
    assert "typer" not in out.lower()


# --- git backend: argv list, never a shell ---------------------------------- #

def test_gitstore_does_not_invoke_a_shell(tmp_path):
    g = GitStore(tmp_path)
    g.init()
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    g.add("f.txt")
    # Shell metacharacters in the message would execute if shell=True were used.
    sha = g.commit("; touch INJECTED; echo $(whoami) `id` && rm -rf .")
    assert sha  # commit succeeded with the literal message
    assert not (tmp_path / "INJECTED").exists()
    # A tag name with metacharacters is a literal ref (git rejects it as an
    # invalid tag name), never a shell command that could create TAGGED.
    try:
        g.tag("v1; touch TAGGED", "HEAD")
    except GitError:
        pass
    assert not (tmp_path / "TAGGED").exists()


# --- spec parsing: safe YAML only ------------------------------------------- #

def test_spec_load_uses_safe_yaml(tmp_path):
    evil = tmp_path / "evil.yaml"
    evil.write_text(
        "!!python/object/apply:os.system ['touch PWNED']\n", encoding="utf-8"
    )
    with pytest.raises(Exception):
        InferenceSpec.load(str(evil))
    assert not (tmp_path / "PWNED").exists()
