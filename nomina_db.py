"""Consultas del módulo de nómina."""
import json
import secrets
from datetime import date, datetime

from consultas import _ejecutar
from db import get_db
from nomina_calculo import a_fecha, rango_periodo

PARAMS_COLS = ["smmlv", "aux_transporte", "uvt", "horas_semana", "rec_nocturno", "rec_extra_diurna",
               "rec_extra_nocturna", "rec_dominical", "salud_empleado", "pension_empleado",
               "salud_empleador", "pension_empleador", "caja", "sena", "icbf", "prima", "cesantias",
               "intereses", "vacaciones"]


def _num(v):
    """Decimal de MySQL -> int/float."""
    if v is None:
        return None
    f = float(v)
    return int(f) if f == int(f) else f


# ---------------------------------------------------------------- empleadores
def listar_empleadores(solo_activos=False):
    return _ejecutar("SELECT e.*, (SELECT COUNT(*) FROM empleados m WHERE m.empleador_id = e.id AND m.activo = 1) "
                     "AS n_empleados FROM empleadores e " + ("WHERE e.activo = 1 " if solo_activos else "") +
                     "ORDER BY e.nombre")


def obtener_empleador(eid):
    return _ejecutar("SELECT * FROM empleadores WHERE id = %s", [eid], uno=True)


def guardar_empleador(eid, d):
    campos = [d["nombre"], d["nit"], d.get("direccion"), d.get("ciudad"), d.get("telefono"), d.get("email"),
              1 if d.get("exonerado") else 0, 1 if d.get("activo", True) else 0]
    if eid:
        _ejecutar("UPDATE empleadores SET nombre=%s, nit=%s, direccion=%s, ciudad=%s, telefono=%s, email=%s, "
                  "exonerado=%s, activo=%s WHERE id=%s", campos + [eid], commit=True)
        return eid
    return _ejecutar("INSERT INTO empleadores (nombre, nit, direccion, ciudad, telefono, email, exonerado, activo) "
                     "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", campos, commit=True)


# ---------------------------------------------------------------- empleados
# El empleado es una vinculación laboral de una PERSONA (tabla única `usuarios`): nombre, documento,
# correo y cargo salen de allí.
EMP_SELECT = ("SELECT m.*, u.nombre, u.tipo_id, u.num_id, u.correo AS email, u.cargo, u.ciudad "
              "FROM empleados m JOIN usuarios u ON u.id = m.usuario_id")


def listar_empleados(empleador_id, buscar=None, solo_activos=False):
    sql, par = (EMP_SELECT + " WHERE m.empleador_id = %s"), [empleador_id]
    if solo_activos:
        sql += " AND m.activo = 1"
    if buscar:
        sql += " AND (u.nombre LIKE %s OR u.num_id LIKE %s)"
        par += ["%" + buscar + "%", "%" + buscar + "%"]
    return [_norm_empleado(r) for r in _ejecutar(sql + " ORDER BY u.nombre", par)]


def obtener_empleado(mid):
    r = _ejecutar(EMP_SELECT + " WHERE m.id = %s", [mid], uno=True)
    return _norm_empleado(r) if r else None


def _norm_empleado(r):
    r = dict(r)
    r["salario"] = _num(r["salario"])
    r["fecha_ingreso"] = a_fecha(r["fecha_ingreso"])
    r["fecha_retiro"] = a_fecha(r.get("fecha_retiro"))
    return r


def guardar_empleado(mid, d):
    campos = [d["empleador_id"], d["usuario_id"], d["fecha_ingreso"], d.get("fecha_retiro"), d["salario"],
              d["nivel_riesgo"], d.get("banco"), d.get("cuenta"), d.get("eps"), d.get("afp"), d.get("caja"),
              1 if d.get("activo", True) else 0]
    if mid:
        _ejecutar("UPDATE empleados SET empleador_id=%s, usuario_id=%s, fecha_ingreso=%s, fecha_retiro=%s, "
                  "salario=%s, nivel_riesgo=%s, banco=%s, cuenta=%s, eps=%s, afp=%s, caja=%s, activo=%s "
                  "WHERE id=%s", campos + [mid], commit=True)
        return mid
    return _ejecutar("INSERT INTO empleados (empleador_id, usuario_id, fecha_ingreso, fecha_retiro, salario, "
                     "nivel_riesgo, banco, cuenta, eps, afp, caja, activo) "
                     "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", campos, commit=True)


def existe_vinculo(empleador_id, usuario_id, excepto=None):
    r = _ejecutar("SELECT id FROM empleados WHERE empleador_id = %s AND usuario_id = %s",
                  [empleador_id, usuario_id], uno=True)
    return bool(r) and r["id"] != excepto


# ---------------------------------------------------------------- parámetros
def listar_parametros():
    return _ejecutar("SELECT * FROM nomina_parametros ORDER BY vigente_desde DESC")


