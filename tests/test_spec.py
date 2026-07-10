"""Upgrade C: ``operation``/``params`` and ``evaluation.comparators`` are
first-class, serialized, and fingerprinted so they diff and attribute like any
other spec field."""
from dow.spec import InferenceSpec, flatten


def test_operation_params_comparators_roundtrip():
    s = InferenceSpec.from_dict(
        {
            "name": "t",
            "operation": "relabel",
            "params": {"variant": "v2", "seed": 3, "n_grid": [1, 2, 4]},
            "evaluation": {"metrics": ["e.py:a"], "comparators": ["m.py:k"]},
            "inputs": [{"artifact": "data.json", "sha256": "abc"}],
        }
    )
    d = s.to_dict()
    assert d["operation"] == "relabel"
    assert d["params"] == {"variant": "v2", "seed": 3, "n_grid": [1, 2, 4]}
    assert d["evaluation"]["comparators"] == ["m.py:k"]
    assert d["inputs"][0]["artifact"] == "data.json"
    # Serialization is a fixed point: reload -> same dict.
    assert InferenceSpec.from_dict(d).to_dict() == d


def test_defaults_are_present_and_empty():
    d = InferenceSpec.from_dict({"name": "t"}).to_dict()
    assert d["operation"] == ""
    assert d["params"] == {}
    assert d["evaluation"]["comparators"] == []


def test_params_change_changes_fingerprint():
    a = InferenceSpec.from_dict({"name": "t", "params": {"variant": "a"}})
    b = InferenceSpec.from_dict({"name": "t", "params": {"variant": "b"}})
    assert a.fingerprint() != b.fingerprint()


def test_operation_change_changes_fingerprint():
    a = InferenceSpec.from_dict({"name": "t", "operation": "relabel"})
    b = InferenceSpec.from_dict({"name": "t", "operation": "recluster"})
    assert a.fingerprint() != b.fingerprint()


def test_comparators_change_changes_fingerprint():
    a = InferenceSpec.from_dict({"name": "t", "evaluation": {"comparators": ["m.py:k"]}})
    b = InferenceSpec.from_dict({"name": "t", "evaluation": {"comparators": ["m.py:alpha"]}})
    assert a.fingerprint() != b.fingerprint()


def test_params_flatten_to_dotted_keys_for_attribution():
    d = InferenceSpec.from_dict({"params": {"variant": "a", "seed": 1}}).to_dict()
    f = flatten(d)
    assert f["params.variant"] == "a"
    assert f["params.seed"] == 1
