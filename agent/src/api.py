"""API REST del agente documental.

Servidor FastAPI que expone los endpoints consumidos por el frontend:
chat (síncrono y por streaming SSE), gestión de sesiones, alta y baja
de documentos, descarga de informes y autenticación JWT. La lógica de
negocio vive en el grafo (`src.core.graph.grafo`); este módulo se
ocupa solo del transporte HTTP, la autorización y la serialización.

Para arrancar el servidor en desarrollo:
    uv run uvicorn src.api:app --reload --port 8080
"""

import hashlib
import json
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from src.core.config import settings
from src.core.graph import grafo
from src.core.rag.index_manifest import (
    listar,
    listar_consultas,
    registrar_consulta,
    guardar_turno,
    cargar_historial,
    listar_sesiones,
    renombrar_sesion,
    limpiar_sesion,
    obtener_owner_sesion,
    obtener_estadisticas_contratos,
)
from src.core.rag.loader import FORMATOS_SOPORTADOS
from src.core.rag.chunker import chunkear
from src.core.rag.embedder import embeber_chunks
from src.core.rag.store import guardar_chunks, borrar_chunks_documento
from src.core.rag import index_manifest
from src.core.auth import (
    crear_usuario,
    autenticar_usuario,
    crear_token,
    obtener_usuario_actual,
    requerir_usuario,
    requerir_admin,
)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

log = logging.getLogger("docuasist")

app = FastAPI(
    title="DocuAsist API",
    description="API del asistente documental corporativo basado en RAG.",
    version="0.3.0",
)


@app.on_event("startup")
async def startup_prewarm():
    """Pre-carga el modelo de embeddings al arrancar.

    Sin esto, la primera consulta del usuario pagaría la inicialización
    del cliente HTTP de Ollama (varios cientos de ms). La pre-carga al
    boot mueve ese coste fuera del camino crítico.
    """
    try:
        from src.core.rag.embedder import embeber_texto
        embeber_texto("test de precarga")
        log.info("Pre-warm embeddings: OK")
    except Exception as e:
        log.warning("Pre-warm embeddings falló: %s", e)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class ChatRequest(BaseModel):
    pregunta: str
    user_id: str = "anonimo"
    session_id: str = "default"


class ChatResponse(BaseModel):
    respuesta: str
    citas: list
    no_consta: bool
    traza: list
    consulta_id: int = 0


class RenombrarRequest(BaseModel):
    titulo: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


def _verificar_ownership(session_id: str, user: dict | None):
    """Garantiza que solo el dueño de una sesión puede operarla.

    Sesiones huérfanas (sin owner registrado) se consideran nuevas y
    se permiten para cubrir el caso de la primera consulta antes de
    persistirse el manifest. En cualquier otro caso, falta de auth o
    auth con usuario distinto del owner cortan el flujo.
    """
    owner = obtener_owner_sesion(session_id)
    if owner:
        if not user:
            raise HTTPException(status_code=401, detail="Autenticación requerida.")
        if owner != user["username"]:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta sesión.")


def _reconstruir_mensajes(historial: list[dict]) -> list:
    """Convierte el historial SQLite a objetos LangChain."""
    mensajes = []
    for msg in historial:
        if msg["role"] == "user":
            mensajes.append(HumanMessage(content=msg["content"]))
        else:
            mensajes.append(AIMessage(content=msg["content"]))
    return mensajes


@app.get("/health", summary="Comprueba el estado del sistema")
def health():
    """Devuelve el estado de los servicios externos (ChromaDB y Ollama).

    Usado por el docker-compose para healthchecks y por el frontend
    para detectar errores de conectividad antes de mostrar la UI.
    """
    import chromadb
    from langchain_ollama import OllamaEmbeddings

    estado = {"api": "ok", "chromadb": "error", "ollama": "error"}

    try:
        cliente = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        cliente.heartbeat()
        estado["chromadb"] = "ok"
    except Exception as e:
        log.warning("Health check ChromaDB falló: %s", e)

    try:
        emb = OllamaEmbeddings(model=settings.embed_model, base_url=settings.ollama_base_url)
        emb.embed_query("test")
        estado["ollama"] = "ok"
    except Exception as e:
        log.warning("Health check Ollama falló: %s", e)

    return estado


