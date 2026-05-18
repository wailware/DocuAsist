"""Generador sintético de contratos en formato SEPE (copia básica).

Produce PDFs con la estructura visual del formulario SEPE oficial
(tablas, celdas y layout) para construir un corpus de prueba realista
sin exponer datos personales. Todos los contratos pertenecen a la
empresa ficticia "BIT BASE, S.L." y los datos personales se sortean
aleatoriamente desde listas predefinidas.

El objetivo es que un revisor del TFG pueda regenerar el corpus si lo
desea, manteniendo la reproducibilidad sin compartir contratos reales.

Uso:
    cd agent && uv run python scripts/generar_contratos.py
"""

import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

# ---------------------------------------------------------------------------
# Estilos — tamaños calibrados contra el PDF real de Daniel Villegas
# ---------------------------------------------------------------------------

_styles = getSampleStyleSheet()

S_COPIA = ParagraphStyle(
    "sepe_copia", parent=_styles["Normal"],
    fontSize=9, leading=11, fontName="Helvetica-Bold",
    alignment=TA_CENTER, spaceBefore=0, spaceAfter=0,
)
S_HEADER = ParagraphStyle(
    "sepe_header", parent=_styles["Normal"],
    fontSize=7.5, leading=9.5, alignment=TA_CENTER,
    fontName="Helvetica-Bold",
)
S_TITLE = ParagraphStyle(
    "sepe_title", parent=_styles["Normal"],
    fontSize=11, leading=13, alignment=TA_CENTER,
    fontName="Helvetica-Bold", spaceBefore=3 * mm, spaceAfter=3 * mm,
)
S_SECTION = ParagraphStyle(
    "sepe_section", parent=_styles["Normal"],
    fontSize=7.5, leading=9, fontName="Helvetica-Bold",
    spaceBefore=3 * mm, spaceAfter=0.5 * mm,
)
S_LABEL = ParagraphStyle(
    "sepe_label", parent=_styles["Normal"],
    fontSize=6, leading=7, fontName="Helvetica",
    textColor=colors.Color(0.35, 0.35, 0.35),
)
S_VALUE = ParagraphStyle(
    "sepe_value", parent=_styles["Normal"],
    fontSize=7.5, leading=9, fontName="Helvetica-Bold",
)
S_CLAUSE = ParagraphStyle(
    "sepe_clause", parent=_styles["Normal"],
    fontSize=7, leading=9.5, fontName="Helvetica",
    alignment=TA_JUSTIFY, spaceBefore=1.5 * mm, spaceAfter=0,
)
S_CLAUSE_BOLD = ParagraphStyle(
    "sepe_clause_b", parent=_styles["Normal"],
    fontSize=7, leading=9.5, fontName="Helvetica-Bold",
    alignment=TA_JUSTIFY, spaceBefore=1.5 * mm, spaceAfter=0,
)
S_FOOTNOTE = ParagraphStyle(
    "sepe_fn", parent=_styles["Normal"],
    fontSize=5, leading=6.5, fontName="Helvetica",
    textColor=colors.Color(0.35, 0.35, 0.35),
)
S_FIRMA = ParagraphStyle(
    "sepe_firma", parent=_styles["Normal"],
    fontSize=6.5, leading=8, fontName="Helvetica",
    alignment=TA_CENTER,
)
S_FSE = ParagraphStyle(
    "sepe_fse", parent=_styles["Normal"],
    fontSize=6.5, leading=8, fontName="Helvetica-Bold",
    alignment=TA_LEFT,
)
S_SMALL = ParagraphStyle(
    "sepe_small", parent=_styles["Normal"],
    fontSize=6.5, leading=8, fontName="Helvetica",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GRID_STYLE = [
    ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.black),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 1 * mm),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm),
    ("LEFTPADDING", (0, 0), (-1, -1), 1.5 * mm),
    ("RIGHTPADDING", (0, 0), (-1, -1), 1.5 * mm),
]


def _celda(label, value):
    """Label pequeño + valor en negrita."""
    parts = []
    if label:
        parts.append(Paragraph(label, S_LABEL))
    parts.append(Paragraph(str(value) if value else "", S_VALUE))
    return parts


def _tabla(data, widths, heights=None, extra_style=None):
    t = Table(data, colWidths=widths, rowHeights=heights)
    style = list(_GRID_STYLE)
    if extra_style:
        style.extend(extra_style)
    t.setStyle(TableStyle(style))
    return t


def _linea():
    return Paragraph("_" * 95, S_FOOTNOTE)


def _header_institucional():
    data = [[
        Paragraph("Cofinanciado por<br/>la Unión Europea", S_HEADER),
        Paragraph("<b>MINISTERIO<br/>DE TRABAJO<br/>Y ECONOMÍA SOCIAL</b>", S_HEADER),
        Paragraph("<b>SERVICIO PÚBLICO<br/>DE EMPLEO ESTATAL<br/>SEPE</b>", S_HEADER),
        Paragraph("<b>Fondos Europeos</b>", S_HEADER),
    ]]
    w = CONTENT_W / 4
    t = Table(data, colWidths=[w] * 4)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    return t


def _fse():
    return Paragraph("<b>FSE+&nbsp;&nbsp;Fondo Social Europeo Plus</b>", S_FSE)


# ---------------------------------------------------------------------------
# Página 1 — Datos empresa + trabajador + PRIMERA/SEGUNDA
# ---------------------------------------------------------------------------

