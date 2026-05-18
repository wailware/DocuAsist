"""Interfaz con ChromaDB y persistencia del corpus BM25.

Encapsula toda la interacción con el almacenamiento vectorial. La
arquitectura usa cuatro colecciones:

- hijos privados/públicos: chunks pequeños con embedding, base de la
  búsqueda semántica.
- padres privados/públicos: páginas completas sin embedding, sirven
  como contexto extendido tras un match en su hijo.

Las colecciones se separan por privacidad porque pueden indexarse en
flujos distintos y se mantienen padres e hijos en colecciones
diferentes porque ChromaDB exige dimensionalidad homogénea por
colección (los hijos llevan vector 4096-d, los padres no llevan
embedding).

Además, este módulo persiste el corpus BM25 en JSON: al añadir o
eliminar un documento, se regenera el fichero para que el retriever
disponga siempre del estado más reciente.
"""

import json
import threading
from pathlib import Path

import chromadb

from .chunker import ChunkHijo, ChunkPadre
from ..config import settings


# Cliente HTTP singleton: ChromaDB tarda en establecer la conexión, y
# en cada request del API se hacen varias consultas a colecciones.
_chroma_client = None


def _cliente() -> chromadb.HttpClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return _chroma_client


# Cache de nombres de trabajadores indexados, con bandera de dirty y
# lock para sincronizar la invalidación cuando se indexa o borra un
# documento desde un hilo distinto al que está sirviendo consultas.
_nombres_cache: dict[str, list[str]] = {}
_nombres_dirty = True
_nombres_lock = threading.Lock()


def invalidar_cache_nombres():
    """Marca el cache de nombres como sucio."""
    global _nombres_dirty
    with _nombres_lock:
        _nombres_dirty = True


def obtener_nombres_indexados(coleccion: str = None) -> list[str]:
    """Devuelve nombres únicos de trabajadores indexados.

    Resultado cacheado en memoria. La función se invoca con frecuencia en la
    fase de resolución de nombres y la consulta de metadatos a ChromaDB es
    relativamente costosa cuando el corpus crece.
    """
    global _nombres_dirty
    nombre_col = coleccion or settings.chroma_collection_private

    with _nombres_lock:
        if not _nombres_dirty and nombre_col in _nombres_cache:
            return _nombres_cache[nombre_col]

    col = _coleccion_hijos(nombre_col)
    resultado = col.get(include=["metadatas"])
    nombres = set()
    for meta in resultado["metadatas"]:
        nombre = meta.get("nombre_trabajador", "")
        if nombre:
            nombres.add(nombre)

    with _nombres_lock:
        _nombres_cache[nombre_col] = list(nombres)
        _nombres_dirty = False
        return _nombres_cache[nombre_col]


def _coleccion_hijos(nombre: str = None):
    return _cliente().get_or_create_collection(
        name=nombre or settings.chroma_collection_private
    )


def _coleccion_padres(nombre: str = None):
    return _cliente().get_or_create_collection(
        name=nombre or settings.chroma_collection_padres_private
    )


def guardar_chunks(
    padres: list[ChunkPadre],
    hijos: list[ChunkHijo],
    embeddings: list[list[float]],
    doc_id: str,
    coleccion: str = None,
) -> None:
    """Guarda padres e hijos en sus colecciones de ChromaDB.

    Operación transaccional desde el punto de vista del documento: tras
    completarse se invalida el cache de nombres y se regenera el corpus
    BM25 si el documento es privado (los públicos no entran en BM25
    porque la normativa se busca solo por semántica).
    """
    nombre_hijos = coleccion or settings.chroma_collection_private
    nombre_padres = (
        settings.chroma_collection_padres_public
        if coleccion == settings.chroma_collection_public
        else settings.chroma_collection_padres_private
    )

    if padres:
        col_padres = _coleccion_padres(nombre_padres)
        col_padres.add(
            ids=[p.id for p in padres],
            documents=[p.texto for p in padres],
            metadatas=[
                {
                    "doc_nombre": p.doc_nombre,
                    "pagina": p.pagina,
                    "doc_id": doc_id,
                }
                for p in padres
            ],
        )

    if hijos:
        col_hijos = _coleccion_hijos(nombre_hijos)
        col_hijos.add(
            ids=[f"{doc_id}_hijo_{h.chunk_index}" for h in hijos],
            documents=[h.texto for h in hijos],
            embeddings=embeddings,
            metadatas=[
                {
                    "parent_id": h.parent_id,
                    "doc_nombre": h.doc_nombre,
                    "pagina": h.pagina,
                    "chunk_index": h.chunk_index,
                    "doc_id": doc_id,
                    "nombre_trabajador": h.nombre_trabajador,
                    "dni": h.dni,
                    "tipo_contrato": h.tipo_contrato,
                }
                for h in hijos
            ],
        )

    invalidar_cache_nombres()

    # BM25 solo se reconstruye para la colección privada: la normativa
    # pública se busca exclusivamente por similitud semántica.
    if nombre_padres == settings.chroma_collection_padres_private:
        _actualizar_corpus_bm25(nombre_hijos, nombre_padres)
        # Import diferido para evitar el ciclo store ↔ retriever durante
        # la carga inicial del módulo.
        try:
            from ..rag.retriever import invalidar_cache_bm25
            invalidar_cache_bm25()
        except ImportError:
            pass


