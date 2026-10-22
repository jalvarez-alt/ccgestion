"""Contraseñas, CSRF, roles y permisos."""
import secrets
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# Catálogo de permisos: clave -> (módulo, descripción). El rol "administrador" siempre los tiene todos.
PERMISOS = {
    "sgcs.formulario": ("S.G.C.S.", "Diligenciar el formulario de vinculación"),
    "sgcs.consultar": ("S.G.C.S.", "Consultar registros y descargar PDF"),
    "sgcs.todos": ("S.G.C.S.", "Ver los registros de todos (sin este permiso solo ve los suyos)"),
    "sgcs.exportar": ("S.G.C.S.", "Exportar registros a Excel"),
    "nomina.gestionar": ("Nómina", "Ver y operar la nómina (salarios, liquidación, desprendibles)"),
    "nomina.reabrir": ("Nómina", "Reabrir periodos de nómina cerrados"),
    "celulares.consultar": ("Adm. Tecnológica · Celulares", "Consultar el inventario de celulares"),
    "celulares.gestionar": ("Adm. Tecnológica · Celulares", "Crear, editar, reasignar y dar de baja celulares"),
    "celulares.reactivar": ("Adm. Tecnológica · Celulares", "Reactivar celulares dados de baja"),
    "equipos.consultar": ("Adm. Tecnológica · Equipos", "Consultar el inventario de equipos"),
    "equipos.gestionar": ("Adm. Tecnológica · Equipos", "Crear y editar equipos y su software"),
    "whatsapp.consultar": ("WhatsApp", "Ver campañas, historial de envíos y respuestas (y exportar a Excel)"),
    "whatsapp.campanas": ("WhatsApp", "Crear campañas, descargar la plantilla y finalizar o reabrir contactos"),
    "whatsapp.enviar": ("WhatsApp", "Enviar los avisos (primero y segundo) y cancelar lo que siga en cola"),
    "whatsapp.servicio": ("WhatsApp", "Conexión (QR), reiniciar el servicio y cerrar la sesión de WhatsApp"),
    "personas.consultar": ("Usuarios", "Ver usuarios de la aplicación y todos los usuarios"),
    "personas.gestionar": ("Usuarios", "Crear/editar personas y habilitar o deshabilitar el acceso"),
}
ADMIN = "administrador"


def hash_clave(clave):
    return generate_password_hash(clave, method="pbkdf2:sha256")


def verificar_clave(hash_guardado, clave):
    return check_password_hash(hash_guardado, clave)


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def revisar_csrf():
    if request.method == "POST":
        enviado = request.form.get("csrf", "").encode()
        esperado = session.get("csrf", "").encode()
        if not esperado or not secrets.compare_digest(enviado, esperado):
            abort(400)


def destino_seguro(destino, defecto):
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return defecto


def tiene(permiso):
    """True si el usuario de la petición actual tiene el permiso."""
    u = g.get("usuario")
    return bool(u) and permiso in g.get("permisos", ())


def tiene_alguno(*permisos):
    return any(tiene(p) for p in permisos)


def requiere_permiso(*permisos):
    """Deja pasar si el usuario tiene AL MENOS UNO de los permisos."""
    def decorador(f):
        @wraps(f)
        def envoltura(*a, **k):
            if not g.get("usuario"):
                return redirect(url_for("login", siguiente=request.path))
            if permisos and not tiene_alguno(*permisos):
                abort(403)
            return f(*a, **k)
        return envoltura
    return decorador


def requiere_rol(*roles):
    def decorador(f):
        @wraps(f)
        def envoltura(*a, **k):
            u = g.get("usuario")
            if not u:
                return redirect(url_for("login", siguiente=request.path))
            if roles and u["rol"] not in roles:
                abort(403)
            return f(*a, **k)
        return envoltura
    return decorador


login_requerido = requiere_rol()