@app.post("/chat", response_model=ChatResponse, summary="Envía una pregunta al agente")
def chat(req: ChatRequest, user: dict | None = Depends(obtener_usuario_actual)):
    """Endpoint síncrono del chat: ejecuta el grafo y devuelve respuesta completa.

    Usado por integraciones que prefieren una sola request HTTP en
    lugar del streaming. El frontend principal usa /chat/stream para
    feedback inmediato al usuario.
    """
    user_id = user["username"] if user else req.user_id
    # Cargamos el historial desde SQLite y lo reconvertimos a objetos
    # LangChain: el grafo espera HumanMessage/AIMessage en state.messages.
    historial_db = cargar_historial(req.session_id)
    mensajes = _reconstruir_mensajes(historial_db)

    estado_entrada = {
        "user_id": user_id,
        "session_id": req.session_id,
        "pregunta": req.pregunta,
        "messages": mensajes,
        "traza": [],
    }

    try:
        resultado = grafo.invoke(estado_entrada)
    except Exception as e:
        import logging
        logging.getLogger("docuasist").error("Error en pipeline: %s", e)
        raise HTTPException(status_code=502, detail="El servicio de procesamiento no está disponible. Inténtalo de nuevo.")

    respuesta = resultado.get("respuesta", resultado.get("pregunta_aclaracion", ""))
    citas = resultado.get("citas", [])
    no_consta = resultado.get("no_consta", False)
    traza = resultado.get("traza", [])
    evidence_pack = resultado.get("evidence_pack", [])

    guardar_turno(
        session_id=req.session_id,
        user_id=user_id,
        pregunta=req.pregunta,
        respuesta=respuesta,
    )

    consulta_id = registrar_consulta(
        user_id=user_id,
        session_id=req.session_id,
        pregunta=req.pregunta,
        respuesta=respuesta,
        intent=resultado.get("intent", ""),
        modo=resultado.get("modo", ""),
        no_consta=no_consta,
        num_fragmentos=len(evidence_pack),
        traza=traza,
    )

    return ChatResponse(
        respuesta=respuesta,
        citas=citas,
        no_consta=no_consta,
        traza=traza,
        consulta_id=consulta_id,
    )


_NOMBRES_FASES = {
    "intent": "Clasificando consulta",
    "retrieval": "Buscando en documentos",
    "analysis": "Analizando información",
    "response": "Generando respuesta",
    "temporal": "Consultando fechas",
    "estadistica": "Calculando estadísticas",
}


