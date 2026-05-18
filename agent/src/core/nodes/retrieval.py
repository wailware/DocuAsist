"""Nodo de retrieval: recupera fragmentos relevantes para la consulta.

Soporta dos modos:
- documental: busca únicamente en contratos privados.
- legal: hace dos retrievals (contratos + normativa pública del Estatuto)
  para que el siguiente nodo pueda contrastar las cláusulas con la ley.

Resuelve además nombres parciales a nombres completos contra el corpus
indexado y maneja consultas multi-persona (comparaciones) buscando una vez
por persona y fusionando resultados.
"""

import time

from langchain_core.messages import HumanMessage

from src.core.config import settings
from src.core.state import AgentState
from src.core.rag.retriever import recuperar
from src.core.rag.store import (
    obtener_nombres_indexados,
    _coleccion_hijos,
)
from src.core.rag.index_manifest import obtener_alertas_por_trabajador


# Diccionario de sinónimos para enriquecer las consultas que se lanzan
# contra la colección de normativa. Sin esto, la query del usuario suele
# usar términos coloquiales ("sueldo") que no aparecen tal cual en el
# Estatuto ("retribución"), y BM25 falla en encontrar el artículo correcto.
_SINONIMOS_LEGALES = {
    "salario": "salario sueldo retribución paga",
    "sueldo": "salario sueldo retribución paga",
    "retribución": "salario sueldo retribución paga",
    "jornada": "jornada horario horas",
    "horario": "jornada horario horas",
    "prueba": "prueba periodo",
    "despido": "despido extinción",
    "vacaciones": "vacaciones descanso permiso",
    "preaviso": "preaviso",
    "competencia": "competencia",
    "confidencialidad": "confidencialidad",
    "movilidad": "movilidad",
    "contrato": "contrato indefinido temporal",
    "excedencia": "excedencia",
    "convenio": "convenio",
}

# Prefijos que se eliminan al construir la query de normativa: estas
# expresiones son metalenguaje del usuario y solo añaden ruido al BM25.
_PREFIJOS_LEGALES = [
    "es legal", "es ilegal", "cumple la ley", "cumple la normativa",
    "legalidad de", "según la ley", "conforme a",
]

# Verbos comparativos que se eliminan al extraer el tema de la pregunta
# en consultas multi-persona (no aportan información sobre QUÉ buscar).
_PALABRAS_COMPARACION = [
    "compara", "comparar", "comparame", "contrasta",
    "diferencia", "diferencias", "versus",
]


def _coleccion_vacia(coleccion: str) -> bool:
    col = _coleccion_hijos(coleccion)
    return col.count() == 0


def _normalizar(texto: str) -> str:
    """Quita acentos y pasa a minúsculas para comparar nombres.

    Necesario porque el LLM tiende a devolver nombres sin acento ("Lopez")
    mientras que los metadatos del documento conservan los acentos
    ("López"). La comparación directa fallaría sin esta normalización.
    """
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _similitud(s1: str, s2: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, s1, s2).ratio()


