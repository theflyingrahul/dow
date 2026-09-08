"""Manifest-driven cohort capture.

Each test names a user-visible break: wrong merge semantics changes the experiment,
weak validation makes resume ambiguous, and unstable identity can join different grids.
"""
from __future__ import annotations

import copy

import pytest

from dow import runner
from dow.spec import CohortSpec, InferenceSpec


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