def _pagina1(c):
    e = []
    e.append(Paragraph("** COPIA BASICA **", S_COPIA))
    e.append(_linea())
    e.append(Spacer(1, 0.5 * mm))

    # Footnotes 1-4 at top
    for fn in [
        "(1) Director/a, Gerente, etc.",
        "(2) Padre, madre, tutor/a o persona o institución que le tenga a su cargo.",
        "(3) Indicar la profesión, oficio o puesto de trabajo a desempeñar.",
        "(4) Las funciones pueden ser todas las del grupo profesional o solamente alguna de ellas.",
    ]:
        e.append(Paragraph(fn, S_FOOTNOTE))

    e.append(Spacer(1, 2 * mm))
    e.append(_header_institucional())

    # Título
    tipo_titulo = {
        "indefinido": "CONTRATO DE TRABAJO INDEFINIDO",
        "temporal": "CONTRATO DE TRABAJO DE DURACIÓN DETERMINADA",
        "practicas": "CONTRATO FORMATIVO PARA LA OBTENCIÓN DE LA PRÁCTICA PROFESIONAL",
    }
    e.append(Paragraph(tipo_titulo.get(c["tipo"], "CONTRATO DE TRABAJO"), S_TITLE))

    emp = c["empresa"]
    w2 = CONTENT_W / 2
    w3 = CONTENT_W / 3

    # DATOS DE LA EMPRESA
    e.append(Paragraph("<b>DATOS DE LA EMPRESA</b>", S_SECTION))

    e.append(_tabla([[_celda("CIF/NIF/NIE", emp["cif"])]], [CONTENT_W], [11 * mm]))

    e.append(_tabla([[
        _celda("D./DÑA.", emp["representante"]),
        _celda("NIF/NIE", emp["nif_repr"]),
        _celda("EN CONCEPTO (1)", emp["concepto"]),
    ]], [CONTENT_W * 0.45, CONTENT_W * 0.25, CONTENT_W * 0.30], [11 * mm]))

    e.append(_tabla([[
        _celda("NOMBRE O RAZÓN SOCIAL DE LA EMPRESA", emp["nombre"]),
        _celda("DOMICILIO SOCIAL", emp["domicilio"]),
    ]], [CONTENT_W * 0.55, CONTENT_W * 0.45], [11 * mm]))

    e.append(_tabla([[
        _celda("PAÍS", ""),
        _celda("MUNICIPIO", emp["municipio"]),
        _celda("C. POSTAL", emp["cp"]),
    ]], [w3, w3, w3], [11 * mm]))

    e.append(Spacer(1, 1 * mm))

    # DATOS DE LA CUENTA DE COTIZACIÓN
    e.append(Paragraph("<b>DATOS DE LA CUENTA DE COTIZACIÓN</b>", S_SECTION))
    e.append(_tabla([[
        _celda("RÉGIMEN", emp["regimen"]),
        _celda("CÓDIGO CUENTA COTIZACIÓN", emp["ccc"]),
        _celda("ACTIVIDAD ECONÓMICA", emp["actividad"]),
    ]], [CONTENT_W * 0.15, CONTENT_W * 0.30, CONTENT_W * 0.55], [13 * mm]))

    e.append(Spacer(1, 1 * mm))

    # DATOS DEL CENTRO DE TRABAJO
    ct = c.get("centro", {})
    e.append(Paragraph("<b>DATOS DEL CENTRO DE TRABAJO</b>", S_SECTION))
    e.append(_tabla([[
        _celda("PAÍS", ""),
        _celda("MUNICIPIO", ct.get("municipio", emp["municipio"])),
        _celda("", ct.get("cp", emp["cp"])),
    ]], [w3, w3, w3], [11 * mm]))

    e.append(Spacer(1, 1 * mm))

    # DATOS DEL TRABAJADOR (copia básica: censurado)
    e.append(Paragraph("<b>DATOS DEL/DE LA TRABAJADOR/A</b>", S_SECTION))
    e.append(_tabla([[
        _celda("D./DÑA.", c["trabajador"]["nombre"]),
        _celda("NIF/NIE", c["trabajador"]["nif"]),
        _celda("FECHA NACIMIENTO", ""),
        _celda("Nº AFILIACIÓN SEGURIDAD SOCIAL", ""),
    ]], [CONTENT_W * 0.35, CONTENT_W * 0.18, CONTENT_W * 0.20, CONTENT_W * 0.27], [11 * mm]))

    e.append(_tabla([[
        _celda("NIVEL FORMATIVO", ""),
        _celda("NACIONALIDAD", ""),
    ]], [w2, w2], [11 * mm]))

    e.append(_tabla([[
        _celda("MUNICIPIO DEL DOMICILIO", ""),
        _celda("PAÍS DOMICILIO", ""),
    ]], [w2, w2], [11 * mm]))

    # DECLARAN
    e.append(Spacer(1, 2 * mm))
    e.append(Paragraph(
        "con la asistencia legal, en su caso, de D./Dña."
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "con NIF/NIE&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        ", en calidad de (2)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.",
        S_CLAUSE,
    ))
    e.append(Paragraph("<b>DECLARAN</b>", ParagraphStyle(
        "decl", parent=S_CLAUSE_BOLD, alignment=TA_CENTER, spaceBefore=2 * mm,
    )))
    e.append(Paragraph(
        "Que reúnen los requisitos exigidos para la celebración del presente contrato y, en su "
        "consecuencia, acuerdan formalizarlo con arreglo a las siguientes:",
        S_CLAUSE,
    ))

    # CLÁUSULAS
    e.append(Paragraph("<b>CLÁUSULAS</b>", ParagraphStyle(
        "cl_t", parent=S_CLAUSE_BOLD, alignment=TA_CENTER, spaceBefore=2 * mm,
    )))

    ct_dir = c.get("centro_direccion", emp["domicilio"])
    ct_muni = ct.get("municipio", emp["municipio"])

    e.append(Paragraph(
        f"<b>PRIMERA:</b> el/la trabajador/a prestará sus servicios como (3) "
        f"<b>{c['puesto']}</b>.<br/>"
        f"incluido en el grupo profesional de <b>{c['grupo']}</b>.<br/>"
        f"para la realización de las funciones (4) <b>TODAS LAS DE SU GRUPO PROFESIONAL</b>.<br/>"
        f"de acuerdo con el sistema de clasificación profesional vigente en la empresa. "
        f"En el centro de trabajo ubicado en (calle, nº y localidad) "
        f"<b>{ct_dir}</b>, <b>{ct_muni}</b>.",
        S_CLAUSE,
    ))

    # Trabajo a distancia
    e.append(Spacer(1, 1.5 * mm))
    e.append(Paragraph("Trabajo a distancia (5)", S_CLAUSE))

    # SEGUNDA
    if c["tipo"] == "temporal":
        e.append(Paragraph(
            f"<b>SEGUNDA:</b> el presente contrato se celebra por circunstancias de la producción, "
            f"al amparo del artículo 15.2 del Estatuto de los Trabajadores.<br/>"
            f"Causa justificativa: <b>{c.get('causa', 'incremento ocasional e imprevisible de la actividad')}</b>.<br/>"
            f"Duración prevista: <b>{c.get('duracion', '6 meses')}</b>.",
            S_CLAUSE,
        ))
    elif c["tipo"] == "practicas":
        e.append(Paragraph(
            f"<b>SEGUNDA:</b> el presente contrato formativo se celebra para la obtención de la "
            f"práctica profesional adecuada al nivel de estudios o de formación objeto del mismo, "
            f"al amparo del artículo 11.3 del Estatuto de los Trabajadores.<br/>"
            f"Titulación: <b>{c.get('titulacion', 'Grado Universitario')}</b>.<br/>"
            f"Duración prevista: <b>{c.get('duracion', '12 meses')}</b>.",
            S_CLAUSE,
        ))
    else:
        conv = emp["convenio"]
        e.append(Paragraph(
            "<b>SEGUNDA:</b> el contrato se concierta para realizar trabajos fijos discontinuos "
            "de acuerdo con el artículo 16 del Estatuto de los Trabajadores<br/>"
            "(6)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "dentro de la actividad cíclica intermitente de (7)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.<br/>"
            "La duración estimada de la actividad será de (8)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.<br/>"
            "La jornada estimada dentro del período de actividad será de "
            "&nbsp;&nbsp;&nbsp;&nbsp; horas (9)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.<br/>"
            f"y la distribución horaria estimada será <b>{c.get('distribucion_fijo', '')}</b>.<br/><br/>"
            "Los/as trabajadores/as serán llamados/as en el orden y forma que se determine en el "
            f"Convenio Colectivo de <b>{conv}</b> o acuerdo de empresa.<br/><br/>"
            "Si el convenio colectivo de ámbito sectorial permite en los contratos fijos-discontinuos "
            "utilizar la modalidad de tiempo parcial, indique si se acoge al mismo: "
            "&nbsp;&nbsp;&nbsp;SÍ&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;NO",
            S_CLAUSE,
        ))

    e.append(Spacer(1, 2 * mm))
    e.append(_fse())
    return e


# ---------------------------------------------------------------------------
# Página 2 — Notas a pie (5-18) + TERCERA a UNDÉCIMA
# ---------------------------------------------------------------------------

