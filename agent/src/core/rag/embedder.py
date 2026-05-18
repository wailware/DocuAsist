"""Wrapper sobre OllamaEmbeddings para reutilizar la conexión.

Genera vectores de 4096 dimensiones con qwen3-embedding:8b. El cliente
HTTP se inicializa una sola vez (patrón singleton) porque cada
construcción negocia parámetros con el servidor Ollama y añade latencia
innecesaria en bucles de indexación que llaman a embed_documents miles
de veces.

Se distingue entre embed_documents (textos a indexar) y embed_query
(consulta del usuario) porque algunos modelos de embedding aplican
plantillas diferentes según el rol; aquí ambos delegan en el mismo
modelo pero la separación se respeta por API.
"""

from langchain_ollama import OllamaEmbeddings

from .chunker import ChunkHijo
from ..config import settings

_embedder = None


def crear_embedder() -> OllamaEmbeddings:
    """Devuelve la instancia singleton del modelo de embeddings."""
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbeddings(
            model=settings.embed_model,
            base_url=settings.ollama_base_url,
        )
    return _embedder


def embeber_chunks(hijos: list[ChunkHijo]) -> list[list[float]]:
    """Genera embeddings en batch para una lista de chunks hijo."""
    textos = [h.texto for h in hijos]
    return crear_embedder().embed_documents(textos)


def embeber_texto(texto: str) -> list[float]:
    """Genera el embedding de un texto individual. Se usa en el retrieval."""
    return crear_embedder().embed_query(texto)