@app.post("/chat/stream", summary="Chat con streaming SSE")
def chat_stream(req: ChatRequest, user: dict | None = Depends(obtener_usuario_actual)):
    """Streaming Server-Sent Events del chat.

    Emite tres tipos de eventos al cliente:
    - `fase`: progreso por nodo del grafo (intent → retrieval → …).
    - `token`: tokens generados por el LLM en tiempo real.
    - `done`: payload final con respuesta completa, citas y traza.

    Esto da feedback inmediato al usuario (ve la pregunta avanzando por
    el pipeline y la respuesta escribiéndose token a token) en lugar de
    quedarse esperando una respuesta única tras varios segundos.
    """
    user_id = user["username"] if user else req.user_id

    def generar_eventos():
        historial_db = cargar_historial(req.session_id)
        mensajes = _reconstruir_mensajes(historial_db)

        estado_entrada = {
            "user_id": user_id,
            "session_id": req.session_id,
            "pregunta": req.pregunta,
            "messages": mensajes,
            "traza": [],
            "stream_mode": True,
        }

        resultado_final = {}

        try:
            for evento in grafo.stream(estado_entrada):
                for nodo, estado in evento.items():
                    resultado_final.update(estado)
                    fase = _NOMBRES_FASES.get(nodo, nodo)
                    traza_nodo = None
                    for t in estado.get("traza", []):
                        if t.get("nodo") == nodo:
                            traza_nodo = t
                            break
                    data = {"fase": fase, "nodo": nodo}
                    if traza_nodo:
                        data["latencia_s"] = traza_nodo.get("latencia_s", 0)
                    yield f"event: fase\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:
            import logging
            logging.getLogger("docuasist").error("Error en pipeline stream: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': 'Error procesando la consulta'}, ensure_ascii=False)}\n\n"
            return

        prompt_messages = resultado_final.get("prompt_messages")
        if prompt_messages:
            from src.core.llm import get_llm
            import time as _time

            llm = get_llm()
            inicio_llm = _time.time()
            respuesta_completa = []

            # Buffer para los bloques <think> de los modelos de
            # razonamiento: si el LLM empieza con "<think>", lo
            # acumulamos sin emitir hasta encontrar el cierre. Si los
            # primeros 10 caracteres no son think, asumimos que no hay
            # bloque y emitimos lo acumulado de golpe.
            think_buffer = True
            for chunk in llm.stream(prompt_messages):
                token = chunk.content
                if token:
                    if think_buffer:
                        respuesta_completa.append(token)
                        texto_parcial = "".join(respuesta_completa)
                        if "</think>" in texto_parcial:
                            limpio = texto_parcial.split("</think>", 1)[-1]
                            respuesta_completa = [limpio]
                            if limpio.strip():
                                yield f"event: token\ndata: {json.dumps({'token': limpio.strip()}, ensure_ascii=False)}\n\n"
                            think_buffer = False
                        elif len(texto_parcial) >= 10 and "<think" not in texto_parcial:
                            think_buffer = False
                            for t in respuesta_completa:
                                yield f"event: token\ndata: {json.dumps({'token': t}, ensure_ascii=False)}\n\n"
                    else:
                        respuesta_completa.append(token)
                        yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            respuesta = "".join(respuesta_completa).strip()
            if "</think>" in respuesta:
                respuesta = respuesta.split("</think>", 1)[-1].strip()
            latencia_llm = round(_time.time() - inicio_llm, 2)

            traza = resultado_final.get("traza", [])
            for t in traza:
                if t.get("nodo") == "response":
                    t["latencia_s"] = latencia_llm
                    break

            _frases_no_consta = ["no consta", "no se dispone", "no he encontrado", "no aparece en"]
            _frases_info_util = ["conclusi", "indefinido", "temporal", "prácticas", "el contrato es", "fecha de inicio"]
            resp_lower = respuesta.lower().strip()
            tiene_info_util = any(f in resp_lower for f in _frases_info_util)
            no_consta = (
                not tiene_info_util
                and len(respuesta) < 300
                and any(f in resp_lower for f in _frases_no_consta)
            )

            citas = resultado_final.get("citas_preparadas", resultado_final.get("citas", []))
        else:
            respuesta = resultado_final.get("respuesta", resultado_final.get("pregunta_aclaracion", ""))
            citas = resultado_final.get("citas", [])
            no_consta = resultado_final.get("no_consta", False)
            traza = resultado_final.get("traza", [])

        evidence_pack = resultado_final.get("evidence_pack", [])

        guardar_turno(req.session_id, user_id, req.pregunta, respuesta)
        consulta_id = registrar_consulta(
            user_id=user_id, session_id=req.session_id,
            pregunta=req.pregunta, respuesta=respuesta,
            intent=resultado_final.get("intent", ""),
            modo=resultado_final.get("modo", ""),
            no_consta=no_consta, num_fragmentos=len(evidence_pack),
            traza=traza,
        )

        resultado = {
            "respuesta": respuesta,
            "citas": citas,
            "no_consta": no_consta,
            "traza": traza,
            "consulta_id": consulta_id,
        }
        yield f"event: done\ndata: {json.dumps(resultado, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generar_eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions", summary="Lista las sesiones conversacionales")
