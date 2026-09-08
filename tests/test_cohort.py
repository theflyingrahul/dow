"""Manifest-driven cohort capture.

Each test names a user-visible break: wrong merge semantics changes the experiment,
weak validation makes resume ambiguous, and unstable identity can join different grids.
"""
from __future__ import annotations

import copy
import pytest
import yaml
from typer.testing import CliRunner

from dow import runner, service
from dow.cli import app
from dow.spec import CohortSpec, InferenceSpec
from dow.store import Store


BASE = {
    "name": "probe",
    "task": "base task",
    "params": {
        "seed": 10,
        "nested": {"kept": "yes", "changed": "old"},
        "nullable": "present",
    },
    "model": {"provider": "mock", "name": "m", "version": "1"},
    "sampling": {"temperature": 0.2, "stop": ["END"]},
    "evaluation": {"samples": 1},
    "inputs": ["base"],
}


def test_member_overrides_merge_mappings_and_replace_lists_scalars_and_nulls():
    """A shallow merge would silently discard fixed nested configuration."""
    original = copy.deepcopy(BASE)
    cohort = CohortSpec.from_dict({
        "name": "seed-grid",
        "spec": "probe",
        "members": [{
            "label": "seed-20",
            "message": "second seed",
            "overrides": {
                "params": {
                    "seed": 20,
                    "nested": {"changed": "new"},
                    "nullable": None,
                },
                "sampling": {"stop": ["DONE"]},
                "inputs": [{"artifact": "run-20"}],
            },
        }],
    })

    materialized = cohort.materialize(InferenceSpec.from_dict(BASE))

    assert BASE == original
    assert len(materialized) == 1
    member, spec = materialized[0]
    assert member.label == "seed-20"
    assert member.message == "second seed"
    assert spec.name == "probe"
    assert spec.params == {
        "seed": 20,
        "nested": {"kept": "yes", "changed": "new"},
        "nullable": None,
    }
    assert spec.sampling.stop == ["DONE"]
    assert spec.inputs == [{"artifact": "run-20"}]


@pytest.mark.parametrize(
    "data,match",
    [
        ({"name": "c", "spec": "probe", "members": []}, "at least one member"),
        ({"name": "c", "spec": "", "members": [{"label": "a"}]}, "base spec"),
        ({"name": "c", "spec": "probe", "members": [
            {"label": "same"}, {"label": "same"},
        ]}, "unique"),
        ({"name": "c", "spec": "probe", "members": [
            {"label": "../escape"},
        ]}, "safe component"),
        ({"name": "../c", "spec": "probe", "members": [
            {"label": "a"},
        ]}, "safe component"),
    ],
)
def test_cohort_rejects_ambiguous_or_unsafe_identity(data, match):
    """Unsafe or duplicate identifiers would make durable record paths ambiguous."""
    with pytest.raises(ValueError, match=match):
        CohortSpec.from_dict(data)


def test_member_cannot_change_base_spec_name():
    """Changing the spec name would scatter one cohort across unrelated histories."""
    cohort = CohortSpec.from_dict({
        "name": "c",
        "spec": "probe",
        "members": [{"label": "a", "overrides": {"name": "other"}}],
    })
    with pytest.raises(ValueError, match="may not override.*name"):
        cohort.materialize(InferenceSpec.from_dict(BASE))


def test_cohort_fingerprint_binds_base_spec_member_order_and_overrides():
    """Reordering or changing a grid must never authenticate as the same cohort."""
    base = InferenceSpec.from_dict(BASE)
    first = CohortSpec.from_dict({
        "name": "c", "spec": "probe",
        "members": [
            {"label": "a", "overrides": {"params": {"seed": 10}}},
            {"label": "b", "overrides": {"params": {"seed": 20}}},
        ],
    })
    identical = CohortSpec.from_dict(first.to_dict())
    reversed_grid = CohortSpec.from_dict({
        **first.to_dict(), "members": list(reversed(first.to_dict()["members"])),
    })
    changed_base = InferenceSpec.from_dict({**BASE, "task": "changed"})

    assert first.fingerprint(base) == identical.fingerprint(base)
    assert first.fingerprint(base) != reversed_grid.fingerprint(base)
    assert first.fingerprint(base) != first.fingerprint(changed_base)


def _artifact_spec(path):
    return InferenceSpec.from_dict({
        **BASE,
        "inputs": [{"artifact": str(path)}],
    })


