"""
Retrieval híbrido: busca por hijos (chunks), responde con padres (páginas completas).
HyDE + semántico + BM25 + fusión RRF.
"""

import re
import threading
import unicodedata

from rank_bm25 import BM25Okapi

from ..rag.embedder import embeber_texto
from ..rag.store import buscar_semantico, cargar_corpus_bm25, obtener_padres_batch
from ..config import settings


def _tokenizar_bm25(texto: str) -> list[str]:
    """Tokeniza texto para BM25: minúsculas, sin acentos, sin puntuación."""
    # Normalización Unicode (NFKD) para separar tildes del carácter base
    # y poder eliminarlas. Importante para que "salario" y "salário" coincidan.
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    limpio = re.sub(r"[^\w\s]", " ", sin_acentos)
    # Descarta tokens de un solo carácter, que generan ruido en el índice.
    return [t for t in limpio.split() if len(t) > 1]


# Cache en memoria del índice BM25. Reconstruirlo desde disco en cada consulta
# sería inviable; el lock evita que dos hilos lo recarguen a la vez.
_bm25_cache = {
    "corpus": None,
    "bm25": None,
    "ids": None,
    "metadatas": None,
}
_bm25_lock = threading.Lock()
_bm25_dirty = True  # se pone a True tras indexar/borrar un documento


def invalidar_cache_bm25():
    """Marca el cache BM25 como sucio."""
    global _bm25_dirty
    _bm25_dirty = True


def _obtener_bm25():
    """Devuelve (bm25, ids, metadatas) desde cache o recargando."""
    global _bm25_dirty
    with _bm25_lock:
        if not _bm25_dirty and _bm25_cache["bm25"] is not None:
            return _bm25_cache["bm25"], _bm25_cache["ids"], _bm25_cache["metadatas"]

        try:
            corpus = cargar_corpus_bm25()
        except FileNotFoundError:
            return None, None, None

        documentos = corpus.get("documentos", [])
        if not documentos:
            return None, None, None

        corpus_tokenizado = [_tokenizar_bm25(doc) for doc in documentos]
        bm25 = BM25Okapi(corpus_tokenizado)

        _bm25_cache["bm25"] = bm25
        _bm25_cache["ids"] = corpus["ids"]
        _bm25_cache["metadatas"] = corpus.get("metadatas", [])
        _bm25_dirty = False

        return bm25, _bm25_cache["ids"], _bm25_cache["metadatas"]


_hyde_cache: dict[str, str] = {}
_HYDE_CACHE_MAX = 100
_hyde_lock = threading.Lock()


def _generar_documento_hipotetico(query: str) -> str | None:
    """Genera un fragmento hipotético de contrato para HyDE. Cache por query."""
    # Cache LRU simple: si la misma consulta ya se procesó, se reutiliza el
    # documento hipotético para evitar una llamada al LLM (~5-10 s).
    with _hyde_lock:
        if query in _hyde_cache:
            return _hyde_cache[query]

    try:
        from ..llm import get_context_llm
        llm = get_context_llm()
        # El prompt fuerza al modelo a usar terminología contractual formal
        # (registro alejado del lenguaje coloquial del usuario) para acercar
        # el embedding al de los fragmentos reales del índice.
        prompt = (
            "Escribe un fragmento breve de un contrato laboral (máximo 5 líneas) "
            "que respondería directamente a esta pregunta. "
            "Usa términos genéricos como 'el trabajador' o 'la empresa', "
            "sin nombres propios. Incluye datos concretos inventados (cifras, plazos). "
            "Solo el fragmento, sin explicaciones.\n\n"
            f"Pregunta: {query}"
        )
        resultado = llm.invoke(prompt).content.strip()
        with _hyde_lock:
            _hyde_cache[query] = resultado
            # Limite duro de tamaño del cache para evitar crecimiento ilimitado.
            if len(_hyde_cache) > _HYDE_CACHE_MAX:
                _hyde_cache.pop(next(iter(_hyde_cache)))
        return resultado
    except Exception:
        # Si HyDE falla por timeout o error del LLM, no se rompe la consulta:
        # se cae a búsqueda directa con la query original.
        import logging
        logging.getLogger("docuasist").warning("HyDE falló para query '%s', usando búsqueda directa", query[:80])
        return None


def _buscar_bm25(query: str, k: int, filtro: dict = None) -> list[dict]:
    """Búsqueda léxica BM25 sobre textos de hijos."""
    bm25, ids, metadatas = _obtener_bm25()
    if bm25 is None:
        return []

    scores = bm25.get_scores(_tokenizar_bm25(query))

    indices_ordenados = sorted(
        range(len(scores)), key=lambda i: scores[i], reverse=True
    )[:k]

    resultados = []
    for rank, idx in enumerate(indices_ordenados):
        score = float(scores[idx])

        if score < settings.min_score_bm25:
            continue

        meta = metadatas[idx] if idx < len(metadatas) else {}

        if filtro and "nombre_trabajador" in filtro:
            if meta.get("nombre_trabajador", "") != filtro["nombre_trabajador"]:
                continue

        resultados.append({
            "parent_id": ids[idx],
            "doc_id": meta.get("doc_id", ""),
            "doc_nombre": meta.get("doc_nombre", ""),
            "pagina": meta.get("pagina", 0),
            "nombre_trabajador": meta.get("nombre_trabajador", ""),
            "dni": meta.get("dni", ""),
            "score_bm25": score,
            "rank_bm25": rank,
        })

    return resultados