def _resolver_nombres(
    personas_parciales: list[str],
    nombres_completos: list[str],
) -> tuple[list[str], dict[str, list[str]]]:
    """Resuelve nombres parciales contra el catálogo de nombres indexados.

    Estrategia en dos pasos:
    1. Coincidencia exacta por palabras (subconjunto de tokens).
       - Si hay una sola coincidencia → resuelto.
       - Si hay varias → ambigüedad (se pide aclaración al usuario).
    2. Fallback fuzzy con SequenceMatcher para tolerar erratas
       ("Anrtonio" → "Antonio"). Solo se activa si la coincidencia exacta
       falla por completo, para evitar matches falsos.

    Devuelve (resueltos, ambiguos) donde ambiguos = {parcial: [candidatos]}.
    """
    resueltos = []
    ambiguos = {}

    for parcial in personas_parciales:
        palabras = _normalizar(parcial).split()

        # Paso 1: match exacto (todas las palabras del parcial aparecen en el completo)
        coincidencias = [
            n for n in nombres_completos if all(p in _normalizar(n) for p in palabras)
        ]

        if len(coincidencias) == 1:
            resueltos.append(coincidencias[0])
            continue
        elif len(coincidencias) > 1:
            # Varias personas con el mismo nombre o subcadena → ambigüedad.
            # Limitamos a 5 candidatos para no abrumar al usuario en la
            # respuesta de desambiguación.
            ambiguos[parcial] = coincidencias[:5]
            continue

        # Paso 2: fuzzy matching. Umbral 0.6 elegido empíricamente: por
        # debajo aparecen falsos positivos (nombres no relacionados).
        mejor_score = 0.0
        mejor_nombre = None
        for nombre_completo in nombres_completos:
            partes_nombre = _normalizar(nombre_completo).split()
            sims = []
            for palabra in palabras:
                mejor_sim = max(
                    (_similitud(palabra, parte) for parte in partes_nombre),
                    default=0.0,
                )
                # Si una palabra del parcial no se parece a ninguna del
                # nombre completo, este candidato queda descartado.
                if mejor_sim < 0.6:
                    break
                sims.append(mejor_sim)
            else:
                # El for-else solo entra si no se rompió por el break:
                # todas las palabras del parcial encontraron un equivalente.
                media = sum(sims) / len(sims)
                if media > mejor_score:
                    mejor_score = media
                    mejor_nombre = nombre_completo

        if mejor_nombre:
            resueltos.append(mejor_nombre)

    return resueltos, ambiguos


def _extraer_personas_del_historial(
    mensajes: list,
    nombres_completos: list[str],
    n_turnos: int = 5,
) -> list[str]:
    """Recupera personas mencionadas en turnos recientes del usuario.

    Mecanismo para resolver consultas como "¿y su salario?" donde la
    persona se introdujo en un turno anterior. Se buscan nombres completos
    cuyas dos primeras palabras (nombre + primer apellido) aparezcan en
    los mensajes de usuario recientes.
    """
    mensajes_usuario = [m for m in mensajes if isinstance(m, HumanMessage)]
    mensajes_recientes = mensajes_usuario[-n_turnos:]
    texto_historial = " ".join(m.content for m in mensajes_recientes)

    personas_encontradas = []
    for nombre_completo in nombres_completos:
        partes = nombre_completo.split()
        if len(partes) >= 2:
            patron = partes[0] + " " + partes[1]
            if _normalizar(patron) in _normalizar(texto_historial):
                personas_encontradas.append(nombre_completo)

    return personas_encontradas


def _query_para_normativa(query: str, personas: list[str]) -> str:
    """Construye una query óptima para buscar en la normativa pública.

    Pasos:
    1. Elimina nombres propios: no aparecen en el Estatuto y solo añaden
       ruido al BM25.
    2. Elimina prefijos meta ("es legal", "según la ley"…).
    3. Expande términos coloquiales con sinónimos del registro jurídico
       ("sueldo" → "salario sueldo retribución paga").
    4. Si no se ha podido enriquecer con sinónimos, añade un fallback
       genérico ("artículo estatuto trabajadores") para sesgar la búsqueda
       hacia documentos legales.
    """
    query_limpia = query.lower()

    for persona in personas:
        query_limpia = query_limpia.replace(persona.lower(), "")

    for prefijo in _PREFIJOS_LEGALES:
        query_limpia = query_limpia.replace(prefijo, "")

    query_limpia = " ".join(query_limpia.split()).strip(" ?¿.,")

    palabras = query_limpia.split()
    conjuntos_sinonimos = set()
    for palabra in palabras:
        if palabra in _SINONIMOS_LEGALES:
            conjuntos_sinonimos.add(_SINONIMOS_LEGALES[palabra])

    if conjuntos_sinonimos:
        sinonimos_combinados = " ".join(conjuntos_sinonimos)
        query_normativa = f"{query_limpia} {sinonimos_combinados}"
    else:
        query_normativa = f"{query_limpia} artículo estatuto trabajadores"

    return query_normativa


