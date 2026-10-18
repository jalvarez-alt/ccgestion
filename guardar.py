"""Guarda cada formulario en tablas y columnas separadas (para reportes)."""
import json
import re
from datetime import datetime

import textos as T


# ------------------------------------------------------------ conversores
def txt(d, k):
    v = (d.get(k) or "").strip()
    return v[:300] or None


def largo(d, k):
    v = (d.get(k) or "").strip()
    return v[:3000] or None


def sn(d, k):
    v = d.get(k)
    return v if v in ("si", "no") else None


def flag(d, k):
    return 1 if d.get(k) else 0


def fecha(d, k):
    try:
        return datetime.strptime(d.get(k) or "", "%Y-%m-%d").date()
    except ValueError:
        return None


def dinero(d, k):
    s = re.sub(r",\d{1,2}$", "", (d.get(k) or "").strip())  # quita decimales ",50"
    s = re.sub(r"[^\d-]", "", s)
    return int(s) if re.fullmatch(r"-?\d{1,18}", s) else None


def anio(d, k):
    s = (d.get(k) or "").strip()
    return int(s) if re.fullmatch(r"\d{4}", s) else None


def porcentaje(d, k):
    m = re.search(r"\d+(?:[.,]\d+)?", d.get(k) or "")
    if not m:
        return None
    v = float(m.group(0).replace(",", "."))
    return v if v <= 9999.99 else None


def persona(d, p):
    return {
        "nombre": txt(d, p + "_nombre"), "tipo_id": txt(d, p + "_tipo_id"),
        "num_id": txt(d, p + "_num_id"), "fecha_exp": fecha(d, p + "_fexp"),
        "lugar_exp": txt(d, p + "_lexp"), "lugar_nac": txt(d, p + "_lnac"),
        "fecha_nac": fecha(d, p + "_fnac"), "depto": txt(d, p + "_depto"),
        "nacionalidad": txt(d, p + "_nacionalidad"), "ciudad": txt(d, p + "_ciudad"),
        "direccion": txt(d, p + "_dir"), "telefono": txt(d, p + "_tel"),
        "email": txt(d, p + "_email"),
    }


def insertar(cur, tabla, cols):
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (
        tabla, ", ".join(cols), ", ".join(["%s"] * len(cols)))
    cur.execute(sql, list(cols.values()))
    return cur.lastrowid


def tiene_datos(cols):
    return any(v is not None for v in cols.values())


