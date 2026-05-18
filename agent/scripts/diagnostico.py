"""Diagnóstico de salud del sistema en un solo comando.

Verifica conectividad con ChromaDB y Ollama, recuento de colecciones,
integridad del corpus BM25 y estado de las tablas de SQLite. Pensado
para ejecutarse dentro del contenedor backend o como paso de
verificación tras un despliegue:

    docker exec tfg-backend python scripts/diagnostico.py
"""

import json
import os
import sys
import time
import sqlite3
from pathlib import Path

# Asegurar que /app está en el PYTHONPATH (para ejecución dentro del contenedor)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Colores para terminal ──────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg):
    print(f"  {GREEN}✔{RESET} {msg}")


def fail(msg):
    print(f"  {RED}✘{RESET} {msg}")


def warn(msg):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def header(msg):
    print(f"\n{BOLD}{CYAN}{'═' * 60}")
    print(f"  {msg}")
    print(f"{'═' * 60}{RESET}")


errores = []


# ═══════════════════════════════════════════════════════════════════════════
# 1. CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════
header("1. CONFIGURACIÓN (.env / variables de entorno)")

try:
    from src.core.config import settings

    ok(f"OLLAMA_BASE_URL    = {settings.ollama_base_url}")
    ok(f"LLM_MODEL          = {settings.llm_model}")
    ok(f"EMBED_MODEL        = {settings.embed_model}")
    ok(f"CONTEXT_MODEL      = {settings.context_model}")
    ok(f"CHROMA_HOST:PORT   = {settings.chroma_host}:{settings.chroma_port}")
    ok(f"SQLITE_PATH        = {settings.sqlite_path}")
    ok(f"Colección privada  = {settings.chroma_collection_private}")
    ok(f"Colección pública  = {settings.chroma_collection_public}")
    ok(f"Padres privados    = {settings.chroma_collection_padres_private}")
    ok(f"Padres públicos    = {settings.chroma_collection_padres_public}")
    ok(f"retrieval_k={settings.retrieval_k}  rrf_k={settings.rrf_k}  memory_turns={settings.memory_turns}")