def _extraer_tema_de_pregunta(pregunta: str, personas: list[str]) -> str:
    """Extrae el tema (sustantivos) de la pregunta para reusarlo por persona.

    En consultas multi-persona ("compara el salario de A y B") interesa
    saber qué se compara para hacer una búsqueda específica por cada
    persona ("salario A", "salario B"). Esta función elimina nombres,
    verbos de comparación y stopwords típicas del español.

    Si tras filtrar no queda nada (pregunta muy genérica), devuelve
    "contrato" como tema por defecto.
    """
    tema = pregunta.lower()

    # Eliminamos los nombres propios para quedarnos solo con el "qué".
    for persona in personas:
        tema = tema.replace(persona.lower(), "")

    # Verbos de comparación: no son tema, son la operación.
    for palabra in _PALABRAS_COMPARACION:
        tema = tema.replace(palabra, "")

    # Stopwords manuales: preferimos lista cerrada antes que cargar NLTK,
    # ya que solo necesitamos las más frecuentes del español castellano.
    palabras_vacias = {
        "de", "del", "la", "el", "los", "las", "con", "y", "a", "al", "que", "lo",
        "en", "un", "una", "es", "por", "su", "sus", "se", "más", "mas", "mejor",
        "quién", "quien", "tiene", "cuál", "cual", "cuánto", "cuanto",
        "dime", "dame", "muestra", "muéstrame", "indica",
    }
    palabras = tema.split()
    palabras_filtradas = [p.strip("?¿.,") for p in palabras if p.strip("?¿.,") not in palabras_vacias]

    tema_limpio = " ".join(palabras_filtradas).strip()

    if not tema_limpio:
        tema_limpio = "contrato"

    return tema_limpio


def _recuperar_por_persona(
    query: str,
    persona: str,
    coleccion: str,
    k: int = None,
) -> list[dict]:
    """Retrieval para una sola persona con filtro estricto de nombre.

    Pide n*3 candidatos para tener margen tras el filtrado posterior
    (algunos fragmentos pueden no llevar el metadato `nombre_trabajador`
    si el chunker no lo detectó en la primera página).

    Si el pipeline completo (HyDE + BM25) devuelve menos de 2 fragmentos,
    se cae a una búsqueda semántica simple incluyendo el nombre en la
    propia query. Esto cubre casos donde el documento tiene poco texto
    indexable y BM25 no es capaz de encontrar nada relevante.
    """
    n = k or settings.retrieval_k
    filtro = {"nombre_trabajador": persona}

    fragmentos = recuperar(
        query=query, coleccion=coleccion, n_resultados=n * 3,
        usar_hyde=settings.use_hyde, usar_bm25=True, filtro=filtro,
    )
    # Filtrado defensivo por si recuperar() devolviera fragmentos sin
    # metadatos correctos (no debería pasar con el filtro, pero protege
    # contra inconsistencias entre ChromaDB y los manifiestos).
    fragmentos = [
        f for f in fragmentos
        if not f.get("nombre_trabajador") or f["nombre_trabajador"] == persona
    ][:n]

    if len(fragmentos) < 2:
        fallback = recuperar(
            query=f"{query} {persona}", coleccion=coleccion, n_resultados=n,
            usar_hyde=False, usar_bm25=False, filtro=filtro,
        )
        # Deduplicamos por parent_id: dos hijos del mismo padre aportan
        # la misma página, conviene diversificar fuentes.
        parent_ids_existentes = {f.get("parent_id") for f in fragmentos}
        for frag in fallback:
            if frag.get("parent_id") not in parent_ids_existentes:
                fragmentos.append(frag)
                parent_ids_existentes.add(frag.get("parent_id"))
            if len(fragmentos) >= n:
                break

    return fragmentos


