"""Chunking semántico con estructura padre-hijo."""

import re
from dataclasses import dataclass, field
from math import sqrt

from langchain_ollama import OllamaEmbeddings

from .loader import Pagina
from ..config import settings

MIN_CHARS_CHUNK = 60

# TODO: el embedder se crea aquí directamente en vez de usar crear_embedder()
# de embedder.py. No se puede importar por dependencia circular
# (embedder.py importa ChunkHijo de chunker.py). Valorar mover la factoría
# a un módulo independiente para eliminar la duplicación.


@dataclass
class ChunkHijo:
    texto: str
    parent_id: str
    doc_nombre: str
    pagina: int
    chunk_index: int
    nombre_trabajador: str = ""
    dni: str = ""
    tipo_contrato: str = ""


@dataclass
class ChunkPadre:
    id: str
    texto: str
    doc_nombre: str
    pagina: int


def _extraer_metadatos(texto_primera_pagina: str) -> dict:
    """Extrae nombre, DNI y tipo de contrato de la primera página."""
    metadatos = {"nombre_trabajador": "", "dni": "", "tipo_contrato": ""}

    # Nombre del trabajador: primero formato SEPE, luego formato libre
    seccion_trab = re.search(
        r'DATOS\s+DEL(?:/DE\s+LA)?\s+TRABAJADOR',
        texto_primera_pagina,
    )
    if seccion_trab:
        texto_despues = texto_primera_pagina[seccion_trab.end():]
        match_sepe = re.search(
            r'D\./D[ÑN]A\.?\s*\n\s*([A-Z][A-ZÁÉÍÓÚÑ ]+,\s*[A-Z][A-ZÁÉÍÓÚÑ ]+)',
            texto_despues,
        )
        if match_sepe:
            metadatos["nombre_trabajador"] = match_sepe.group(1).strip()

    if not metadatos["nombre_trabajador"]:
        patrones_nombre = [
            r'Trabajador[a]?\s*:\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})',
            r'De otra parte,\s*D\.?[ªa]?\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})\s*,',
            r'[Ee]l\s+[Tt]rabajador[»)]\s*[.:]\s*D\.?[ªa]?\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})',
        ]
        for patron in patrones_nombre:
            match_nombre = re.search(patron, texto_primera_pagina)
            if match_nombre:
                metadatos["nombre_trabajador"] = match_nombre.group(1).strip()
                break

    # DNI/NIE
    if seccion_trab:
        texto_despues = texto_primera_pagina[seccion_trab.end():]
        match_dni_trab = re.search(r'\b([XYZ]?\d{7,8}[A-Z])\b', texto_despues)
        if match_dni_trab:
            metadatos["dni"] = match_dni_trab.group(1)

    if not metadatos["dni"]:
        match_dni = re.search(r'\b([XYZ]?\d{7,8}[A-Z])\b', texto_primera_pagina)
        if match_dni:
            metadatos["dni"] = match_dni.group(1)

    # Tipo de contrato
    if re.search(r'INDEFINIDO', texto_primera_pagina, re.IGNORECASE):
        metadatos["tipo_contrato"] = "indefinido"
    elif re.search(r'CIRCUNSTANCIAS DE LA PRODUCCI[OÓ]N|DETERMINADA|TEMPORAL|OBRA.*SERVICIO', texto_primera_pagina, re.IGNORECASE):
        metadatos["tipo_contrato"] = "temporal"
    elif re.search(r'PR[AÁ]CTICAS|FORMATIVO', texto_primera_pagina, re.IGNORECASE):
        metadatos["tipo_contrato"] = "prácticas"
    elif re.search(r'INTERINIDAD', texto_primera_pagina, re.IGNORECASE):
        metadatos["tipo_contrato"] = "interinidad"
    elif re.search(r'TIEMPO PARCIAL|PARCIAL', texto_primera_pagina, re.IGNORECASE):
        metadatos["tipo_contrato"] = "parcial"

    return metadatos


def _dividir_parrafos(texto: str) -> list[str]:
    parrafos = re.split(r'\n{2,}', texto)
    return [p.strip() for p in parrafos if p.strip()]


