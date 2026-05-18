"""Nodo temporal: responde consultas sobre fechas vía SQL.

Atajo para preguntas tipo "qué contratos vencen este mes" o "contratos
firmados en 2024". No tiene sentido pasarlas por el pipeline RAG (la
respuesta no está en el texto, está en los metadatos), por lo que el
intent las redirige aquí y se resuelven con una consulta SQL directa
sobre la tabla de manifiestos.
"""

import time
from datetime import date, timedelta

from langchain_core.messages import AIMessage, HumanMessage

from src.core.state import AgentState
from src.core.rag.index_manifest import consultar_por_fechas


def _formatear_resultados(docs: list[dict], campo: str, query_desc: str) -> str:
    """Formatea la lista de documentos encontrados como texto legible."""
    if not docs:
        return f"No se encontraron contratos {query_desc}."

    lineas = [f"Se encontraron {len(docs)} contrato(s) {query_desc}:\n"]
    for d in docs:
        nombre = d.get("nombre", "").replace("contrato_", "").replace(".pdf", "").replace("_", " ").title()
        tipo = d.get("tipo_contrato", "") or "no especificado"
        fecha = d.get(campo) or "no especificada"
        lineas.append(f"- **{nombre}**: tipo {tipo}, fecha {campo.replace('_', ' ')}: {fecha}")

    return "\n".join(lineas)


def nodo_temporal(state: AgentState) -> dict:
    """Procesa consultas temporales usando SQL sobre metadatos."""
    inicio = time.time()

    rango_fechas = state.get("rango_fechas", {})
    # Por defecto buscamos por fecha_fin (vencimientos): es el caso más
    # frecuente. El intent puede haber escogido otro campo (fecha_inicio,
    # fecha_firma) si la pregunta lo sugiere.
    campo_fecha = rango_fechas.get("campo", "fecha_fin")
    desde = rango_fechas.get("desde")
    hasta = rango_fechas.get("hasta")

    # Fallback: si el intent no consiguió extraer rango, asumimos "este
    # mes". Calculamos primer y último día del mes actual.
    if not desde and not hasta:
        hoy = date.today()
        desde = hoy.replace(day=1).isoformat()
        # Truco para obtener el último día: avanzar al mes siguiente y
        # retroceder un día. Funciona con todos los meses (28/29/30/31).
        ultimo_dia = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        hasta = ultimo_dia.isoformat()

    docs = consultar_por_fechas(campo=campo_fecha, desde=desde, hasta=hasta)

    if desde and hasta:
        desc = f"con {campo_fecha.replace('_', ' ')} entre {desde} y {hasta}"
    elif desde:
        desc = f"con {campo_fecha.replace('_', ' ')} desde {desde}"
    elif hasta:
        desc = f"con {campo_fecha.replace('_', ' ')} hasta {hasta}"
    else:
        desc = ""

    respuesta = _formatear_resultados(docs, campo_fecha, desc)

    latencia = round(time.time() - inicio, 2)
    traza = list(state.get("traza", []))
    traza.append({
        "nodo": "temporal",
        "latencia_s": latencia,
        "resultados": len(docs),
        "campo": campo_fecha,
    })

    return {
        "respuesta": respuesta,
        "citas": [],
        "no_consta": len(docs) == 0,
        "traza": traza,
        "messages": [
            HumanMessage(content=state["pregunta"]),
            AIMessage(content=respuesta),
        ],
    }