def _recuperar_multi_persona(
    pregunta_original: str,
    personas: list[str],
    coleccion: str,
    sub_consultas: list[dict] = None,
) -> list[dict]:
    """Retrieval específico para consultas que comparan varias personas.

    Estrategia: en lugar de lanzar la query global y filtrar luego, se
    hace una búsqueda independiente por persona con su propio filtro de
    metadatos. Esto evita el problema de que una persona "dominara" los
    top-k y la otra quedara fuera del evidence pack.

    Si el nodo de intent generó sub_consultas con una query específica
    por persona, se usan; en caso contrario, se extrae un tema común de
    la pregunta original y se aplica a todas.
    """
    evidence_pack = []
    vistos = set()
    k_por_persona = settings.retrieval_k

    # Mapeo persona_completa → query a ejecutar. Se construye a partir
    # de las sub_consultas que produjo el nodo intent (si existen).
    queries_por_persona = {}
    if sub_consultas:
        for sc in sub_consultas:
            sc_query = sc.get("query", "")
            for p_parcial in sc.get("personas", []):
                for persona_completa in personas:
                    if p_parcial.lower() in persona_completa.lower():
                        queries_por_persona[persona_completa] = sc_query
                        break

    if not queries_por_persona:
        tema = _extraer_tema_de_pregunta(pregunta_original, personas)
        for persona in personas:
            queries_por_persona[persona] = f"{tema} {persona}"

    for persona in personas:
        query_persona = queries_por_persona.get(persona, f"contrato {persona}")
        # El nombre se añade explícitamente a la query: refuerza el sesgo
        # del retriever hacia el documento correcto incluso si el filtro
        # de metadatos fallara por alguna razón.
        if persona.lower() not in query_persona.lower():
            query_persona = f"{query_persona} {persona}"

        filtro = {"nombre_trabajador": persona}
        fragmentos = recuperar(
            query=query_persona, coleccion=coleccion,
            n_resultados=k_por_persona * 2,
            usar_hyde=settings.use_hyde, usar_bm25=True, filtro=filtro,
        )
        fragmentos = [
            f for f in fragmentos
            if not f.get("nombre_trabajador") or f["nombre_trabajador"] == persona
        ][:k_por_persona]

        if not fragmentos:
            fragmentos = recuperar(
                query=query_persona, coleccion=coleccion,
                n_resultados=k_por_persona,
                usar_hyde=False, usar_bm25=False, filtro=filtro,
            )

        # Deduplicación global por parent_id (un mismo padre podría
        # aparecer si varias personas compartieran documento, lo que no
        # debería ocurrir, pero protegemos el caso).
        for frag in fragmentos:
            clave = frag.get("parent_id", "")
            if clave and clave not in vistos:
                vistos.add(clave)
                evidence_pack.append(frag)

    # Reordenamos por puntuación RRF para que los fragmentos más
    # relevantes aparezcan primero, independientemente de qué persona
    # se procesó antes.
    evidence_pack.sort(key=lambda x: x.get("score_rrf", 0), reverse=True)
    return evidence_pack


def _extraer_dni_de_pregunta(texto: str) -> str | None:
    """Extrae un DNI/NIE de la pregunta del usuario si lo menciona."""
    import re
    match = re.search(r'\b([XYZ]?\d{7,8}[A-Za-z])\b', texto)
    return match.group(1).upper() if match else None


