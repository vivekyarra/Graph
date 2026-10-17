"""Model-led MCP tool selection contract using a fake LLM only in tests."""
from types import SimpleNamespace as N
import pytest
import maelin.reasoner as reasoner
from test_agents import FakeFalkorStore, SCENE


class FakeChat:
    def __init__(self,tool): self.calls=0;self.tool=tool
    def create(self, **kwargs):
        self.calls+=1
        if self.calls==1:
            tool=N(id="tool-1",function=N(name=self.tool,arguments="{}"))
            return N(choices=[N(message=N(tool_calls=[tool],content=None))])
        return N(choices=[N(message=N(tool_calls=[],content="The graph evidence supports bounded review, not live changes."))])


def test_recon_specialist_selects_actual_bounded_graph_tool(monkeypatch):
    chat=FakeChat("inspect_attack_paths")
    monkeypatch.setattr(reasoner,"model_enabled",lambda:True)
    monkeypatch.setattr(reasoner,"make_client",lambda:N(chat=N(completions=chat)))
    store=FakeFalkorStore()
    result=reasoner.reason_with_tools("recon",store,"alpha","a",SCENE,{"alert":"synthetic"})
    assert result["status"]=="reasoned_with_mcp_tools"
    assert result["tools"]==["inspect_attack_paths"]
    assert ("alpha","attack_paths") in store.seen_queries
    assert chat.calls==2


def test_model_cannot_request_arbitrary_tool(monkeypatch):
    chat=FakeChat("execute_cypher")
    monkeypatch.setattr(reasoner,"model_enabled",lambda:True)
    monkeypatch.setattr(reasoner,"make_client",lambda:N(chat=N(completions=chat)))
    with pytest.raises(ValueError,match="unapproved"):
        reasoner.reason_with_tools("recon",FakeFalkorStore(),"alpha","a",SCENE,{})


def test_no_model_does_not_fake_agent_reasons(monkeypatch):
    monkeypatch.setattr(reasoner,"model_enabled",lambda:False)
    assert reasoner.reason_with_tools("recon",FakeFalkorStore(),"alpha","a",SCENE,{}) is None
