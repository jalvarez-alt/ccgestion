"""Roles y permisos."""
import re

from consultas import _ejecutar
from db import get_db
from seguridad import ADMIN, PERMISOS


def listar_roles():
    roles = _ejecutar("SELECT r.*, (SELECT COUNT(*) FROM usuarios u WHERE u.rol = r.clave) AS n_usuarios "
                      "FROM roles r ORDER BY r.sistema DESC, r.nombre")
    for r in roles:
        r["permisos"] = permisos_de(r["clave"])
    return roles


def nombres_roles():
    return {r["clave"]: r["nombre"] for r in _ejecutar("SELECT clave, nombre FROM roles ORDER BY nombre")}


def permisos_de(rol):
    if rol == ADMIN:
        return set(PERMISOS)
    if not rol:
        return set()
    return {r["permiso"] for r in _ejecutar("SELECT permiso FROM rol_permisos WHERE rol = %s", [rol])
            if r["permiso"] in PERMISOS}


def existe(clave):
    return bool(_ejecutar("SELECT clave FROM roles WHERE clave = %s", [clave], uno=True))


def clave_desde_nombre(nombre):
    base = re.sub(r"[^a-z0-9]+", "_", nombre.lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("_")[:28]
    return base or "rol"


def crear(nombre, descripcion):
    clave, n = clave_desde_nombre(nombre), 1
    while existe(clave):
        n += 1
        clave = "%s_%d" % (clave_desde_nombre(nombre)[:24], n)
    _ejecutar("INSERT INTO roles (clave, nombre, descripcion, sistema) VALUES (%s, %s, %s, 0)",
              [clave, nombre, descripcion], commit=True)
    return clave


def guardar_permisos(rol, permisos):
    """Reemplaza los permisos del rol (el administrador no se edita)."""
    if rol == ADMIN:
        return
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("DELETE FROM rol_permisos WHERE rol = %s", [rol])
            for p in sorted(set(permisos) & set(PERMISOS)):
                cur.execute("INSERT INTO rol_permisos (rol, permiso) VALUES (%s, %s)", [rol, p])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def actualizar(clave, nombre, descripcion):
    _ejecutar("UPDATE roles SET nombre=%s, descripcion=%s WHERE clave=%s", [nombre, descripcion, clave], commit=True)


def eliminar(clave):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("DELETE FROM rol_permisos WHERE rol = %s", [clave])
            cur.execute("DELETE FROM roles WHERE clave = %s AND sistema = 0", [clave])
        db.commit()
    finally:
        db.close()