def _recuperar_contratos(state: dict, query: str, coleccion: str) -> tuple:
    """Orquesta la búsqueda en la colección de contratos privados.

    Aplica una cadena de estrategias en orden:
    1. Resolución de nombres parciales detectados por el intent.
    2. Si no hay nombres, intenta extraer un DNI de la pregunta.
    3. Si no hay DNI tampoco, busca en el historial reciente.
    4. Si nada de lo anterior funciona, lanza la búsqueda sin filtro.

    Devuelve (evidence, personas_resueltas, es_multi, ambiguos).
    `ambiguos` no está vacío cuando hay varios candidatos para un mismo
    nombre parcial: en ese caso, el nodo termina pidiendo aclaración.
    """
    nombres_completos = obtener_nombres_indexados(coleccion)
    entidades = state.get("entidades", {})
    personas_parciales = entidades.get("personas", [])

    # Las sub_consultas también pueden contener personas: si el intent
    # extrajo a las personas solo allí (no en entidades), las recogemos.
    if not personas_parciales:
        for sc in state.get("sub_consultas", []):
            for p in sc.get("personas", []):
                if p and p not in personas_parciales:
                    personas_parciales.append(p)

    # Identificador alternativo: si el usuario menciona un DNI, lo
    # usamos como filtro exacto (más robusto que el matching de nombres).
    dni_query = _extraer_dni_de_pregunta(state.get("pregunta", ""))

    if personas_parciales:
        personas_resueltas, ambiguos = _resolver_nombres(personas_parciales, nombres_completos)

        # Caso de usuario que preguntó por una sola persona y el corpus
        # tiene varias coincidencias: paramos el flujo y pedimos que
        # aclare a cuál se refiere. Es preferible a responder sobre la
        # persona equivocada.
        if ambiguos and len(personas_parciales) == 1:
            return [], [], False, ambiguos

        # En consultas multi-persona (comparaciones) la ambigüedad se
        # tolera: incluimos todos los candidatos y dejamos que el LLM
        # razone sobre el conjunto. La alternativa sería pedir aclaración
        # múltiple, pero perjudicaría la experiencia.
        if ambiguos:
            for candidatos in ambiguos.values():
                personas_resueltas.extend(candidatos)

        if not personas_resueltas:
            if dni_query:
                evidence = recuperar(
                    query=query,
                    coleccion=coleccion,
                    n_resultados=settings.retrieval_k * 2,
                    usar_hyde=settings.use_hyde,
                    usar_bm25=True,
                    filtro={"dni": dni_query},
                )
                return evidence, [f"DNI {dni_query}"], False, {}
            return [], [], False, {}
    elif dni_query:
        personas_resueltas = []
        evidence = recuperar(
            query=query,
            coleccion=coleccion,
            n_resultados=settings.retrieval_k * 2,
            usar_hyde=settings.use_hyde,
            usar_bm25=True,
            filtro={"dni": dni_query},
        )
        return evidence, [f"DNI {dni_query}"], False, {}
    else:
        personas_resueltas = _extraer_personas_del_historial(
            mensajes=state.get("messages", []),
            nombres_completos=nombres_completos,
        )

    es_multi = len(personas_resueltas) >= 2

    if es_multi:
        evidence = _recuperar_multi_persona(
            pregunta_original=state["pregunta"],
            personas=personas_resueltas,
            coleccion=coleccion,
            sub_consultas=state.get("sub_consultas", []),
        )
    elif personas_resueltas:
        evidence = _recuperar_por_persona(
            query=query,
            persona=personas_resueltas[0],
            coleccion=coleccion,
        )
    else:
        evidence = recuperar(
            query=query,
            coleccion=coleccion,
            usar_hyde=settings.use_hyde,
            filtro=None,
        )

    return evidence, personas_resueltas, es_multi, {}