def test_directory_artifact_digest_is_order_independent_and_binds_nested_bytes(tmp_path):
    """Filesystem enumeration order must not change provenance, but content must."""
    left = tmp_path / "left"
    right = tmp_path / "right"
    (left / "nested").mkdir(parents=True)
    (right / "nested").mkdir(parents=True)
    (left / "z.txt").write_text("z", encoding="utf-8")
    (left / "nested" / "a.txt").write_text("a", encoding="utf-8")
    (right / "nested" / "a.txt").write_text("a", encoding="utf-8")
    (right / "z.txt").write_text("z", encoding="utf-8")

    left_record = runner.input_artifacts(_artifact_spec(left), tmp_path)[0]
    right_record = runner.input_artifacts(_artifact_spec(right), tmp_path)[0]

    assert left_record["kind"] == "directory"
    assert left_record["files"] == 2
    assert left_record["bytes"] == 2
    assert left_record["sha256"] == right_record["sha256"]
    (right / "z.txt").write_text("changed", encoding="utf-8")
    changed = runner.input_artifacts(_artifact_spec(right), tmp_path)[0]
    assert changed["sha256"] != left_record["sha256"]


def test_file_artifact_retains_hash_and_reports_kind(tmp_path):
    """Adding directory support must not weaken the existing file contract."""
    artifact = tmp_path / "one.bin"
    artifact.write_bytes(b"abc")
    record = runner.input_artifacts(_artifact_spec(artifact), tmp_path)[0]
    assert record["kind"] == "file"
    assert record["bytes"] == 3
    assert record["sha256"] == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert "files" not in record


def test_directory_artifact_rejects_symlinks(tmp_path):
    """A symlink must not let a declared tree depend on undeclared external bytes."""
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    artifact = tmp_path / "tree"
    artifact.mkdir()
    (artifact / "link").symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        runner.input_artifacts(_artifact_spec(artifact), tmp_path)


def _cohort_project(root):
    specs = root / "specs"
    specs.mkdir(parents=True)
    (root / "ops.py").write_text(
        "def run(req):\n"
        "    variant = req.config['params']['variant']\n"
        "    return {'output': variant, 'payload': {'variant': variant}}\n",
        encoding="utf-8",
    )
    artifact_a = root / "run-a"
    artifact_b = root / "run-b"
    artifact_a.mkdir()
    artifact_b.mkdir()
    (artifact_a / "result.json").write_text('{"value": 1}\n', encoding="utf-8")
    (artifact_b / "result.json").write_text('{"value": 2}\n', encoding="utf-8")
    base = {
        "name": "probe",
        "task": "cohort integration",
        "params": {"variant": "base", "fixed": True},
        "model": {"provider": "python", "name": "ops.py:run", "version": "1"},
        "sampling": {"seed": 7},
        "evaluation": {"embedding_model": "none", "samples": 1},
        "inputs": [{"artifact": str(artifact_a)}],
    }
    cohort = {
        "name": "grid",
        "spec": "probe",
        "members": [
            {"label": "a", "overrides": {
                "params": {"variant": "a"},
                "inputs": [{"artifact": str(artifact_a)}],
            }},
            {"label": "b", "message": "second", "overrides": {
                "params": {"variant": "b"},
                "inputs": [{"artifact": str(artifact_b)}],
            }},
        ],
    }
    base_path = specs / "probe.yaml"
    cohort_path = specs / "grid.cohort.yaml"
    base_path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    cohort_path.write_text(yaml.safe_dump(cohort, sort_keys=False), encoding="utf-8")
    return base_path, cohort_path


def test_capture_cohort_commits_ordered_members_and_aggregates_only_them(tmp_path):
    """Global history must never leak an unrelated version into a cohort result."""
    base_path, _ = _cohort_project(tmp_path)
    original_base = base_path.read_text(encoding="utf-8")

    result = service.capture_cohort(tmp_path, "grid")

    assert base_path.read_text(encoding="utf-8") == original_base
    assert result["cohort"]["status"] == "complete"
    assert [(m["label"], m["version"]) for m in result["cohort"]["completed"]] == [
        ("a", "v1"), ("b", "v2"),
    ]
    assert result["aggregation"]["members"] == ["v1", "v2"]
    store = Store(tmp_path)
    first = store.get_record("probe", "v1")
    second = store.get_record("probe", "v2")
    assert first["config"]["params"] == {"variant": "a", "fixed": True}
    assert second["config"]["params"] == {"variant": "b", "fixed": True}
    assert first["runtime"]["cohort"]["label"] == "a"
    assert second["runtime"]["cohort"]["label"] == "b"
    assert first["runtime"]["cohort"]["id"] == second["runtime"]["cohort"]["id"]
    assert first["runtime"]["input_artifacts"][0]["kind"] == "directory"