def listar_sesiones_endpoint(
    user_id: str = Query(default=None),
    limite: int = Query(default=30, le=100),
    user: dict | None = Depends(obtener_usuario_actual),
):
    uid = user["username"] if user else user_id
    sesiones = listar_sesiones(user_id=uid, limite=limite)
    return {"sesiones": sesiones, "total": len(sesiones)}


@app.get("/sessions/{session_id}/history", summary="Carga el historial de una sesión")
def obtener_historial(session_id: str, user: dict | None = Depends(obtener_usuario_actual)):
    _verificar_ownership(session_id, user)
    mensajes = cargar_historial(session_id)
    return {"session_id": session_id, "mensajes": mensajes}


@app.patch("/sessions/{session_id}", summary="Renombra una sesión")
def renombrar_sesion_endpoint(session_id: str, req: RenombrarRequest, user: dict | None = Depends(obtener_usuario_actual)):
    _verificar_ownership(session_id, user)
    renombrar_sesion(session_id, req.titulo)
    return {"mensaje": f"Sesión renombrada a '{req.titulo}'."}


@app.delete("/sessions/{session_id}", summary="Elimina una sesión")
def eliminar_sesion(session_id: str, user: dict | None = Depends(obtener_usuario_actual)):
    _verificar_ownership(session_id, user)
    limpiar_sesion(session_id)
    return {"mensaje": f"Sesión '{session_id}' eliminada."}


@app.post("/documents", summary="Sube e indexa un documento")
async def subir_documento(fichero: UploadFile = File(...), user: dict = Depends(requerir_usuario)):
    """Sube un documento al corpus privado y lanza la indexación completa.

    El flujo es: validación → guardado en disco → chunking + embeddings
    → persistencia en ChromaDB → postproceso (resumen, metadatos,
    compliance). Si alguna fase falla se hace rollback del fichero y se
    devuelve un error informativo; la indexación es la fase más cara
    (varios segundos por PDF).
    """
    extension = Path(fichero.filename).suffix.lower()
    if extension not in FORMATOS_SOPORTADOS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: '{extension}'. Válidos: {sorted(FORMATOS_SOPORTADOS)}",
        )

    # Path(...).name elimina cualquier intento de path traversal
    # (../../etc/passwd) y deja solo el basename del fichero.
    nombre_seguro = Path(fichero.filename).name
    if not nombre_seguro or nombre_seguro.startswith("."):
        raise HTTPException(status_code=400, detail="Nombre de fichero no válido.")

    contenido = await fichero.read()
    # Límite de 50 MB: PDFs de contratos rara vez superan los 5 MB, pero
    # margen amplio para anexos. Por encima sería sospechoso.
    if len(contenido) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El fichero supera el límite de 50 MB.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / nombre_seguro

    with open(destino, "wb") as f:
        f.write(contenido)

    doc_id = hashlib.md5(nombre_seguro.encode()).hexdigest()[:12]
    if index_manifest.esta_indexado(doc_id):
        raise HTTPException(
            status_code=409,
            detail=f"'{fichero.filename}' ya está indexado. Elimínalo primero.",
        )

    from src.core.rag.loader import cargar_documento
    try:
        paginas = cargar_documento(destino)
    except Exception as e:
        destino.unlink(missing_ok=True)
        log.error("Error al cargar %s: %s", fichero.filename, e)
        raise HTTPException(status_code=422, detail="No se pudo procesar el fichero. Verifique el formato.")

    if not paginas:
        destino.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No se pudo extraer texto.")

    try:
        padres, hijos = chunkear(paginas, doc_id)
        embeddings = embeber_chunks(hijos)
        guardar_chunks(padres, hijos, embeddings, doc_id)
        index_manifest.registrar(doc_id, fichero.filename, str(destino), len(hijos))
    except Exception as e:
        destino.unlink(missing_ok=True)
        log.error("Error indexando %s: %s", fichero.filename, e)
        raise HTTPException(status_code=500, detail="Error interno durante la indexación.")

    resumen = ""
    alertas = []
    try:
        from src.core.rag.summarizer import generar_resumen
        from src.core.rag.metadata_extractor import extraer_metadatos, extraer_datos_estructurados
        from src.core.rag.compliance_checker import verificar_cumplimiento
        texto_completo = "\n".join(p.texto for p in paginas if p.texto)
        resumen = generar_resumen(texto_completo)
        if resumen:
            index_manifest.actualizar_resumen(doc_id, resumen)
        metadatos = extraer_metadatos(texto_completo)
        if any(metadatos.values()):
            index_manifest.actualizar_metadatos(
                doc_id,
                fecha_inicio=metadatos.get("fecha_inicio"),
                fecha_fin=metadatos.get("fecha_fin"),
                tipo_contrato=metadatos.get("tipo_contrato"),
            )
        datos = extraer_datos_estructurados(texto_completo, fichero.filename)
        if any(datos.values()):
            index_manifest.actualizar_datos_extraidos(doc_id, datos)
        alertas = verificar_cumplimiento(texto_completo)
        if alertas:
            index_manifest.actualizar_alertas(doc_id, alertas)
    except Exception as e:
        log.warning("Postproceso de %s falló (resumen/datos/alertas): %s", fichero.filename, e)

    return {
        "mensaje": f"'{fichero.filename}' indexado correctamente.",
        "doc_id": doc_id,
        "num_chunks": len(hijos),
        "num_paginas": len(paginas),
        "resumen": resumen,
        "alertas": alertas,
    }