# ------------------------------------------------------------ guardado
def guardar_registro(db, token, d, usuario_id=None):
    """Inserta el registro y todas sus tablas hijas en una sola transaccion."""
    natural = d.get("tipo_persona") == "natural"
    juridica = d.get("tipo_persona") == "juridica"

    principal = {
        "token": token,
        "usuario_id": usuario_id,
        "fecha_diligenciamiento": fecha(d, "fecha"),
        "es_cliente": flag(d, "es_cliente"),
        "es_proveedor": flag(d, "es_proveedor"),
        "solicitud": d.get("solicitud"),
        "tipo_persona": d.get("tipo_persona"),
    }
    if natural:
        for k, v in persona(d, "pn").items():
            principal["pn_" + k] = v
        principal["nombre"] = txt(d, "pn_nombre")
        principal["identificacion"] = txt(d, "pn_num_id")
    elif juridica:
        principal.update({
            "pj_razon_social": txt(d, "pj_razon"), "pj_nit": txt(d, "pj_nit"),
            "pj_ciudad": txt(d, "pj_ciudad"), "pj_direccion": txt(d, "pj_dir"),
            "pj_telefono": txt(d, "pj_tel"),
            "nombre": txt(d, "pj_razon"), "identificacion": txt(d, "pj_nit"),
        })
    principal.update({
        "ciiu": txt(d, "ciiu"), "actividad_economica": txt(d, "actividad"),
        "sector_economico": txt(d, "sector"),
        "descripcion_actividad": largo(d, "descripcion"),
        "gremios": sn(d, "gremios"), "gremio_cual": txt(d, "gremio_cual"),
        "moneda_extranjera": sn(d, "mext"),
        "moneda_extranjera_tipo": txt(d, "mext_tipo"),
        "moneda_extranjera_monedas": txt(d, "mext_moneda"),
        "activos_virtuales": sn(d, "avirt"),
        "activos_virtuales_tipo": txt(d, "avirt_tipo"),
        "pep_vinculados": sn(d, "pep1"), "pep_vinculados_detalle": largo(d, "pep1_detalle"),
        "pep_familiares": sn(d, "pep2"), "pep_familiares_detalle": largo(d, "pep2_detalle"),
        "trib_23_agente_retencion": flag(d, "trib_23"),
        "trib_13_gran_contribuyente": flag(d, "trib_13"),
        "trib_47_regimen_simple": flag(d, "trib_47"),
        "trib_49_no_responsable": flag(d, "trib_49"),
        "trib_15_autorretenedor": flag(d, "trib_15"),
        "resolucion_gran_contribuyente": txt(d, "res_gran"),
        "resolucion_autorretenedor": txt(d, "res_auto"),
        "origen_fondos": largo(d, "origen_fondos"),
        "acepta_datos": flag(d, "acepta_datos"),
        "firma_nombre": txt(d, "firma_nombre"), "firma_cc": txt(d, "firma_cc"),
        "firma_img": d.get("firma_img") or None,
        "datos": json.dumps(d, ensure_ascii=False),
    })

    try:
        with db.cursor() as cur:
            rid = insertar(cur, "registros", principal)

            if juridica:
                insertar(cur, "registro_representante", dict(registro_id=rid, **persona(d, "rl")))

            for n in (1, 2):
                p = "fin%d_" % n
                fin = {
                    "anio": anio(d, p + "anio"),
                    "ingresos_mensuales": dinero(d, p + "ingresos"),
                    "egresos_mensuales": dinero(d, p + "egresos"),
                    "activos": dinero(d, p + "activos"),
                    "pasivos": dinero(d, p + "pasivos"),
                    "patrimonio": dinero(d, p + "patrimonio"),
                    "otros_ingresos": dinero(d, p + "otros"),
                    "concepto_otros_ingresos": txt(d, p + "concepto"),
                }
                if tiene_datos(fin):
                    insertar(cur, "registro_financiero", dict(registro_id=rid, periodo=n, **fin))

            for i in range(1, T.N_CUENTAS + 1):
                fila = {"entidad": txt(d, "cta_entidad_%d" % i),
                        "tipo_producto": txt(d, "cta_tipo_%d" % i),
                        "numero_producto": txt(d, "cta_num_%d" % i)}
                if tiene_datos(fila):
                    insertar(cur, "registro_cuentas", dict(registro_id=rid, **fila))

            for i in range(1, T.N_BENEFICIARIOS + 1):
                fila = {"tipo_documento": txt(d, "bf_tipo_%d" % i),
                        "num_identificacion": txt(d, "bf_num_%d" % i),
                        "fecha_expedicion": fecha(d, "bf_fexp_%d" % i),
                        "nombres_apellidos": txt(d, "bf_nombre_%d" % i),
                        "participacion": porcentaje(d, "bf_part_%d" % i)}
                if tiene_datos(fila):
                    insertar(cur, "registro_beneficiarios", dict(registro_id=rid, **fila))

            for i in range(1, T.N_REFERENCIAS + 1):
                fila = {"entidad": txt(d, "ref_entidad_%d" % i),
                        "contacto": txt(d, "ref_contacto_%d" % i),
                        "cargo": txt(d, "ref_cargo_%d" % i),
                        "telefono": txt(d, "ref_tel_%d" % i)}
                if tiene_datos(fila):
                    insertar(cur, "registro_referencias", dict(registro_id=rid, **fila))
        db.commit()
        return rid
    except Exception:
        db.rollback()
        raise
