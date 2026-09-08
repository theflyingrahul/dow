"""Manifest-driven cohort capture.

Each test names a user-visible break: wrong merge semantics changes the experiment,
weak validation makes resume ambiguous, and unstable identity can join different grids.
"""
from __future__ import annotations

import copy

import pytest

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
