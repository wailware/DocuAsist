"""Estado compartido del grafo LangGraph.

TypedDict que viaja entre nodos. Cada nodo lee únicamente los campos que
necesita y escribe los que produce; LangGraph se encarga de fusionar los
diccionarios parciales que devuelve cada nodo con el estado global.

Hereda de MessagesState para tener soporte nativo del historial de mensajes
acumulado a lo largo de la sesión.
"""

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    # Entrada de la consulta
    user_id: str
    session_id: str
    pregunta: str

    # Resultado del nodo Intent
    intent: str                          # buscar, resumir, comparar, legal, temporal, estadistica, conversacional
    modo: str                            # documental | legal
    query_normalizada: str               # consulta limpia de erratas y normalizada
    necesita_aclaracion: bool            # true si el sistema necesita pedir más info al usuario
    pregunta_aclaracion: str
    entidades: dict                      # personas, fechas y demás entidades extraídas
    sub_consultas: list[dict]            # sub-consultas en consultas multi-persona
    rango_fechas: dict                   # para consultas temporales

    # Resultado del nodo Retrieval
    evidence_pack: list[dict]            # fragmentos recuperados (con metadatos)
    alertas_compliance: list[dict]       # infracciones detectadas por reglas (modo legal)

    # Resultado del nodo Analysis
    campos_extraidos: dict               # campos estructurados del contrato (modo resumen)
    observaciones: list[str]             # comparativa contrato vs Estatuto (modo legal)

    # Resultado del nodo Response
    respuesta: str
    citas: list[dict]
    no_consta: bool                      # true si la información solicitada no aparece en los documentos

    # Streaming SSE
    stream_mode: bool
    prompt_messages: list
    citas_preparadas: list[dict]

    # Auditoría: latencia por nodo para la traza visible en el frontend
    traza: list[dict]
