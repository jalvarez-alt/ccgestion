"""Consultas del inventario de celulares."""
from datetime import date, datetime

from consultas import _ejecutar
from db import get_db
from nomina_calculo import a_fecha

MOTIVOS_BAJA = {"dano": "Daño", "perdida": "Pérdida", "robo": "Robo", "obsolescencia": "Obsolescencia",
                "venta": "Venta", "otro": "Otro"}
ACTAS = {"firmada": "Firmada", "pendiente": "Pendiente", "no_aplica": "No aplica"}
TIPOS_MOV = {"alta": "Ingreso al inventario", "asignacion": "Asignación / rotación", "baja": "Baja",
             "reactivacion": "Reactivación"}


def antiguedad(desde, hasta=None):
    """Devuelve (texto, años completos) entre la compra y hoy (o la fecha de baja)."""
    desde, hasta = a_fecha(desde), a_fecha(hasta) or date.today()
    if not desde or hasta < desde:
        return "", None
    meses = (hasta.year - desde.year) * 12 + hasta.month - desde.month - (1 if hasta.day < desde.day else 0)
    años, m = divmod(meses, 12)
    partes = []
    if años:
        partes.append("%d año%s" % (años, "" if años == 1 else "s"))
    if m or not años:
        partes.append("%d mes%s" % (m, "" if m == 1 else "es"))
    return ", ".join(partes), años


# Quién tiene el celular es una PERSONA de la tabla única `usuarios`.
CEL_SELECT = ("SELECT c.*, pa.nombre AS usuario_actual, pn.nombre AS usuario_anterior FROM celulares c "
              "LEFT JOIN usuarios pa ON pa.id = c.persona_actual_id "
              "LEFT JOIN usuarios pn ON pn.id = c.persona_anterior_id")


def _norm(r):
    r = dict(r)
    r["valor_plan"] = int(float(r["valor_plan"] or 0))
    for k in ("fecha_compra", "baja_fecha"):
        r[k] = a_fecha(r.get(k))
    fin = r["baja_fecha"] if r["estado"] == "baja" else None
    r["antiguedad"], r["anios"] = antiguedad(r["fecha_compra"], fin)
    r["situacion"] = ("Baja" if r["estado"] == "baja" else "Asignado" if r["persona_actual_id"] else "Disponible")
    return r


def _filtros(f):
    sql, par = " WHERE 1=1", []
    est = f.get("estado") or "activos"
    if est == "baja":
        sql += " AND c.estado = 'baja'"
    elif est == "asignado":
        sql += " AND c.estado = 'activo' AND c.persona_actual_id IS NOT NULL"
    elif est == "disponible":
        sql += " AND c.estado = 'activo' AND c.persona_actual_id IS NULL"
    elif est == "activos":
        sql += " AND c.estado = 'activo'"
    if f.get("marca"):
        sql += " AND c.marca = %s"
        par.append(f["marca"])
    if f.get("operador"):
        sql += " AND c.operador = %s"
        par.append(f["operador"])
    if f.get("q"):
        like = "%" + f["q"] + "%"
        sql += (" AND (c.marca LIKE %s OR c.modelo LIKE %s OR c.imei1 LIKE %s OR c.imei2 LIKE %s OR c.sn LIKE %s "
                "OR c.linea LIKE %s OR pa.nombre LIKE %s OR pn.nombre LIKE %s)")
        par += [like] * 8
    return sql, par


def listar(f):
    sql, par = _filtros(f)
    return [_norm(r) for r in _ejecutar(CEL_SELECT + sql + " ORDER BY c.marca, c.modelo, c.id", par)]


def resumen():
    r = _ejecutar("SELECT "
                  "SUM(CASE WHEN estado='activo' THEN 1 ELSE 0 END) AS activos, "
                  "SUM(CASE WHEN estado='activo' AND persona_actual_id IS NOT NULL THEN 1 ELSE 0 END) AS asignados, "
                  "SUM(CASE WHEN estado='activo' AND persona_actual_id IS NULL THEN 1 ELSE 0 END) AS disponibles, "
                  "SUM(CASE WHEN estado='baja' THEN 1 ELSE 0 END) AS bajas, "
                  "SUM(CASE WHEN estado='activo' THEN valor_plan ELSE 0 END) AS plan_total FROM celulares", uno=True)
    return {k: int(float(v or 0)) for k, v in r.items()}


def valores_distintos(columna):
    assert columna in ("marca", "operador")
    return [r["v"] for r in _ejecutar("SELECT DISTINCT %s AS v FROM celulares WHERE %s IS NOT NULL AND %s <> '' "
                                      "ORDER BY 1" % (columna, columna, columna))]


