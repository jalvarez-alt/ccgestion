"""Administración de usuarios (tabla única de personas) y de roles/permisos."""
import re
from datetime import date

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

import importar_personas as IMP

import personas_db as P
import roles_db as R
from seguridad import ADMIN, PERMISOS, requiere_permiso, requiere_rol, tiene

bp = Blueprint("usuarios", __name__)
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.route("/usuarios")
@requiere_permiso("personas.consultar")
def lista():
    ver = "todos" if request.args.get("ver") == "todos" else "app"
    q = (request.args.get("q") or "").strip()[:100] or None
    return render_template("usuarios/lista.html", ver=ver, q=q, filas=P.con_antiguedad(P.listar(ver, q)), cuentas=P.conteos())


def roles_asignables():
    nombres = R.nombres_roles()
    if g.usuario["rol"] != ADMIN:
        nombres.pop(ADMIN, None)
    return nombres


def leer_persona(pid=None):
    f = request.form
    d = {"nombre": f.get("nombre", "").strip()[:200], "tipo_id": f.get("tipo_id") if f.get("tipo_id") in P.TIPOS_ID else None,
         "num_id": re.sub(r"\s", "", f.get("num_id", ""))[:30] or None,
         "correo": f.get("correo", "").strip().lower()[:190] or None,
         "telefono": f.get("telefono", "").strip()[:40] or None, "cargo": f.get("cargo", "").strip()[:150] or None,
         "ciudad": f.get("ciudad", "").strip()[:100] or None,
         "fecha_ingreso": P.a_fecha(f.get("fecha_ingreso"))}
    if d["num_id"] and not d["tipo_id"]:
        d["tipo_id"] = "C.C."
    if not d["num_id"]:
        d["tipo_id"] = None
    e = []
    if f.get("fecha_ingreso", "").strip() and not d["fecha_ingreso"]:
        e.append("La fecha de ingreso no es válida.")
    elif d["fecha_ingreso"] and d["fecha_ingreso"] > date.today():
        e.append("La fecha de ingreso no puede ser futura.")
    if len(d["nombre"]) < 3:
        e.append("Escribe el nombre completo.")
    if d["correo"] and (not RE_CORREO.match(d["correo"])):
        e.append("El correo no es válido.")
    if P.duplicado("correo", d["correo"], pid):
        e.append("Ya existe una persona con ese correo.")
    if P.duplicado("num_id", d["num_id"], pid):
        e.append("Ya existe una persona con ese número de documento.")
    return d, e


@bp.route("/usuarios/<int:pid>")
@requiere_permiso("personas.consultar")
def ficha(pid):
    p = P.obtener(pid) or abort(404)
    return render_template("usuarios/ficha.html", p=P.con_antiguedad(p), ROL=R.nombres_roles().get(p["rol"]) if p["rol"] else None)


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@bp.route("/usuarios/<int:pid>/editar", methods=["GET", "POST"])
@requiere_permiso("personas.gestionar")
def formulario(pid=None):
    actual = P.obtener(pid) if pid else {"activo": 0, "rol": None}
    if pid and not actual:
        abort(404)
    if pid and actual["rol"] == ADMIN and g.usuario["rol"] != ADMIN:
        abort(403)
    es_yo = bool(pid) and pid == g.usuario["id"]
    errores = []
    if request.method == "POST":
        d, errores = leer_persona(pid)
        acceso = (request.form.get("acceso") == "1") or es_yo
        rol = request.form.get("rol") or None
        clave, clave2 = request.form.get("clave", "")[:200], request.form.get("clave2", "")[:200]
        if es_yo:
            rol, acceso = actual["rol"], True
        asignables = roles_asignables()
        if rol and rol not in asignables and not (es_yo and rol == actual["rol"]):
            errores.append("Selecciona un rol válido.")
        if clave and len(clave) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")
        if clave != clave2:
            errores.append("Las contraseñas no coinciden.")
        if acceso:
            if not rol:
                errores.append("Para habilitar el acceso elige un rol.")
            if not d["correo"]:
                errores.append("Para habilitar el acceso la persona necesita un correo (es su usuario de ingreso).")
            if not clave and not (pid and actual["tiene_clave"]):
                errores.append("Para habilitar el acceso define una contraseña.")
        if pid and actual["rol"] == ADMIN and actual["activo"] and (not acceso or rol != ADMIN) \
                and P.admins_activos(excepto=pid) == 0:
            errores.append("Debe quedar al menos un administrador con acceso.")
        if not errores:
            if pid:
                P.actualizar(pid, d, rol=rol if (acceso or rol) else None, activo=acceso, clave=clave or None,
                             cambiar_acceso=True)
                flash("Datos guardados.")
            else:
                pid = P.crear(d, rol=rol, clave=clave or None, activo=acceso)
                flash("Persona creada%s." % (" con acceso a la aplicación" if acceso else " (sin acceso a la aplicación)"))
            return redirect(url_for("usuarios.lista", ver="app" if acceso else "todos"))
        actual = {**actual, **d, "rol": rol, "activo": 1 if acceso else 0}
    if pid:
        actual = {**actual, "antiguedad": P.antiguedad(actual.get("fecha_ingreso"))[0]}
    return render_template("usuarios/form.html", v=actual, errores=errores, pid=pid, es_yo=es_yo,
                           roles=roles_asignables(), tipos_id=P.TIPOS_ID, hoy=date.today().isoformat())


