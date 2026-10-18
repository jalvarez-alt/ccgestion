"""Etiquetas en español y formato de valores (web y Excel)."""
from datetime import date, datetime
from decimal import Decimal

REGISTRO_COLS = [
    ("id", "ID"), ("creada", "Fecha de registro"),
    ("fecha_diligenciamiento", "Fecha de diligenciamiento"),
    ("es_cliente", "Cliente"), ("es_proveedor", "Proveedor"),
    ("solicitud", "Tipo de solicitud"), ("tipo_persona", "Tipo de persona"),
    ("nombre", "Nombre / Razón social"), ("identificacion", "Identificación / NIT"),
    ("registrado_por", "Registrado por"),
    ("pn_nombre", "PN - Nombre completo"), ("pn_tipo_id", "PN - Tipo de identificación"),
    ("pn_num_id", "PN - Número de identificación"), ("pn_fecha_exp", "PN - Fecha de expedición"),
    ("pn_lugar_exp", "PN - Lugar de expedición"), ("pn_lugar_nac", "PN - Lugar de nacimiento"),
    ("pn_fecha_nac", "PN - Fecha de nacimiento"), ("pn_depto", "PN - Departamento"),
    ("pn_nacionalidad", "PN - Nacionalidad"), ("pn_ciudad", "PN - Ciudad"),
    ("pn_direccion", "PN - Dirección"), ("pn_telefono", "PN - Teléfono"),
    ("pn_email", "PN - Correo electrónico"),
    ("pj_razon_social", "PJ - Razón social"), ("pj_nit", "PJ - NIT"),
    ("pj_ciudad", "PJ - Ciudad"), ("pj_direccion", "PJ - Dirección"),
    ("pj_telefono", "PJ - Teléfono"),
    ("ciiu", "Código CIIU"), ("actividad_economica", "Actividad económica"),
    ("sector_economico", "Sector económico"),
    ("descripcion_actividad", "Descripción de la actividad principal"),
    ("gremios", "¿Pertenece a gremios?"), ("gremio_cual", "Gremio"),
    ("moneda_extranjera", "¿Opera en moneda extranjera?"),
    ("moneda_extranjera_tipo", "Tipo de operación"),
    ("moneda_extranjera_monedas", "Monedas utilizadas"),
    ("activos_virtuales", "¿Opera con activos virtuales?"),
    ("activos_virtuales_tipo", "Tipo de activo virtual"),
    ("pep_vinculados", "PEP: socios, junta o colaboradores"),
    ("pep_vinculados_detalle", "PEP: detalle (vinculados)"),
    ("pep_familiares", "PEP: relacionados con PEP"),
    ("pep_familiares_detalle", "PEP: detalle (familiares)"),
    ("trib_23_agente_retencion", "23 - Agente de retención en ventas"),
    ("trib_13_gran_contribuyente", "13 - Gran Contribuyente"),
    ("trib_47_regimen_simple", "47 - Régimen simple de tributación"),
    ("trib_49_no_responsable", "49 - No Responsable"),
    ("trib_15_autorretenedor", "15 - Autorretenedor"),
    ("resolucion_gran_contribuyente", "Resolución Gran Contribuyente"),
    ("resolucion_autorretenedor", "Resolución Autorretenedor"),
    ("origen_fondos", "Origen de fondos"),
    ("acepta_datos", "Aceptó tratamiento de datos"),
    ("firma_nombre", "Firmante - Nombre"), ("firma_cc", "Firmante - C.C."),
]
REPRESENTANTE_COLS = [
    ("nombre", "Nombre completo"), ("tipo_id", "Tipo de identificación"),
    ("num_id", "Número de identificación"), ("fecha_exp", "Fecha de expedición"),
    ("lugar_exp", "Lugar de expedición"), ("lugar_nac", "Lugar de nacimiento"),
    ("fecha_nac", "Fecha de nacimiento"), ("depto", "Departamento"),
    ("nacionalidad", "Nacionalidad"), ("ciudad", "Ciudad"), ("direccion", "Dirección"),
    ("telefono", "Teléfono"), ("email", "Correo electrónico"),
]
FINANCIERO_COLS = [
    ("periodo", "Periodo"), ("anio", "Año"),
    ("ingresos_mensuales", "Ingresos mensuales ($)"), ("egresos_mensuales", "Egresos mensuales ($)"),
    ("activos", "Activos ($)"), ("pasivos", "Pasivos ($)"), ("patrimonio", "Patrimonio ($)"),
    ("otros_ingresos", "Otros ingresos ($)"), ("concepto_otros_ingresos", "Concepto otros ingresos"),
]
CUENTAS_COLS = [("entidad", "Entidad financiera"), ("tipo_producto", "Tipo de producto"),
                ("numero_producto", "Nro. de producto")]
