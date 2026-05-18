"""Grafo LangGraph: orquestador del pipeline de nodos.

El grafo se compila una sola vez al importar el módulo y se reutiliza para
todas las consultas. Las bifurcaciones condicionales permiten que cada tipo
de intención siga la ruta mínima necesaria.
"""

from langgraph.graph import StateGraph, END

from src.core.state import AgentState
from src.core.nodes.intent import nodo_intent
from src.core.nodes.retrieval import nodo_retrieval
from src.core.nodes.analysis import nodo_analysis
from src.core.nodes.response import nodo_response
from src.core.nodes.temporal import nodo_temporal
from src.core.nodes.estadistica import nodo_estadistica


def _routing_intent(state: AgentState) -> str:
    """Decide el siguiente nodo tras el intent."""
    # Las consultas conversacionales (saludos, agradecimientos…) terminan ya:
    # el nodo intent las resuelve sin pasar por retrieval ni response.
    if state.get("intent") == "conversacional":
        return "fin_conversacional"
    # Si la pregunta es ambigua, se devuelve la solicitud de aclaración
    # generada por intent y se cierra el flujo.
    if state.get("necesita_aclaracion"):
        return "fin_aclaracion"
    # Consultas que no requieren búsqueda vectorial (se resuelven con SQL).
    if state.get("intent") == "temporal":
        return "temporal"
    if state.get("intent") == "estadistica":
        return "estadistica"
    return "retrieval"


def _routing_retrieval(state: AgentState) -> str:
    """Decide si pasar por analysis o ir directo a response."""
    # Caso especial: retrieval detectó ambigüedad de nombres y ya produjo
    # un mensaje pidiendo al usuario que aclare a quién se refiere.
    if state.get("respuesta"):
        return "fin_retrieval"

    modo = state.get("modo", "documental")
    intent = state.get("intent", "buscar")

    # Modo legal y resumen necesitan análisis estructurado antes de redactar
    # la respuesta. El resto va directo al nodo de respuesta.
    if modo == "legal":
        return "analysis"
    if intent == "resumir":
        return "analysis"
    return "response"


def construir_grafo() -> StateGraph:
    """Construye y compila el grafo del agente."""
    grafo = StateGraph(AgentState)

    grafo.add_node("intent", nodo_intent)
    grafo.add_node("retrieval", nodo_retrieval)
    grafo.add_node("analysis", nodo_analysis)
    grafo.add_node("response", nodo_response)
    grafo.add_node("temporal", nodo_temporal)
    grafo.add_node("estadistica", nodo_estadistica)

    grafo.set_entry_point("intent")

    grafo.add_conditional_edges(
        "intent",
        _routing_intent,
        {
            "fin_conversacional": END,
            "fin_aclaracion": END,
            "temporal": "temporal",
            "estadistica": "estadistica",
            "retrieval": "retrieval",
        },
    )

    grafo.add_edge("temporal", END)
    grafo.add_edge("estadistica", END)

    grafo.add_conditional_edges(
        "retrieval",
        _routing_retrieval,
        {
            "fin_retrieval": END,
            "analysis": "analysis",
            "response": "response",
        },
    )

    grafo.add_edge("analysis", "response")
    grafo.add_edge("response", END)

    return grafo.compile()


grafo = construir_grafo()