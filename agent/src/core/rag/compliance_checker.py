"""Verificación determinista de cumplimiento del Estatuto.

Complementa al LLM en el modo legal: las cuatro comprobaciones que se
hacen aquí (vacaciones, jornada, periodo de prueba y salario mínimo)
son las más típicas y, sobre todo, las más sensibles a errores de
razonamiento del modelo (números, comparaciones cuantitativas con la
ley). Aplicar regex + cálculo aritmético garantiza un veredicto exacto.

Las alertas se calculan al indexar el contrato (no al consultarlo) y
se persisten en SQLite junto con los manifiestos. El nodo de retrieval
las inyecta en el prompt del análisis legal para que el LLM disponga
de información factual sobre las infracciones.
"""

import re

from ..config import settings
from .metadata_extractor import _parse_numero

# El SMI cambia cada año por Real Decreto. Se inyecta desde settings
# para poder actualizarlo sin tocar este módulo.
_SMI_ANUAL = settings.smi_anual


# Las regex de detección comparten un patrón: capturan un número y un
# calificador opcional (naturales/laborables, semanales/diarias…) para
# poder aplicar la regla legal correcta según contexto.

# Vacaciones: el contrato puede expresar el dato en días naturales o
# laborables; el umbral del art. 38 ET difiere según la unidad.
_RE_VACACIONES_DIAS = re.compile(
    r"vacaciones\b[^.]*?(?<!\()\b(\d{1,2})\b(?!\))\s*d[ií]as\s*(naturales|laborables|h[áa]biles)?",
    re.IGNORECASE,
)

# Jornada semanal: el límite legal son 40h/semana (art. 34 ET).
_RE_JORNADA_SEMANAL = re.compile(
    r"(\d{1,2}(?:[.,]\d{1,2})?)\s*horas?\s*(?:semanales|a la semana|/\s*semana)",
    re.IGNORECASE,
)

# Jornada diaria: límite ordinario 9h/día (art. 34.3 ET).
_RE_JORNADA_DIARIA = re.compile(
    r"jornada\s+(?:laboral\s+)?(?:diaria\s+)?(?:de\s+)?(\d{1,2}(?:[.,]\d{1,2})?)\s*horas?\s*(?:diarias|al d[ií]a|/\s*d[ií]a)",
    re.IGNORECASE,
)

# Periodo de prueba: depende de si el trabajador es titulado o no
# (art. 14 ET). La unidad puede ser días o meses, normalizamos a meses.
_RE_PRUEBA = re.compile(
    r"per[ií]odo\s+de\s+prueba\b.*?(\d{1,2})\s*(mes(?:es)?|d[ií]as?)",
    re.IGNORECASE | re.DOTALL,
)

# Salario anual: regex permisiva para cubrir variaciones del SEPE
# ("retribución anual de XXX euros", "salario bruto anual XXX €"…).
_RE_SALARIO_ANUAL = re.compile(
    r"(?:retribuci[oó]n|salario|remuneraci[oó]n|retribuir[áa]\s+un\s+importe)"
    r".{0,80}?([\d][\d.,]+)\s*(?:euros?|EUR|€)"
    r"\s*(?:brut[ao]s?\s*)?(?:\([^)]*\)\s*)?anual",
    re.IGNORECASE | re.DOTALL,
)

# Salario mensual: alternativa cuando el contrato solo lo expresa
# mensualmente. Se estima el anual multiplicando por pagas_anuales.
_RE_SALARIO_MENSUAL = re.compile(
    r"(?:retribuci[oó]n|salario|remuneraci[oó]n)"
    r".{0,80}?([\d][\d.,]+)\s*(?:euros?|EUR|€)"
    r"\s*(?:brut[ao]s?\s*)?(?:\([^)]*\)\s*)?mensual",
    re.IGNORECASE | re.DOTALL,
)

# Grupo profesional del trabajador (clausulado del contrato).
# Buscamos "grupo profesional ... GRUPO" en el contrato real, no en
# texto explicativo. Sirve para distinguir titulados/técnicos de no titulados.
_RE_GRUPO_PROFESIONAL = re.compile(
    r"grupo\s+profesional\s+(?:de\s+)?([A-ZÁÉÍÓÚÑ/]+)",
    re.IGNORECASE,
)


def _es_titulado(texto: str) -> bool:
    """True si el trabajador es de un grupo técnico o de dirección."""
    for m in _RE_GRUPO_PROFESIONAL.finditer(texto):
        grupo = m.group(1).upper()
        # En el template SEPE los grupos son TECNICO, ADMINISTRATIVO, COMERCIAL, etc.
        if grupo in ("TECNICO", "TÉCNICO", "DIRECCION", "DIRECCIÓN"):
            return True
    return False



