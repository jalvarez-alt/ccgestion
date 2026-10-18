"""Inventario de equipos de cómputo y su software instalado."""
from datetime import date

from consultas import _ejecutar
from db import get_db
from nomina_calculo import a_fecha

TIPOS = {"portatil": "Portátil", "escritorio": "Computador de escritorio", "todo_en_uno": "Todo en uno",
         "servidor": "Servidor", "monitor": "Monitor", "camara": "Cámara", "teclado": "Teclado",
         "mouse": "Mouse", "teclado_mouse": "Teclado con mouse"}
COMPUTO = ("portatil", "escritorio", "todo_en_uno", "servidor")   # llevan procesador, RAM, SSD, SO, Office, antivirus
ESTADOS = {"activo": "Activo", "reparacion": "En reparación", "almacenado": "Almacenado", "baja": "Dado de baja"}
LICENCIAS = {"propietaria": "Propietaria", "suscripcion": "Suscripción", "oem": "OEM",
             "volumen": "Por volumen", "libre": "Libre", "gratuita": "Gratuita", "otra": "Otra"}
SW_ESTADOS = {"activo": "Activo", "por_renovar": "Por renovar", "vencido": "Vencido",
              "sin_licencia": "Sin licencia", "desinstalado": "Desinstalado"}

SELECT = ("SELECT e.*, u.nombre AS usuario, u.num_id AS usuario_doc, "
          "(SELECT COUNT(*) FROM equipo_software s WHERE s.equipo_id = e.id) AS n_software "
          "FROM equipos e LEFT JOIN usuarios u ON u.id = e.persona_id")


def _norm(r):
    r = dict(r)
    for k in ("ram_gb", "ssd_gb"):
        r[k] = int(r[k]) if r.get(k) is not None else None
    r["es_computo"] = r["tipo"] in COMPUTO
    return r


def _filtros(f):
    sql, par = " WHERE 1=1", []
    if f.get("tipo"):
        sql += " AND e.tipo = %s"
        par.append(f["tipo"])
    if f.get("estado"):
        sql += " AND e.estado = %s"
        par.append(f["estado"])
    if f.get("ciudad"):
        sql += " AND e.ciudad = %s"
        par.append(f["ciudad"])
    if f.get("software"):
        sql += " AND EXISTS (SELECT 1 FROM equipo_software s WHERE s.equipo_id = e.id AND s.nombre LIKE %s)"
        par.append("%" + f["software"] + "%")
    if f.get("q"):
        like = "%" + f["q"] + "%"
        sql += (" AND (e.codigo LIKE %s OR e.marca LIKE %s OR e.modelo LIKE %s OR e.serie LIKE %s "
                "OR e.procesador LIKE %s OR e.sistema_operativo LIKE %s OR e.antivirus LIKE %s OR u.nombre LIKE %s)")
        par += [like] * 8
    return sql, par


def listar(f):
    sql, par = _filtros(f)
    return [_norm(r) for r in _ejecutar(SELECT + sql + " ORDER BY e.codigo", par)]


def resumen():
    r = _ejecutar("SELECT COUNT(*) AS total, "
                  "SUM(CASE WHEN persona_id IS NOT NULL THEN 1 ELSE 0 END) AS asignados, "
                  "SUM(CASE WHEN persona_id IS NULL THEN 1 ELSE 0 END) AS sin_asignar, "
                  "SUM(CASE WHEN estado = 'reparacion' THEN 1 ELSE 0 END) AS reparacion FROM equipos", uno=True)
    return {k: int(float(v or 0)) for k, v in r.items()}


def ciudades():
    filas = _ejecutar("SELECT DISTINCT ciudad AS v FROM equipos WHERE ciudad IS NOT NULL AND ciudad <> '' "
                      "UNION SELECT DISTINCT ciudad FROM usuarios WHERE ciudad IS NOT NULL AND ciudad <> '' ORDER BY 1")
    return [r["v"] for r in filas]


def obtener(eid):
    r = _ejecutar(SELECT + " WHERE e.id = %s", [eid], uno=True)
    return _norm(r) if r else None


def siguiente_codigo():
    n = int(_ejecutar("SELECT COALESCE(MAX(id), 0) AS n FROM equipos", uno=True)["n"]) + 1
    while duplicado("EQ-%04d" % n):
        n += 1
    return "EQ-%04d" % n


def duplicado(codigo, excepto=None):
    r = _ejecutar("SELECT id FROM equipos WHERE codigo = %s", [codigo], uno=True)
    return bool(r) and r["id"] != excepto


CAMPOS = ["codigo", "tipo", "marca", "modelo", "serie", "procesador", "ram_gb", "ssd_gb", "persona_id", "ciudad",
          "sistema_operativo", "office", "antivirus", "estado", "observaciones"]


def crear(d):
    return _ejecutar("INSERT INTO equipos (" + ", ".join(CAMPOS) + ") VALUES (" + ", ".join(["%s"] * len(CAMPOS)) + ")",
                     [d[c] for c in CAMPOS], commit=True)


def actualizar(eid, d):
    _ejecutar("UPDATE equipos SET " + ", ".join(c + "=%s" for c in CAMPOS) + " WHERE id=%s",
              [d[c] for c in CAMPOS] + [eid], commit=True)


def software(eid=None):
    sql = ("SELECT s.*, e.codigo, e.tipo, u.nombre AS usuario FROM equipo_software s "
           "JOIN equipos e ON e.id = s.equipo_id LEFT JOIN usuarios u ON u.id = e.persona_id")
    par = []
    if eid:
        sql += " WHERE s.equipo_id = %s"
        par.append(eid)
    filas = _ejecutar(sql + " ORDER BY e.codigo, s.nombre, s.id", par)
    hoy = date.today()
    for s in filas:
        s["vencimiento"] = a_fecha(s["vencimiento"])
        s["vencido"] = bool(s["vencimiento"] and s["vencimiento"] < hoy and s["estado"] != "desinstalado")
    return filas


def guardar_software(eid, filas, borrar):
    """filas: [{id|None, nombre, version, tipo_licencia, estado, vencimiento, notas}]; borrar: set de ids."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT id FROM equipo_software WHERE equipo_id = %s", [eid])
            propios = {r["id"] for r in cur.fetchall()}
            for sid in borrar & propios:
                cur.execute("DELETE FROM equipo_software WHERE id = %s AND equipo_id = %s", [sid, eid])
            for f in filas:
                v = [f["nombre"], f["version"], f["tipo_licencia"], f["estado"], f["vencimiento"], f["notas"]]
                if f["id"] and f["id"] in propios and f["id"] not in borrar:
                    cur.execute("UPDATE equipo_software SET nombre=%s, version=%s, tipo_licencia=%s, estado=%s, "
                                "vencimiento=%s, notas=%s WHERE id=%s AND equipo_id=%s", v + [f["id"], eid])
                elif not f["id"]:
                    cur.execute("INSERT INTO equipo_software (nombre, version, tipo_licencia, estado, vencimiento, "
                                "notas, equipo_id) VALUES (%s, %s, %s, %s, %s, %s, %s)", v + [eid])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