def _dividir_frases(texto: str) -> list[str]:
    frases = re.split(r'(?<=[.!?])\s+', texto)
    return [f.strip() for f in frases if f.strip()]


def _unidades_de_texto(texto_pagina: str, max_chars: int) -> list[str]:
    unidades = []
    for parrafo in _dividir_parrafos(texto_pagina):
        if len(parrafo) <= max_chars:
            unidades.append(parrafo)
        else:
            unidades.extend(_dividir_frases(parrafo))
    return unidades


def _similitud_coseno(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norma1 = sqrt(sum(a ** 2 for a in v1))
    norma2 = sqrt(sum(b ** 2 for b in v2))
    if norma1 == 0 or norma2 == 0:
        return 0.0
    return dot / (norma1 * norma2)


def _agrupar_por_similitud(
    unidades: list[str],
    embeddings: list[list[float]],
    umbral: float,
    max_chars: int,
) -> list[str]:
    """Agrupa unidades consecutivas mientras la similitud entre ellas supere
    el umbral y el grupo no exceda el tamaño máximo. Cuando se rompe alguna
    de las dos condiciones, se cierra el grupo y empieza uno nuevo.
    """
    if not unidades:
        return []

    chunks = []
    grupo_actual = [unidades[0]]

    for i in range(1, len(unidades)):
        similitud = _similitud_coseno(embeddings[i - 1], embeddings[i])
        texto_si_se_añade = "\n".join(grupo_actual + [unidades[i]])
        # Condición de corte: salto temático (similitud baja) o tamaño excedido.
        if similitud < umbral or len(texto_si_se_añade) > max_chars:
            chunks.append("\n".join(grupo_actual))
            grupo_actual = [unidades[i]]
        else:
            grupo_actual.append(unidades[i])

    # No olvidar el último grupo abierto.
    if grupo_actual:
        chunks.append("\n".join(grupo_actual))

    return chunks


def _es_chunk_valido(texto: str) -> bool:
    """Descarta chunks demasiado cortos o que son solo numeración."""
    texto_limpio = texto.strip()
    if len(texto_limpio) < MIN_CHARS_CHUNK:
        return False
    # Filtra fragmentos como "1." o "23" que aparecen al partir tablas.
    if re.fullmatch(r'\d+\.?', texto_limpio):
        return False
    return True


def chunkear(
    paginas: list[Pagina],
    doc_id: str,
) -> tuple[list[ChunkPadre], list[ChunkHijo]]:
    """Genera los chunks padre e hijo para un documento.

    El umbral de similitud y el tamaño máximo de chunk se leen de la
    configuración (`semantic_threshold` y `max_chunk_chars`).
    """
    embedder = OllamaEmbeddings(
        model=settings.embed_model,
        base_url=settings.ollama_base_url,
    )

    metadatos_doc = {}
    if paginas:
        metadatos_doc = _extraer_metadatos(paginas[0].texto)

    padres: list[ChunkPadre] = []
    hijos: list[ChunkHijo] = []
    contador_hijo = 0

    for pagina in paginas:
        parent_id = f"{doc_id}_padre_{pagina.numero}"
        padres.append(ChunkPadre(
            id=parent_id,
            texto=pagina.texto,
            doc_nombre=pagina.doc_nombre,
            pagina=pagina.numero,
        ))

        unidades = _unidades_de_texto(pagina.texto, settings.max_chunk_chars)
        if not unidades:
            continue

        embeddings_unidades = embedder.embed_documents(unidades)
        textos_hijos = _agrupar_por_similitud(
            unidades=unidades,
            embeddings=embeddings_unidades,
            umbral=settings.semantic_threshold,
            max_chars=settings.max_chunk_chars,
        )

        for texto in textos_hijos:
            if not _es_chunk_valido(texto):
                continue
            hijos.append(ChunkHijo(
                texto=texto,
                parent_id=parent_id,
                doc_nombre=pagina.doc_nombre,
                pagina=pagina.numero,
                chunk_index=contador_hijo,
                nombre_trabajador=metadatos_doc.get("nombre_trabajador", ""),
                dni=metadatos_doc.get("dni", ""),
                tipo_contrato=metadatos_doc.get("tipo_contrato", ""),
            ))
            contador_hijo += 1

    return padres, hijos