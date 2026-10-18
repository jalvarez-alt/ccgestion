"""Genera el PDF del formato P01FOR007 con ReportLab (Python puro, ligero)."""
import base64
import re
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

import textos as T

AZUL = colors.HexColor("#254AA5")
GRIS = colors.HexColor("#52606d")
LINEA = colors.HexColor("#9aa5b1")
MARGEN = 14 * mm
ANCHO = letter[0] - 2 * MARGEN

S_CELDA = ParagraphStyle("celda", fontName="Helvetica", fontSize=8.5, leading=10.5)
S_TXT = ParagraphStyle("txt", fontName="Helvetica", fontSize=7.5, leading=9.5, alignment=4)
S_NOTA = ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=7, leading=9, textColor=GRIS)
S_SEC = ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=colors.white)
S_SUB = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=8.5, leading=10,
                       textColor=AZUL, spaceBefore=3, spaceAfter=1)
S_TIT = ParagraphStyle("tit", fontName="Helvetica-Bold", fontSize=10.5, leading=13, alignment=1)
S_EMP = ParagraphStyle("emp", fontName="Helvetica", fontSize=8, leading=10)
S_PEQ = ParagraphStyle("peq", fontName="Helvetica", fontSize=7, leading=9, textColor=GRIS)


# ---------------------------------------------------------------- utilidades
def t(valor):
    """Texto seguro para Paragraph (Helvetica solo soporta Latin-1/cp1252)."""
    s = "" if valor is None else str(valor)
    s = s.encode("cp1252", "replace").decode("cp1252")
    return escape(s).replace("\n", "<br/>")


def marca(activo):
    return "[X]" if activo else "[&nbsp;&nbsp;&nbsp;]"


def sino(valor):
    return "Sí %s &nbsp;&nbsp; No %s" % (marca(valor == "si"), marca(valor == "no"))