def obtener(cid):
    r = _ejecutar(CEL_SELECT + " WHERE c.id = %s", [cid], uno=True)
    return _norm(r) if r else None


def movimientos(cid=None):
    sql = ("SELECT m.*, c.marca, c.modelo, c.imei1, pa.nombre AS usuario_anterior, pn.nombre AS usuario_nuevo "
           "FROM celular_movimientos m JOIN celulares c ON c.id = m.celular_id "
           "LEFT JOIN usuarios pa ON pa.id = m.persona_anterior_id "
           "LEFT JOIN usuarios pn ON pn.id = m.persona_nueva_id")
    par = []
    if cid:
        sql += " WHERE m.celular_id = %s"
        par.append(cid)
    rows = _ejecutar(sql + " ORDER BY m.fecha DESC, m.id DESC", par)
    for r in rows:
        r["fecha"] = a_fecha(r["fecha"])
    return rows


def duplicado(campo, valor, excepto=None):
    assert campo in ("imei1", "sn")
    if not valor:
        return False
    r = _ejecutar("SELECT id FROM celulares WHERE %s = %%s" % campo, [valor], uno=True)
    return bool(r) and r["id"] != excepto


CAMPOS = ["fecha_compra", "marca", "modelo", "imei1", "imei2", "sn", "acta", "observaciones", "linea", "operador",
          "valor_plan"]


def _mov(cur, cid, fecha, tipo, ant_id, nuevo_id, nota, quien):
    cur.execute("INSERT INTO celular_movimientos (celular_id, fecha, tipo, persona_anterior_id, persona_nueva_id, "
                "nota, registrado_por) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [cid, fecha, tipo, ant_id, nuevo_id, nota, quien])


def _transaccion(trabajo):
    db = get_db()
    try:
        with db.cursor() as cur:
            res = trabajo(cur)
        db.commit()
        return res
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def crear(d, persona_id, fecha_mov, quien):
    def trabajo(cur):
        cur.execute("INSERT INTO celulares (" + ", ".join(CAMPOS) + ", persona_actual_id) VALUES (" +
                    ", ".join(["%s"] * (len(CAMPOS) + 1)) + ")", [d[c] for c in CAMPOS] + [persona_id])
        cid = cur.lastrowid
        _mov(cur, cid, fecha_mov, "alta", None, persona_id, "Ingreso al inventario", quien)
        return cid
    return _transaccion(trabajo)


def actualizar(cid, d):
    _ejecutar("UPDATE celulares SET " + ", ".join(c + "=%s" for c in CAMPOS) + " WHERE id=%s",
              [d[c] for c in CAMPOS] + [cid], commit=True)


def reasignar(cid, nuevo_id, fecha_mov, nota, quien):
    def trabajo(cur):
        cur.execute("SELECT persona_actual_id, persona_anterior_id FROM celulares WHERE id = %s", [cid])
        c = cur.fetchone()
        ant = c["persona_actual_id"] or c["persona_anterior_id"]
        cur.execute("UPDATE celulares SET persona_anterior_id=%s, persona_actual_id=%s WHERE id=%s", [ant, nuevo_id, cid])
        _mov(cur, cid, fecha_mov, "asignacion", c["persona_actual_id"], nuevo_id, nota, quien)
    _transaccion(trabajo)


def dar_baja(cid, fecha_baja, motivo, nota, quien):
    def trabajo(cur):
        cur.execute("SELECT persona_actual_id, persona_anterior_id FROM celulares WHERE id = %s", [cid])
        c = cur.fetchone()
        ant = c["persona_actual_id"] or c["persona_anterior_id"]
        cur.execute("UPDATE celulares SET estado='baja', baja_fecha=%s, baja_motivo=%s, baja_nota=%s, "
                    "persona_anterior_id=%s, persona_actual_id=NULL WHERE id=%s", [fecha_baja, motivo, nota, ant, cid])
        _mov(cur, cid, fecha_baja, "baja", c["persona_actual_id"], None,
             "%s%s" % (MOTIVOS_BAJA.get(motivo, motivo), ": " + nota if nota else ""), quien)
    _transaccion(trabajo)


def reactivar(cid, fecha_mov, quien):
    def trabajo(cur):
        cur.execute("UPDATE celulares SET estado='activo', baja_fecha=NULL, baja_motivo=NULL, baja_nota=NULL "
                    "WHERE id=%s", [cid])
        _mov(cur, cid, fecha_mov, "reactivacion", None, None, "Vuelve al inventario como disponible", quien)
    _transaccion(trabajo)
