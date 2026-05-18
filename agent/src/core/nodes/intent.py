"""Nodo de intent: clasifica intención, extrae entidades y normaliza la query."""

import json
import time
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.core.config import settings
from src.core.state import AgentState
from src.core.prompts.intent import SYSTEM, HUMAN

# Patrones léxicos para detectar mensajes puramente conversacionales sin
# necesidad de llamar al LLM. Cubrir estos casos en código evita unos 30 s
# de latencia por consulta trivial.
_SALUDOS = ["hola", "buenos días", "buenas tardes", "buenas noches", "buenas"]
_DESPEDIDAS = ["adiós", "adios", "hasta pronto", "hasta luego", "chao", "bye"]
_AGRADECIMIENTOS = ["gracias", "muchas gracias", "perfecto", "genial"]
_IDENTIDAD = ["quién eres", "quien eres", "qué eres", "que eres", "cómo te llamas", "qué puedes hacer", "que puedes hacer", "qué haces", "que haces", "para qué sirves", "para que sirves"]

# Patrones típicos de inyección de prompts. La detección es básica
# (palabras clave en la consulta) y se complementa con instrucciones
# explícitas en el system prompt del clasificador.
_INJECTION_PATTERNS = [
    "ignora", "olvida", "forget", "override", "bypass",
    "system prompt", "actúa como", "actua como", "act as",
    "pretend", "finge ser", "dime un chiste",
]

# Para estos tipos siempre se devuelve la respuesta predefinida, ignorando
# lo que pueda generar el LLM. Evita respuestas pomposas del modelo a un
# simple "hola".
_TIPOS_CON_FALLBACK_FORZADO = {"saludo", "despedida", "agradecimiento", "identidad"}

_RESPUESTAS = {
    "saludo": "¡Hola! Soy un asistente documental. Puedo ayudarte a consultar información sobre contratos laborales. ¿En qué puedo ayudarte?",
    "despedida": "¡Hasta pronto! Si necesitas consultar algo más, aquí estaré.",
    "agradecimiento": "De nada. Si tienes más preguntas sobre los contratos, no dudes en preguntar.",
    "identidad": "Soy un asistente documental corporativo. Me especializo en responder preguntas sobre contratos laborales consultando directamente los documentos indexados.",
    "default": "Estoy aquí para ayudarte a consultar información sobre contratos laborales.",
}


def _detectar_tipo_conversacional(pregunta: str) -> str:
    """Detecta el tipo de mensaje conversacional (saludo, despedida, etc.)."""
    p = pregunta.lower().strip()
    if any(s in p for s in _SALUDOS):
        return "saludo"
    if any(s in p for s in _DESPEDIDAS):
        return "despedida"
    if any(s in p for s in _AGRADECIMIENTOS):
        return "agradecimiento"
    if any(s in p for s in _IDENTIDAD):
        return "identidad"
    return "default"


def _respuesta_conversacional(pregunta: str, respuesta_llm: str) -> str:
    """Selecciona respuesta conversacional: predefinida para tipos conocidos, LLM para el resto."""
    tipo = _detectar_tipo_conversacional(pregunta)

    if tipo in _TIPOS_CON_FALLBACK_FORZADO:
        return _RESPUESTAS[tipo]

    # Si el LLM filtra parte del system prompt en su respuesta, se descarta
    # y se usa la respuesta por defecto en lugar de mostrar texto interno.
    texto = respuesta_llm.strip()
    frases_sistema = ["clasificador", "asistente documental corporativo", "json", "intent", "modo"]
    if not texto or any(f in texto.lower() for f in frases_sistema):
        return _RESPUESTAS["default"]

    return texto


def _formatear_historial(mensajes: list) -> str:
    """Formatea el historial de mensajes para incluirlo en el prompt."""
    if not mensajes:
        return "Sin historial previo."
    # Solo se incluyen los últimos N turnos (memory_turns × 2 mensajes por
    # turno: usuario + asistente). Historiales más largos degradan la
    # clasificación de intención.
    turnos = []
    for msg in mensajes[-settings.memory_turns * 2:]:
        rol = "Usuario" if isinstance(msg, HumanMessage) else "Asistente"
        turnos.append(f"{rol}: {msg.content}")
    return "\n".join(turnos)


