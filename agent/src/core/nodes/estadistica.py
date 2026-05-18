"""Nodo de estadísticas: agregaciones sobre el corpus indexado.

Responde preguntas tipo "salario medio de los contratos", "distribución
por tipo de contrato", "empresas con más contratos"… La información
proviene de los metadatos almacenados en SQLite al indexar, no del LLM
ni del retrieval semántico: la respuesta es determinista y trazable a
los registros de la base de datos.

La salida se compone como Markdown listo para renderizar en el frontend.
"""

import time

from langchain_core.messages import HumanMessage, AIMessage

from src.core.state import AgentState
from src.core.rag.index_manifest import obtener_estadisticas_contratos


def nodo_estadistica(state: AgentState) -> dict:
    """Genera respuesta estadística a partir de datos SQL agregados."""
    inicio = time.time()

    stats = obtener_estadisticas_contratos()
    query = state.get("query_normalizada", state.get("pregunta", ""))

    partes = []
    partes.append(f"**Estadísticas de {stats['total_contratos']} contratos indexados:**\n")

    # Salarios
    sal = stats["salario"]
    if sal["total_datos"] > 0:
        partes.append("### Salarios")
        partes.append(f"- **Media**: {sal['media']:,.0f} EUR/año")
        if sal.get("mediana") is not None:
            partes.append(f"- **Mediana**: {sal['mediana']:,.0f} EUR/año")
        partes.append(f"- **Mínimo**: {sal['minimo']:,.0f} EUR/año")
        partes.append(f"- **Máximo**: {sal['maximo']:,.0f} EUR/año")
        partes.append(f"- *Datos disponibles: {sal['total_datos']}/{stats['total_contratos']}*\n")

    # Salario medio por tipo de contrato
    sal_tipo = stats.get("salario_por_tipo", {})
    if sal_tipo:
        partes.append("### Salario medio por tipo")
        for tipo, media in sorted(sal_tipo.items(), key=lambda x: -x[1]):
            partes.append(f"- **{tipo.capitalize()}**: {media:,.0f} EUR/año")
        partes.append("")

    # Jornada
    jor = stats["jornada"]
    if jor["total_datos"] > 0:
        partes.append("### Jornada")
        partes.append(f"- **Media**: {jor['media']}h semanales")
        partes.append(f"- *Datos disponibles: {jor['total_datos']}/{stats['total_contratos']}*\n")

    # Vacaciones
    vac = stats["vacaciones"]
    if vac["total_datos"] > 0:
        partes.append("### Vacaciones")
        partes.append(f"- **Media**: {vac['media']} días")
        partes.append(f"- *Datos disponibles: {vac['total_datos']}/{stats['total_contratos']}*\n")

    # Antigüedad media
    ant = stats.get("antiguedad_anios", {})
    if ant.get("total_datos", 0) > 0:
        partes.append("### Antigüedad")
        partes.append(f"- **Media**: {ant['media']} años desde el inicio del contrato")
        partes.append(f"- *Datos disponibles: {ant['total_datos']}/{stats['total_contratos']}*\n")

    # Tipos de contrato
    if stats["tipos_contrato"]:
        partes.append("### Tipos de contrato")
        total = stats["total_contratos"]
        for tipo, cantidad in sorted(stats["tipos_contrato"].items(), key=lambda x: -x[1]):
            pct = round(cantidad / max(total, 1) * 100, 1)
            partes.append(f"- **{tipo.capitalize()}**: {cantidad} ({pct}%)")
        partes.append("")

    # Empresas
    if stats["empresas"]:
        partes.append("### Distribución por empresa")
        for emp, cantidad in sorted(stats["empresas"].items(), key=lambda x: -x[1]):
            partes.append(f"- **{emp}**: {cantidad} contratos")
        partes.append("")

    # Top puestos
    if stats["puestos"]:
        top = sorted(stats["puestos"].items(), key=lambda x: -x[1])[:10]
        partes.append("### Puestos más frecuentes")
        for puesto, cantidad in top:
            partes.append(f"- {puesto}: {cantidad}")
        partes.append("")

    respuesta = "\n".join(partes)
    latencia = round(time.time() - inicio, 3)

    traza = list(state.get("traza", []))
    traza.append({"nodo": "estadistica", "latencia_s": latencia})

    return {
        "respuesta": respuesta,
        "citas": [],
        "no_consta": False,
        "traza": traza,
        "messages": [
            HumanMessage(content=state["pregunta"]),
            AIMessage(content=respuesta),
        ],
    }
