"""Nodo de respuesta: redacta la respuesta final con citas verificables.

Es el último nodo del grafo. Selecciona el prompt apropiado según el modo
(documental, legal, resumen) y la naturaleza de la consulta (simple,
multi-persona). Limita el número y tamaño de fragmentos para no exceder
el contexto del LLM, y soporta dos rutas de salida:

- Invocación normal: llama al LLM y devuelve texto completo.
- Modo stream: prepara los mensajes y citas pero delega la inferencia al
  endpoint SSE, que va emitiendo tokens al frontend.
"""

import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.core.config import settings
from src.core.state import AgentState
from src.core.prompts.response import (
    SYSTEM_DOCUMENTAL,
    HUMAN_DOCUMENTAL,
    SYSTEM_LEGAL,
    HUMAN_LEGAL,
    SYSTEM_RESUMEN,
    HUMAN_RESUMEN,
    SYSTEM_EXTRACCION_INDIVIDUAL,
    HUMAN_EXTRACCION_INDIVIDUAL,
    SYSTEM_COMPARACION,
    HUMAN_COMPARACION,
    ALERTAS_LEGAL_RESPONSE_TPL,
)


def _formatear_alertas(alertas: list[dict]) -> str:
    """Formatea las alertas del compliance_checker para el prompt legal."""
    if not alertas:
        return ""
    lineas = []
    for a in alertas:
        trab = a.get("trabajador", "")
        articulo = a.get("articulo", "")
        mensaje = a.get("mensaje", "")
        prefijo = f"- [{trab}] " if trab else "- "
        lineas.append(f"{prefijo}{articulo}: {mensaje}")
    return ALERTAS_LEGAL_RESPONSE_TPL.format(lineas="\n".join(lineas))

# Umbral mínimo de puntuación RRF para considerar un fragmento útil.
# Por debajo, asumimos que el retrieval no encontró nada relevante.
UMBRAL_RELEVANCIA = 0.01

# Límites de fragmentos según el tipo de consulta. Calibrados para que
# el contexto del LLM no se sature: con qwen3:14b-nothink y fragmentos
# de hasta 2500 caracteres, 4-7 fragmentos caben holgadamente.
MAX_FRAGMENTOS_SIMPLE = 4            # Búsqueda simple, una persona
MAX_FRAGMENTOS_POR_PERSONA = 2       # Cota por persona en multi-persona
MAX_FRAGMENTOS_LEGAL = 7             # Legal: necesita más contexto (contrato + normativa)
MAX_FRAGMENTOS_RESUMEN = 5           # Resumen: barrido más amplio
MAX_CHARS_POR_FRAGMENTO = 2500       # Páginas de contrato (padres) llegan a 2-3 kc
MAX_CHARS_POR_FRAGMENTO_NORMATIVA = 1000  # Artículos legales son más cortos

_RESPUESTA_SIN_NORMATIVA = (
    "No se dispone de normativa laboral indexada para responder a esta pregunta con rigor. "
    "Para consultar sobre legalidad o cumplimiento normativo, se recomienda consultar "
    "el Estatuto de los Trabajadores en el BOE (boe.es) o contactar con un asesor laboral. "
    "Esta respuesta no constituye asesoramiento jurídico."
)

_RESPUESTA_VACIA = (
    "No he podido generar una respuesta para esta consulta. "
    "Intenta reformular la pregunta indicando el nombre del trabajador "
    "y el aspecto concreto que deseas consultar."
)