def fecha_fmt(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return s or ""


def miles(s):
    """Formatea 1234567 -> 1.234.567 si el valor es puramente numérico."""
    s = (s or "").strip()
    if s and re.fullmatch(r"[\s$\d.,-]+", s):
        limpio = re.sub(r"[^\d-]", "", s)
        if re.fullmatch(r"-?\d+", limpio):
            return "{:,}".format(int(limpio)).replace(",", ".")
    return s


def celda(etiqueta, valor="", raw=False):
    cuerpo = valor if raw else t(valor)
    return Paragraph('<font size="6.5" color="#52606d">%s</font><br/>%s'
                     % (t(etiqueta), cuerpo or "&nbsp;"), S_CELDA)


def fila(items, pesos=None):
    n = len(items)
    pesos = pesos or [1.0] * n
    total = float(sum(pesos))
    tabla = Table([items], colWidths=[ANCHO * p / total for p in pesos])
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabla


def encabezado_seccion(titulo):
    tabla = Table([[Paragraph(t(titulo), S_SEC)]], colWidths=[ANCHO])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def seccion(titulo, contenido):
    """Título + contenido; el título nunca queda solo al final de una página."""
    if not contenido:
        return [Spacer(1, 6), encabezado_seccion(titulo)]
    return [Spacer(1, 6), KeepTogether([encabezado_seccion(titulo), contenido[0]])] + contenido[1:]


def tabla_cuadro(cabecera, filas, pesos):
    """Tabla con fila de cabecera y filas de datos."""
    datos = [[Paragraph("<b>%s</b>" % t(c), ParagraphStyle("h", parent=S_CELDA, fontSize=7.5, leading=9))
              for c in cabecera]]
    for f in filas:
        datos.append([Paragraph(t(c) or "&nbsp;", S_CELDA) for c in f])
    total = float(sum(pesos))
    tabla = Table(datos, colWidths=[ANCHO * p / total for p in pesos], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


# ---------------------------------------------------------------- bloques
def encabezado_documento(d):
    izq = [Paragraph("<b>%s</b>" % t(T.EMPRESA), S_EMP), Paragraph("NIT %s" % T.NIT, S_EMP)]
    centro = Paragraph(t(T.TITULO), S_TIT)
    der = [Paragraph("<b>Código:</b> %s" % T.CODIGO, S_EMP)]
    tabla = Table([[izq, centro, der]], colWidths=[ANCHO * 0.28, ANCHO * 0.48, ANCHO * 0.24])
    tabla.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, AZUL), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    f = d.get("fecha", "")
    try:
        dt = datetime.strptime(f, "%Y-%m-%d")
        dia, mes, anio = "%02d" % dt.day, "%02d" % dt.month, str(dt.year)
    except ValueError:
        dia = mes = anio = ""
    c1 = celda("Fecha de diligenciamiento", "Día: %s &nbsp; Mes: %s &nbsp; Año: %s"
               % (t(dia), t(mes), t(anio)), raw=True)
    c2 = celda("Vinculación como", "Cliente %s &nbsp; Proveedor %s"
               % (marca(d.get("es_cliente")), marca(d.get("es_proveedor"))), raw=True)
    c3 = celda("Tipo de solicitud", "Nuevo %s &nbsp; Actualización %s"
               % (marca(d.get("solicitud") == "nuevo"), marca(d.get("solicitud") == "actualizacion")), raw=True)
    c4 = celda("Tipo de persona", "Natural %s &nbsp; Jurídica %s"
               % (marca(d.get("tipo_persona") == "natural"), marca(d.get("tipo_persona") == "juridica")), raw=True)
    return [tabla, Spacer(1, 3), fila([c1, c2, c3, c4], [0.29, 0.25, 0.27, 0.23])]


def filas_persona(d, p):
    g = lambda k: d.get(p + "_" + k, "")
    return [
        fila([celda("Nombre completo", g("nombre"))]),
        fila([celda("Tipo de identificación", g("tipo_id")), celda("Número de identificación", g("num_id")),
              celda("Fecha de expedición", fecha_fmt(g("fexp"))), celda("Lugar de expedición", g("lexp"))],
             [0.2, 0.28, 0.22, 0.30]),
        fila([celda("Lugar de nacimiento", g("lnac")), celda("Fecha de nacimiento", fecha_fmt(g("fnac"))),
              celda("Departamento", g("depto")), celda("Nacionalidad", g("nacionalidad"))]),
        fila([celda("Ciudad", g("ciudad")), celda("Dirección", g("dir")),
              celda("Teléfono de contacto", g("tel")), celda("Correo electrónico", g("email"))],
             [0.2, 0.3, 0.2, 0.3]),
    ]


def bloque_financiero(d, n, titulo):
    p = "fin%d_" % n
    g = lambda k: d.get(p + k, "")
    anio = g("anio")
    cab = Paragraph(t(titulo) + ((" — " + t(anio)) if anio else ""), S_SUB)
    return [
        cab,
        fila([celda("Ingresos mensuales ($)", miles(g("ingresos"))), celda("Egresos mensuales ($)", miles(g("egresos")))]),
        fila([celda("Activos ($)", miles(g("activos"))), celda("Pasivos ($)", miles(g("pasivos")))]),
        fila([celda("Patrimonio (Act. - Pas $)", miles(g("patrimonio"))), celda("Otros Ingresos ($)", miles(g("otros")))]),
        fila([celda("Concepto de otros ingresos mensuales", g("concepto"))]),
    ]


def imagen_firma(d):
    data = d.get("firma_img", "")
    prefijo = "data:image/png;base64,"
    if not data.startswith(prefijo):
        return None
    try:
        png = base64.b64decode(data[len(prefijo):])
        return Image(BytesIO(png), width=62 * mm, height=20 * mm)
    except Exception:
        return None


def lista_docs(items):
    return [Paragraph("[&nbsp;&nbsp;&nbsp;] " + t(i), ParagraphStyle("d", parent=S_CELDA, fontSize=7.5, leading=9.5,
                                                                    spaceAfter=2)) for i in items]


# ---------------------------------------------------------------- PDF
class CanvasNumerado(rl_canvas.Canvas):
    """Canvas que escribe 'Página X de Y' en el pie."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._estados = []

    def showPage(self):
        self._estados.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._estados)
        for estado in self._estados:
            self.__dict__.update(estado)
            self.setFont("Helvetica", 7)
            self.setFillColor(GRIS)
            self.drawRightString(letter[0] - MARGEN, 8 * mm, "Página %d de %d" % (self._pageNumber, total))
            super().showPage()
        super().save()


def generar_pdf(d):
    g = d.get
    story = encabezado_documento(d)
    natural = g("tipo_persona") == "natural"

    if natural:
        story += seccion("1. Persona Natural", filas_persona(d, "pn"))
    else:
        story += seccion("2. Persona Jurídica", [
            fila([celda("Razón social", g("pj_razon"))]),
            fila([celda("NIT", g("pj_nit")), celda("Ciudad", g("pj_ciudad")),
                  celda("Dirección", g("pj_dir")), celda("Teléfono de contacto", g("pj_tel"))],
                 [0.22, 0.2, 0.34, 0.24]),
        ])
        story += seccion("2.1 Representante Legal", filas_persona(d, "rl"))

    story += seccion("3. Información General", [
        fila([celda("Código CIIU", g("ciiu")), celda("Actividad económica", g("actividad")),
              celda("Sector económico", g("sector"))], [0.2, 0.4, 0.4]),
        fila([celda("Describa la actividad económica principal", g("descripcion"))]),
        fila([celda("¿Pertenece a gremios o asociaciones reconocidas?", sino(g("gremios")), raw=True),
              celda("En caso afirmativo, por favor cual", g("gremio_cual"))], [0.4, 0.6]),
    ])

    fin = [Paragraph(t(T.NOTA_FINANCIERA), S_NOTA)]
    fin += bloque_financiero(d, 1, "Primer año")
    fin += bloque_financiero(d, 2, "Segundo año")
    story += seccion("4. Información Financiera", fin)

    cuentas = [tabla_cuadro(["Entidad financiera", "Tipo de producto", "Nro. de producto"],
                            [[g("cta_entidad_%d" % i), g("cta_tipo_%d" % i), g("cta_num_%d" % i)]
                             for i in range(1, T.N_CUENTAS + 1)], [0.4, 0.3, 0.3]),
               Paragraph(t(T.NOTA_CUENTAS), S_NOTA)]
    story += seccion("4.1 Cuentas o productos financieros en entidades bancarias", cuentas)

    story += seccion("4.2 Operaciones en Moneda Extranjera y Activos Virtuales", [
        fila([celda("¿Realiza operaciones en moneda extranjera?", sino(g("mext")), raw=True),
              celda("Tipo de operación", g("mext_tipo")), celda("Moneda utilizadas", g("mext_moneda"))],
             [0.34, 0.33, 0.33]),
        fila([celda("¿Realiza operaciones en activos virtuales?", sino(g("avirt")), raw=True),
              celda("Tipo de virtual utilizado", g("avirt_tipo"))], [0.4, 0.6]),
    ])

    bf = [Paragraph(t(T.BF_TEXTO), S_TXT), Spacer(1, 2),
          tabla_cuadro(["Tipo de Documento", "No. Identificación", "Fecha de Expedición",
                        "Nombres y Apellidos", "Participación accionaria"],
                       [[g("bf_tipo_%d" % i), g("bf_num_%d" % i), fecha_fmt(g("bf_fexp_%d" % i)),
                         g("bf_nombre_%d" % i), g("bf_part_%d" % i)]
                        for i in range(1, T.N_BENEFICIARIOS + 1)], [0.16, 0.2, 0.17, 0.3, 0.17]),
          Spacer(1, 2), Paragraph(t(T.BF_NOTA), S_NOTA)]
    story += seccion("5. Información de Beneficiarios Finales", bf)

    story += seccion("6. Información relacionada con PEP (Persona Expuesta Políticamente)", [
        fila([celda(T.PEP_1, sino(g("pep1")), raw=True), celda("Indica", g("pep1_detalle"))], [0.6, 0.4]),
        fila([celda(T.PEP_2, sino(g("pep2")), raw=True), celda("Indica", g("pep2_detalle"))], [0.6, 0.4]),
        Paragraph(t(T.PEP_NOTA), S_NOTA),
    ])

    c = lambda k, txt: "%s %s" % (marca(g(k)), t(txt))
    story += seccion("7. Información Tributaria", [
        fila([celda("", c("trib_23", "23 - Agente de retención en ventas"), raw=True),
              celda("", c("trib_13", "13 - Gran Contribuyente"), raw=True),
              celda("Resolución", g("res_gran"))], [0.38, 0.3, 0.32]),
        fila([celda("", c("trib_47", "47 - Régimen simple de tributación"), raw=True),
              celda("", c("trib_49", "49 - No Responsable"), raw=True),
              celda("", c("trib_15", "15 - Autorretenedor"), raw=True),
              celda("Resolución", g("res_auto"))], [0.3, 0.22, 0.22, 0.26]),
    ])

    story += seccion("8. Referencias Comerciales", [
        tabla_cuadro(["Entidad", "Nombre del contacto", "Cargo", "Teléfono de contacto"],
                     [[g("ref_entidad_%d" % i), g("ref_contacto_%d" % i), g("ref_cargo_%d" % i), g("ref_tel_%d" % i)]
                      for i in range(1, T.N_REFERENCIAS + 1)], [0.3, 0.3, 0.2, 0.2])])

    story += seccion("9. Declaración de Origen, Destino de Fondos y/o Bienes", [
        Paragraph("<b>1.</b> " + t(T.DECL_1), S_TXT),
        fila([celda("", g("origen_fondos"))]),
        Spacer(1, 3),
        Paragraph("<b>2.</b> " + t(T.DECL_2), S_TXT), Spacer(1, 2),
        Paragraph("<b>3.</b> " + t(T.DECL_3), S_TXT), Spacer(1, 2),
        Paragraph("<b>4.</b> " + t(T.DECL_4), S_TXT),
    ])

    story += seccion("10. Autorización de Tratamiento de Datos Personales", [
        Paragraph(t(T.AUTORIZACION), S_TXT), Spacer(1, 3),
        Paragraph("<b>Autorización otorgada:</b> %s" % marca(g("acepta_datos")), S_CELDA),
    ])

    story += seccion("11. Documentos Solicitados", [
        Table([[Paragraph("<b>PERSONA NATURAL</b>", S_CELDA), Paragraph("<b>PERSONA JURIDICA</b>", S_CELDA)],
               [lista_docs(T.DOCS_NATURAL), lista_docs(T.DOCS_JURIDICA)]],
              colWidths=[ANCHO / 2, ANCHO / 2],
              style=TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINEA),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4e7eb")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP")]))])

    img = imagen_firma(d)
    firma = Table([[img if img else "", [Paragraph("<b>Nombre:</b> " + t(g("firma_nombre")), S_CELDA), Spacer(1, 4),
                                         Paragraph("<b>C.C.:</b> " + t(g("firma_cc")), S_CELDA)]],
                   [Paragraph("Firma del Solicitante (o Representante Legal)", S_PEQ), ""]],
                  colWidths=[ANCHO * 0.55, ANCHO * 0.45], rowHeights=[23 * mm, None])
    firma.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, LINEA), ("LINEABOVE", (0, 1), (0, 1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += seccion("12. Firma", [Paragraph(t(T.FIRMA_TEXTO), S_TXT), Spacer(1, 3), firma])

    caja = Table([[""]], colWidths=[ANCHO], rowHeights=[16 * mm])
    caja.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, LINEA)]))
    story += seccion("13. Espacio Exclusivo para la Empresa - Validación y Confirmación de Datos", [
        fila([celda("Nombre de quien realiza la verificación"), celda("Cargo"), celda("Fecha"),
              celda("Hora", "&nbsp;&nbsp; A.M. [&nbsp;&nbsp;&nbsp;] &nbsp; P.M. [&nbsp;&nbsp;&nbsp;]", raw=True)],
             [0.38, 0.22, 0.17, 0.23]),
        Paragraph("Firma", S_PEQ), caja, Spacer(1, 3), Paragraph(t(T.NOTA_FINAL), S_NOTA),
    ])

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN,
                            topMargin=12 * mm, bottomMargin=16 * mm,
                            title="%s - Formato de vinculación" % T.CODIGO, author=T.EMPRESA)
    doc.build(story, canvasmaker=CanvasNumerado)
    return buf.getvalue()