def _pagina2(c):
    e = []
    e.append(Paragraph("** COPIA BASICA **", S_COPIA))
    e.append(Spacer(1, 1 * mm))

    # Footnotes 5-18 at top (like the real form)
    footnotes = [
        "(5) El trabajo a distancia se regula por lo dispuesto en la Ley 10/2021, de 9 de julio y requiere la firma del correspondiente acuerdo.",
        "(6) Esta cláusula solo se cumplimentará en caso de desarrollar trabajos de carácter fijos discontinuos. Indicar la actividad profesional a desarrollar por el/la trabajador/a.",
        "(7) Indicar la actividad fija discontinua o de temporada de la empresa y su duración.",
        "(8) Diarios, semanales, mensuales o anuales. Detallar Convenio.",
        "(9) Indique el número de horas según convenio colectivo para jornada completa, máximo legal o lo del trabajador a tiempo completo.",
        "(10) Indíquese la jornada del trabajador.",
        '(11) Se entenderá por "trabajador a tiempo completo comparable" a un trabajador a tiempo completo de la misma empresa y centro de trabajo con el mismo tipo de contrato de trabajo y que realice un trabajo idéntico o similar. Si en la empresa no hubiera ningún trabajador comparable a tiempo completo, se considerará la jornada a tiempo completo prevista en el convenio colectivo de aplicación o, en su defecto, la jornada máxima legal.',
        "(12) Indique la distribución del tiempo de trabajo según el convenio colectivo.",
        "(13) Señálese lo que proceda y en caso afirmativo adjunte el anexo si hay horas complementarias.",
        "(14) Respetando lo establecido en el artículo 14.1 del Estatuto de los Trabajadores.",
        "(15) Diarios, semanales, mensuales o anuales.",
        "(16) Salario base, complementos salariales, pluses.",
        "(17) Mínimo: 30 días naturales.",
        "(18) Un mínimo del 25% y un máximo del 75%.",
    ]
    for fn in footnotes:
        e.append(Paragraph(fn, S_FOOTNOTE))

    e.append(Spacer(1, 2 * mm))
    e.append(_header_institucional())
    e.append(Spacer(1, 3 * mm))

    emp = c["empresa"]
    es_parcial = c.get("jornada_tipo", "completo") == "parcial"
    horas = c.get("horas_semana", 40)

    # TERCERA — jornada
    if es_parcial:
        horas_dia = c.get("horas_dia", 4)
        dist = c.get("distribucion", "LUNES A VIERNES - 9:00 A 13:00")
        tercera = (
            "<b>TERCERA:</b> la jornada de trabajo será:<br/><br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;A tiempo completo: la jornada de trabajo será de "
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; horas semanales, prestadas de &nbsp;&nbsp;&nbsp;, "
            "a &nbsp;&nbsp;&nbsp;, con los descansos establecidos legal o convencionalmente (10).<br/><br/>"
            f"&nbsp;&nbsp;<b>X</b>&nbsp;&nbsp;A tiempo parcial: la jornada de trabajo ordinaria será de "
            f"<b>{horas_dia:.2f}</b> horas &nbsp;&nbsp;al día, <b>X</b> a la semana, "
            "&nbsp;&nbsp; al mes, &nbsp;&nbsp; al año (6).<br/><br/>"
            "Siendo esta jornada inferior a la de un trabajador a tiempo completo comparable (11).<br/><br/>"
            f"La distribución del tiempo de trabajo será de (12) <b>{dist}</b>, "
            "conforme a lo previsto en el convenio colectivo.<br/><br/>"
            "En el caso de jornada a tiempo parcial señálese si existe o no pacto sobre la "
            "realización de horas complementarias (13):<br/>"
            "SÍ&nbsp;&nbsp;&nbsp;&nbsp;NO <b>X</b>"
        )
    else:
        tercera = (
            "<b>TERCERA:</b> la jornada de trabajo será:<br/><br/>"
            f"&nbsp;&nbsp;<b>X</b>&nbsp;&nbsp;A tiempo completo: la jornada de trabajo será de "
            f"<b>{horas:.2f}</b> horas semanales, prestadas de <b>lunes</b> a <b>viernes</b>, "
            "con los descansos establecidos legal o convencionalmente (10).<br/><br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;A tiempo parcial: la jornada de trabajo ordinaria será de "
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; horas al día, &nbsp;&nbsp; a la semana, "
            "&nbsp;&nbsp; al mes, &nbsp;&nbsp; al año (6)."
        )
    e.append(Paragraph(tercera, S_CLAUSE))

    # CUARTA — duración
    if c["tipo"] == "indefinido":
        cuarta = (
            f"<b>CUARTA:</b> la duración del presente contrato será <b>INDEFINIDA</b>, "
            f"iniciándose la relación laboral en fecha <b>{c['fecha_inicio']}</b>, "
            f"y se establece un período de prueba de (14) <b>{c['periodo_prueba']}</b>."
        )
    else:
        cuarta = (
            f"<b>CUARTA:</b> la duración del presente contrato será de <b>{c.get('duracion', '6 meses')}</b>, "
            f"iniciándose la relación laboral en fecha <b>{c['fecha_inicio']}</b> "
            f"y finalizando en fecha <b>{c.get('fecha_fin', '')}</b>, "
            f"y se establece un período de prueba de (14) <b>{c['periodo_prueba']}</b>."
        )
    e.append(Paragraph(cuarta, S_CLAUSE))

    # QUINTA — retribución
    sal = c.get("salario_texto", "Según Convenio")
    pagas = c.get("pagas", "12 PAGAS")
    conceptos = c.get("conceptos_salariales", "Según Convenio")
    e.append(Paragraph(
        f"<b>QUINTA:</b> el/la trabajador/a percibirá una retribución total de "
        f"<b>{sal}</b> euros brutos (15) <b>ANUALES X {pagas}</b> que se distribuirán en los "
        f"siguientes conceptos salariales (16) <b>{conceptos}</b>.",
        S_CLAUSE,
    ))

    # SEXTA — vacaciones
    vac = c.get("vacaciones", "23 días laborables")
    e.append(Paragraph(
        f"<b>SEXTA:</b> la duración de las vacaciones anuales será de (17) "
        f"<b>{vac} por año de trabajo</b> o proporcionales al alta.",
        S_CLAUSE,
    ))

    # SÉPTIMA — convenio
    e.append(Paragraph(
        f"<b>SÉPTIMA:</b> en lo no previsto en este contrato, se estará a la legislación "
        f"vigente que resulte de aplicación y particularmente en el Estatuto de los "
        f"Trabajadores y el Convenio Colectivo de <b>{emp['convenio']}</b>.",
        S_CLAUSE,
    ))

    # OCTAVA — relevo
    ct_dir = c.get("centro_direccion", emp["domicilio"])
    ct_muni = c.get("centro", {}).get("municipio", emp["municipio"])
    e.append(Paragraph(
        "<b>OCTAVA:</b> el presente contrato se formaliza bajo la modalidad de contrato "
        "de relevo: &nbsp;&nbsp;SÍ&nbsp;&nbsp;&nbsp;&nbsp;NO <b>X</b>.",
        S_CLAUSE,
    ))
    e.append(Paragraph(
        "El/la trabajador/a:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Que está en desempleo e inscrito/a como demandante en el "
        "Servicio Público de Empleo de ____________.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Que tiene concertado con la empresa un contrato de duración "
        "determinada que fue registrado en el Servicio Público de Empleo de __________, "
        "con el número __________ con fecha __________.",
        S_CLAUSE,
    ))
    e.append(Paragraph(
        "El/la representante de la empresa:<br/>"
        "Que el/la trabajador/a de la Empresa, D./Dña. __________, nacido el __________, "
        "que presta sus servicios en el centro de trabajo ubicado en (calle, nº y localidad) "
        f"<b>{ct_dir}</b>, <b>{ct_muni}</b> con la profesión de __________, "
        "incluido en el grupo profesional __________, de acuerdo con el sistema de clasificación "
        "profesional vigente en la empresa que reduce su jornada ordinaria de trabajo y su salario "
        "en un __________ (18) por acceder a la situación de jubilación parcial regulada por el "
        "artículo 215 del Real Decreto Legislativo 8/2015...",
        S_CLAUSE,
    ))

    # NOVENA
    e.append(Paragraph(
        "<b>NOVENA:</b> ESTE CONTRATO PODRÁ SER COFINANCIADO POR EL FONDO SOCIAL EUROPEO.",
        S_CLAUSE,
    ))

    # DÉCIMA
    e.append(Paragraph(
        "<b>DÉCIMA:</b> el contenido del presente contrato se comunicará al Servicio Público "
        "de Empleo de <b>CONTRAT@</b>, en el plazo de los 10 días hábiles siguientes a su concertación.",
        S_CLAUSE,
    ))

    # UNDÉCIMA
    e.append(Paragraph(
        "<b>UNDÉCIMA:</b> PROTECCIÓN DE DATOS. - Los datos consignados en el presente modelo "
        "tendrán la protección derivada del Reglamento (UE) 2016/679 del Parlamento Europeo, "
        "de 27 de abril de 2016 y de la Ley Orgánica 3/2018, de 5 de diciembre.",
        S_CLAUSE,
    ))

    e.append(Spacer(1, 2 * mm))
    e.append(_fse())
    return e