def _limpiar_texto_padre(texto: str) -> str:
    """Limpia el texto de contratos SEPE antes de pasarlo al LLM.

    Los formularios SEPE traen mucho boilerplate (cabeceras del
    ministerio, footnotes numeradas, checkboxes de opciones mutuamente
    excluyentes…) que ocupa contexto sin aportar información. Esta
    función aplica regex para eliminar todo eso y dejar solo la cláusula
    útil para responder a la pregunta.
    """
    import re

    # Footnotes (1)–(18): se eliminan tanto las líneas que las inician
    # como las continuaciones hasta encontrar una nueva cláusula.
    lineas = texto.split("\n")
    lineas_limpias = []
    en_footnote = False

    for linea in lineas:
        stripped = linea.strip()

        if re.match(r'^\(\d{1,2}\)\s+\S', stripped):
            en_footnote = False
            continue
        if re.match(r'^\(\d{1,2}\)\s*$', stripped):
            en_footnote = True
            continue
        if en_footnote:
            # Una cabecera de cláusula o sección rompe la footnote.
            if re.match(r'^(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|SÉPTIMA|SEPTIMA|OCTAVA|NOVENA|DÉCIMA|DECIMA|UNDÉCIMA|Cofinanciado|MINISTERIO|SERVICIO|DATOS)', stripped):
                en_footnote = False
                lineas_limpias.append(linea)
                continue
            continue
        lineas_limpias.append(linea)

    texto = "\n".join(lineas_limpias)

    # Checkboxes mutuamente excluyentes: si está marcada "A tiempo
    # parcial", la opción "A tiempo completo" sobra (y viceversa).
    if re.search(r'X\s+A tiempo parcial', texto):
        texto = re.sub(r'A tiempo completo:[^\n]*\n(?:[^\n]*convencionalmente[^\n]*\n)?', '', texto)
        texto = re.sub(r',\s+X?\s+a la semana,\s+al mes,\s+al año', '', texto)
    elif re.search(r'X\s+A tiempo completo', texto):
        texto = re.sub(r'A tiempo parcial:[^\n]*(?:horas al día[^\n]*)?(?:\n|$)', '', texto)

    # Referencias inline tipo "salario(3)" que apuntan a footnotes ya eliminadas.
    texto = re.sub(r'\s*\(\d{1,2}\)(?=[\s,.\n]|$)', '', texto)

    # Cabeceras institucionales del formulario.
    texto = re.sub(r'\*\* COPIA BASICA \*\*\s*', '', texto)
    texto = re.sub(
        r'Cofinanciado por\s*\nla Unión Europea\s*\n'
        r'MINISTERIO\s*\nDE TRABAJO\s*\nY ECONOMÍA SOCIAL\s*\n'
        r'SERVICIO PÚBLICO\s*\nDE EMPLEO ESTATAL\s*\nSEPE\s*\n'
        r'(?:Fondos Europeos\s*\n)?',
        '', texto,
    )
    texto = re.sub(r'FSE\+\s+Fondo Social Europeo Plus\s*', '', texto)

    # Cláusulas 8ª–11ª de los contratos SEPE: contienen remisiones
    # legales estándar (jurisdicción, registro…) que no aportan datos
    # sobre las condiciones del trabajador concreto.
    texto = re.sub(r'OCTAVA:.*?(?=\n[A-Z]{2,}|\Z)', '', texto, flags=re.DOTALL)
    texto = re.sub(r'NOVENA:.*?(?=\n[A-Z]{2,}|\Z)', '', texto, flags=re.DOTALL)
    texto = re.sub(r'D[ÉE]CIMA:.*?(?=\n[A-Z]{2,}|\Z)', '', texto, flags=re.DOTALL)
    texto = re.sub(r'UND[ÉE]CIMA:.*?(?=\n|\Z)', '', texto, flags=re.DOTALL)

    # Tras los borrados pueden quedar bloques de líneas en blanco que
    # enrarecen la lectura del LLM; los colapsamos a un único par.
    texto = re.sub(r'\n\s*\n(\s*\n)+', '\n\n', texto)

    return texto.strip()