def obtener_parametro(pid):
    return _ejecutar("SELECT * FROM nomina_parametros WHERE id = %s", [pid], uno=True)


def parametros_vigentes(fecha):
    """Parámetros aplicables a una fecha (el último con vigente_desde <= fecha)."""
    r = _ejecutar("SELECT * FROM nomina_parametros WHERE vigente_desde <= %s ORDER BY vigente_desde DESC LIMIT 1",
                  [str(fecha)], uno=True)
    if not r:
        return None
    return {k: _num(r[k]) for k in PARAMS_COLS}


def guardar_parametro(pid, vigente_desde, valores, nota):
    cols = PARAMS_COLS
    if pid:
        _ejecutar("UPDATE nomina_parametros SET vigente_desde=%s, " + ", ".join(c + "=%s" for c in cols) +
                  ", nota=%s WHERE id=%s", [vigente_desde] + [valores[c] for c in cols] + [nota, pid], commit=True)
        return pid
    return _ejecutar("INSERT INTO nomina_parametros (vigente_desde, " + ", ".join(cols) + ", nota) VALUES (%s, " +
                     ", ".join(["%s"] * len(cols)) + ", %s)", [vigente_desde] + [valores[c] for c in cols] + [nota],
                     commit=True)


# ---------------------------------------------------------------- periodos
def listar_periodos(empleador_id=None, anio=None):
    sql = ("SELECT p.*, e.nombre AS empleador, "
           "(SELECT COUNT(*) FROM nomina_liquidaciones l WHERE l.periodo_id = p.id) AS n_liq, "
           "(SELECT COALESCE(SUM(l.neto), 0) FROM nomina_liquidaciones l WHERE l.periodo_id = p.id) AS total_neto "
           "FROM nomina_periodos p JOIN empleadores e ON e.id = p.empleador_id WHERE 1=1")
    par = []
    if empleador_id:
        sql += " AND p.empleador_id = %s"
        par.append(empleador_id)
    if anio:
        sql += " AND p.anio = %s"
        par.append(anio)
    return _ejecutar(sql + " ORDER BY p.anio DESC, p.mes DESC, p.quincena DESC", par)


def obtener_periodo(pid):
    r = _ejecutar("SELECT p.*, e.nombre AS empleador, e.nit, e.exonerado FROM nomina_periodos p "
                  "JOIN empleadores e ON e.id = p.empleador_id WHERE p.id = %s", [pid], uno=True)
    if r:
        r["fecha_inicio"], r["fecha_fin"] = a_fecha(r["fecha_inicio"]), a_fecha(r["fecha_fin"])
    return r