# ---------------------------------------------------------------------------
# Página 3 — Tipo de contrato con checkboxes
# ---------------------------------------------------------------------------

def _pagina3(c):
    e = []
    e.append(Paragraph("** COPIA BASICA **", S_COPIA))
    e.append(Spacer(1, 2 * mm))
    e.append(_header_institucional())
    e.append(Spacer(1, 6 * mm))

    if c["tipo"] == "indefinido":
        e.append(Paragraph(
            "Que el <b>CONTRATO INDEFINIDO</b> que se celebra (marque la casilla que corresponda) "
            "se realiza con las siguientes cláusulas específicas:",
            S_CLAUSE,
        ))
    elif c["tipo"] == "temporal":
        e.append(Paragraph(
            "Que el <b>CONTRATO DE DURACIÓN DETERMINADA</b> que se celebra (marque la casilla que corresponda) "
            "se realiza con las siguientes cláusulas específicas:",
            S_CLAUSE,
        ))
    else:
        e.append(Paragraph(
            "Que el <b>CONTRATO FORMATIVO</b> que se celebra (marque la casilla que corresponda) "
            "se realiza con las siguientes cláusulas específicas:",
            S_CLAUSE,
        ))

    e.append(Spacer(1, 4 * mm))

    # Opciones con checkbox
    if c["tipo"] == "indefinido":
        opciones = [
            ("INDEFINIDO ORDINARIO.", "Pág. 4", True),
            ("PARA PERSONAS CON DISCAPACIDAD.", "Pág. 5", False),
            ("PARA PERSONAS CON CAPACIDAD INTELECTUAL LÍMITE.", "Pág. 6", False),
            ("PARA PERSONAS CON DISCAPACIDAD EN CENTROS ESPECIALES DE EMPLEO.", "Pág. 7", False),
            ("PARA PERSONAS TRABAJADORAS READMITIDAS TRAS HABER CESADO EN LA EMPRESA POR INCAPACIDAD PERMANENTE TOTAL O ABSOLUTA.", "Pág. 8", False),
            ("PARA PERSONAS DESEMPLEADAS DE LARGA DURACIÓN.", "Pág. 9", False),
            ("PARA PERSONAS TRABAJADORAS EN SITUACIÓN DE EXCLUSIÓN SOCIAL.", "Pág. 10", False),
            ("PARA MUJERES TRABAJADORAS VÍCTIMAS DE VIOLENCIA DE GÉNERO, VÍCTIMAS DE VIOLENCIAS SEXUALES, VÍCTIMAS DE TRATA DE SERES HUMANOS, TANTO CON FINES DE EXPLOTACIÓN SEXUAL COMO LABORAL Y MUJERES EN CONTEXTO DE PROSTITUCIÓN, O PERSONAS VÍCTIMAS DE TERRORISMO.", "Pág. 11", False),
            ("PARA PERSONAS TRABAJADORAS EN SITUACIÓN DE EXCLUSIÓN SOCIAL EN EMPRESAS DE INSERCIÓN.", "Pág. 12", False),
            ("PARA PERSONAS TRABAJADORAS JÓVENES CON BAJA CUALIFICACIÓN BENEFICIARIAS DEL SISTEMA NACIONAL DE GARANTÍA JUVENIL.", "Pág. 13", False),
            ("PARA PERSONAS QUE REALIZAN FORMACIÓN PRÁCTICA EN EMPRESAS.", "Pág. 14", False),
            ("PARA PERSONAS PROCEDENTES DE UN CONTRATO FORMATIVO DE EMPRESAS DE TRABAJO TEMPORAL.", "Pág. 15", False),
            ("DE PERSONAS TRABAJADORAS DEL SERVICIO DEL HOGAR FAMILIAR.", "Pág. 16", False),
            ("CONVERSIÓN DE CONTRATO TEMPORAL EN CONTRATO INDEFINIDO.", "Pág. 17", False),
            ("OTRAS SITUACIONES.", "Pág. 18", False),
        ]
    elif c["tipo"] == "temporal":
        opciones = [
            ("POR CIRCUNSTANCIAS DE LA PRODUCCIÓN (art. 15.2 ET).", "Pág. 4", True),
            ("POR SUSTITUCIÓN DE PERSONA TRABAJADORA (art. 15.3 ET).", "Pág. 5", False),
            ("OTRAS SITUACIONES.", "Pág. 6", False),
        ]
    else:
        opciones = [
            ("CONTRATO FORMATIVO PARA LA OBTENCIÓN DE LA PRÁCTICA PROFESIONAL (art. 11.3 ET).", "Pág. 4", True),
            ("CONTRATO DE FORMACIÓN EN ALTERNANCIA (art. 11.2 ET).", "Pág. 5", False),
        ]

    data = []
    for texto, pag, marcado in opciones:
        data.append([
            Paragraph("<b>X</b>" if marcado else "", ParagraphStyle("chk", parent=S_VALUE, alignment=TA_CENTER)),
            Paragraph(texto, S_SMALL),
            Paragraph(pag, S_SMALL),
        ])

    chk_w = 10 * mm
    pag_w = 16 * mm
    txt_w = CONTENT_W - chk_w - pag_w

    t = Table(data, colWidths=[chk_w, txt_w, pag_w])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (0, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (0, -1), 0.3, colors.black),
        ("LINEAFTER", (1, 0), (1, -1), 0.3, colors.Color(0.7, 0.7, 0.7)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("LEFTPADDING", (0, 0), (0, -1), 1 * mm),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 1 * mm),
    ]))
    e.append(t)

    e.append(Spacer(1, 4 * mm))
    e.append(Paragraph(
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;y cumple los requisitos exigidos en la norma regulatoria.",
        S_CLAUSE,
    ))

    e.append(Spacer(1, 10 * mm))
    e.append(_fse())
    return e


# ---------------------------------------------------------------------------
# Página 4 — Código de contrato
# ---------------------------------------------------------------------------