def _formatear_fragmentos(evidence_pack: list[dict]) -> str:
    """Serializa el evidence_pack al formato que espera el prompt del LLM.

    Cada fragmento se etiqueta como [CONTRATO] o [NORMATIVA] e incluye
    el nombre del trabajador (o del documento legal) y la página, para
    que el LLM pueda citar en formato [Contrato de: X, Pág: N].

    Se aplica truncado por longitud con preferencia por cortar en un
    punto o salto de línea (evita partir una frase a medias).
    """
    if not evidence_pack:
        return "Sin fragmentos disponibles."
    partes = []
    for i, frag in enumerate(evidence_pack):
        origen = frag.get("origen", "contrato")
        pagina = frag.get("pagina", "?")
        texto = frag.get("texto", "")

        # Solo se limpia el boilerplate en contratos: los textos legales
        # vienen ya en formato compacto y no llevan footnotes SEPE.
        if origen != "normativa":
            texto = _limpiar_texto_padre(texto)

        if origen == "normativa":
            max_chars = MAX_CHARS_POR_FRAGMENTO_NORMATIVA
            doc_nombre = frag.get("doc_nombre", "Normativa")
            cabecera = f"[NORMATIVA] {doc_nombre} | Pág: {pagina}"
        else:
            max_chars = MAX_CHARS_POR_FRAGMENTO
            nombre = frag.get("nombre_trabajador") or "No identificado"
            cabecera = f"[CONTRATO] Contrato de: {nombre} | Pág: {pagina}"

        # Truncado "inteligente": si excede el tamaño máximo, cortamos
        # en el último punto o salto de línea dentro del límite, siempre
        # que esté en la segunda mitad (si está antes, el corte queda
        # demasiado pronto y se pierde contexto).
        if len(texto) > max_chars:
            truncado = texto[:max_chars]
            ultimo_punto = truncado.rfind(".")
            ultimo_salto = truncado.rfind("\n")
            corte = max(ultimo_punto, ultimo_salto)
            if corte > max_chars // 2:
                texto = truncado[:corte + 1]
            else:
                texto = truncado
            texto += "\n[...fragmento truncado...]"

        partes.append(f"[{i+1}] {cabecera}\n{texto}")

    return "\n\n".join(partes)


def _formatear_analisis(campos, observaciones: list) -> str:
    """Serializa el resultado del nodo Analysis para el prompt.

    Soporta dos formatos según el modo:
    - dict (modo documental/resumen): pares campo → valor extraído.
    - list[dict] (modo legal): puntos comparativos con la estructura
      {aspecto, contrato, normativa, valoración}.
    """
    if not campos and not observaciones:
        return "Sin análisis disponible."

    partes = []

    if isinstance(campos, dict):
        partes = [f"- {k}: {v}" for k, v in campos.items()]
    elif isinstance(campos, list):
        for punto in campos:
            if isinstance(punto, dict):
                aspecto = punto.get("aspecto", "Sin especificar")
                contrato = punto.get("contrato", "No consta")
                normativa = punto.get("normativa", "Sin normativa indexada")
                valoracion = punto.get("valoracion", "Sin valoración")
                partes.append(
                    f"- {aspecto}:\n"
                    f"    Contrato: {contrato}\n"
                    f"    Normativa: {normativa}\n"
                    f"    Valoración: {valoracion}"
                )

    if observaciones:
        partes.append("\nObservaciones:")
        partes.extend(f"  · {o}" for o in observaciones)

    return "\n".join(partes)


def _extraer_citas(evidence_pack: list[dict]) -> list[dict]:
    """Extrae la lista de citas únicas (trabajador/normativa + página).

    Las citas aparecen en el frontend como referencias clicables debajo
    de la respuesta. Se deduplica por (nombre, página) para no mostrar
    la misma referencia dos veces si dos fragmentos hijos provienen del
    mismo padre.
    """
    vistas = set()
    citas = []
    for frag in evidence_pack:
        origen = frag.get("origen", "contrato")
        pagina = frag.get("pagina", 0)

        if origen == "normativa":
            doc_nombre = frag.get("doc_nombre", "Normativa")
            clave = (f"normativa:{doc_nombre}", pagina)
            if clave not in vistas:
                vistas.add(clave)
                citas.append({
                    "nombre_trabajador": doc_nombre,
                    "pagina": pagina,
                    "score": round(frag.get("score_rrf", 0), 4),
                    "origen": "normativa",
                })
        else:
            nombre = frag.get("nombre_trabajador", "")
            if not nombre:
                continue
            clave = (nombre, pagina)
            if clave not in vistas:
                vistas.add(clave)
                citas.append({
                    "nombre_trabajador": nombre,
                    "pagina": pagina,
                    "score": round(frag.get("score_rrf", 0), 4),
                    "origen": "contrato",
                })

    return citas


