"""Consultas a la base de datos (usuarios y registros)."""
import etiquetas as E
from db import get_db
from seguridad import hash_clave

POR_PAGINA = 25


def _ejecutar(sql, params=(), uno=False, commit=False):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, list(params))
            if commit:
                db.commit()
                return cur.lastrowid
            return cur.fetchone() if uno else cur.fetchall()
    finally:
        db.close()


def hay_usuarios():
    return _ejecutar("SELECT COUNT(*) AS n FROM usuarios", uno=True)["n"] > 0


def usuario_por_id(uid):
    return _ejecutar("SELECT id, nombre, correo, rol, activo FROM usuarios WHERE id = %s", [uid], uno=True)


def usuario_por_correo(correo):
    return _ejecutar("SELECT id, nombre, correo, password_hash, rol, activo, intentos, "
                     "bloqueado_hasta FROM usuarios WHERE correo = %s", [correo], uno=True)


def crear_usuario(nombre, correo, clave, rol):
    """Crea una persona CON acceso a la aplicación (primer administrador, autoregistro)."""
    return _ejecutar("INSERT INTO usuarios (nombre, correo, password_hash, rol, activo) VALUES (%s, %s, %s, %s, 1)",
                     [nombre, correo, hash_clave(clave), rol], commit=True)


def cambiar_clave(uid, nueva):
    _ejecutar("UPDATE usuarios SET password_hash=%s, intentos=0, bloqueado_hasta=NULL WHERE id=%s",
              [hash_clave(nueva), uid], commit=True)


def login_exitoso(uid, ahora):
    _ejecutar("UPDATE usuarios SET intentos=0, bloqueado_hasta=NULL, ultimo_acceso=%s WHERE id=%s",
              [ahora, uid], commit=True)


def login_fallido(uid, intentos_actuales, bloquear_hasta, limite=5):
    n = intentos_actuales + 1
    if n >= limite:
        _ejecutar("UPDATE usuarios SET intentos=0, bloqueado_hasta=%s WHERE id=%s",
                  [bloquear_hasta, uid], commit=True)
    else:
        _ejecutar("UPDATE usuarios SET intentos=%s WHERE id=%s", [n, uid], commit=True)


def _cond(filtros, usuario):
    cond, par = [], []
    if not usuario.get("ver_todos"):
        cond.append("r.usuario_id = %s")
        par.append(usuario["id"])
    q = (filtros.get("q") or "").strip()
    if q:
        cond.append("(r.nombre LIKE %s OR r.identificacion LIKE %s)")
        par += ["%" + q + "%", "%" + q + "%"]
    if filtros.get("tipo") in ("natural", "juridica"):
        cond.append("r.tipo_persona = %s")
        par.append(filtros["tipo"])
    if filtros.get("desde"):
        cond.append("r.fecha_diligenciamiento >= %s")
        par.append(filtros["desde"])
    if filtros.get("hasta"):
        cond.append("r.fecha_diligenciamiento <= %s")
        par.append(filtros["hasta"])
    return (" AND ".join(cond) or "1=1"), par


def contar_registros(filtros, usuario):
    donde, par = _cond(filtros, usuario)
    return _ejecutar("SELECT COUNT(*) AS n FROM registros r WHERE " + donde, par, uno=True)["n"]


def listar_registros(filtros, usuario, pagina):
    donde, par = _cond(filtros, usuario)
    return _ejecutar(
        "SELECT r.id, r.creada, r.fecha_diligenciamiento, r.tipo_persona, r.nombre, "
        "r.identificacion, r.solicitud, u.nombre AS registrado_por "
        "FROM registros r LEFT JOIN usuarios u ON u.id = r.usuario_id WHERE " + donde +
        " ORDER BY r.id DESC LIMIT %s OFFSET %s", par + [POR_PAGINA, (pagina - 1) * POR_PAGINA])


def _propietario(usuario):
    if not usuario.get("ver_todos"):
        return " AND r.usuario_id = %s", [usuario["id"]]
    return "", []


def obtener_registro(rid, usuario):
    extra, par = _propietario(usuario)
    r = _ejecutar("SELECT r.*, u.nombre AS registrado_por FROM registros r "
                  "LEFT JOIN usuarios u ON u.id = r.usuario_id WHERE r.id = %s" + extra,
                  [rid] + par, uno=True)
    if not r:
        return None
    r.pop("datos", None)
    r.pop("firma_img", None)
    hijos = {}
    for clave, tabla in (("financiero", "registro_financiero"), ("cuentas", "registro_cuentas"),
                         ("beneficiarios", "registro_beneficiarios"),
                         ("referencias", "registro_referencias")):
        hijos[clave] = _ejecutar("SELECT * FROM " + tabla + " WHERE registro_id = %s ORDER BY id", [rid])
    rep = _ejecutar("SELECT * FROM registro_representante WHERE registro_id = %s", [rid], uno=True)
    return dict(r=r, representante=rep, **hijos)


def datos_pdf(rid, usuario):
    extra, par = _propietario(usuario)
    return _ejecutar("SELECT r.datos, r.identificacion FROM registros r WHERE r.id = %s" + extra,
                     [rid] + par, uno=True)


def datos_exportacion(filtros, usuario):
    donde, par = _cond(filtros, usuario)
    sel = ", ".join("u.nombre AS registrado_por" if c == "registrado_por" else "r." + c
                    for c, _ in E.REGISTRO_COLS)
    hojas = {"Registros": _ejecutar(
        "SELECT " + sel + " FROM registros r LEFT JOIN usuarios u ON u.id = r.usuario_id "
        "WHERE " + donde + " ORDER BY r.id", par)}
    for hoja, tabla, cols in (
            ("Representante legal", "registro_representante", E.REPRESENTANTE_COLS),
            ("Financiero", "registro_financiero", E.FINANCIERO_COLS),
            ("Cuentas bancarias", "registro_cuentas", E.CUENTAS_COLS),
            ("Beneficiarios finales", "registro_beneficiarios", E.BENEFICIARIOS_COLS),
            ("Referencias comerciales", "registro_referencias", E.REFERENCIAS_COLS)):
        sel = ("r.id AS reg_id, r.nombre AS reg_nombre, r.identificacion AS reg_ident, "
               + ", ".join("t." + c for c, _ in cols))
        hojas[hoja] = _ejecutar(
            "SELECT " + sel + " FROM " + tabla + " t JOIN registros r ON r.id = t.registro_id "
            "WHERE " + donde + " ORDER BY r.id, t.id", par)
    return hojas