def _pagina4(c):
    e = []
    e.append(Paragraph("** COPIA BASICA **", S_COPIA))
    e.append(Spacer(1, 2 * mm))
    e.append(_header_institucional())
    e.append(Spacer(1, 10 * mm))

    es_parcial = c.get("jornada_tipo", "completo") == "parcial"

    if c["tipo"] == "indefinido":
        subtipo = "INDEFINIDO ORDINARIO"
    elif c["tipo"] == "temporal":
        subtipo = "TEMPORAL POR CIRCUNSTANCIAS DE LA PRODUCCIÓN"
    else:
        subtipo = "CONTRATO FORMATIVO - PRÁCTICAS PROFESIONALES"

    # Tipo marcado en tabla
    e.append(_tabla(
        [[Paragraph(f"<b>X&nbsp;&nbsp;&nbsp;{subtipo}</b>", S_VALUE)]],
        [CONTENT_W], [9 * mm],
    ))

    e.append(Spacer(1, 15 * mm))

    # CÓDIGO DE CONTRATO (alineado a la derecha como en el real)
    e.append(Paragraph(
        "&nbsp;" * 100 + "<b>CÓDIGO DE CONTRATO</b>",
        ParagraphStyle("cod_t", parent=S_VALUE, alignment=TA_LEFT),
    ))
    e.append(Spacer(1, 4 * mm))

    rows = [
        ("", "TIEMPO COMPLETO", "1", "0", "0"),
        ("", "TIEMPO PARCIAL", "2", "0", "0"),
        ("", "FIJO DISCONTINUO", "3", "0", "0"),
    ]
    if es_parcial:
        rows = list(rows)
        rows[1] = ("X", "TIEMPO PARCIAL", "2", "0", "0")
    else:
        rows = list(rows)
        rows[0] = ("X", "TIEMPO COMPLETO", "1", "0", "0")

    data = []
    for mark, label, c1, c2, c3 in rows:
        data.append([
            Paragraph(f"<b>{mark}</b>", ParagraphStyle("chk2", parent=S_VALUE, alignment=TA_CENTER)),
            Paragraph(label, S_SMALL),
            Paragraph(f"<b>{c1}</b>", ParagraphStyle("d", parent=S_VALUE, alignment=TA_CENTER)),
            Paragraph(f"<b>{c2}</b>", ParagraphStyle("d", parent=S_VALUE, alignment=TA_CENTER)),
            Paragraph(f"<b>{c3}</b>", ParagraphStyle("d", parent=S_VALUE, alignment=TA_CENTER)),
        ])

    t = Table(data, colWidths=[10 * mm, 45 * mm, 9 * mm, 9 * mm, 9 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (0, -1), 0.5, colors.black),
        ("BOX", (2, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (2, 0), (-1, -1), 0.3, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
    ]))

    # Centrar la tabla un poco a la derecha
    wrapper = Table([[Spacer(1, 1), t]], colWidths=[55 * mm, 90 * mm])
    e.append(wrapper)

    e.append(Spacer(1, 40 * mm))
    e.append(_fse())
    return e


# ---------------------------------------------------------------------------
# Página 5 — Cláusulas adicionales + firmas
# ---------------------------------------------------------------------------

def _pagina5(c):
    e = []
    e.append(Paragraph("** COPIA BASICA **", S_COPIA))
    e.append(Spacer(1, 2 * mm))
    e.append(_header_institucional())
    e.append(Spacer(1, 4 * mm))

    e.append(Paragraph("<b>CLÁUSULAS ADICIONALES</b>", ParagraphStyle(
        "cl_ad", parent=S_CLAUSE_BOLD, alignment=TA_CENTER, fontSize=9,
    )))

    emp = c["empresa"]

    e.append(Paragraph(
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Y para que conste, se extiende este contrato por triplicado "
        "ejemplar en el lugar y fecha a continuación indicados, firmando las partes interesadas.",
        ParagraphStyle("ft", parent=S_CLAUSE, fontSize=6.5),
    ))
    e.append(Spacer(1, 2 * mm))

    lugar = c.get("lugar_firma", c.get("centro", {}).get("municipio", emp["municipio"]))
    e.append(Paragraph(
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;En <b>{lugar}</b>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;a <b>{c['fecha_firma']}</b>",
        ParagraphStyle("fl", parent=S_CLAUSE, fontSize=6.5),
    ))

    e.append(Spacer(1, 3 * mm))

    # Firma (4 columnas)
    firma = [[
        Paragraph("El/la Trabajador/a", S_FIRMA),
        Paragraph("El/la representante de<br/>la Empresa", S_FIRMA),
        Paragraph("El/la representante legal<br/>del/de la menor, si procede", S_FIRMA),
        Paragraph("El/la representante legal<br/>de los trabajadores", S_FIRMA),
    ]]
    fw = CONTENT_W / 4
    t = Table(firma, colWidths=[fw] * 4, rowHeights=[18 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.Color(0.6, 0.6, 0.6)),
    ]))
    e.append(t)

    e.append(Spacer(1, 4 * mm))
    e.append(Paragraph(
        "<b>IMPORTANTE</b><br/>"
        "(TODAS LAS PÁGINAS CUMPLIMENTADAS DE ESTE CONTRATO DEBERÁN IR FIRMADAS "
        "EN EL MARGEN IZQUIERDO PARA MAYOR SEGURIDAD JURÍDICA)",
        ParagraphStyle("imp", parent=S_CLAUSE, alignment=TA_CENTER, fontName="Helvetica-Bold"),
    ))

    e.append(Spacer(1, 6 * mm))

    # Cláusulas adicionales
    e.append(Paragraph(
        "<b>PRIMERA:</b> El/la trabajador/a declara haber recibido la formación, orientación e "
        "información que regulan los artículos 19 y 28 de la Ley de Riesgos Laborales, por lo que "
        "hace referencia a su trabajo dentro de la empresa.",
        S_CLAUSE,
    ))
    e.append(Paragraph(
        "<b>SEGUNDA:</b> El periodo de prueba se entiende de trabajo efectivo, por lo que este periodo, "
        "será interrumpido y prorrogado en caso de baja por Incapacidad Temporal o accidente.",
        S_CLAUSE,
    ))
    e.append(Paragraph(
        "<b>TERCERA:</b> En función de las necesidades del servicio y anunciándose previamente, podrá "
        "prestar sus servicios en horario distinto al habitual, incluidos sábados y domingos, así como "
        "si las necesidades lo requieren podrá cambiar el día de descanso semanal, incluido el domingo, "
        "respetando en cualquier caso el período de descanso reglamentariamente establecido, sustituyendo "
        "a tal efecto por descanso en día laborable.",
        S_CLAUSE,
    ))
    e.append(Paragraph(
        "<b>CUARTA:</b> En cumplimiento de lo dispuesto en el Reglamento (UE) 2016/679 de 27 de abril "
        "de 2016 (RGPD), la Ley Orgánica 3/2018 de 5 de diciembre de 2018 (LOPDGDD) y demás normativa "
        "legal vigente en materia de protección de datos personales, el/la trabajador/a da su consentimiento "
        f"a la empresa para que ceda sus datos personales a la asesoría <b>ALTIBEN S.L.</b>, que incluirá "
        "en un fichero, con la única finalidad de confeccionar su contrato de trabajo, sus nóminas y demás "
        "documentos oficiales.",
        S_CLAUSE,
    ))
    e.append(Paragraph(
        "<b>QUINTA:</b> La empresa y el/la trabajador/a acuerdan el prorrateo de las gratificaciones "
        "extraordinarias, de vacaciones (julio) y Navidad (diciembre).",
        S_CLAUSE,
    ))

    # Cláusulas adicionales opcionales (confidencialidad, no competencia, teletrabajo)
    for idx, clausula in enumerate(c.get("clausulas_extra", []), 6):
        e.append(Paragraph(clausula, S_CLAUSE))

    e.append(Spacer(1, 4 * mm))
    e.append(_fse())
    return e


# ---------------------------------------------------------------------------
# Generador
# ---------------------------------------------------------------------------

def generar_contrato(contrato: dict, output_path: Path):
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    elements = []
    elements.extend(_pagina1(contrato))
    elements.append(PageBreak())
    elements.extend(_pagina2(contrato))
    elements.append(PageBreak())
    elements.extend(_pagina3(contrato))
    elements.append(PageBreak())
    elements.extend(_pagina4(contrato))
    elements.append(PageBreak())
    elements.extend(_pagina5(contrato))
    doc.build(elements)


# ---------------------------------------------------------------------------
# Empresa ficticia — INNOVA CLOUD SOLUTIONS, S.L.
# ---------------------------------------------------------------------------