def _seleccion_round_robin(fragmentos: list[dict], max_total: int) -> list[dict]:
    """Distribuye los fragmentos equitativamente entre personas.

    En consultas multi-persona ordenadas por score, sin esta función
    podría darse el caso de que el top-k quedara monopolizado por una
    sola persona (su contrato tiene más matches). Round-robin garantiza
    que cada persona aporta al menos un fragmento antes de añadir el
    segundo de otra.
    """
    from collections import defaultdict

    por_persona = defaultdict(list)
    sin_persona = []
    for frag in fragmentos:
        nombre = frag.get("nombre_trabajador", "")
        if nombre:
            por_persona[nombre].append(frag)
        else:
            sin_persona.append(frag)

    # Si solo hay una persona (o ninguna identificada), no hay que
    # balancear nada: devolvemos el orden original por score.
    if len(por_persona) <= 1:
        return fragmentos[:max_total]

    seleccionados = []
    personas = list(por_persona.keys())
    idx_por_persona = {p: 0 for p in personas}

    # Ronda a ronda: cogemos un fragmento de cada persona hasta llenar
    # max_total. Si alguna persona se queda sin fragmentos, la ronda
    # siguiente la salta sin bloquear al resto.
    while len(seleccionados) < max_total:
        añadido = False
        for persona in personas:
            if idx_por_persona[persona] < len(por_persona[persona]):
                seleccionados.append(por_persona[persona][idx_por_persona[persona]])
                idx_por_persona[persona] += 1
                añadido = True
                if len(seleccionados) >= max_total:
                    break
        if not añadido:
            break

    # Los fragmentos sin persona identificada se añaden al final, sin
    # entrar en el balanceo (suelen ser normativa o anexos genéricos).
    for frag in sin_persona:
        if len(seleccionados) >= max_total:
            break
        seleccionados.append(frag)

    return seleccionados


def _es_multi_documento(traza: list[dict]) -> bool:
    """Detecta si el retrieval fue multi-documento."""
    for t in traza:
        if t.get("nodo") == "retrieval" and t.get("multi_documento"):
            return True
    return False


def _es_modo_legal(traza: list[dict]) -> bool:
    """Detecta si el retrieval fue en modo legal."""
    for t in traza:
        if t.get("nodo") == "retrieval" and t.get("modo") == "legal":
            return True
    return False


def _extraer_datos_por_persona(
    pregunta: str,
    fragmentos_validos: list[dict],
) -> tuple[dict, list[dict]]:
    """Lanza una llamada al LLM por persona y devuelve los datos extraídos.

    Estrategia "divide y vencerás" para comparaciones: en lugar de
    pedirle al modelo que compare a dos personas en una sola llamada
    (lo que provoca confusiones entre fragmentos), se le pide a cada
    persona por separado el dato concreto y luego se combina en un
    segundo prompt de comparación.
    """
    from collections import defaultdict
    from src.core.llm import get_llm

    llm = get_llm()

    por_persona = defaultdict(list)
    for frag in fragmentos_validos:
        nombre = frag.get("nombre_trabajador", "")
        if nombre:
            por_persona[nombre].append(frag)

    if len(por_persona) < 2:
        return {}, []

    resultados = {}
    fragmentos_usados = []

    for persona, frags in por_persona.items():
        frags_sel = frags[:MAX_FRAGMENTOS_SIMPLE]
        fragmentos_usados.extend(frags_sel)
        texto = _formatear_fragmentos(frags_sel)

        mensajes = [
            SystemMessage(content=SYSTEM_EXTRACCION_INDIVIDUAL),
            HumanMessage(content=HUMAN_EXTRACCION_INDIVIDUAL.format(
                pregunta=pregunta, fragmentos=texto,
            )),
        ]

        resp = llm.invoke(mensajes)
        resultado = resp.content.strip()
        # Limpieza defensiva de los bloques <think> que pueden aparecer con modelos
        # en modo razonamiento; conservamos solo el contenido posterior al cierre.
        if "</think>" in resultado:
            resultado = resultado.split("</think>", 1)[-1].strip()

        resultados[persona] = resultado

    return resultados, fragmentos_usados


