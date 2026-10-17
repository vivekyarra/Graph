"""Dynamic scenario validation must be based on FalkorDB topology, not fixtures."""
import pytest
from maelin.incident import select_scene


class TopologyDouble:
    def topology(self, tenant):
        assert tenant == "alpha"
        return {"nodes":[
            {"id":"internet","kind":"ingress"}, {"id":"auth-service","kind":"service"},
            {"id":"vault-sync","kind":"service"}, {"id":"customer-db","kind":"database"},
            {"id":"checkout","kind":"business_flow"}]}


def test_default_scenario_preserves_memory_identity():
    scene = select_scene(TopologyDouble(), "alpha")
    assert scene["fingerprint"] == "exploited-identity-to-customer-db"


def test_user_selected_node_changes_graph_query_context_and_memory_identity():
    scene = select_scene(TopologyDouble(),"alpha",vulnerable="vault-sync", alert="Service telemetry")
    assert scene["vulnerable"] == "vault-sync"
    assert scene["fingerprint"] != "exploited-identity-to-customer-db"
    assert "vault-sync" in scene["scenario"]


@pytest.mark.parametrize("fields",[
    {"vulnerable":"made-up-node"}, {"vulnerable":"checkout"},
    {"source":"checkout"}, {"source":"customer-db","target":"customer-db"}])
def test_incident_refuses_unknown_or_invalid_node_selection(fields):
    with pytest.raises(ValueError):
        select_scene(TopologyDouble(), "alpha", **fields)