def borrar_chunks_documento(doc_id: str, coleccion: str = None) -> None:
    """Elimina todos los chunks (hijos y padres) de un documento."""
    nombre_hijos = coleccion or settings.chroma_collection_private
    nombre_padres = (
        settings.chroma_collection_padres_public
        if coleccion == settings.chroma_collection_public
        else settings.chroma_collection_padres_private
    )
    _coleccion_hijos(nombre_hijos).delete(where={"doc_id": doc_id})
    _coleccion_padres(nombre_padres).delete(where={"doc_id": doc_id})

    invalidar_cache_nombres()

    if nombre_padres == settings.chroma_collection_padres_private:
        _actualizar_corpus_bm25(nombre_hijos, nombre_padres)
        from ..rag.retriever import invalidar_cache_bm25
        invalidar_cache_bm25()


def buscar_semantico(
    query_embedding: list[float],
    n_resultados: int = None,
    coleccion: str = None,
    filtro: dict = None,
) -> list[dict]:
    """Busca los chunks hijo más similares a un embedding.

    El `filtro` aprovecha la cláusula `where` de ChromaDB sobre los
    metadatos. Se usa típicamente para restringir por nombre de
    trabajador, DNI o tipo de contrato; aplicar el filtro al motor es
    más eficiente que filtrar en Python después.
    """
    nombre_hijos = coleccion or settings.chroma_collection_private
    col = _coleccion_hijos(nombre_hijos)
    k = n_resultados or settings.retrieval_k

    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": k,
        "include": ["documents", "metadatas", "distances"],
    }
    if filtro:
        kwargs["where"] = filtro

    resultado = col.query(**kwargs)

    if not resultado["documents"] or not resultado["documents"][0]:
        return []

    return [
        {
            "texto": texto,
            "parent_id": meta["parent_id"],
            "doc_nombre": meta["doc_nombre"],
            "pagina": meta["pagina"],
            "chunk_index": meta["chunk_index"],
            "doc_id": meta["doc_id"],
            "nombre_trabajador": meta.get("nombre_trabajador", ""),
            "dni": meta.get("dni", ""),
            "distancia": distancia,
        }
        for texto, meta, distancia in zip(
            resultado["documents"][0],
            resultado["metadatas"][0],
            resultado["distances"][0],
        )
    ]



def obtener_padre(parent_id: str, coleccion_hijos: str = None) -> str:
    """Recupera el texto completo de un padre por su ID."""
    nombre_padres = (
        settings.chroma_collection_padres_public
        if coleccion_hijos == settings.chroma_collection_public
        else settings.chroma_collection_padres_private
    )
    col = _coleccion_padres(nombre_padres)
    resultado = col.get(ids=[parent_id], include=["documents"])
    if resultado["documents"]:
        return resultado["documents"][0]
    return ""


def obtener_padres_batch(parent_ids: list[str], coleccion_hijos: str = None) -> dict[str, str]:
    """Recupera textos de múltiples padres en una sola query batch.

    El retriever necesita los padres de todos los hijos del top-k tras
    la fusión; hacer una llamada por padre añadiría latencia notable
    sobre ChromaDB. Devuelve un dict {parent_id: texto} para acceso O(1).
    """
    if not parent_ids:
        return {}
    nombre_padres = (
        settings.chroma_collection_padres_public
        if coleccion_hijos == settings.chroma_collection_public
        else settings.chroma_collection_padres_private
    )
    col = _coleccion_padres(nombre_padres)
    ids_unicos = list(set(parent_ids))
    resultado = col.get(ids=ids_unicos, include=["documents"])
    return dict(zip(resultado["ids"], resultado["documents"])) if resultado["documents"] else {}


def _ruta_corpus() -> Path:
    return Path(settings.bm25_corpus_path)


def _actualizar_corpus_bm25(
    nombre_coleccion_hijos: str,
    nombre_coleccion_padres: str = None,
) -> None:
    """Reconstruye el fichero de corpus BM25 desde el estado de ChromaDB.

    Volcamos el corpus en JSON en disco en lugar de calcular BM25 al
    vuelo desde ChromaDB cada vez, porque rank_bm25 necesita el corpus
    en memoria y reconstruirlo en cada consulta sería muy costoso. La
    regeneración solo ocurre al indexar o borrar documentos.
    """
    col_hijos = _coleccion_hijos(nombre_coleccion_hijos)
    hijos = col_hijos.get(include=["documents", "metadatas"])

    corpus = {
        "ids": [meta.get("parent_id", "") for meta in hijos["metadatas"]],
        "documentos": hijos["documents"],
        "metadatas": hijos["metadatas"],
    }

    ruta = _ruta_corpus()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False)


def cargar_corpus_bm25() -> dict:
    """Carga el corpus BM25 desde disco."""
    ruta = _ruta_corpus()
    if not ruta.exists():
        raise FileNotFoundError(
            "No se encontró el corpus BM25. "
            "Asegúrate de haber indexado al menos un documento."
        )
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)