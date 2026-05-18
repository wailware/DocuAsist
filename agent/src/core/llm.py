"""Singletons de los modelos LLM (Ollama).

Se mantiene una instancia por modelo para evitar la inicialización repetida
del cliente HTTP en cada invocación.
"""

from langchain_ollama import ChatOllama
from .config import settings

_llm_main = None
_llm_context = None


def get_llm():
    global _llm_main
    if _llm_main is None:
        _llm_main = ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
        )
    return _llm_main


def get_context_llm():
    global _llm_context
    if _llm_context is None:
        _llm_context = ChatOllama(
            model=settings.context_model,
            base_url=settings.ollama_base_url,
            temperature=settings.context_temperature,
        )
    return _llm_context
