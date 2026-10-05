"""LangGraph wiring for the five agents.

S2 WALKING SKELETON: agents run in a fixed order so the end-to-end path can be built and
tested. S4 replaces these static edges with agent-directed `Command` handoffs and Planner
arbitration (see docs/IMPLEMENTATION_PLAN.md §2.1).
"""

from langgraph.graph import END, START, StateGraph

from app.agents.analysis import AnalysisAgent
from app.agents.planner import PlannerAgent
from app.agents.search import SearchAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.writer import WriterAgent
from app.graph.context import RunContext
from app.graph.state import ResearchState


def _plan_ready(state: ResearchState) -> str:
    return "search" if state.plan is not None else END


def build_graph():
    graph = StateGraph(ResearchState, context_schema=RunContext)
    graph.add_node("planner", PlannerAgent())
    graph.add_node("search", SearchAgent())
    graph.add_node("analysis", AnalysisAgent())
    graph.add_node("synthesis", SynthesisAgent())
    graph.add_node("writer", WriterAgent())

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", _plan_ready, ["search", END])
    graph.add_edge("search", "analysis")
    graph.add_edge("analysis", "synthesis")
    graph.add_edge("synthesis", "writer")
    graph.add_edge("writer", END)
    return graph.compile()