@app.get("/documents", summary="Lista los documentos indexados")
def listar_documentos(user: dict = Depends(requerir_usuario)):
    docs = listar()
    for d in docs:
        if isinstance(d.get("alertas"), str):
            try:
                d["alertas"] = json.loads(d["alertas"])
            except (json.JSONDecodeError, TypeError):
                d["alertas"] = []
    return {"documentos": docs, "total": len(docs)}


@app.delete("/documents/{nombre}", summary="Elimina un documento del índice")
def eliminar_documento(nombre: str, user: dict = Depends(requerir_admin)):
    docs = listar()
    encontrado = next((d for d in docs if d["nombre"] == nombre), None)
    if not encontrado:
        raise HTTPException(status_code=404, detail=f"'{nombre}' no encontrado.")

    borrar_chunks_documento(encontrado["doc_id"])
    index_manifest.eliminar(encontrado["doc_id"])
    return {"mensaje": f"'{nombre}' eliminado del índice."}


@app.post("/documents/scan-compliance", summary="Escanea todos los documentos buscando ilegalidades y extrayendo datos")
def scan_compliance(user: dict = Depends(requerir_admin)):
    """Reescaneo masivo del corpus para refrescar alertas y metadatos.

    Útil cuando se cambia el `compliance_checker` o se actualiza el SMI
    en config: en lugar de reindexar todos los documentos, se reaprovecha
    el texto ya cargado y se actualizan únicamente las tablas auxiliares.
    Solo accesible para administradores.
    """
    from src.core.rag.compliance_checker import verificar_cumplimiento
    from src.core.rag.metadata_extractor import extraer_metadatos, extraer_datos_estructurados
    from src.core.rag.loader import cargar_documento

    docs = listar()
    resultados = []
    for doc in docs:
        ruta = Path(doc["ruta"])
        if not ruta.exists():
            continue
        try:
            paginas = cargar_documento(ruta)
            texto = "\n".join(p.texto for p in paginas if p.texto)
            alertas = verificar_cumplimiento(texto)
            index_manifest.actualizar_alertas(doc["doc_id"], alertas)
            datos = extraer_datos_estructurados(texto, doc["nombre"])
            if any(datos.values()):
                index_manifest.actualizar_datos_extraidos(doc["doc_id"], datos)
            metadatos = extraer_metadatos(texto)
            if any(metadatos.values()):
                index_manifest.actualizar_metadatos(
                    doc["doc_id"],
                    fecha_inicio=metadatos.get("fecha_inicio"),
                    fecha_fin=metadatos.get("fecha_fin"),
                    tipo_contrato=metadatos.get("tipo_contrato"),
                )
            if alertas:
                resultados.append({"nombre": doc["nombre"], "alertas": alertas})
        except Exception as e:
            log.warning("scan-compliance falló para %s: %s", doc.get("nombre"), e)

    return {
        "documentos_escaneados": len(docs),
        "con_alertas": len(resultados),
        "detalle": resultados,
    }


