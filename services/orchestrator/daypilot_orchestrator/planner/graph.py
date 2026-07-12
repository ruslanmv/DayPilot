"""Minimal LangGraph-compatible state graph runtime.

The day planner is expressed as a graph of agent nodes over a shared state dict,
using the LangGraph API shape — ``add_node``, ``add_edge``,
``add_conditional_edges``, ``set_entry_point``, ``compile().invoke(state)`` and
the ``START``/``END`` sentinels — so the graph definition can be moved onto the
real ``langgraph`` package without rewriting the nodes. Keeping the runtime
in-repo keeps the dependency surface small and the planner fully offline-testable.
"""
from __future__ import annotations

from typing import Any, Callable

START = "__start__"
END = "__end__"

State = dict[str, Any]
NodeFn = Callable[[State], State]
RouterFn = Callable[[State], str]

MAX_STEPS = 64  # hard guard against accidental infinite loops


class GraphError(RuntimeError):
    pass


class CompiledGraph:
    def __init__(self, nodes: dict[str, NodeFn], edges: dict[str, str],
                 branches: dict[str, RouterFn], entry: str) -> None:
        self._nodes = nodes
        self._edges = edges
        self._branches = branches
        self._entry = entry

    def invoke(self, state: State) -> State:
        """Run the graph to END, threading the state through each node. Every
        visited node is recorded in state['__path__'] for observability."""
        current = self._entry
        state = dict(state)
        path: list[str] = []
        for _ in range(MAX_STEPS):
            if current == END:
                state["__path__"] = path
                return state
            node = self._nodes.get(current)
            if node is None:
                raise GraphError(f"unknown node '{current}'")
            path.append(current)
            update = node(state)
            if update:
                state.update(update)
            if current in self._branches:
                current = self._branches[current](state)
            elif current in self._edges:
                current = self._edges[current]
            else:
                current = END
        raise GraphError(f"graph exceeded {MAX_STEPS} steps (loop guard)")


class StateGraph:
    """LangGraph-shaped builder: nodes + fixed and conditional edges."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, str] = {}
        self._branches: dict[str, RouterFn] = {}
        self._entry: str | None = None

    def add_node(self, name: str, fn: NodeFn) -> "StateGraph":
        self._nodes[name] = fn
        return self

    def add_edge(self, source: str, target: str) -> "StateGraph":
        if source == START:
            self._entry = target
        else:
            self._edges[source] = target
        return self

    def add_conditional_edges(self, source: str, router: RouterFn) -> "StateGraph":
        self._branches[source] = router
        return self

    def set_entry_point(self, name: str) -> "StateGraph":
        self._entry = name
        return self

    def compile(self) -> CompiledGraph:
        if self._entry is None:
            raise GraphError("no entry point set")
        return CompiledGraph(self._nodes, self._edges, self._branches, self._entry)