def _check_vacaciones(texto: str) -> list[dict]:
    alertas = []
    for m in _RE_VACACIONES_DIAS.finditer(texto):
        dias = int(m.group(1))
        tipo = (m.group(2) or "naturales").lower()

        if "laborab" in tipo or "habil" in tipo or "hábil" in tipo:
            if dias < 22:
                alertas.append({
                    "tipo": "vacaciones",
                    "severidad": "alta",
                    "articulo": "Art. 38 ET",
                    "mensaje": f"Vacaciones de {dias} dias laborables (minimo legal: 22 dias laborables / 30 naturales).",
                })
        else:  # naturales
            if dias < 30:
                alertas.append({
                    "tipo": "vacaciones",
                    "severidad": "alta",
                    "articulo": "Art. 38 ET",
                    "mensaje": f"Vacaciones de {dias} dias naturales (minimo legal: 30 dias naturales).",
                })
    return alertas


def _check_jornada(texto: str) -> list[dict]:
    alertas = []

    for m in _RE_JORNADA_SEMANAL.finditer(texto):
        horas = _parse_numero(m.group(1))
        if horas and horas > 40:
            alertas.append({
                "tipo": "jornada",
                "severidad": "alta",
                "articulo": "Art. 34 ET",
                "mensaje": f"Jornada semanal de {horas}h (maximo legal: 40h semanales).",
            })

    for m in _RE_JORNADA_DIARIA.finditer(texto):
        horas = _parse_numero(m.group(1))
        if horas and horas > 9:
            alertas.append({
                "tipo": "jornada",
                "severidad": "media",
                "articulo": "Art. 34.3 ET",
                "mensaje": f"Jornada diaria de {horas}h (maximo ordinario: 9h diarias).",
            })

    return alertas


def _check_periodo_prueba(texto: str) -> list[dict]:
    alertas = []
    titulado = _es_titulado(texto)

    for m in _RE_PRUEBA.finditer(texto):
        cantidad = int(m.group(1))
        unidad = m.group(2).lower()

        # Normalización a meses para comparar con el umbral del ET.
        # Aproximación 1 mes ≈ 30 días: el ET no especifica conversión
        # exacta y esta es la usada habitualmente en convenios.
        meses = cantidad
        if "dia" in unidad or "día" in unidad:
            meses = cantidad / 30

        # Art. 14.1 ET: titulados máximo 6 meses, resto máximo 2 meses.
        if titulado and meses > 6:
            alertas.append({
                "tipo": "periodo_prueba",
                "severidad": "alta",
                "articulo": "Art. 14 ET",
                "mensaje": f"Periodo de prueba de {cantidad} {m.group(2)} para titulado (maximo: 6 meses).",
            })
        elif not titulado and meses > 2:
            alertas.append({
                "tipo": "periodo_prueba",
                "severidad": "alta",
                "articulo": "Art. 14 ET",
                "mensaje": f"Periodo de prueba de {cantidad} {m.group(2)} para grupo no titulado (maximo: 2 meses).",
            })

    return alertas


def _check_salario(texto: str) -> list[dict]:
    alertas = []

    # Primero intentamos detectar el salario anual explícito. Es la
    # forma más fiable porque no depende del número de pagas.
    for m in _RE_SALARIO_ANUAL.finditer(texto):
        try:
            anual = _parse_numero(m.group(1))
            if anual < _SMI_ANUAL:
                alertas.append({
                    "tipo": "salario",
                    "severidad": "alta",
                    "articulo": "Art. 27 ET / RD SMI",
                    "mensaje": f"Salario anual bruto de {anual:,.0f} EUR — por debajo del SMI ({_SMI_ANUAL:,} EUR/ano).",
                })
        except (ValueError, OverflowError):
            pass

    # Solo si el contrato no expresa salario anual recurrimos al
    # mensual, para evitar generar dos alertas sobre el mismo contrato.
    if not alertas:
        for m in _RE_SALARIO_MENSUAL.finditer(texto):
            try:
                mensual = _parse_numero(m.group(1))
                anual_est = mensual * settings.pagas_anuales
                if anual_est < _SMI_ANUAL:
                    alertas.append({
                        "tipo": "salario",
                        "severidad": "alta",
                        "articulo": "Art. 27 ET / RD SMI",
                        "mensaje": f"Salario mensual de {mensual:,.0f} EUR (x14 = {anual_est:,.0f} EUR/ano) — por debajo del SMI ({_SMI_ANUAL:,} EUR/ano).",
                    })
            except (ValueError, OverflowError):
                pass

    return alertas


def verificar_cumplimiento(texto_completo: str) -> list[dict]:
    """Ejecuta todas las comprobaciones sobre el texto de un contrato."""
    alertas = []
    alertas.extend(_check_vacaciones(texto_completo))
    alertas.extend(_check_jornada(texto_completo))
    alertas.extend(_check_periodo_prueba(texto_completo))
    alertas.extend(_check_salario(texto_completo))
    return alertas