EMPRESAS = [
    {
        "nombre": "INNOVA CLOUD SOLUTIONS, S.L.",
        "cif": "B84567321",
        "representante": "ROMERO DELGADO, FERNANDO",
        "nif_repr": "52436178L",
        "concepto": "ADMINISTRADOR UNICO",
        "domicilio": "PASEO DE LA CASTELLANA 89",
        "municipio": "MADRID",
        "cp": "28046",
        "actividad": "Actividades de programación informática (CNAE 6201)",
        "regimen": "0111",
        "ccc": "28 1234567 89",
        "convenio": "EMPRESAS DE CONSULTORIA Y ESTUDIOS DE MERCADO",
        "centros": [
            {"municipio": "MADRID",    "cp": "28046", "direccion": "PASEO DE LA CASTELLANA 89"},
            {"municipio": "BARCELONA", "cp": "08036", "direccion": "CL DIAGONAL 477"},
        ],
    },
    {
        "nombre": "GRUPO SOLARIS INGENIERIA, S.A.",
        "cif": "A28765432",
        "representante": "MARTINEZ VEGA, PATRICIA",
        "nif_repr": "43218765B",
        "concepto": "DIRECTORA GENERAL",
        "domicilio": "CL GRAN VIA 32",
        "municipio": "MADRID",
        "cp": "28013",
        "actividad": "Servicios técnicos de ingeniería (CNAE 7112)",
        "regimen": "0111",
        "ccc": "28 2345678 01",
        "convenio": "EMPRESAS DE INGENIERIA Y OFICINAS DE ESTUDIOS TECNICOS",
        "centros": [
            {"municipio": "MADRID",    "cp": "28013", "direccion": "CL GRAN VIA 32"},
            {"municipio": "SEVILLA",   "cp": "41001", "direccion": "AVDA. DE LA CONSTITUCION 18"},
        ],
    },
    {
        "nombre": "NEXUS DIGITAL MEDIA, S.L.",
        "cif": "B91234567",
        "representante": "GARCIA FERNANDEZ, LUIS",
        "nif_repr": "12345678Z",
        "concepto": "ADMINISTRADOR UNICO",
        "domicilio": "CL DIAGONAL 477",
        "municipio": "BARCELONA",
        "cp": "08036",
        "actividad": "Edición de programas informáticos (CNAE 5829)",
        "regimen": "0111",
        "ccc": "08 3456789 12",
        "convenio": "INDUSTRIA QUIMICA",
        "centros": [
            {"municipio": "BARCELONA", "cp": "08036", "direccion": "CL DIAGONAL 477"},
            {"municipio": "VALENCIA",  "cp": "46004", "direccion": "CL COLON 60"},
        ],
    },
    {
        "nombre": "IBERIA LOGISTICA Y TRANSPORTE, S.A.",
        "cif": "A76543210",
        "representante": "LOPEZ RUIZ, ANDRES",
        "nif_repr": "87654321X",
        "concepto": "CONSEJERO DELEGADO",
        "domicilio": "AVDA. JUAN DE BORBON 38",
        "municipio": "MURCIA",
        "cp": "30007",
        "actividad": "Transporte de mercancías por carretera (CNAE 4941)",
        "regimen": "0111",
        "ccc": "30 4567890 23",
        "convenio": "TRANSPORTE DE MERCANCIAS POR CARRETERA",
        "centros": [
            {"municipio": "MURCIA",    "cp": "30007", "direccion": "AVDA. JUAN DE BORBON 38"},
            {"municipio": "ALICANTE",  "cp": "03001", "direccion": "CL RAMBLA MENDEZ NUÑEZ 12"},
        ],
    },
    {
        "nombre": "CLINICA SALUS INTEGRAL, S.L.",
        "cif": "B65432109",
        "representante": "SANCHEZ TORRES, ELENA",
        "nif_repr": "65432109W",
        "concepto": "ADMINISTRADORA SOLIDARIA",
        "domicilio": "CL DOCTOR FLEMING 5",
        "municipio": "VALENCIA",
        "cp": "46005",
        "actividad": "Actividades sanitarias (CNAE 8690)",
        "regimen": "0111",
        "ccc": "46 5678901 34",
        "convenio": "ESTABLECIMIENTOS SANITARIOS DE HOSPITALIZACION Y ASISTENCIA",
        "centros": [
            {"municipio": "VALENCIA",  "cp": "46005", "direccion": "CL DOCTOR FLEMING 5"},
            {"municipio": "CASTELLON", "cp": "12001", "direccion": "AVDA. DEL MAR 24"},
        ],
    },
]

# Alias para compatibilidad (empresa por defecto)
EMPRESA = EMPRESAS[0]

CENTROS = EMPRESA["centros"]

# ---------------------------------------------------------------------------
# Pools de datos para generación aleatoria (seed fijo = reproducible)
# ---------------------------------------------------------------------------

_NOMBRES_M = [
    "ANTONIO", "CARLOS", "DANIEL", "DAVID", "DIEGO", "EDUARDO", "ENRIQUE",
    "FRANCISCO", "GABRIEL", "GONZALO", "HUGO", "IVAN", "JAVIER", "JESUS",
    "JORGE", "JOSE", "JUAN", "LUIS", "MANUEL", "MARCOS", "MARIO", "MIGUEL",
    "NICOLAS", "PABLO", "PEDRO", "RAFAEL", "RAUL", "RICARDO", "ROBERTO",
    "RUBEN", "SAMUEL", "SANTIAGO", "SERGIO", "TOMAS", "VICTOR", "ADRIAN",
    "ALBERTO", "ALEJANDRO", "ALVARO", "ANDRES",
]

_NOMBRES_F = [
    "ANA", "ANDREA", "ANGELA", "BEATRIZ", "BLANCA", "CARMEN", "CAROLINA",
    "CLARA", "CLAUDIA", "CRISTINA", "DIANA", "ELENA", "EVA", "FATIMA",
    "GLORIA", "INES", "IRENE", "ISABEL", "LAURA", "LUCIA", "MARTA",
    "MARIA", "NATALIA", "NURIA", "OLIVIA", "PATRICIA", "PAULA", "RAQUEL",
    "ROCIO", "ROSA", "SARA", "SILVIA", "SOFIA", "SUSANA", "TERESA",
    "VALENTINA", "VERONICA", "VICTORIA", "VIRGINIA", "YOLANDA",
]

_APELLIDOS = [
    "GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "HERNANDEZ", "GONZALEZ",
    "SANCHEZ", "RUIZ", "FERNANDEZ", "JIMENEZ", "MORENO", "MUNOZ",
    "ALVAREZ", "ROMERO", "TORRES", "NAVARRO", "DIAZ", "GIL", "MORALES",
    "ORTIZ", "REYES", "MOLINA", "SERRANO", "BLANCO", "CASTRO", "SOTO",
    "MARQUEZ", "PEREZ", "GUTIERREZ", "MARTIN", "VEGA", "DOMINGUEZ",
    "CABALLERO", "PRIETO", "RAMOS", "MEDINA", "FUENTES", "HERRERO",
    "AGUILAR", "PENA", "DELGADO", "VARGAS", "CAMPOS", "FLORES",
    "LEON", "MORA", "SANTOS", "GALLEGO", "CANO", "CALVO",
]