def nodo_retrieval(state: AgentState) -> dict:
    """Recupera los fragmentos más relevantes para la query.

    Modo documental: una sola búsqueda en la colección privada.
    Modo legal: dos búsquedas (privada + pública) cuyo resultado se
    concatena marcando `origen` para que el nodo de análisis sepa qué
    fragmentos son contractuales y cuáles normativos.
    """
    inicio = time.time()

    modo = state.get("modo", "documental")
    query = state["query_normalizada"]

    if modo == "legal":
        evidence_contrato, personas_resueltas, es_multi, ambiguos = _recuperar_contratos(
            state, query, settings.chroma_collection_private,
        )

        if ambiguos:
            return _respuesta_ambiguedad(state, ambiguos, time.time() - inicio)

        # Etiquetamos cada fragmento con su origen para que el LLM pueda
        # distinguir cláusula contractual de artículo legal al citar.
        for frag in evidence_contrato:
            frag["origen"] = "contrato"

        todas_las_personas = personas_resueltas + state.get("entidades", {}).get("personas", [])
        query_normativa = _query_para_normativa(query, todas_las_personas)

        # Guard: si la colección pública está vacía (instalación sin
        # normativa indexada), avisamos en lugar de fallar silenciosamente.
        coleccion_publica_vacia = _coleccion_vacia(settings.chroma_collection_public)
        if coleccion_publica_vacia:
            evidence_normativa = []
            sin_normativa = True
        else:
            # Sobre la normativa no aplicamos HyDE ni BM25: los documentos
            # legales son pocos y muy estructurados, la búsqueda semántica
            # directa funciona mejor y es más rápida.
            evidence_normativa = recuperar(
                query=query_normativa,
                coleccion=settings.chroma_collection_public,
                n_resultados=settings.k_normativa,
                usar_hyde=False,
                usar_bm25=False,
                filtro=None,
            )
            for frag in evidence_normativa:
                frag["origen"] = "normativa"
            sin_normativa = len(evidence_normativa) == 0

        # Bandera que el nodo response usará para avisar al usuario de
        # que no se pudo contrastar con normativa.
        if sin_normativa:
            for frag in evidence_contrato:
                frag["sin_normativa"] = True

        evidence_pack = evidence_contrato + evidence_normativa

    else:
        evidence_pack, personas_resueltas, es_multi, ambiguos = _recuperar_contratos(
            state, query, settings.chroma_collection_private,
        )

        if ambiguos:
            return _respuesta_ambiguedad(state, ambiguos, time.time() - inicio)

        sin_normativa = False

    # Alertas pre-detectadas por el compliance_checker durante la
    # indexación (salario < SMI, jornada > 40h, periodo de prueba
    # excesivo…). Son determinísticas (basadas en regex y umbrales) y
    # complementan al LLM, que por sí solo no es fiable detectándolas.
    alertas_compliance = []
    if modo == "legal":
        for persona in personas_resueltas:
            alertas_persona = obtener_alertas_por_trabajador(persona)
            for alerta in alertas_persona:
                alerta_con_trab = {**alerta, "trabajador": persona}
                alertas_compliance.append(alerta_con_trab)

    latencia = round(time.time() - inicio, 2)

    traza = list(state.get("traza", []))
    traza.append({
        "nodo": "retrieval",
        "latencia_s": latencia,
        "fragmentos_recuperados": len(evidence_pack),
        "multi_documento": es_multi,
        "personas_filtradas": personas_resueltas,
        "sin_normativa": sin_normativa,
        "alertas_compliance": len(alertas_compliance),
        "modo": modo,
    })

    return {
        "evidence_pack": evidence_pack,
        "alertas_compliance": alertas_compliance,
        "traza": traza,
    }


def _respuesta_ambiguedad(state: dict, ambiguos: dict, latencia: float) -> dict:
    """Genera respuesta de desambiguación cuando hay nombres duplicados."""
    parcial = list(ambiguos.keys())[0]
    candidatos = ambiguos[parcial]

    lineas = [f"He encontrado varias personas con el nombre «{parcial}»:\n"]
    for i, nombre in enumerate(candidatos, 1):
        lineas.append(f"{i}. **{nombre}**")
    lineas.append("\n¿A cuál te refieres? Puedes indicarme el apellido completo o el DNI.")

    texto = "\n".join(lineas)

    traza = list(state.get("traza", []))
    traza.append({
        "nodo": "retrieval",
        "latencia_s": round(latencia, 2),
        "fragmentos_recuperados": 0,
        "desambiguacion": True,
        "candidatos": candidatos,
    })

    return {
        "respuesta": texto,
        "evidence_pack": [],
        "citas": [],
        "no_consta": False,
        "traza": traza,
    }