except Exception as e:
    fail(f"Error cargando settings: {e}")
    errores.append(("config", str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# 2. CONECTIVIDAD CHROMADB
# ═══════════════════════════════════════════════════════════════════════════
header("2. CONECTIVIDAD CHROMADB")

try:
    import chromadb

    cliente = chromadb.HttpClient(
        host=settings.chroma_host, port=settings.chroma_port
    )
    heartbeat = cliente.heartbeat()
    ok(f"Heartbeat ChromaDB: {heartbeat}")

    colecciones = cliente.list_collections()
    if colecciones:
        ok(f"Colecciones encontradas: {len(colecciones)}")
        for col in colecciones:
            nombre = col if isinstance(col, str) else col.name
            try:
                c = cliente.get_collection(nombre)
                count = c.count()
                ok(f"  · {nombre}: {count} documentos")
            except Exception as e:
                warn(f"  · {nombre}: error al contar → {e}")
    else:
        warn("No hay colecciones en ChromaDB (¿faltan documentos indexados?)")
except Exception as e:
    fail(f"ChromaDB no accesible: {e}")
    errores.append(("chromadb", str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# 3. CONECTIVIDAD OLLAMA + MODELOS
# ═══════════════════════════════════════════════════════════════════════════
header("3. CONECTIVIDAD OLLAMA")

try:
    import requests

    r = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=10)
    r.raise_for_status()
    modelos_disponibles = [m["name"] for m in r.json().get("models", [])]
    ok(f"Ollama accesible — {len(modelos_disponibles)} modelo(s) instalados")

    for nombre_modelo in [settings.llm_model, settings.embed_model, settings.context_model]:
        # Comprobar coincidencia exacta o por prefijo (qwen2.5:7b vs qwen2.5:7b-instruct...)
        encontrado = any(
            m == nombre_modelo or m.startswith(nombre_modelo.split(":")[0])
            for m in modelos_disponibles
        )
        if encontrado:
            ok(f"  Modelo '{nombre_modelo}' disponible")
        else:
            fail(f"  Modelo '{nombre_modelo}' NO encontrado en Ollama")
            errores.append(("ollama_modelo", nombre_modelo))

    # Test de embedding rápido
    print()
    ok("Probando embedding...")
    t0 = time.time()
    from langchain_ollama import OllamaEmbeddings

    emb = OllamaEmbeddings(model=settings.embed_model, base_url=settings.ollama_base_url)
    vec = emb.embed_query("test de diagnóstico")
    t1 = time.time()
    ok(f"  Embedding OK — dimensión={len(vec)}, latencia={t1 - t0:.2f}s")

except Exception as e:
    fail(f"Ollama no accesible: {e}")
    errores.append(("ollama", str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# 4. SQLITE (index_manifest)
# ═══════════════════════════════════════════════════════════════════════════
header("4. SQLITE (index_manifest)")

db_path = Path(settings.sqlite_path)
if db_path.exists():
    ok(f"Base de datos encontrada: {db_path} ({db_path.stat().st_size / 1024:.1f} KB)")
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        # Tablas existentes
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tablas = [r[0] for r in cur.fetchall()]
        ok(f"Tablas: {tablas}")

        # Documentos indexados
        if "documentos" in tablas:
            cur.execute("SELECT COUNT(*) FROM documentos")
            n = cur.fetchone()[0]
            ok(f"  documentos: {n} registros")
            if n > 0:
                cur.execute("SELECT doc_id, nombre, num_chunks FROM documentos")
                for row in cur.fetchall():
                    ok(f"    → {row[1]} (id={row[0]}, chunks={row[2]})")

        # Sesiones
        if "sesiones_meta" in tablas:
            cur.execute("SELECT COUNT(*) FROM sesiones_meta")
            ok(f"  sesiones_meta: {cur.fetchone()[0]} sesiones")

        if "sesiones_mensajes" in tablas:
            cur.execute("SELECT COUNT(*) FROM sesiones_mensajes")
            ok(f"  sesiones_mensajes: {cur.fetchone()[0]} mensajes")

        # Auditoría
        if "consultas" in tablas:
            cur.execute("SELECT COUNT(*) FROM consultas")
            n_consultas = cur.fetchone()[0]
            ok(f"  consultas (auditoría): {n_consultas} registros")
            if n_consultas > 0:
                cur.execute(
                    "SELECT intent, modo, COUNT(*) FROM consultas GROUP BY intent, modo"
                )
                for row in cur.fetchall():
                    ok(f"    → intent={row[0]}, modo={row[1]}: {row[2]} consultas")

        conn.close()
    except Exception as e:
        fail(f"Error leyendo SQLite: {e}")
        errores.append(("sqlite", str(e)))
else:
    warn(f"Base de datos no existe aún: {db_path}")


# ═══════════════════════════════════════════════════════════════════════════
# 5. FICHEROS DE DATOS
# ═══════════════════════════════════════════════════════════════════════════
header("5. FICHEROS DE DATOS")

raw_dir = Path("data/raw")
legal_dir = Path("data/legal")

if raw_dir.exists():
    archivos_raw = list(raw_dir.iterdir())
    ok(f"data/raw/: {len(archivos_raw)} fichero(s)")
    for f in archivos_raw[:10]:
        ok(f"  · {f.name} ({f.stat().st_size / 1024:.1f} KB)")
    if len(archivos_raw) > 10:
        warn(f"  ... y {len(archivos_raw) - 10} más")
else:
    warn("data/raw/ no existe")

if legal_dir.exists():
    archivos_legal = list(legal_dir.iterdir())
    ok(f"data/legal/: {len(archivos_legal)} fichero(s)")
    for f in archivos_legal[:10]:
        ok(f"  · {f.name} ({f.stat().st_size / 1024:.1f} KB)")
else:
    warn("data/legal/ no existe (modo legal no disponible)")

bm25_path = Path(settings.bm25_corpus_path)
if bm25_path.exists():
    ok(f"BM25 corpus: {bm25_path} ({bm25_path.stat().st_size / 1024:.1f} KB)")
else:
    warn(f"BM25 corpus no encontrado: {bm25_path}")


# ═══════════════════════════════════════════════════════════════════════════
# 6. GRAFO LANGGRAPH
# ═══════════════════════════════════════════════════════════════════════════
header("6. GRAFO LANGGRAPH")

try:
    from src.core.graph import grafo

    ok(f"Grafo cargado correctamente: {type(grafo).__name__}")
    if hasattr(grafo, "nodes"):
        nodos = list(grafo.nodes.keys()) if isinstance(grafo.nodes, dict) else list(grafo.nodes)
        ok(f"  Nodos: {nodos}")
except Exception as e:
    fail(f"Error cargando el grafo: {e}")
    errores.append(("grafo", str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# 7. TEST END-TO-END (pregunta simple)
# ═══════════════════════════════════════════════════════════════════════════
header("7. TEST END-TO-END")

try:
    ok("Enviando pregunta de prueba al grafo: 'Hola, ¿qué puedes hacer?'")
    t0 = time.time()
    resultado = grafo.invoke({
        "user_id": "diagnostico",
        "session_id": "diag_test",
        "pregunta": "Hola, ¿qué puedes hacer?",
        "messages": [],
        "traza": [],
    })
    t1 = time.time()

    respuesta = resultado.get("respuesta", resultado.get("pregunta_aclaracion", ""))
    intent = resultado.get("intent", "?")
    modo = resultado.get("modo", "?")
    traza = resultado.get("traza", [])

    ok(f"  Intent detectado: {intent}")
    ok(f"  Modo: {modo}")
    ok(f"  Latencia total: {t1 - t0:.2f}s")
    ok(f"  Traza: {json.dumps(traza, ensure_ascii=False, default=str)[:200]}")
    ok(f"  Respuesta (primeros 200 chars):")
    print(f"    {CYAN}{respuesta[:200]}{RESET}")

except Exception as e:
    fail(f"Error en test E2E: {e}")
    errores.append(("e2e", str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# 8. TEST RAG (pregunta documental)
# ═══════════════════════════════════════════════════════════════════════════
header("8. TEST RAG (pregunta documental)")

try:
    # Primero verificar si hay documentos indexados
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documentos")
    n_docs = cur.fetchone()[0]
    conn.close()

    if n_docs == 0:
        warn("No hay documentos indexados — saltando test RAG")
    else:
        ok(f"Hay {n_docs} documento(s) indexado(s), probando consulta documental...")
        t0 = time.time()
        resultado = grafo.invoke({
            "user_id": "diagnostico",
            "session_id": "diag_rag_test",
            "pregunta": "¿Qué documentos tienes indexados?",
            "messages": [],
            "traza": [],
        })
        t1 = time.time()

        respuesta = resultado.get("respuesta", "")
        intent = resultado.get("intent", "?")
        modo = resultado.get("modo", "?")
        evidence = resultado.get("evidence_pack", [])
        citas = resultado.get("citas", [])

        ok(f"  Intent: {intent} | Modo: {modo}")
        ok(f"  Fragmentos recuperados: {len(evidence)}")
        ok(f"  Citas generadas: {len(citas)}")
        ok(f"  Latencia: {t1 - t0:.2f}s")
        ok(f"  Respuesta (primeros 300 chars):")
        print(f"    {CYAN}{respuesta[:300]}{RESET}")

except Exception as e:
    fail(f"Error en test RAG: {e}")
    errores.append(("rag", str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════════════════════════════════════════
header("RESUMEN DEL DIAGNÓSTICO")

if not errores:
    print(f"\n  {GREEN}{BOLD}✔ Todo OK — el sistema está operativo.{RESET}\n")
else:
    print(f"\n  {RED}{BOLD}✘ Se encontraron {len(errores)} problema(s):{RESET}")
    for componente, detalle in errores:
        print(f"    {RED}· [{componente}]{RESET} {detalle}")
    print()

sys.exit(len(errores))