@bp.route("/usuarios/<int:pid>/acceso", methods=["POST"])
@requiere_permiso("personas.gestionar")
def acceso(pid):
    p = P.obtener(pid) or abort(404)
    if p["rol"] == ADMIN and g.usuario["rol"] != ADMIN:
        abort(403)
    volver = url_for("usuarios.lista", ver="todos" if request.form.get("ver") == "todos" else "app")
    if request.form.get("accion") == "habilitar":
        if not (p["correo"] and p["rol"] and p["tiene_clave"]):
            flash("Para habilitar el acceso de %s completa su correo, rol y contraseña." % p["nombre"])
            return redirect(url_for("usuarios.formulario", pid=pid))
        P.cambiar_acceso(pid, True)
        flash("Acceso habilitado: %s." % p["nombre"])
    else:
        if pid == g.usuario["id"]:
            flash("No puedes deshabilitar tu propio acceso.")
        elif p["rol"] == ADMIN and p["activo"] and P.admins_activos(excepto=pid) == 0:
            flash("Debe quedar al menos un administrador con acceso.")
        else:
            P.cambiar_acceso(pid, False)
            flash("Acceso deshabilitado: %s. Su información no se eliminó." % p["nombre"])
    return redirect(volver)


# ---------------------------------------------------------------- roles y permisos
@bp.route("/roles", methods=["GET", "POST"])
@requiere_rol(ADMIN)
def roles():
    errores = []
    if request.method == "POST":
        accion = request.form.get("accion")
        clave = request.form.get("rol", "")
        if accion == "crear":
            nombre = request.form.get("nombre", "").strip()[:60]
            if len(nombre) < 3:
                errores.append("Escribe un nombre para el rol (mínimo 3 letras).")
            elif nombre.lower() in {n.lower() for n in R.nombres_roles().values()}:
                errores.append("Ya existe un rol con ese nombre.")
            else:
                nuevo = R.crear(nombre, request.form.get("descripcion", "").strip()[:200] or None)
                flash("Rol creado. Marca ahora sus permisos y guarda.")
                return redirect(url_for("usuarios.roles") + "#r-" + nuevo)
        elif accion == "guardar" and R.existe(clave) and clave != ADMIN:
            R.guardar_permisos(clave, [p for p in request.form.getlist("permiso") if p in PERMISOS])
            if request.form.get("nombre", "").strip():
                R.actualizar(clave, request.form["nombre"].strip()[:60],
                             request.form.get("descripcion", "").strip()[:200] or None)
            flash("Permisos del rol guardados.")
            return redirect(url_for("usuarios.roles") + "#r-" + clave)
        elif accion == "eliminar" and R.existe(clave):
            fila = next((r for r in R.listar_roles() if r["clave"] == clave), None)
            if fila["sistema"]:
                errores.append("Los roles base no se pueden eliminar.")
            elif fila["n_usuarios"]:
                errores.append("No se puede eliminar: hay %d persona(s) con ese rol. Cámbiales el rol primero." % fila["n_usuarios"])
            else:
                R.eliminar(clave)
                flash("Rol eliminado.")
                return redirect(url_for("usuarios.roles"))
    grupos = {}
    for k, (modulo, desc) in PERMISOS.items():
        grupos.setdefault(modulo, []).append((k, desc))
    return render_template("usuarios/roles.html", roles=R.listar_roles(), grupos=grupos, errores=errores, ADMIN=ADMIN)


EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.route("/usuarios/plantilla")
@requiere_permiso("personas.gestionar")
def plantilla_importar():
    return Response(IMP.plantilla(), mimetype=EXCEL_MIME,
                    headers={"Content-Disposition": 'attachment; filename="plantilla_personas.xlsx"'})


@bp.route("/usuarios/importar", methods=["GET", "POST"])
@requiere_permiso("personas.gestionar")
def importar():
    if request.method == "GET":
        return render_template("usuarios/importar.html", res=None)
    arch = request.files.get("archivo")
    if not arch or not arch.filename:
        flash("Selecciona un archivo .xlsx o .csv.")
        return render_template("usuarios/importar.html", res=None), 400
    filas, error = IMP.leer_archivo(arch.filename, arch.read())
    if error:
        flash(error)
        return render_template("usuarios/importar.html", res=None), 400
    guardar = request.form.get("solo_validar") != "1"
    res = IMP.procesar(filas, guardar=guardar)
    return render_template("usuarios/importar.html", res=res, guardado=guardar, total=len(filas))