# (puesto, grupo, salario_min, salario_max)
_PUESTOS = [
    ("ADMINISTRATIVO/A", "ADMINISTRATIVO", 18000, 26000),
    ("RECEPCIONISTA", "ADMINISTRATIVO", 16000, 22000),
    ("CONTABLE", "ADMINISTRATIVO", 24000, 32000),
    ("ASISTENTE DE RRHH", "ADMINISTRATIVO", 20000, 26000),
    ("GESTOR/A DOCUMENTAL", "ADMINISTRATIVO", 20000, 26000),
    ("AUXILIAR CONTABLE", "ADMINISTRATIVO", 18000, 24000),
    ("SECRETARIO/A DE DIRECCION", "ADMINISTRATIVO", 22000, 30000),
    ("PROGRAMADOR/A", "TECNICO", 28000, 42000),
    ("ANALISTA DE DATOS", "TECNICO", 30000, 40000),
    ("INGENIERO/A DE SISTEMAS", "TECNICO", 35000, 48000),
    ("TECNICO/A DE SOPORTE", "TECNICO", 20000, 28000),
    ("DESARROLLADOR/A WEB", "TECNICO", 26000, 38000),
    ("OPERADOR/A DE SISTEMAS", "TECNICO", 22000, 30000),
    ("ADMINISTRADOR/A DE BBDD", "TECNICO", 30000, 42000),
    ("ANALISTA DE SEGURIDAD", "TECNICO", 32000, 45000),
    ("ARQUITECTO/A DE SOFTWARE", "TECNICO", 40000, 55000),
    ("TECNICO/A DE REDES", "TECNICO", 24000, 34000),
    ("COMERCIAL", "COMERCIAL", 20000, 30000),
    ("ESPECIALISTA EN MARKETING", "COMERCIAL", 24000, 34000),
    ("DIRECTOR/A DE PROYECTO", "COMERCIAL", 40000, 55000),
    ("CONSULTOR/A", "COMERCIAL", 30000, 45000),
    ("COORDINADOR/A LOGISTICA", "COMERCIAL", 25000, 35000),
    ("AUDITOR/A INTERNO/A", "COMERCIAL", 28000, 38000),
    ("GESTOR/A DE CUENTAS", "COMERCIAL", 24000, 34000),
]

_CAUSAS_TEMPORALES = [
    "incremento ocasional e imprevisible de la actividad derivado del aumento de demanda en periodo estival",
    "necesidades de la producción derivadas de la puesta en marcha del nuevo sistema de gestión",
    "acumulación de tareas derivada del período de cierre contable y auditoría anual",
    "incremento de actividad derivado del lanzamiento de nuevo producto",
    "pico de trabajo derivado del cierre del ejercicio fiscal",
    "incremento de la demanda derivado de la campaña comercial de temporada alta",
    "necesidades productivas derivadas de la migración tecnológica en curso",
    "acumulación de tareas por ampliación de cartera de clientes",
    "refuerzo del departamento durante la implementación del nuevo sistema ERP",
    "incremento de la actividad derivado de nuevo contrato con administración pública",
]

_TITULACIONES = [
    ("Grado en Ingeniería Informática", "Universidad Politécnica de Madrid"),
    ("Grado en ADE", "Universidad de Murcia"),
    ("Grado en Marketing y Comunicación Digital", "Universidad de Barcelona"),
    ("Grado en Relaciones Laborales y RRHH", "Universidad de Valencia"),
    ("Grado en Economía", "UCAM"),
    ("Grado en Ingeniería de Telecomunicaciones", "UPC"),
    ("CFGS Desarrollo de Aplicaciones Web", "IES Francisco de Goya"),
    ("CFGS Administración y Finanzas", "IES Ramón y Cajal"),
    ("Grado en Estadística", "Universidad Complutense de Madrid"),
    ("Grado en Ingeniería del Software", "Universidad Autónoma de Barcelona"),
    ("Máster en Ciberseguridad", "Universidad Politécnica de Cartagena"),
    ("Grado en Matemáticas", "Universidad de Murcia"),
]

_DISTRIBUCIONES_PARCIAL = [
    "LUNES A VIERNES - 9:00 A 14:00",
    "LUNES A VIERNES - 8:00 A 12:00",
    "LUNES A VIERNES - 15:00 A 19:00",
    "LUNES, MIERCOLES Y VIERNES - 9:00 A 15:00",
    "LUNES A JUEVES - 9:00 A 13:00",
    "LUNES A VIERNES - 16:00 A 20:00",
    "MARTES A SABADO - 10:00 A 14:00",
    "LUNES A VIERNES - 8:00 A 13:00",
]

# Cláusulas adicionales opcionales (no todos los contratos las tienen)
_CLAUSULAS_CONFIDENCIALIDAD = (
    "<b>CONFIDENCIALIDAD:</b> El/la trabajador/a se compromete a mantener en secreto toda "
    "la información confidencial a la que tenga acceso en el desempeño de sus funciones, "
    "incluyendo datos de clientes, estrategias comerciales, know-how técnico y cualquier "
    "información que no sea de dominio público. Esta obligación subsistirá durante la vigencia "
    "del contrato y durante un plazo de <b>2 años</b> tras su extinción."
)

_CLAUSULAS_NO_COMPETENCIA = (
    "<b>NO COMPETENCIA POST-CONTRACTUAL:</b> El/la trabajador/a se obliga a no prestar servicios "
    "para empresas competidoras durante un periodo de <b>{duracion}</b> tras la finalización de "
    "la relación laboral, percibiendo como compensación económica adecuada la cantidad de "
    "<b>{compensacion} euros brutos</b>, conforme al artículo 21.2 del Estatuto de los Trabajadores."
)

_CLAUSULAS_TELETRABAJO = (
    "<b>TELETRABAJO:</b> De conformidad con la Ley 10/2021, de 9 de julio, de trabajo a distancia, "
    "las partes acuerdan que el/la trabajador/a podrá prestar sus servicios en modalidad de trabajo "
    "a distancia un máximo de <b>{dias} días a la semana</b>, debiendo acudir presencialmente al "
    "centro de trabajo los días restantes. La empresa proporcionará los medios tecnológicos "
    "necesarios y compensará los gastos asociados al teletrabajo según lo previsto en el convenio colectivo."
)

_MESES_ESP = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}

_DNI_LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"


# ---------------------------------------------------------------------------
# Helpers de generación
# ---------------------------------------------------------------------------

def _calcular_dni(num: int) -> str:
    """DNI español válido: 8 dígitos + letra de control."""
    return f"{num:08d}{_DNI_LETRAS[num % 23]}"


def _formato_salario(n: int) -> str:
    """42000 → '42.000' (formato español)."""
    return f"{n:,}".replace(",", ".")


def _fecha_firma_texto(d: date) -> str:
    """date → '28 de FEBRERO de 2024'."""
    return f"{d.day} de {_MESES_ESP[d.month]} de {d.year}"


def _fecha_ddmmyyyy(d: date) -> str:
    """date → '01/03/2024'."""
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _sumar_meses(d: date, meses: int) -> date:
    """Suma N meses a una fecha, ajustando el día si el mes destino es más corto."""
    import calendar
    month = d.month + meses
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, max_day))


# ---------------------------------------------------------------------------
# Generador de datos de contratos
# ---------------------------------------------------------------------------