def _fusionar_rrf(
    resultados_semanticos: list[dict],
    resultados_bm25: list[dict],
    k: int,
) -> list[dict]:
    """Fusiona rankings semántico y BM25 con RRF."""
    # Reciprocal Rank Fusion ignora las puntuaciones absolutas (que están en
    # escalas distintas entre ambas búsquedas) y trabaja solo con las posiciones.
    # Score(d) = sum_{r in R} 1 / (k + rank_r(d))
    scores_rrf: dict[str, dict] = {}

    # Primera pasada: ranking semántico.
    for rank, r in enumerate(resultados_semanticos):
        clave = r["parent_id"]
        if clave not in scores_rrf:
            scores_rrf[clave] = {
                **r,
                "score_rrf": 1 / (k + rank),
                "rank_semantico": rank,
                "rank_bm25": None,
            }

    # Segunda pasada: ranking BM25. Si el documento ya estaba, se acumula la
    # puntuación; si no, se añade como entrada nueva.
    for rank, r in enumerate(resultados_bm25):
        clave = r["parent_id"]
        if clave in scores_rrf:
            scores_rrf[clave]["score_rrf"] += 1 / (k + rank)
            scores_rrf[clave]["rank_bm25"] = rank
        else:
            scores_rrf[clave] = {
                **r,
                "score_rrf": 1 / (k + rank),
                "rank_semantico": None,
                "rank_bm25": rank,
                "nombre_trabajador": r.get("nombre_trabajador", ""),
                "dni": r.get("dni", ""),
            }

    return sorted(scores_rrf.values(), key=lambda x: x["score_rrf"], reverse=True)


def _enriquecer_con_padre(
    fusionados: list[dict],
    coleccion: str = None,
) -> list[dict]:
    """Sustituye texto del hijo por texto del padre (página completa)."""
    # Varios chunks hijo pueden apuntar al mismo padre; deduplicamos por
    # parent_id para no devolver la misma página varias veces al LLM.
    fusionados_unicos = []
    padres_vistos = set()
    for resultado in fusionados:
        parent_id = resultado.get("parent_id", "")
        if parent_id and parent_id not in padres_vistos:
            padres_vistos.add(parent_id)
            fusionados_unicos.append(resultado)

    # Lectura por lotes de los padres en ChromaDB (una sola llamada para todos).
    parent_ids = [r["parent_id"] for r in fusionados_unicos]
    textos_padres = obtener_padres_batch(parent_ids, coleccion)

    evidence_pack = []
    for resultado in fusionados_unicos:
        parent_id = resultado["parent_id"]
        texto = textos_padres.get(parent_id, "") or resultado.get("texto", "")
        if not texto:
            continue

        evidence_pack.append({
            "texto": texto,
            "nombre_trabajador": resultado.get("nombre_trabajador", ""),
            "dni": resultado.get("dni", ""),
            "doc_nombre": resultado.get("doc_nombre", ""),
            "pagina": resultado.get("pagina", 0),
            "doc_id": resultado.get("doc_id", ""),
            "parent_id": parent_id,
            "score_rrf": resultado.get("score_rrf", 0),
            "rank_semantico": resultado.get("rank_semantico"),
            "rank_bm25": resultado.get("rank_bm25"),
        })

    return evidence_pack


def recuperar(
    query: str,
    coleccion: str = None,
    n_resultados: int = None,
    usar_hyde: bool = True,
    usar_bm25: bool = True,
    filtro: dict = None,
) -> list[dict]:
    """Pipeline de retrieval: HyDE → semántico → BM25 → RRF → enriquecimiento padre."""
    k = n_resultados or settings.retrieval_k

    if usar_hyde:
        texto_hyde = _generar_documento_hipotetico(query)
        query_embedding = embeber_texto(texto_hyde if texto_hyde else query)
    else:
        query_embedding = embeber_texto(query)

    from concurrent.futures import ThreadPoolExecutor

    resultados_semanticos = []
    resultados_bm25 = []

    def _busqueda_semantica():
        raw = buscar_semantico(
            query_embedding=query_embedding,
            n_resultados=k * 2,
            coleccion=coleccion,
            filtro=filtro,
        )
        return [r for r in raw if len(r.get("texto", "")) >= settings.min_chars_resultado]

    def _busqueda_bm25_fn():
        return _buscar_bm25(query=query, k=k, filtro=filtro)

    # Búsqueda semántica y BM25 en paralelo para reducir la latencia total.
    with ThreadPoolExecutor(max_workers=2) as executor:
        fut_sem = executor.submit(_busqueda_semantica)
        fut_bm25 = executor.submit(_busqueda_bm25_fn) if usar_bm25 else None

        resultados_semanticos = fut_sem.result()
        if fut_bm25:
            resultados_bm25 = fut_bm25.result()

    # k=60: constante de suavizado RRF según el paper original de Cormack et al. (2009).
    fusionados = _fusionar_rrf(
        resultados_semanticos=resultados_semanticos,
        resultados_bm25=resultados_bm25,
        k=settings.rrf_k,
    )[:k]

    evidence_pack = _enriquecer_con_padre(fusionados, coleccion)

    return evidence_pack
