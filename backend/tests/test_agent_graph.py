from app.agents import AgentRegistry


def test_agent_graph_has_one_supervisor_and_four_workers() -> None:
    graph = AgentRegistry().graph()
    supervisors = [agent for agent in graph.agents if agent.kind == "supervisor"]
    workers = [agent for agent in graph.agents if agent.kind == "worker"]

    assert len(supervisors) == 1
    assert len(workers) == 4
    assert len(graph.edges) == 4
    assert {edge.source for edge in graph.edges} == {"supervisor"}
