"""CLI para ingestar y gestionar documentos en el pipeline RAG.

Replica el flujo de subida del endpoint /documents pero desde línea de
comandos: útil para indexar lotes completos de contratos en un solo
comando o para procesar normativa pública (que no se sube por la UI).

Modo legal (`--legal`) procesa documentos de `data/legal/` y los manda
a la colección pública, aplicando un filtrado adicional de páginas de
índice/TOC que no aportan información al retrieval.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.rag.loader import cargar_documento, FORMATOS_SOPORTADOS
from core.rag.chunker import chunkear
from core.rag.embedder import embeber_chunks
from core.rag.store import guardar_chunks, borrar_chunks_documento
from core.rag.metadata_extractor import extraer_metadatos
from core.rag import index_manifest
from core.config import settings

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
LEGAL_DIR = Path(__file__).resolve().parents[1] / "data" / "legal"


def id_documento(ruta: Path) -> str:
    """Genera un ID de 12 caracteres basado en el nombre del fichero."""
    return hashlib.md5(ruta.name.encode()).hexdigest()[:12]


def verificar_conexiones() -> None:
    """Comprueba que ChromaDB y Ollama son accesibles antes de ingestar."""
    import chromadb
    from langchain_ollama import OllamaEmbeddings

    print("Verificando ChromaDB...")
    try:
        cliente = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        cliente.heartbeat()
        print(f"  [ok] ChromaDB en {settings.chroma_host}:{settings.chroma_port}")
    except Exception as e:
        print(f"  [error] ChromaDB no responde: {e}")
        sys.exit(1)

    print("Verificando Ollama (embeddings)...")
    try:
        emb = OllamaEmbeddings(
            model=settings.embed_model,
            base_url=settings.ollama_base_url,
        )
        emb.embed_query("test")
        print(f"  [ok] Ollama en {settings.ollama_base_url} — modelo: {settings.embed_model}")
    except Exception as e:
        print(f"  [error] Ollama no responde: {e}")
        sys.exit(1)


def _es_pagina_indice(pagina) -> bool:
    """Detecta heurísticamente páginas de índice/TOC.

    Dos señales:
    - Múltiples líneas con puntos suspensivos ("....", "…"): formato
      típico del índice ("Artículo 1 ........ 4").
    - Patrón "texto, NN" o "texto, NN y MM" al final de líneas: forma
      compacta del índice del BOE.

    Filtrar estas páginas mejora notablemente la calidad del retrieval
    sobre normativa: sin filtrarlas, BM25 sale enganchado a los títulos
    del índice en lugar de al artículo real.
    """
    texto = pagina.texto
    lineas = texto.strip().split("\n")

    lineas_puntos = sum(1 for l in lineas if "...." in l or "…" in l)
    if lineas_puntos >= 3:
        return True

    lineas_indice = sum(
        1 for l in lineas
        if re.search(r',\s+\d{1,3}(\.\d)?\.?$', l.strip())
        or re.search(r',\s+\d{1,3}(\.\d)?\s+y\s+\d', l.strip())
    )
    if lineas_indice >= 5:
        return True

    return False


def _filtrar_paginas_normativa(paginas: list) -> list:
    """Filtra páginas de índice/TOC de documentos normativos."""
    filtradas = [p for p in paginas if not _es_pagina_indice(p)]
    n_filtradas = len(paginas) - len(filtradas)
    if n_filtradas > 0:
        print(f"  [filtrado]    {n_filtradas} páginas de índice/TOC eliminadas")
    return filtradas


def ingestar(ruta: Path, forzar: bool = False, coleccion: str = None) -> None:
    """Ejecuta el pipeline completo para un documento: carga → chunks → embeddings → ChromaDB."""
    doc_id = id_documento(ruta)

    if index_manifest.esta_indexado(doc_id) and not forzar:
        print(f"  [omitido]     {ruta.name} — ya indexado. Usa --forzar para reindexar.")
        return

    if index_manifest.esta_indexado(doc_id) and forzar:
        print(f"  [reindexando] {ruta.name}")
        borrar_chunks_documento(doc_id, coleccion)
        index_manifest.eliminar(doc_id)

    print(f"  [cargando]    {ruta.name}")
    try:
        paginas = cargar_documento(ruta)
    except Exception as e:
        print(f"  [error]       {ruta.name} — no se pudo cargar: {e}")
        return

    if not paginas:
        print(f"  [error]       {ruta.name} — no se extrajo texto.")
        return

    if coleccion == settings.chroma_collection_public:
        paginas = _filtrar_paginas_normativa(paginas)

    print(f"  [chunkeando]  {len(paginas)} página(s) — generando chunks padre-hijo...")
    try:
        padres, hijos = chunkear(paginas, doc_id)
    except Exception as e:
        print(f"  [error]       {ruta.name} — fallo en chunking: {e}")
        return

    if not hijos:
        print(f"  [error]       {ruta.name} — no se generaron chunks hijo.")
        return

    print(f"  [embebiendo]  {len(hijos)} chunks hijo...")
    try:
        embeddings = embeber_chunks(hijos)
    except Exception as e:
        print(f"  [error]       {ruta.name} — fallo en embeddings: {e}")
        return

    col = coleccion or settings.chroma_collection_private
    print(f"  [guardando]   {len(padres)} padres + {len(hijos)} hijos en '{col}'...")
    guardar_chunks(padres, hijos, embeddings, doc_id, coleccion=coleccion)

    fecha_inicio = None
    fecha_fin = None
    tipo_contrato = ""
    if coleccion != settings.chroma_collection_public:
        texto_completo = "\n".join(p.texto for p in paginas)
        meta = extraer_metadatos(texto_completo)
        fecha_inicio = meta.get("fecha_inicio")
        fecha_fin = meta.get("fecha_fin")
        tipo_contrato = meta.get("tipo_contrato", "")
        if fecha_inicio or fecha_fin:
            print(f"  [metadatos]   inicio={fecha_inicio}, fin={fecha_fin}, tipo={tipo_contrato}")

    index_manifest.registrar(
        doc_id, ruta.name, str(ruta), len(hijos), coleccion=col,
        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, tipo_contrato=tipo_contrato,
    )

    print(f"  [ok]          {ruta.name} — {len(hijos)} hijos, {len(padres)} padres (doc_id: {doc_id})\n")


def borrar_documento(nombre: str) -> None:
    """Elimina un documento del índice por nombre de fichero."""
    docs = index_manifest.listar()
    encontrado = next((d for d in docs if d["nombre"] == nombre), None)
    if not encontrado:
        print(f"No se encontró '{nombre}' en el índice.")
        return
    borrar_chunks_documento(encontrado["doc_id"], encontrado.get("coleccion"))
    index_manifest.eliminar(encontrado["doc_id"])
    print(f"Eliminado: {nombre}")


def mostrar_lista() -> None:
    """Muestra todos los documentos indexados con sus estadísticas."""
    docs = index_manifest.listar()
    if not docs:
        print("No hay documentos indexados.")
        return
    print(f"\n{'Nombre':<40} {'Hijos':>6}  {'Colección':<25}  Indexado en")
    print("-" * 95)
    for d in docs:
        print(f"  {d['nombre']:<38} {d['num_chunks']:>6}  {d['coleccion']:<25}  {d['indexado_en'][:19]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Gestión del índice de documentos RAG.")
    parser.add_argument("--forzar",    action="store_true", help="Reindexa aunque ya existan.")
    parser.add_argument("--listar",    action="store_true", help="Muestra documentos indexados.")
    parser.add_argument("--verificar", action="store_true", help="Comprueba ChromaDB y Ollama.")
    parser.add_argument("--borrar",    metavar="NOMBRE",    help="Elimina un documento del índice.")
    parser.add_argument("--legal",     action="store_true", help="Indexa normativa desde data/legal/ en la colección pública.")
    args = parser.parse_args()

    if args.verificar:
        verificar_conexiones()
        return

    if args.listar:
        mostrar_lista()
        return

    if args.borrar:
        borrar_documento(args.borrar)
        return

    if args.legal:
        directorio = LEGAL_DIR
        coleccion = settings.chroma_collection_public
        tipo = "normativa legal"
    else:
        directorio = RAW_DIR
        coleccion = None  # usa la privada por defecto
        tipo = "contratos"

    if not directorio.exists():
        directorio.mkdir(parents=True, exist_ok=True)
        print(f"Creado directorio {directorio}")

    ficheros = sorted(
        f for f in directorio.iterdir()
        if f.is_file() and f.suffix.lower() in FORMATOS_SOPORTADOS
    )

    if not ficheros:
        print(f"No se encontraron documentos de {tipo} en {directorio}")
        return

    print(f"Encontrados {len(ficheros)} documento(s) de {tipo} en {directorio}\n")
    for fichero in ficheros:
        ingestar(fichero, forzar=args.forzar, coleccion=coleccion)

    print("Ingesta completada.")
    mostrar_lista()


if __name__ == "__main__":
    main()