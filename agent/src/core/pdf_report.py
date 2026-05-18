"""Generador de informes PDF de auditoría legal.

Construye un PDF descargable desde el frontend a partir de los datos
estructurados del contrato y las alertas del compliance_checker. Usa
ReportLab por ser la solución más estable de Python para layouts
tabulares y por no requerir dependencias externas (a diferencia de
WeasyPrint, que necesita Cairo). El estilo se mantiene minimalista
para que el PDF sea apto tanto para revisión interna como para
adjuntarse en comunicaciones legales.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)


_STYLES = getSampleStyleSheet()

_TITULO = ParagraphStyle(
    "Titulo",
    parent=_STYLES["Title"],
    fontSize=18,
    spaceAfter=6,
    textColor=colors.HexColor("#1a1a2e"),
)

_SUBTITULO = ParagraphStyle(
    "Subtitulo",
    parent=_STYLES["Heading2"],
    fontSize=13,
    spaceBefore=14,
    spaceAfter=6,
    textColor=colors.HexColor("#16213e"),
)

_NORMAL = ParagraphStyle(
    "Normal2",
    parent=_STYLES["Normal"],
    fontSize=10,
    leading=14,
)

_ALERTA_ALTA = ParagraphStyle(
    "AlertaAlta",
    parent=_STYLES["Normal"],
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#dc2626"),
)

_ALERTA_MEDIA = ParagraphStyle(
    "AlertaMedia",
    parent=_STYLES["Normal"],
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#d97706"),
)

_META = ParagraphStyle(
    "Meta",
    parent=_STYLES["Normal"],
    fontSize=9,
    textColor=colors.HexColor("#6b7280"),
)


def generar_informe_pdf(doc_info: dict, alertas: list, datos: dict) -> bytes:
    """Genera un informe PDF de auditoría legal para un contrato.

    Devuelve los bytes del PDF (no escribe a disco): el endpoint del API
    los reenvía directamente al cliente como descarga, evitando ficheros
    temporales en el servidor.
    """
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    contenido = []

    # Encabezado
    contenido.append(Paragraph("Informe de Auditoría Legal", _TITULO))
    contenido.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')} — DocuAsist",
        _META,
    ))
    contenido.append(Spacer(1, 8))
    contenido.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
    contenido.append(Spacer(1, 10))

    # Datos del documento
    contenido.append(Paragraph("Documento analizado", _SUBTITULO))

    info_rows = [
        ["Archivo", doc_info.get("nombre", "—")],
        ["Tipo de contrato", (doc_info.get("tipo_contrato") or "—").capitalize()],
        ["Fecha de inicio", doc_info.get("fecha_inicio") or "—"],
        ["Fecha de fin", doc_info.get("fecha_fin") or "—"],
    ]

    if datos.get("trabajador"):
        info_rows.append(["Trabajador/a", datos["trabajador"]])
    if datos.get("empresa"):
        info_rows.append(["Empresa", datos["empresa"]])
    if datos.get("puesto"):
        info_rows.append(["Puesto", datos["puesto"]])
    if datos.get("salario_anual"):
        info_rows.append(["Salario anual bruto", f"{datos['salario_anual']:,.0f} EUR"])
    if datos.get("jornada_semanal"):
        info_rows.append(["Jornada semanal", f"{datos['jornada_semanal']}h"])
    if datos.get("vacaciones_dias"):
        info_rows.append(["Vacaciones", f"{datos['vacaciones_dias']} días"])

    tabla_info = Table(info_rows, colWidths=[120, 350])
    tabla_info.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
    ]))
    contenido.append(tabla_info)
    contenido.append(Spacer(1, 10))

    # Resumen
    if doc_info.get("resumen"):
        contenido.append(Paragraph("Resumen", _SUBTITULO))
        contenido.append(Paragraph(doc_info["resumen"], _NORMAL))
        contenido.append(Spacer(1, 8))

    # Resultado de auditoría
    contenido.append(Paragraph("Resultado de la auditoría", _SUBTITULO))

    if not alertas:
        contenido.append(Paragraph(
            "No se han detectado posibles incumplimientos del Estatuto de los Trabajadores "
            "en las cláusulas analizadas (vacaciones, jornada, periodo de prueba, salario mínimo).",
            _NORMAL,
        ))
        contenido.append(Spacer(1, 6))
        contenido.append(Paragraph(
            "Resultado: CONFORME",
            ParagraphStyle("Ok", parent=_NORMAL, fontSize=12, textColor=colors.HexColor("#059669"), fontName="Helvetica-Bold"),
        ))
    else:
        altas = [a for a in alertas if a["severidad"] == "alta"]
        medias = [a for a in alertas if a["severidad"] == "media"]

        contenido.append(Paragraph(
            f"Se han detectado <b>{len(alertas)}</b> posible(s) incumplimiento(s): "
            f"{len(altas)} de severidad alta, {len(medias)} de severidad media.",
            _NORMAL,
        ))
        contenido.append(Spacer(1, 8))

        # Tabla de alertas
        header = [
            Paragraph("<b>Severidad</b>", _NORMAL),
            Paragraph("<b>Artículo</b>", _NORMAL),
            Paragraph("<b>Descripción</b>", _NORMAL),
        ]
        rows = [header]
        for a in alertas:
            sev_style = _ALERTA_ALTA if a["severidad"] == "alta" else _ALERTA_MEDIA
            rows.append([
                Paragraph(a["severidad"].upper(), sev_style),
                Paragraph(a["articulo"], _NORMAL),
                Paragraph(a["mensaje"], _NORMAL),
            ])

        tabla_alertas = Table(rows, colWidths=[70, 90, 310])
        tabla_alertas.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        contenido.append(tabla_alertas)

    # Disclaimer
    contenido.append(Spacer(1, 20))
    contenido.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d1d5db")))
    contenido.append(Spacer(1, 6))
    contenido.append(Paragraph(
        "Este informe ha sido generado automáticamente por DocuAsist mediante análisis "
        "basado en reglas sobre el texto del contrato. No constituye asesoramiento legal. "
        "Las comprobaciones cubren: vacaciones mínimas (Art. 38 ET), jornada máxima (Art. 34 ET), "
        "periodo de prueba (Art. 14 ET) y salario mínimo interprofesional (Art. 27 ET).",
        _META,
    ))

    pdf.build(contenido)
    return buffer.getvalue()