@app.get("/documents/{doc_id}/audit-pdf", summary="Genera informe PDF de auditoría legal")
def audit_pdf(doc_id: str, user: dict = Depends(requerir_usuario)):
    doc = index_manifest.obtener(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    import json as _json
    from src.core.pdf_report import generar_informe_pdf

    alertas = []
    if isinstance(doc.get("alertas"), str):
        try:
            alertas = _json.loads(doc["alertas"])
        except (ValueError, TypeError):
            pass
    elif isinstance(doc.get("alertas"), list):
        alertas = doc["alertas"]

    datos = {}
    if isinstance(doc.get("datos_extraidos"), str):
        try:
            datos = _json.loads(doc["datos_extraidos"])
        except (ValueError, TypeError):
            pass
    elif isinstance(doc.get("datos_extraidos"), dict):
        datos = doc["datos_extraidos"]

    pdf_bytes = generar_informe_pdf(doc, alertas, datos)
    nombre_pdf = f"auditoria_{doc['nombre'].rsplit('.', 1)[0]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_pdf}"'},
    )


@app.get("/audit", summary="Historial de consultas")
def audit(
    limite: int = Query(default=50, le=200),
    user_id: str = Query(default=None),
    user: dict = Depends(requerir_usuario),
):
    """Devuelve la auditoría de consultas.

    Los usuarios sin rol admin ven únicamente sus propias consultas
    (forzamos el user_id al del autenticado); los admins pueden
    consultar el historial completo o filtrar por usuario.
    """
    if user.get("rol") != "admin":
        user_id = user["username"]
    consultas = listar_consultas(limite=limite, user_id=user_id)
    return {"consultas": consultas, "total": len(consultas)}



@app.post("/auth/register", summary="Registra un nuevo usuario")
def register(req: RegisterRequest):
    try:
        user = crear_usuario(req.username, req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = crear_token(user["id"], user["username"], user["rol"])
    return {
        "token": token,
        "user": {"id": user["id"], "username": user["username"], "email": user["email"], "rol": user["rol"]},
    }


@app.post("/auth/login", summary="Inicia sesión")
def login(req: LoginRequest):
    user = autenticar_usuario(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas.")
    token = crear_token(user["id"], user["username"], user["rol"])
    return {
        "token": token,
        "user": {"id": user["id"], "username": user["username"], "email": user["email"], "rol": user["rol"]},
    }


@app.get("/auth/me", summary="Obtiene el usuario actual")
def me(user: dict = Depends(obtener_usuario_actual)):
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado.")
    return {"username": user["username"], "rol": user["rol"]}



@app.get("/contracts/stats", summary="Estadísticas agregadas de contratos")
def contract_stats(user: dict = Depends(requerir_usuario)):
    return obtener_estadisticas_contratos()



@app.get("/sessions/{session_id}/export", summary="Exporta una sesión como Markdown")
def exportar_sesion(session_id: str, user: dict | None = Depends(obtener_usuario_actual)):
    _verificar_ownership(session_id, user)
    mensajes = cargar_historial(session_id, max_turnos=500)
    if not mensajes:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o vacía.")

    lineas = [f"# Conversación — Sesión {session_id}\n"]
    for msg in mensajes:
        rol = "🧑 Usuario" if msg["role"] == "user" else "🤖 Asistente"
        lineas.append(f"## {rol}\n\n{msg['content']}\n")

    contenido = "\n".join(lineas)
    return Response(
        content=contenido,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="sesion_{session_id}.md"'},
    )
