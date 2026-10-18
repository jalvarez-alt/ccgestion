"""Desprendible de pago en PDF (ReportLab)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERDE = colors.HexColor("#254AA5")
VERDE_CLARO = colors.HexColor("#EAEFFA")
GRIS = colors.HexColor("#5c5d5e")
LINEA = colors.HexColor("#c9cdcc")
MARGEN = 15 * mm
ANCHO = letter[0] - 2 * MARGEN

S = ParagraphStyle("n", fontName="Helvetica", fontSize=8.5, leading=10.5)
S_B = ParagraphStyle("b", parent=S, fontName="Helvetica-Bold")
S_R = ParagraphStyle("r", parent=S, alignment=2)
S_RB = ParagraphStyle("rb", parent=S_R, fontName="Helvetica-Bold")
S_T = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=VERDE)
S_PEQ = ParagraphStyle("p", parent=S, fontSize=7, leading=9, textColor=GRIS)
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def t(v):
    s = "" if v is None else str(v)
    return escape(s.encode("cp1252", "replace").decode("cp1252"))


def pesos(n):
    return "$ " + "{:,}".format(int(n)).replace(",", ".")


def nombre_periodo(per):
    return "%s quincena de %s de %s" % ("1.ª" if per["quincena"] == 1 else "2.ª", MESES[per["mes"]], per["anio"])


def generar_desprendible(empleador, empleado, periodo, calc, clave=None):
    """clave: si se indica, el PDF se abre solo con esa contraseña (se usa el número de documento)."""
    fi, ff = str(periodo["fecha_inicio"])[:10], str(periodo["fecha_fin"])[:10]
    story = [Paragraph("Desprendible de pago de nómina", S_T), Spacer(1, 2),
             Paragraph("<b>%s</b> &nbsp; NIT %s" % (t(empleador["nombre"]), t(empleador["nit"])), S), Spacer(1, 6)]

    datos = [
        [Paragraph("<b>Empleado</b>", S), Paragraph(t(empleado["nombre"]), S),
         Paragraph("<b>Documento</b>", S), Paragraph("%s %s" % (t(empleado.get("tipo_id")), t(empleado["num_id"])), S)],
        [Paragraph("<b>Cargo</b>", S), Paragraph(t(empleado.get("cargo") or "—"), S),
         Paragraph("<b>Salario básico</b>", S), Paragraph(pesos(empleado["salario"]), S)],
        [Paragraph("<b>Periodo</b>", S), Paragraph(t(nombre_periodo(periodo)), S),
         Paragraph("<b>Fechas</b>", S), Paragraph("%s al %s" % (t(fi), t(ff)), S)],
        [Paragraph("<b>Días trabajados</b>", S), Paragraph("%g" % calc.get("dias_trabajados", 0), S),
         Paragraph("<b>Banco / cuenta</b>", S),
         Paragraph(t(" ".join(x for x in (empleado.get("banco"), empleado.get("cuenta")) if x) or "—"), S)],
    ]
    tab = Table(datos, colWidths=[ANCHO * 0.17, ANCHO * 0.33, ANCHO * 0.17, ANCHO * 0.33])
    tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINEA), ("BACKGROUND", (0, 0), (0, -1), VERDE_CLARO),
                             ("BACKGROUND", (2, 0), (2, -1), VERDE_CLARO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [tab, Spacer(1, 8)]

    filas = [[Paragraph("<b>Concepto</b>", S_B), Paragraph("<b>Cant.</b>", S_RB),
              Paragraph("<b>Devengado</b>", S_RB), Paragraph("<b>Deducciones</b>", S_RB)]]
    for c in calc["conceptos"]:
        cant = "" if c.get("cantidad") is None else ("%g" % c["cantidad"])
        dev = pesos(c["valor"]) if c["tipo"] == "devengo" else ""
        ded = pesos(c["valor"]) if c["tipo"] == "deduccion" else ""
        filas.append([Paragraph(t(c["nombre"]), S), Paragraph(cant, S_R), Paragraph(dev, S_R), Paragraph(ded, S_R)])
    filas.append([Paragraph("<b>Totales</b>", S_B), "", Paragraph("<b>%s</b>" % pesos(calc["total_devengado"]), S_R),
                  Paragraph("<b>%s</b>" % pesos(calc["total_deducciones"]), S_R)])
    tc = Table(filas, colWidths=[ANCHO * 0.5, ANCHO * 0.1, ANCHO * 0.2, ANCHO * 0.2], repeatRows=1)
    tc.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VERDE_CLARO), ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
                            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f4f6f5")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [tc, Spacer(1, 8)]

    neto = Table([[Paragraph("<b>NETO A PAGAR</b>", ParagraphStyle("nn", parent=S_B, textColor=colors.white, fontSize=10)),
                   Paragraph("<b>%s</b>" % pesos(calc["neto"]),
                             ParagraphStyle("nv", parent=S_RB, textColor=colors.white, fontSize=11))]],
                 colWidths=[ANCHO * 0.5, ANCHO * 0.5])
    neto.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), VERDE), ("TOPPADDING", (0, 0), (-1, -1), 6),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [neto, Spacer(1, 6),
              Paragraph("Base de cotización (IBC) del periodo: %s." % pesos(calc["ibc"]), S_PEQ), Spacer(1, 10),
              Paragraph("Este desprendible es un documento informativo y confidencial dirigido al empleado. "
                        "Si encuentra diferencias, comuníquese con el área de nómina.", S_PEQ)]

    cifrado = StandardEncryption(str(clave), ownerPassword=None, canPrint=1, canModify=0, canCopy=0,
                                 canAnnotate=0, strength=128) if clave else None
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=14 * mm,
                            bottomMargin=14 * mm, title="Desprendible de pago", author=empleador["nombre"],
                            encrypt=cifrado)
    doc.build(story)
    return buf.getvalue()