BENEFICIARIOS_COLS = [
    ("tipo_documento", "Tipo de documento"), ("num_identificacion", "No. identificación"),
    ("fecha_expedicion", "Fecha de expedición"), ("nombres_apellidos", "Nombres y apellidos"),
    ("participacion", "Participación accionaria"),
]
REFERENCIAS_COLS = [("entidad", "Entidad"), ("contacto", "Nombre del contacto"),
                    ("cargo", "Cargo"), ("telefono", "Teléfono de contacto")]

LABELS = {}
for _l in (REGISTRO_COLS, REPRESENTANTE_COLS, FINANCIERO_COLS, CUENTAS_COLS,
           BENEFICIARIOS_COLS, REFERENCIAS_COLS):
    for _c, _t in _l:
        LABELS.setdefault(_c, _t)

SECCIONES = [
    ("Datos de la solicitud", ["fecha_diligenciamiento", "creada", "registrado_por", "es_cliente",
                               "es_proveedor", "solicitud", "tipo_persona"], None),
    ("1. Persona natural", ["pn_nombre", "pn_tipo_id", "pn_num_id", "pn_fecha_exp", "pn_lugar_exp",
                            "pn_lugar_nac", "pn_fecha_nac", "pn_depto", "pn_nacionalidad",
                            "pn_ciudad", "pn_direccion", "pn_telefono", "pn_email"], "natural"),
    ("2. Persona jurídica", ["pj_razon_social", "pj_nit", "pj_ciudad", "pj_direccion",
                             "pj_telefono"], "juridica"),
    ("3. Información general", ["ciiu", "actividad_economica", "sector_economico",
                                "descripcion_actividad", "gremios", "gremio_cual"], None),
    ("4.2 Moneda extranjera y activos virtuales",
     ["moneda_extranjera", "moneda_extranjera_tipo", "moneda_extranjera_monedas",
      "activos_virtuales", "activos_virtuales_tipo"], None),
    ("6. Información PEP", ["pep_vinculados", "pep_vinculados_detalle", "pep_familiares",
                            "pep_familiares_detalle"], None),
    ("7. Información tributaria",
     ["trib_23_agente_retencion", "trib_13_gran_contribuyente", "resolucion_gran_contribuyente",
      "trib_47_regimen_simple", "trib_49_no_responsable", "trib_15_autorretenedor",
      "resolucion_autorretenedor"], None),
    ("9. Origen de fondos", ["origen_fondos"], None),
    ("10 y 12. Autorización y firma", ["acepta_datos", "firma_nombre", "firma_cc"], None),
]
COLS_BOOL = {"es_cliente", "es_proveedor", "acepta_datos", "trib_23_agente_retencion",
             "trib_13_gran_contribuyente", "trib_47_regimen_simple", "trib_49_no_responsable",
             "trib_15_autorretenedor"}
COLS_SN = {"gremios", "moneda_extranjera", "activos_virtuales", "pep_vinculados", "pep_familiares"}
COLS_DINERO = {"ingresos_mensuales", "egresos_mensuales", "activos", "pasivos", "patrimonio",
               "otros_ingresos"}
SOLICITUD = {"nuevo": "Nuevo", "actualizacion": "Actualización"}
TIPO_PERSONA = {"natural": "Persona Natural", "juridica": "Persona Jurídica"}
PERIODO = {1: "Primer año", 2: "Segundo año"}


def valor_plano(col, v):
    if v is None:
        return None
    if col in COLS_BOOL:
        return "Sí" if v else "No"
    if col in COLS_SN:
        return {"si": "Sí", "no": "No"}.get(v, v)
    if col == "solicitud":
        return SOLICITUD.get(v, v)
    if col == "tipo_persona":
        return TIPO_PERSONA.get(v, v)
    if col == "periodo":
        return PERIODO.get(int(v), v)
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


def mostrar(col, v):
    if v is None or v == "":
        return "—"
    v = valor_plano(col, v)
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if col in COLS_DINERO:
        return "{:,}".format(int(v)).replace(",", ".")
    if col == "participacion":
        return "%g %%" % float(v)
    return str(v)