def nodo_response(state: AgentState) -> dict:
    """Genera la respuesta final seleccionando el prompt según el modo.

    Decisiones clave:
    - Filtra fragmentos por umbral absoluto y relativo (30% del top
      score) para no incluir ruido.
    - En multi-persona documental usa la estrategia "divide y vencerás".
    - En modo legal sin normativa indexada, devuelve mensaje informativo
      sin llamar al LLM (evita alucinaciones).
    - Si stream_mode está activo, prepara los mensajes y devuelve sin
      invocar el LLM: el endpoint SSE lo hace en streaming.
    """
    inicio = time.time()

    evidence_pack = state.get("evidence_pack", [])
    modo = state.get("modo", "documental")

    traza = list(state.get("traza", []))

    # Guard: el retriever marca los fragmentos con sin_normativa=True
    # cuando la colección pública está vacía y el modo es legal. En ese
    # caso, mejor avisar que generar una respuesta sin base normativa.
    sin_normativa = any(f.get("sin_normativa") for f in evidence_pack)
    if modo == "legal" and sin_normativa:
        latencia = round(time.time() - inicio, 2)
        traza.append({"nodo": "response", "latencia_s": latencia, "no_consta": True, "sin_normativa": True})
        return {
            "respuesta": _RESPUESTA_SIN_NORMATIVA,
            "citas": [],
            "no_consta": True,
            "traza": traza,
            "messages": [
                HumanMessage(content=state["pregunta"]),
                AIMessage(content=_RESPUESTA_SIN_NORMATIVA),
            ],
        }

    # Filtrado en dos pasos:
    # 1. Umbral absoluto: descartar lo claramente irrelevante.
    # 2. Umbral relativo (30% del top): elimina la "cola larga" de
    #    fragmentos que solo aportan ruido aunque pasen el umbral 1.
    fragmentos_validos = [
        f for f in evidence_pack
        if f.get("score_rrf", 0) >= UMBRAL_RELEVANCIA
    ]
    if fragmentos_validos:
        top_score = max(f.get("score_rrf", 0) for f in fragmentos_validos)
        umbral_relativo = top_score * 0.3
        fragmentos_validos = [
            f for f in fragmentos_validos
            if f.get("score_rrf", 0) >= umbral_relativo
        ]

    if not fragmentos_validos:
        respuesta = (
            "No consta en los documentos consultados. "
            "Para responder a esta pregunta sería necesario disponer de "
            "documentación específica sobre el tema consultado."
        )
        latencia = round(time.time() - inicio, 2)
        traza.append({"nodo": "response", "latencia_s": latencia, "no_consta": True})
        return {
            "respuesta": respuesta,
            "citas": [],
            "no_consta": True,
            "traza": traza,
            "messages": [
                HumanMessage(content=state["pregunta"]),
                AIMessage(content=respuesta),
            ],
        }

    intent = state.get("intent", "buscar")
    es_multi = _es_multi_documento(traza)
    es_legal = _es_modo_legal(traza)

    # Si el intent normalizó la query (correcciones, sinónimos…) la
    # usamos en el prompt; si no, la pregunta original del usuario.
    pregunta_para_llm = state.get("query_normalizada") or state["pregunta"]

    # Estrategia divide-y-vencerás para comparaciones documentales:
    # primero extraer dato de cada persona, luego combinar en un prompt
    # de comparación. Solo aplica si NO estamos en modo legal (que tiene
    # su propio flujo con análisis estructurado) ni en intent resumir.
    if es_multi and not es_legal and intent != "resumir":
        resultados_persona, fragmentos_usados = _extraer_datos_por_persona(
            pregunta_para_llm, fragmentos_validos,
        )

        if len(resultados_persona) >= 2:
            citas = _extraer_citas(fragmentos_usados)
            datos = "\n".join(
                f"- **{p}**: {r}" for p, r in resultados_persona.items()
            )

            mensajes_comp = [
                SystemMessage(content=SYSTEM_COMPARACION),
                HumanMessage(content=HUMAN_COMPARACION.format(
                    pregunta=pregunta_para_llm, datos=datos,
                )),
            ]

            if state.get("stream_mode"):
                latencia = round(time.time() - inicio, 2)
                traza.append({"nodo": "response", "latencia_s": latencia, "comparacion_separada": True})
                return {
                    "prompt_messages": mensajes_comp,
                    "citas_preparadas": citas,
                    "citas": citas,
                    "traza": traza,
                }

            from src.core.llm import get_llm
            llm = get_llm()
            resp_comp = llm.invoke(mensajes_comp)
            respuesta = resp_comp.content.strip()
            if "</think>" in respuesta:
                respuesta = respuesta.split("</think>", 1)[-1].strip()
            if not respuesta:
                respuesta = _RESPUESTA_VACIA

            latencia = round(time.time() - inicio, 2)
            traza.append({"nodo": "response", "latencia_s": latencia, "comparacion_separada": True})
            return {
                "respuesta": respuesta,
                "citas": citas,
                "no_consta": False,
                "traza": traza,
                "messages": [
                    HumanMessage(content=state["pregunta"]),
                    AIMessage(content=respuesta),
                ],
            }

    # Flujo estándar: una sola llamada al LLM con todos los fragmentos.
    # El número máximo se calibra según el tipo de consulta para no
    # exceder el contexto del modelo.
    if es_legal:
        max_frag = MAX_FRAGMENTOS_LEGAL
    elif intent == "resumir":
        max_frag = MAX_FRAGMENTOS_RESUMEN
    elif es_multi:
        # En multi-persona se reserva una cuota por persona.
        n_personas = len({f.get("nombre_trabajador") for f in fragmentos_validos if f.get("nombre_trabajador")})
        max_frag = max(4, n_personas * MAX_FRAGMENTOS_POR_PERSONA)
    else:
        max_frag = MAX_FRAGMENTOS_SIMPLE

    if es_multi:
        fragmentos_para_llm = _seleccion_round_robin(fragmentos_validos, max_frag)
    else:
        fragmentos_para_llm = fragmentos_validos[:max_frag]

    fragmentos_texto = _formatear_fragmentos(fragmentos_para_llm)
    analisis_texto = _formatear_analisis(
        state.get("campos_extraidos", {}),
        state.get("observaciones", []),
    )

    if modo == "legal":
        system_prompt = SYSTEM_LEGAL
        alertas_bloque = _formatear_alertas(state.get("alertas_compliance", []))
        human_prompt = HUMAN_LEGAL.format(
            pregunta=pregunta_para_llm,
            fragmentos=fragmentos_texto,
            analisis=analisis_texto,
            alertas_bloque=alertas_bloque,
        )
    elif intent == "resumir":
        system_prompt = SYSTEM_RESUMEN
        human_prompt = HUMAN_RESUMEN.format(
            pregunta=pregunta_para_llm,
            fragmentos=fragmentos_texto,
            analisis=analisis_texto,
        )
    else:
        system_prompt = SYSTEM_DOCUMENTAL
        human_prompt = HUMAN_DOCUMENTAL.format(
            pregunta=pregunta_para_llm,
            fragmentos=fragmentos_texto,
            analisis=analisis_texto,
        )

    mensajes_llm = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]

    if state.get("stream_mode"):
        citas = _extraer_citas(fragmentos_para_llm)
        latencia = round(time.time() - inicio, 2)
        traza.append({"nodo": "response", "latencia_s": latencia})
        return {
            "prompt_messages": mensajes_llm,
            "citas_preparadas": citas,
            "citas": citas,
            "traza": traza,
        }

    from src.core.llm import get_llm
    llm = get_llm()

    respuesta_llm = llm.invoke(mensajes_llm)
    respuesta = respuesta_llm.content.strip()

    if "</think>" in respuesta:
        respuesta = respuesta.split("</think>", 1)[-1].strip()

    if not respuesta:
        respuesta = _RESPUESTA_VACIA

    # Detección post-hoc de respuestas vacías: el LLM puede contestar
    # "no consta" aun habiendo recibido fragmentos válidos. Marcamos la
    # respuesta para que el frontend pueda mostrarla con un estilo
    # diferente. Requisitos para considerarla "no consta":
    # - No menciona campos típicos del contrato.
    # - Respuesta corta (< 300 chars).
    # - Contiene alguna frase canónica de no-consta.
    _frases_no_consta = ["no consta", "no se dispone", "no he encontrado", "no aparece en"]
    _frases_info_util = ["conclusi", "indefinido", "temporal", "prácticas", "el contrato es", "fecha de inicio"]
    resp_lower = respuesta.lower().strip()
    tiene_info_util = any(f in resp_lower for f in _frases_info_util)
    llm_dice_no_consta = (
        not tiene_info_util
        and len(respuesta) < 300
        and any(f in resp_lower for f in _frases_no_consta)
    )

    citas = _extraer_citas(fragmentos_para_llm)

    latencia = round(time.time() - inicio, 2)
    traza.append({"nodo": "response", "latencia_s": latencia, "no_consta": llm_dice_no_consta})

    return {
        "respuesta": respuesta,
        "citas": citas,
        "no_consta": llm_dice_no_consta,
        "traza": traza,
        "messages": [
            HumanMessage(content=state["pregunta"]),
            AIMessage(content=respuesta),
        ],
    }