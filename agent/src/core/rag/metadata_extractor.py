"""Extracción de metadatos estructurados a partir del texto del contrato.

Estos metadatos se persisten en SQLite al indexar el documento y se
usan en dos sitios:

- El nodo `estadistica` los agrega para responder preguntas sobre
  salarios medios, distribución por tipo, etc.
- El nodo `temporal` filtra por fechas (vencimientos del mes, contratos
  firmados en X periodo).

Como los contratos vienen mayoritariamente en formato SEPE, los
patrones están optimizados para esa plantilla; los contratos de
formato libre caen al fallback más permisivo. Es preferible que un
campo quede vacío a forzar una extracción incorrecta, que envenenaría
los agregados estadísticos.
"""

import re
from datetime import date

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_RE_FECHA = re.compile(
    r"(\d{1,2})\s+de\s+("
    + "|".join(_MESES.keys())
    + r")\s+de\s+(\d{4})",
    re.IGNORECASE,
)

# Formato corto DD/MM/YYYY o DD-MM-YYYY (típico del template SEPE).
_RE_FECHA_NUM = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")

# Patrones para localizar la fecha de inicio del contrato. Los más
# específicos primero — el template SEPE usa "iniciándose la relación
# laboral en fecha DD/MM/YYYY".
_PATRONES_INICIO = [
    re.compile(r"inici[áa]ndose\s+la\s+relaci[oó]n\s+laboral\s+en\s+fecha\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", re.IGNORECASE),
    re.compile(r"fecha\s+de\s+inicio[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"con\s+efectos?\s+desde[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"fecha\s+de\s+incorporaci[oó]n[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"comenzar[áa]\s+(?:a prestar|sus)\s+servicios.*?(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})", re.IGNORECASE),
]

# Patrones para fecha de finalización (solo contratos temporales).
_PATRONES_FIN = [
    re.compile(r"finalizando\s+en\s+fecha\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", re.IGNORECASE),
    re.compile(r"fecha\s+de\s+finalizaci[oó]n[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"fecha\s+de\s+fin(?:alizaci[oó]n)?[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"vigencia\s+hasta[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"duraci[oó]n\s+hasta[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"finalizar[áa]\s+el\s+(.+)", re.IGNORECASE),
]

_PATRONES_TIPO = [
    (re.compile(r"contrato\s+de\s+trabajo\s+indefinido", re.IGNORECASE), "indefinido"),
    (re.compile(r"contrato\s+(?:de\s+trabajo\s+)?temporal", re.IGNORECASE), "temporal"),
    (re.compile(r"contrato\s+(?:de\s+trabajo\s+)?(?:de\s+)?duraci[oó]n\s+determinada", re.IGNORECASE), "temporal"),
    (re.compile(r"contrato\s+(?:de\s+trabajo\s+)?(?:en\s+)?pr[áa]cticas", re.IGNORECASE), "prácticas"),
    (re.compile(r"contrato\s+formativo", re.IGNORECASE), "prácticas"),
    (re.compile(r"PR[ÁA]CTICAS\s+PROFESIONALES", re.IGNORECASE), "prácticas"),
    (re.compile(r"contrato\s+(?:de\s+trabajo\s+)?(?:de\s+)?interinidad", re.IGNORECASE), "interinidad"),
    (re.compile(r"obra\s+o\s+servicio", re.IGNORECASE), "temporal"),
    (re.compile(r"circunstancias\s+de\s+la\s+producci[oó]n", re.IGNORECASE), "temporal"),
    (re.compile(r"INDEFINIDO", re.IGNORECASE), "indefinido"),
]


def _parse_fecha(texto: str) -> str | None:
    """Extrae la primera fecha en formato ISO (YYYY-MM-DD) del texto."""
    # Probamos primero con DD/MM/YYYY (formato más común en plantilla SEPE).
    m = _RE_FECHA_NUM.search(texto)
    if m:
        try:
            dia, mes, anio = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(anio, mes, dia).isoformat()
        except ValueError:
            pass
    # Después, formato largo "DD de MES de YYYY".
    match = _RE_FECHA.search(texto)
    if not match:
        return None
    dia = int(match.group(1))
    mes = _MESES.get(match.group(2).lower())
    año = int(match.group(3))
    if not mes:
        return None
    try:
        return date(año, mes, dia).isoformat()
    except ValueError:
        return None


_RE_SALARIO_ANUAL = [
    re.compile(
        r"(?:retribuci[oó]n|salario|remuneraci[oó]n)\s+(?:brut[ao]\s+)?anual\b.*?"
        r"([\d.,]+)\s*(?:euros?|EUR|€)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:retribuci[oó]n|salario)\s+(?:total|brut[ao])\s+(?:de\s+)?([\d.,]+)\s*(?:euros?|EUR|€)\s*(?:brutos?)?\s*.*?(?:anuales|/\s*año)",
        re.IGNORECASE | re.DOTALL,
    ),
]

_RE_SALARIO_MENSUAL = re.compile(
    r"(?:retribuci[oó]n|salario|remuneraci[oó]n)\s+(?:brut[ao]\s+)?mensual\b.*?"
    r"([\d.,]+)\s*(?:euros?|EUR|€)",
    re.IGNORECASE | re.DOTALL,
)

_RE_JORNADA_SEMANAL = re.compile(
    r"(\d{1,2}(?:[.,]\d{1,2})?)\s*horas?\s*(?:semanales|a la semana|/\s*semana)",
    re.IGNORECASE,
)

_RE_VACACIONES = [
    re.compile(r"vacaciones\b.*?(\d{1,2})\s*d[ií]as\s*(naturales|laborables|h[áa]biles)?", re.IGNORECASE | re.DOTALL),
    re.compile(r"(\d{1,2})\s*d[ií]as\s*(naturales|laborables|h[áa]biles)?\s*(?:de\s+)?vacaciones", re.IGNORECASE),
]

_RE_TRABAJADOR = re.compile(
    r"(?:D\.|D[oña]+\.?|Sr\.?|Sra\.?)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})",
)

# El template SEPE escribe el puesto entre "servicios como (3) PUESTO." e
# "incluido en el grupo profesional...". Es el formato más fiable.
_RE_PUESTO = re.compile(
    r"servicios?\s+como\s+(?:\(\d+\)\s*)?([A-ZÁÉÍÓÚÑ][\w/\sÁÉÍÓÚÑáéíóúñ\-]{3,60}?)\.\s*\n?\s*incluido\s+en\s+el\s+grupo",
    re.IGNORECASE,
)

_RE_EMPRESA = re.compile(
    r"(?:empresa|sociedad|entidad|mercantil)\s+(?:denominada\s+)?[\"']?([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s.,]+?(?:S\.?[AL]\.?U?\.?|S\.?L\.?L?\.?))",
    re.IGNORECASE,
)


def _parse_numero(texto: str) -> float | None:
    """Convierte un número en formato español/inglés a float.

    Maneja varios formatos:
    - "24.500,00" (español: punto miles, coma decimal)
    - "24500.00"  (inglés: punto decimal)
    - "14.000"    (puede ser 14000 con separador miles o 14.0 decimal,
                  se desambigua por la longitud de la parte fraccional)
    """
    limpio = texto.replace(" ", "")
    # Si tiene punto y coma, asumimos formato español: el punto es
    # separador de miles y la coma el decimal.
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif "," in limpio:
        # Solo coma → decimal español.
        limpio = limpio.replace(",", ".")
    elif "." in limpio:
        # Punto solo: ambiguo. "14.000" puede ser 14000 (miles) o 14.0.
        # Si tras el punto hay grupos de 3 dígitos, es separador de miles.
        partes = limpio.split(".")
        if all(len(p) == 3 for p in partes[1:]):
            limpio = limpio.replace(".", "")
    try:
        return float(limpio)
    except ValueError:
        return None


def extraer_metadatos(texto_completo: str) -> dict:
    """Extrae fecha_inicio, fecha_fin y tipo_contrato del contrato.

    Limita la búsqueda a la cabecera (primeros 6000 caracteres) por dos
    motivos: rendimiento, y especificidad (los datos clave están en las
    primeras cláusulas; buscarlos más adelante aumenta el riesgo de
    falsos positivos al cruzarse con anexos o referencias).
    """
    resultado = {
        "fecha_inicio": None,
        "fecha_fin": None,
        "tipo_contrato": "",
    }

    # El tipo se busca en los primeros 2000 chars: suele aparecer en el
    # título o primera cláusula del contrato.
    cabecera = texto_completo[:2000]
    for patron, tipo in _PATRONES_TIPO:
        if patron.search(cabecera):
            resultado["tipo_contrato"] = tipo
            break

    # Ventana de 6000 chars: en los contratos SEPE la cláusula CUARTA
    # (donde aparece la fecha de inicio) suele estar sobre la posición
    # 4000. Más allá hay anexos y boilerplate.
    ventana = texto_completo[:6000]

    for patron in _PATRONES_INICIO:
        match = patron.search(ventana)
        if match:
            fecha = _parse_fecha(match.group(0))
            if fecha:
                resultado["fecha_inicio"] = fecha
                break

    for patron in _PATRONES_FIN:
        match = patron.search(ventana)
        if match:
            fecha = _parse_fecha(match.group(0))
            if fecha:
                resultado["fecha_fin"] = fecha
                break

    return resultado


_RE_NOMBRE_FICHERO = re.compile(
    r"contrato(?:_\d+)?_([a-záéíóúñ]+)_([a-záéíóúñ]+)\.pdf",
    re.IGNORECASE,
)


def extraer_datos_estructurados(texto_completo: str, nombre_fichero: str = "") -> dict:
    """Extrae datos estructurados del contrato para comparativas globales.

    Devuelve un dict con campos cuantitativos (salario, jornada,
    vacaciones) y cualitativos (trabajador, empresa, puesto). Los
    valores son None si no se han podido extraer con fiabilidad: el
    nodo de estadísticas filtra esos casos al agregar.
    """
    datos = {
        "trabajador": None,
        "empresa": None,
        "puesto": None,
        "salario_anual": None,
        "jornada_semanal": None,
        "vacaciones_dias": None,
    }

    m = _RE_TRABAJADOR.search(texto_completo[:2000])
    if m:
        datos["trabajador"] = m.group(1).strip()

    # Fallback al nombre del fichero: convenio común "contrato_apellido_nombre.pdf".
    if not datos["trabajador"] and nombre_fichero:
        m = _RE_NOMBRE_FICHERO.search(nombre_fichero)
        if m:
            apellido = m.group(1).capitalize()
            nombre = m.group(2).capitalize()
            datos["trabajador"] = f"{nombre} {apellido}"

    m = _RE_EMPRESA.search(texto_completo[:2000])
    if m:
        datos["empresa"] = m.group(1).strip()

    # Lista de "puestos basura": cabeceras genéricas del SEPE que el
    # regex capturaría por error si no las filtramos explícitamente.
    _PUESTOS_BASURA = {"trabajo a desempeñar", "trabajo", "desempeñar", "las funciones"}
    m = _RE_PUESTO.search(texto_completo[:6000])
    if m:
        puesto = m.group(1).strip()
        if puesto.lower() not in _PUESTOS_BASURA:
            datos["puesto"] = puesto

    # Salario: prioridad al anual explícito; si no, estimamos desde el
    # mensual asumiendo 14 pagas (caso típico en convenios españoles).
    for patron in _RE_SALARIO_ANUAL:
        m = patron.search(texto_completo)
        if m:
            datos["salario_anual"] = _parse_numero(m.group(1))
            break
    if not datos["salario_anual"]:
        m = _RE_SALARIO_MENSUAL.search(texto_completo)
        if m:
            mensual = _parse_numero(m.group(1))
            if mensual:
                datos["salario_anual"] = round(mensual * 14, 2)

    m = _RE_JORNADA_SEMANAL.search(texto_completo)
    if m:
        datos["jornada_semanal"] = _parse_numero(m.group(1))

    for patron in _RE_VACACIONES:
        m = patron.search(texto_completo)
        if m:
            datos["vacaciones_dias"] = int(m.group(1))
            break

    return datos