def crear_periodo(empleador_id, anio, mes, quincena, usuario_id):
    ini, fin = rango_periodo(anio, mes, quincena)
    ya = _ejecutar("SELECT id FROM nomina_periodos WHERE empleador_id=%s AND anio=%s AND mes=%s AND quincena=%s",
                   [empleador_id, anio, mes, quincena], uno=True)
    if ya:
        return ya["id"], False
    pid = _ejecutar("INSERT INTO nomina_periodos (empleador_id, anio, mes, quincena, fecha_inicio, fecha_fin, "
                    "creado_por) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [empleador_id, anio, mes, quincena, ini.isoformat(), fin.isoformat(), usuario_id], commit=True)
    return pid, True


def cambiar_estado_periodo(pid, estado):
    _ejecutar("UPDATE nomina_periodos SET estado=%s WHERE id=%s", [estado, pid], commit=True)


# ---------------------------------------------------------------- novedades
def listar_novedades(periodo_id):
    return _ejecutar("SELECT n.*, u.nombre AS empleado, u.num_id FROM nomina_novedades n "
                     "JOIN empleados m ON m.id = n.empleado_id JOIN usuarios u ON u.id = m.usuario_id "
                     "WHERE n.periodo_id = %s ORDER BY u.nombre, n.id",
                     [periodo_id])


def novedades_por_empleado(periodo_id):
    out = {}
    for n in listar_novedades(periodo_id):
        out.setdefault(n["empleado_id"], []).append(
            {"tipo": n["tipo"], "cantidad": _num(n["cantidad"]), "valor": _num(n["valor"]),
             "previos": n["previos"], "nota": n["nota"]})
    return out


def agregar_novedad(periodo_id, empleado_id, tipo, cantidad, valor, previos, nota):
    return _ejecutar("INSERT INTO nomina_novedades (periodo_id, empleado_id, tipo, cantidad, valor, previos, nota) "
                     "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     [periodo_id, empleado_id, tipo, cantidad, valor, previos, nota], commit=True)


def eliminar_novedad(periodo_id, nid):
    _ejecutar("DELETE FROM nomina_novedades WHERE id = %s AND periodo_id = %s", [nid, periodo_id], commit=True)


# ---------------------------------------------------------------- liquidaciones
def guardar_liquidaciones(periodo_id, resultados):
    """resultados: {empleado_id: calculo}. Inserta o actualiza en una sola transacción."""
    db = get_db()
    try:
        with db.cursor() as cur:
            for emp_id, c in resultados.items():
                cur.execute("SELECT id FROM nomina_liquidaciones WHERE periodo_id = %s AND empleado_id = %s",
                            [periodo_id, emp_id])
                existe = cur.fetchone()
                valores = [c["dias_trabajados"], c["total_devengado"], c["total_deducciones"], c["neto"], c["ibc"],
                           c["aportes"]["total"], c["provisiones"]["total"], json.dumps(c, ensure_ascii=False)]
                if existe:
                    cur.execute("UPDATE nomina_liquidaciones SET dias_trabajados=%s, total_devengado=%s, "
                                "total_deducciones=%s, neto=%s, ibc=%s, aportes_empleador=%s, provisiones=%s, "
                                "detalle=%s, correo_enviado=NULL, correo_error=NULL WHERE id=%s",
                                valores + [existe["id"]])
                else:
                    cur.execute("INSERT INTO nomina_liquidaciones (periodo_id, empleado_id, token, dias_trabajados, "
                                "total_devengado, total_deducciones, neto, ibc, aportes_empleador, provisiones, "
                                "detalle) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                [periodo_id, emp_id, secrets.token_urlsafe(24)] + valores)
            if resultados:
                marcador = ", ".join(["%s"] * len(resultados))
                cur.execute("DELETE FROM nomina_liquidaciones WHERE periodo_id = %s AND empleado_id NOT IN (" +
                            marcador + ")", [periodo_id] + list(resultados.keys()))
            else:
                cur.execute("DELETE FROM nomina_liquidaciones WHERE periodo_id = %s", [periodo_id])
            cur.execute("UPDATE nomina_periodos SET liquidado_en = %s WHERE id = %s",
                        [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), periodo_id])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _norm_liq(r):
    r = dict(r)
    for k in ("total_devengado", "total_deducciones", "neto", "ibc", "aportes_empleador", "provisiones",
              "dias_trabajados"):
        if k in r:
            r[k] = _num(r[k])
    if r.get("detalle"):
        r["calculo"] = json.loads(r["detalle"])
    return r


def liquidaciones_periodo(periodo_id):
    rows = _ejecutar("SELECT l.*, u.nombre, u.num_id, u.tipo_id, u.cargo, u.correo AS email, m.salario, m.banco, m.cuenta "
                     "FROM nomina_liquidaciones l JOIN empleados m ON m.id = l.empleado_id "
                     "JOIN usuarios u ON u.id = m.usuario_id WHERE l.periodo_id = %s ORDER BY u.nombre", [periodo_id])
    return [_norm_liq(r) for r in rows]


def obtener_liquidacion(lid):
    r = _ejecutar("SELECT l.*, u.nombre, u.num_id, u.tipo_id, u.cargo, u.correo AS email, m.salario, m.banco, m.cuenta, "
                  "m.empleador_id FROM nomina_liquidaciones l JOIN empleados m ON m.id = l.empleado_id "
                  "JOIN usuarios u ON u.id = m.usuario_id WHERE l.id = %s", [lid], uno=True)
    return _norm_liq(r) if r else None


def marcar_envio(lid, error=None):
    if error:
        _ejecutar("UPDATE nomina_liquidaciones SET correo_error=%s WHERE id=%s", [error[:300], lid], commit=True)
    else:
        _ejecutar("UPDATE nomina_liquidaciones SET correo_enviado=%s, correo_error=NULL WHERE id=%s",
                  [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), lid], commit=True)


def consultar(empleador_id=None, anio=None, mes=None, quincena=None, buscar=None):
    sql = ("SELECT l.*, u.nombre, u.num_id, u.cargo, u.correo AS email, p.anio, p.mes, p.quincena, p.empleador_id, "
           "e.nombre AS empleador FROM nomina_liquidaciones l "
           "JOIN empleados m ON m.id = l.empleado_id JOIN usuarios u ON u.id = m.usuario_id "
           "JOIN nomina_periodos p ON p.id = l.periodo_id "
           "JOIN empleadores e ON e.id = p.empleador_id WHERE 1=1")
    par = []
    for col, val in (("p.empleador_id", empleador_id), ("p.anio", anio), ("p.mes", mes), ("p.quincena", quincena)):
        if val:
            sql += " AND " + col + " = %s"
            par.append(val)
    if buscar:
        sql += " AND (u.nombre LIKE %s OR u.num_id LIKE %s)"
        par += ["%" + buscar + "%", "%" + buscar + "%"]
    sql += " ORDER BY e.nombre, p.anio, p.mes, p.quincena, u.nombre"
    return [_norm_liq(r) for r in _ejecutar(sql, par)]
