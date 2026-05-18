"""Nodo de análisis: paso intermedio entre retrieval y response.

Se activa solo en dos casos (ver routing en graph.py):
- intent == "resumir": extrae campos estructurados del contrato para que
  el response genere un resumen organizado por secciones.
- modo == "legal": cruza cláusulas del contrato con artículos del
  Estatuto y produce una valoración por punto.

Para búsquedas simples este nodo se salta, ya que añadiría una llamada
extra al LLM sin aportar valor.
"""

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.state import AgentState
from src.core.prompts.analysis import (
    SYSTEM_DOCUMENTAL,
    HUMAN_DOCUMENTAL,
    SYSTEM_LEGAL,
    HUMAN_LEGAL,
    ALERTAS_LEGAL_TPL,
)


def _formatear_alertas_compliance(alertas: list[dict]) -> str:
    """Convierte la lista de alertas en el bloque para el prompt legal.

    Las alertas vienen del compliance_checker (verificación determinista
    durante la indexación). Se inyectan en el prompt como pista
    explícita: el LLM puede confirmarlas, ampliarlas o contextualizarlas
    con los fragmentos recuperados.
    """
    if not alertas:
        return ""
    lineas = []
    for a in alertas:
        trab = a.get("trabajador", "")
        articulo = a.get("articulo", "")
        mensaje = a.get("mensaje", "")
        prefijo = f"- [{trab}] " if trab else "- "
        lineas.append(f"{prefijo}{articulo}: {mensaje}")
    return ALERTAS_LEGAL_TPL.format(lineas="\n".join(lineas))


def _formatear_fragmentos_documental(evidence_pack: list[dict]) -> str:
    """Formatea el evidence pack para extracción documental."""
    if not evidence_pack:
        return "Sin fragmentos disponibles."

    partes = []
    for i, frag in enumerate(evidence_pack):
        doc_nombre = frag.get("doc_nombre", "") or frag.get("doc_id", "Desconocido")
        partes.append(
            f"[{i+1}] Doc: {doc_nombre} | Pág: {frag.get('pagina', '?')}\n"
            f"{frag.get('texto', '')}"
        )
    return "\n\n".join(partes)


def _formatear_fragmentos_legal(evidence_pack: list[dict]) -> str:
    """Formatea fragmentos para cruce legal ([CONTRATO] / [NORMATIVA])."""
    if not evidence_pack:
        return "Sin fragmentos disponibles."

    partes = []
    for i, frag in enumerate(evidence_pack):
        origen = frag.get("origen", "contrato").upper()
        etiqueta = f"[{origen}]"

        if origen == "CONTRATO":
            nombre = frag.get("nombre_trabajador") or "No identificado"
            cabecera = f"{etiqueta} Contrato de: {nombre} | Pág: {frag.get('pagina', '?')}"
        else:
            doc_nombre = frag.get("doc_nombre", "") or "Normativa"
            cabecera = f"{etiqueta} {doc_nombre} | Pág: {frag.get('pagina', '?')}"

        partes.append(f"[{i+1}] {cabecera}\n{frag.get('texto', '')}")

    return "\n\n".join(partes)


def nodo_analysis(state: AgentState) -> dict:
    """Analiza el evidence pack según el modo (documental o legal).

    Produce salida JSON estructurada que el nodo de respuesta usa para
    construir un texto coherente. Si el LLM falla en devolver JSON
    válido, se cae a campos vacíos y se marca el error en la traza
    (mejor degradar que romper toda la cadena).
    """
    inicio = time.time()

    evidence_pack = state.get("evidence_pack", [])
    # Salida temprana si retrieval no encontró nada: no tiene sentido
    # llamar al LLM con contexto vacío.
    if not evidence_pack:
        return {
            "campos_extraidos": {},
            "observaciones": [],
            "traza": list(state.get("traza", [])) + [
                {"nodo": "analysis", "latencia_s": 0, "info": "sin evidencia"}
            ],
        }

    modo = state.get("modo", "documental")

    from src.core.llm import get_llm
    llm = get_llm()

    if modo == "legal":
        fragmentos = _formatear_fragmentos_legal(evidence_pack)
        alertas_bloque = _formatear_alertas_compliance(
            state.get("alertas_compliance", []),
        )
        mensajes = [
            SystemMessage(content=SYSTEM_LEGAL),
            HumanMessage(content=HUMAN_LEGAL.format(
                fragmentos=fragmentos,
                pregunta=state.get("pregunta", ""),
                alertas_bloque=alertas_bloque,
            )),
        ]
    else:
        fragmentos = _formatear_fragmentos_documental(evidence_pack)
        mensajes = [
            SystemMessage(content=SYSTEM_DOCUMENTAL),
            HumanMessage(content=HUMAN_DOCUMENTAL.format(fragmentos=fragmentos)),
        ]

    respuesta = llm.invoke(mensajes)

    # Parseo defensivo: el LLM puede envolver el JSON en bloques
    # ```json ... ``` o anteceder un razonamiento en <think>. Limpiamos
    # ambos casos antes de intentar el json.loads.
    try:
        texto = respuesta.content.strip()
        if "</think>" in texto:
            texto = texto.split("</think>", 1)[-1].strip()
        texto = texto.replace("```json", "").replace("```", "").strip()
        datos = json.loads(texto)

        if modo == "legal":
            campos = datos.get("puntos_analizados", datos)
            observaciones = datos.get("observaciones", [])
        else:
            campos = datos.get("campos_extraidos", datos)
            observaciones = datos.get("observaciones", [])

    except json.JSONDecodeError:
        campos = {}
        observaciones = []
        import logging
        logging.warning("analysis: JSON parse failed. Raw LLM output: %s", respuesta.content[:500])

    latencia = round(time.time() - inicio, 2)

    traza = list(state.get("traza", []))
    traza_entry = {
        "nodo": "analysis",
        "latencia_s": latencia,
        "modo": modo,
    }
    if not campos and evidence_pack:
        traza_entry["json_parse_error"] = True
    traza.append(traza_entry)

    return {
        "campos_extraidos": campos,
        "observaciones": observaciones,
        "traza": traza,
    }