def _generar_contratos(n: int = 200, seed: int = 42) -> list[dict]:
    """
    Genera N contratos con datos realistas y reproducibles (seed fijo).
    Distribución: 50% indef TC, 17.5% indef TP, 20% temporal, 12.5% prácticas.
    """
    rng = random.Random(seed)

    # --- Nombres únicos: APELLIDO1 APELLIDO2, NOMBRE ---
    todos_nombres = _NOMBRES_M + _NOMBRES_F
    used = set()
    combos = []
    intentos = 0
    while len(combos) < n and intentos < n * 20:
        nombre = rng.choice(todos_nombres)
        ap1 = rng.choice(_APELLIDOS)
        ap2 = rng.choice(_APELLIDOS)
        if ap1 != ap2:
            key = (ap1, ap2, nombre)
            if key not in used:
                used.add(key)
                combos.append(key)
        intentos += 1

    # --- Distribución de tipos de contrato ---
    n_indef_tc = int(n * 0.50)
    n_indef_tp = int(n * 0.175)
    n_temporal = int(n * 0.20)
    n_practicas = n - n_indef_tc - n_indef_tp - n_temporal

    tipos = (
        [("indefinido", False)] * n_indef_tc
        + [("indefinido", True)] * n_indef_tp
        + [("temporal", False)] * n_temporal
        + [("practicas", False)] * n_practicas
    )
    rng.shuffle(tipos)

    # --- Pools de fechas ---
    fechas_indef = [date(y, m, d)
                    for y in range(2022, 2026) for m in range(1, 13) for d in (1, 15)]
    fechas_recientes = [date(y, m, d)
                        for y in range(2024, 2026) for m in range(1, 13) for d in (1, 15)]

    # --- Generación ---
    contratos = []
    dni_base = 10000000

    for i in range(n):
        ap1, ap2, nombre_pila = combos[i]
        tipo, es_parcial = tipos[i]

        # Empresa aleatoria (distribución ponderada: primera empresa más frecuente)
        pesos_empresa = [35, 20, 20, 15, 10]  # % aprox por empresa
        empresa = rng.choices(EMPRESAS, weights=pesos_empresa, k=1)[0]
        centros_emp = empresa.get("centros", [{"municipio": empresa["municipio"], "cp": empresa["cp"], "direccion": empresa["domicilio"]}])

        puesto, grupo, sal_min, sal_max = rng.choice(_PUESTOS)
        centro_data = rng.choice(centros_emp)
        centro = {"municipio": centro_data["municipio"], "cp": centro_data["cp"]}

        # Salario (redondeado a 500 EUR)
        salario = rng.randint(sal_min // 500, sal_max // 500) * 500
        if es_parcial:
            horas_dia = rng.choice([3.0, 4.0, 5.0, 6.0])
            salario = round(salario * horas_dia / 8.0 / 500) * 500
            salario = max(salario, 10000)
        if tipo == "practicas":
            tope = (sal_min + sal_max) // 2
            salario = rng.randint(max(15000, sal_min) // 500, tope // 500) * 500

        pagas_n = rng.choice([12, 14])

        # Fechas
        if tipo in ("temporal", "practicas"):
            fecha_inicio = rng.choice(fechas_recientes)
            dur_opciones = [3, 4, 6, 9, 12] if tipo == "temporal" else [6, 9, 12]
            duracion_meses = rng.choice(dur_opciones)
            fecha_fin = _sumar_meses(fecha_inicio, duracion_meses) - timedelta(days=1)
        else:
            fecha_inicio = rng.choice(fechas_indef)
            duracion_meses = None
            fecha_fin = None

        fecha_firma_d = fecha_inicio - timedelta(days=rng.randint(2, 10))

        # Periodo de prueba (según ley y grupo)
        if tipo == "practicas":
            periodo = "1 Mes"
        elif tipo == "temporal":
            periodo = "1 Mes" if duracion_meses <= 6 else "2 Meses"
        elif grupo == "TECNICO":
            periodo = rng.choice(["3 Meses", "6 Meses"])
        else:
            periodo = rng.choice(["1 Mes", "2 Meses", "3 Meses"])

        # Conceptos salariales
        if tipo == "practicas":
            conceptos = "Según Convenio, no inferior al 60% del salario del grupo profesional"
        elif salario >= 30000:
            base_m = round(salario * 0.7 / pagas_n)
            comp_m = round(salario * 0.3 / pagas_n)
            conceptos = (f"Salario base {base_m} EUR/mes más "
                         f"complemento de puesto {comp_m} EUR/mes")
        elif salario >= 20000:
            conceptos = "Salario base más complementos según convenio"
        else:
            conceptos = "Según Convenio"

        vacaciones = rng.choice(["23 días laborables", "30 días naturales"])
        dni = _calcular_dni(dni_base + i * 397)

        contrato = {
            "empresa": empresa,
            "centro": centro,
            "centro_direccion": centro_data["direccion"],
            "trabajador": {
                "nombre": f"{ap1} {ap2}, {nombre_pila}",
                "nif": dni,
            },
            "tipo": tipo,
            "puesto": puesto,
            "grupo": grupo,
            "fecha_inicio": _fecha_ddmmyyyy(fecha_inicio),
            "periodo_prueba": periodo,
            "salario_texto": _formato_salario(salario),
            "pagas": f"{pagas_n} PAGAS",
            "conceptos_salariales": conceptos,
            "vacaciones": vacaciones,
            "fecha_firma": _fecha_firma_texto(fecha_firma_d),
        }

        if es_parcial:
            contrato["jornada_tipo"] = "parcial"
            contrato["horas_dia"] = horas_dia
            contrato["distribucion"] = rng.choice(_DISTRIBUCIONES_PARCIAL)

        if tipo == "temporal":
            contrato["causa"] = rng.choice(_CAUSAS_TEMPORALES)
            contrato["duracion"] = f"{duracion_meses} meses"
            contrato["fecha_fin"] = _fecha_ddmmyyyy(fecha_fin)

        if tipo == "practicas":
            tit, uni = rng.choice(_TITULACIONES)
            contrato["titulacion"] = f"{tit} por {uni}"
            contrato["duracion"] = f"{duracion_meses} meses"
            contrato["fecha_fin"] = _fecha_ddmmyyyy(fecha_fin)

        # Cláusulas adicionales opcionales (probabilidades por tipo)
        clausulas_extra = []
        if tipo == "indefinido" and salario >= 28000 and rng.random() < 0.35:
            clausulas_extra.append(_CLAUSULAS_CONFIDENCIALIDAD)
        if tipo == "indefinido" and grupo == "TECNICO" and rng.random() < 0.20:
            dur_nc = rng.choice(["6 meses", "1 año", "2 años"])
            comp_nc = _formato_salario(rng.choice([3000, 5000, 6000, 8000]))
            clausulas_extra.append(
                _CLAUSULAS_NO_COMPETENCIA.format(duracion=dur_nc, compensacion=comp_nc)
            )
        if tipo in ("indefinido", "temporal") and grupo == "TECNICO" and rng.random() < 0.30:
            dias_tt = rng.choice([1, 2, 3])
            clausulas_extra.append(
                _CLAUSULAS_TELETRABAJO.format(dias=dias_tt)
            )
        if clausulas_extra:
            contrato["clausulas_extra"] = clausulas_extra

        contratos.append(contrato)

    return contratos


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    output_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Limpiar contratos generados anteriormente (mantener daniel_villegas)
    for old in output_dir.glob("contrato_*.pdf"):
        if "daniel_villegas" not in old.name:
            old.unlink()
    for zi in output_dir.glob("*Zone.Identifier"):
        zi.unlink()

    contratos = _generar_contratos(200)

    print(f"Generando {len(contratos)} contratos de {len(EMPRESAS)} empresas...\n")

    for i, contrato in enumerate(contratos, 1):
        nombre_trab = contrato["trabajador"]["nombre"]
        partes = nombre_trab.replace(",", "").lower().split()
        filename = f"contrato_{i:03d}_{partes[0]}_{partes[-1]}.pdf"

        generar_contrato(contrato, output_dir / filename)
        if i % 20 == 0 or i == 1:
            print(f"  [{i:3d}/200] {filename} ({contrato['tipo']}, {contrato['empresa']['nombre'][:20]})")

    # Resumen
    from collections import Counter
    tipos = Counter(c["tipo"] for c in contratos)
    empresas_cnt = Counter(c["empresa"]["nombre"] for c in contratos)
    parciales = sum(1 for c in contratos if c.get("jornada_tipo") == "parcial")
    con_extras = sum(1 for c in contratos if c.get("clausulas_extra"))
    print(f"\n{len(contratos)} contratos generados en {output_dir}")
    print(f"\n  Por tipo:")
    print(f"    Indefinido TC: {tipos['indefinido'] - parciales}")
    print(f"    Indefinido TP: {parciales}")
    print(f"    Temporal:      {tipos['temporal']}")
    print(f"    Prácticas:     {tipos['practicas']}")
    print(f"\n  Por empresa:")
    for emp_name, cnt in empresas_cnt.most_common():
        print(f"    {emp_name}: {cnt}")
    print(f"\n  Con cláusulas especiales: {con_extras}")


if __name__ == "__main__":
    main()