def nodo_intent(state: AgentState) -> dict:
    """Clasifica intención, extrae entidades y normaliza la query."""
    inicio = time.time()

    pregunta = (state.get("pregunta") or "").strip()

    p_lower = pregunta.lower()
    if any(pat in p_lower for pat in _INJECTION_PATTERNS):
        latencia = round(time.time() - inicio, 2)
        respuesta_guard = (
            "Soy un asistente documental especializado en contratos laborales. "
            "Solo puedo responder preguntas sobre los documentos indexados. "
            "¿En qué puedo ayudarte?"
        )
        return {
            "intent": "conversacional",
            "modo": "documental",
            "query_normalizada": "",
            "necesita_aclaracion": False,
            "pregunta_aclaracion": "",
            "entidades": {"personas": []},
            "sub_consultas": [],
            "rango_fechas": {},
            "respuesta": respuesta_guard,
            "no_consta": False,
            "citas": [],
            "traza": list(state.get("traza", [])) + [
                {"nodo": "intent", "latencia_s": latencia, "prompt_injection": True}
            ],
            "messages": [
                HumanMessage(content=pregunta),
                AIMessage(content=respuesta_guard),
            ],
        }

    import re as _re
    if not pregunta or not _re.search(r'[a-záéíóúñA-ZÁÉÍÓÚÑ0-9]', pregunta):
        latencia = round(time.time() - inicio, 2)
        respuesta_vacia = "No he recibido ninguna pregunta. ¿En qué puedo ayudarte?"
        return {
            "intent": "conversacional",
            "modo": "documental",
            "query_normalizada": "",
            "necesita_aclaracion": False,
            "pregunta_aclaracion": "",
            "entidades": {"personas": []},
            "sub_consultas": [],
            "rango_fechas": {},
            "respuesta": respuesta_vacia,
            "no_consta": False,
            "citas": [],
            "traza": list(state.get("traza", [])) + [
                {"nodo": "intent", "latencia_s": latencia, "sub_consultas": 0, "query_vacia": True}
            ],
            "messages": [
                HumanMessage(content=""),
                AIMessage(content=respuesta_vacia),
            ],
        }

    # Atajo conversacional: si solo es saludo/despedida sin pregunta real, respuesta directa
    tipo_conv = _detectar_tipo_conversacional(pregunta)
    if tipo_conv in _TIPOS_CON_FALLBACK_FORZADO:
        resto = p_lower
        for pat in _SALUDOS + _DESPEDIDAS + _AGRADECIMIENTOS + _IDENTIDAD:
            resto = resto.replace(pat, "")
        resto = _re.sub(r'[¿?!¡.,;:\-\s]+', ' ', resto).strip()
        tiene_contenido = any(len(w) >= 3 for w in resto.split())
    else:
        tiene_contenido = True

    if tipo_conv in _TIPOS_CON_FALLBACK_FORZADO and not tiene_contenido:
        latencia = round(time.time() - inicio, 2)
        respuesta_conv = _RESPUESTAS[tipo_conv]
        return {
            "intent": "conversacional",
            "modo": "documental",
            "query_normalizada": "",
            "necesita_aclaracion": False,
            "pregunta_aclaracion": "",
            "entidades": {"personas": []},
            "sub_consultas": [],
            "rango_fechas": {},
            "respuesta": respuesta_conv,
            "no_consta": False,
            "citas": [],
            "traza": list(state.get("traza", [])) + [
                {"nodo": "intent", "latencia_s": latencia, "sub_consultas": 0}
            ],
            "messages": [
                HumanMessage(content=pregunta),
                AIMessage(content=respuesta_conv),
            ],
        }

    from src.core.llm import get_llm
    llm = get_llm()

    historial = _formatear_historial(state.get("messages", []))
    mensajes_llm = [
        SystemMessage(content=SYSTEM.format(
            historial=historial,
            fecha_hoy=date.today().isoformat(),
        )),
        HumanMessage(content=HUMAN.format(pregunta=state["pregunta"])),
    ]

    respuesta = llm.invoke(mensajes_llm)

    try:
        texto = respuesta.content.strip().replace("```json", "").replace("```", "").strip()
        datos = json.loads(texto)
    except json.JSONDecodeError:
        datos = {
            "intent": "buscar",
            "modo": "documental",
            "query_normalizada": state["pregunta"],
            "necesita_aclaracion": False,
            "pregunta_aclaracion": "",
            "respuesta_conversacional": "",
            "entidades": {"personas": []},
            "sub_consultas": [],
        }

    intent = datos.get("intent", "buscar")
    entidades = datos.get("entidades", {"personas": [], "tipos_contrato": []})
    sub_consultas = datos.get("sub_consultas", [])

    sub_consultas_validadas = []
    for sc in sub_consultas:
        if isinstance(sc, dict) and "query" in sc and "personas" in sc:
            sub_consultas_validadas.append({
                "query": sc["query"],
                "personas": sc["personas"] if isinstance(sc["personas"], list) else [],
            })

    latencia = round(time.time() - inicio, 2)

    traza = list(state.get("traza", []))
    traza.append({
        "nodo": "intent",
        "latencia_s": latencia,
        "sub_consultas": len(sub_consultas_validadas),
    })

    rango_fechas = datos.get("rango_fechas", {})
    if isinstance(rango_fechas, dict):
        rango_fechas = {
            "campo": rango_fechas.get("campo", "fecha_fin"),
            "desde": rango_fechas.get("desde"),
            "hasta": rango_fechas.get("hasta"),
        }
    else:
        rango_fechas = {}

    resultado = {
        "intent": intent,
        "modo": datos.get("modo", "documental"),
        "query_normalizada": datos.get("query_normalizada", state["pregunta"]),
        "necesita_aclaracion": datos.get("necesita_aclaracion", False),
        "pregunta_aclaracion": datos.get("pregunta_aclaracion", ""),
        "entidades": entidades,
        "sub_consultas": sub_consultas_validadas,
        "rango_fechas": rango_fechas,
        "traza": traza,
    }

    if intent == "conversacional":
        respuesta_raw = datos.get("respuesta_conversacional", "")
        respuesta_conv = _respuesta_conversacional(state["pregunta"], respuesta_raw)
        resultado["respuesta"] = respuesta_conv
        resultado["no_consta"] = False
        resultado["citas"] = []
        resultado["messages"] = [
            HumanMessage(content=state["pregunta"]),
            AIMessage(content=respuesta_conv),
        ]

    return resultado