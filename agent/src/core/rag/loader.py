"""Carga de documentos del corpus y extracción de texto por página.

Punto único de entrada del pipeline de ingesta. La salida es una lista
de `Pagina`, que el chunker procesará después para generar los pares
padre-hijo. Conservar la numeración de páginas es crítico: las citas en
las respuestas referencian "Pág: N" y deben coincidir con la página
real del PDF original.

PDF se procesa con PyMuPDF (pymupdf) por ser el extractor más fiable
para formularios SEPE; DOCX y HTML se tratan como un único bloque ya
que no tienen paginación explícita.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup
from docx import Document


@dataclass
class Pagina:
    texto: str
    numero: int
    doc_nombre: str


def _cargar_pdf(ruta: Path) -> list[Pagina]:
    """Extrae texto página a página con PyMuPDF.

    Se descartan las páginas vacías (común en PDFs con páginas de
    portada o separadores) para no generar chunks artificiales.
    Numeración 1-based, coherente con la mostrada al usuario.
    """
    paginas = []
    doc = pymupdf.open(str(ruta))
    for i, pagina in enumerate(doc):
        texto = pagina.get_text().strip()
        if texto:
            paginas.append(Pagina(
                texto=texto,
                numero=i + 1,
                doc_nombre=ruta.name,
            ))
    doc.close()
    return paginas


def _cargar_docx(ruta: Path) -> list[Pagina]:
    """Extrae texto de un .docx como una sola página."""
    doc = Document(str(ruta))
    texto = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if not texto:
        return []
    return [Pagina(texto=texto, numero=1, doc_nombre=ruta.name)]


def _cargar_html(ruta: Path) -> list[Pagina]:
    """Extrae texto limpio de un fichero HTML eliminando etiquetas."""
    with open(ruta, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    texto = soup.get_text(separator="\n").strip()
    if not texto:
        return []
    return [Pagina(texto=texto, numero=1, doc_nombre=ruta.name)]


# Tabla de despacho extensión → extractor. Para añadir un nuevo formato
# basta con implementar la función y registrarla aquí.
_EXTRACTORES = {
    ".pdf":  _cargar_pdf,
    ".docx": _cargar_docx,
    ".html": _cargar_html,
    ".htm":  _cargar_html,
}

FORMATOS_SOPORTADOS = set(_EXTRACTORES.keys())


def cargar_documento(ruta: Path) -> list[Pagina]:
    """Detecta el formato y extrae el texto."""
    extension = ruta.suffix.lower()
    extractor = _EXTRACTORES.get(extension)
    if extractor is None:
        raise ValueError(
            f"Formato no soportado: '{extension}'. "
            f"Formatos válidos: {sorted(FORMATOS_SOPORTADOS)}"
        )
    return extractor(ruta)