"""Personas (tabla única `usuarios`): empleados, usuarios de la aplicación y demás."""
from datetime import date, datetime

from consultas import _ejecutar
from seguridad import ADMIN, hash_clave

CAMPOS = ["nombre", "tipo_id", "num_id", "correo", "telefono", "cargo", "ciudad", "fecha_ingreso"]
TIPOS_ID = ["C.C.", "C.E.", "T.I.", "PEP", "PPT", "Pasaporte", "NIT"]


def a_fecha(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def antiguedad(desde, hasta=None):
    """Tiempo en la empresa: (texto «X años, Y meses y Z días», años completos). ('', None) si no hay fecha."""
    desde, hasta = a_fecha(desde), a_fecha(hasta) or date.today()
    if not desde or hasta < desde:
        return "", None
    meses = (hasta.year - desde.year) * 12 + hasta.month - desde.month - (1 if hasta.day < desde.day else 0)
    años, m = divmod(meses, 12)
    ini = date(desde.year + (desde.month - 1 + meses) // 12, (desde.month - 1 + meses) % 12 + 1, 1)
    try:
        ancla = ini.replace(day=desde.day)
    except ValueError:                      # p. ej. ingreso un 31 y el mes tiene 30
        from calendar import monthrange
        ancla = ini.replace(day=monthrange(ini.year, ini.month)[1])
    dias = (hasta - ancla).days
    partes = []
    if años:
        partes.append("%d año%s" % (años, "" if años == 1 else "s"))
    if m:
        partes.append("%d mes%s" % (m, "" if m == 1 else "es"))
    if dias or not partes:
        partes.append("%d día%s" % (dias, "" if dias == 1 else "s"))
    texto = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
    return texto, años


def con_antiguedad(filas):
    """Agrega ingreso (date), antiguedad (texto) y anios a una persona o lista de personas."""
    uno = isinstance(filas, dict)
    out = []
    for r in ([filas] if uno else filas):
        r = dict(r)
        r["fecha_ingreso"] = a_fecha(r.get("fecha_ingreso"))
        r["antiguedad"], r["anios"] = antiguedad(r["fecha_ingreso"])
        out.append(r)
    return out[0] if uno else out


def listar(ver="app", q=None):
    """ver='app': solo con acceso habilitado. ver='todos': todas las personas."""
    sql = ("SELECT id, nombre, tipo_id, num_id, correo, cargo, ciudad, fecha_ingreso, rol, activo, ultimo_acceso, "
           "(password_hash IS NOT NULL) AS tiene_clave FROM usuarios WHERE 1=1")
    par = []
    if ver != "todos":
        sql += " AND activo = 1"
    if q:
        sql += " AND (nombre LIKE %s OR num_id LIKE %s OR correo LIKE %s OR cargo LIKE %s)"
        par += ["%" + q + "%"] * 4
    return _ejecutar(sql + " ORDER BY nombre", par)


def conteos():
    r = _ejecutar("SELECT COUNT(*) AS todos, SUM(CASE WHEN activo = 1 THEN 1 ELSE 0 END) AS app FROM usuarios",
                  uno=True)
    return {"todos": int(r["todos"] or 0), "app": int(r["app"] or 0)}


def obtener(pid):
    return _ejecutar("SELECT id, nombre, tipo_id, num_id, correo, telefono, cargo, ciudad, fecha_ingreso, rol, activo, "
                     "ultimo_acceso, (password_hash IS NOT NULL) AS tiene_clave FROM usuarios WHERE id = %s",
                     [pid], uno=True)


def duplicado(campo, valor, excepto=None):
    assert campo in ("correo", "num_id")
    if not valor:
        return False
    r = _ejecutar("SELECT id FROM usuarios WHERE %s = %%s" % campo, [valor], uno=True)
    return bool(r) and r["id"] != excepto


def crear(d, rol=None, clave=None, activo=False):
    return _ejecutar("INSERT INTO usuarios (nombre, tipo_id, num_id, correo, telefono, cargo, ciudad, fecha_ingreso, rol, "
                     "password_hash, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     [d[c] for c in CAMPOS] + [rol, hash_clave(clave) if clave else None, 1 if activo else 0],
                     commit=True)


def actualizar(pid, d, rol=None, activo=None, clave=None, cambiar_acceso=False):
    """Actualiza los datos de la persona. Si cambiar_acceso, también rol/activo y (opcional) la clave."""
    sets = ", ".join(c + "=%s" for c in CAMPOS)
    par = [d[c] for c in CAMPOS]
    if cambiar_acceso:
        sets += ", rol=%s, activo=%s"
        par += [rol, 1 if activo else 0]
        if clave:
            sets += ", password_hash=%s, intentos=0, bloqueado_hasta=NULL"
            par.append(hash_clave(clave))
    _ejecutar("UPDATE usuarios SET " + sets + " WHERE id=%s", par + [pid], commit=True)


def cambiar_acceso(pid, activo):
    _ejecutar("UPDATE usuarios SET activo=%s WHERE id=%s", [1 if activo else 0, pid], commit=True)


def admins_activos(excepto=None):
    sql, par = "SELECT COUNT(*) AS n FROM usuarios WHERE rol = %s AND activo = 1", [ADMIN]
    if excepto:
        sql += " AND id <> %s"
        par.append(excepto)
    return _ejecutar(sql, par, uno=True)["n"]


# ---- selector de personas para los demás módulos (nómina, celulares, equipos...) ----
def etiqueta(p):
    return "%s · %s" % (p["nombre"], p["num_id"] or "#%d" % p["id"])


def opciones():
    return [{"id": p["id"], "etiqueta": etiqueta(p), "nombre": p["nombre"], "num_id": p["num_id"]}
            for p in _ejecutar("SELECT id, nombre, num_id FROM usuarios ORDER BY nombre")]


def resolver(texto):
    """Convierte lo escrito en el selector («Nombre · documento») en el id de la persona, o None."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for o in opciones():
        if o["etiqueta"].lower() == texto.lower():
            return o["id"]
    return None
