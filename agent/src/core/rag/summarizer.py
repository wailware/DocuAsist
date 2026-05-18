"""Genera un resumen breve de un documento recién indexado."""

import logging

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import settings

log = logging.getLogger("docuasist")

_PROMPT = """Eres un asistente que resume contratos laborales.
Dado el texto de un contrato, genera un resumen en español de máximo 3 frases.
Incluye: nombre del trabajador, empresa, tipo de contrato, puesto y salario si aparecen.
Responde SOLO con el resumen, sin encabezados ni explicaciones."""


def generar_resumen(texto: str, max_chars: int = 4000) -> str:
    """Genera un resumen breve del texto, truncado a max_chars."""
    fragmento = texto[:max_chars]
    try:
        llm = ChatOllama(
            model=settings.context_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
        )
        resp = llm.invoke([
            SystemMessage(content=_PROMPT),
            HumanMessage(content=fragmento),
        ])
        resumen = resp.content.strip()
        log.info("Resumen generado (%d chars)", len(resumen))
        return resumen
    except Exception as e:
        log.warning("Error generando resumen: %s", e)
        return ""