def test_capture_cohort_resumes_only_the_exact_completed_prefix(tmp_path, monkeypatch):
    """A crash after member one must resume member two without rerunning member one."""
    _cohort_project(tmp_path)
    real_execute = service.execute
    calls = 0

    def interrupt_second(spec, base_dir=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated interruption")
        return real_execute(spec, base_dir=base_dir)

    monkeypatch.setattr(service, "execute", interrupt_second)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        service.capture_cohort(tmp_path, "grid")
    partial = service.read_cohort(tmp_path, "grid")
    assert partial["status"] == "partial"
    assert [(m["label"], m["version"]) for m in partial["completed"]] == [("a", "v1")]

    monkeypatch.setattr(service, "execute", real_execute)
    resumed = service.capture_cohort(tmp_path, "grid", resume=True)
    assert [(m["label"], m["version"]) for m in resumed["cohort"]["completed"]] == [
        ("a", "v1"), ("b", "v2"),
    ]
    assert len(Store(tmp_path).list_versions("probe")) == 2


def test_capture_cohort_adopts_exact_version_committed_before_checkpoint(tmp_path, monkeypatch):
    """A crash between version commit and progress save must not rerun that member."""
    _cohort_project(tmp_path)
    real_save = Store.save_cohort
    saves = 0

    def interrupt_first_member_checkpoint(self, cohort_name, record):
        nonlocal saves
        saves += 1
        if saves == 2:
            raise RuntimeError("simulated checkpoint interruption")
        return real_save(self, cohort_name, record)

    monkeypatch.setattr(Store, "save_cohort", interrupt_first_member_checkpoint)
    with pytest.raises(RuntimeError, match="simulated checkpoint interruption"):
        service.capture_cohort(tmp_path, "grid")
    assert [v["id"] for v in Store(tmp_path).list_versions("probe")] == ["v1"]
    assert service.read_cohort(tmp_path, "grid")["completed"] == []

    monkeypatch.setattr(Store, "save_cohort", real_save)
    resumed = service.capture_cohort(tmp_path, "grid", resume=True)
    assert [(m["label"], m["version"]) for m in resumed["cohort"]["completed"]] == [
        ("a", "v1"), ("b", "v2"),
    ]
    assert [v["id"] for v in Store(tmp_path).list_versions("probe")] == ["v1", "v2"]


def test_capture_cohort_refuses_resume_after_manifest_or_artifact_change(tmp_path):
    """A changed grid or changed input bytes must require a new cohort identity."""
    _, cohort_path = _cohort_project(tmp_path)
    service.capture_cohort(tmp_path, "grid")
    data = yaml.safe_load(cohort_path.read_text(encoding="utf-8"))
    data["members"][1]["overrides"]["params"]["variant"] = "changed"
    cohort_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(service.DowError, match="cohort identity changed"):
        service.capture_cohort(tmp_path, "grid", resume=True)

    data["members"][1]["overrides"]["params"]["variant"] = "b"
    cohort_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (tmp_path / "run-b" / "result.json").write_text('{"value": 99}\n', encoding="utf-8")
    with pytest.raises(service.DowError, match="cohort identity changed"):
        service.capture_cohort(tmp_path, "grid", resume=True)


def test_capture_cohort_refuses_concurrent_writer(tmp_path):
    """Two writers must not allocate overlapping version ids for one cohort."""
    _cohort_project(tmp_path)
    store = Store(tmp_path)
    store.ensure()
    with store.cohort_lock("grid"):
        with pytest.raises(service.DowError, match="locked"):
            service.capture_cohort(tmp_path, "grid")
    assert not (tmp_path / ".dow" / "locks" / "cohort-grid.lock").exists()


def test_cohort_cli_captures_and_requires_explicit_resume(tmp_path, monkeypatch):
    """The CLI must be a thin, usable surface over the durable service workflow."""
    _cohort_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli = CliRunner()

    first = cli.invoke(app, ["cohort", "grid"])
    assert first.exit_code == 0, first.output
    assert "grid" in first.output
    assert "v1" in first.output and "v2" in first.output

    duplicate = cli.invoke(app, ["cohort", "grid"])
    assert duplicate.exit_code != 0
    assert "resume" in duplicate.output

    resumed = cli.invoke(app, ["cohort", "grid", "--resume"])
    assert resumed.exit_code == 0, resumed.output
    assert [v["id"] for v in Store(tmp_path).list_versions("probe")] == ["v1", "v2"]
