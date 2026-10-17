"""Unit security checks for graph ingestion; no file traversal in production."""
import copy
import pytest
from maelin.schema import validate_dataset
from maelin.seed import dataset


def test_original_scenario_is_accepted():
    result=validate_dataset(dataset())
    assert len(result["pivot_edges"])==8


def test_generic_synthetic_incident_accepts_missing_layout():
    d=dataset()
    for asset in d["assets"]:
        asset.pop("x",None)
        asset.pop("y",None)
    result=validate_dataset(d)
    assert all(isinstance(n["x"],(float,int)) for n in result["assets"])


@pytest.mark.parametrize("mutate", [
    lambda d: d["assets"].append(dict(d["assets"][0])),
    lambda d: d["pivot_edges"].append(dict(d["pivot_edges"][0],id="new",to="absent")),
    lambda d: d["actions"][0].update(blocked_nodes=["missing"]),
    lambda d: d["actions"][0].update(cost=float("nan")),
    lambda d: d["actions"][0].update(blocked_nodes=[],blocked_edges=[]),
    lambda d: d.update(source="missing"),
    lambda d: d.update(fingerprint=""),
])
def test_ingestion_rejects_invalid_topologies(mutate):
    d=copy.deepcopy(dataset())
    mutate(d)
    with pytest.raises(ValueError):
        validate_dataset(d)
