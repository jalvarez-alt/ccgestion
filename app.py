import json
import math
import re
import secrets
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)

import config
import consultas as Q
import etiquetas
import textos
from db import get_db
from excel import generar_excel
from guardar import guardar_registro
from pdf_gen import generar_pdf
import roles_db as R
from celulares import bp as celulares_bp
from equipos import bp as equipos_bp
from nomina import bp as nomina_bp
from usuarios import bp as usuarios_bp
from seguridad import (PERMISOS, csrf_token, destino_seguro, login_requerido, requiere_permiso, requiere_rol, tiene, tiene_alguno,
                       revisar_csrf, verificar_clave)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config.update(
    MAX_CONTENT_LENGTH=1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=getattr(config, "COOKIE_SEGURA", True),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

CAMPOS_LARGOS = {"descripcion", "origen_fondos", "pep1_detalle", "pep2_detalle"}
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LOGO_POR_DEFECTO = "https://camionesycamiones.com.co/wp-content/uploads/2025/08/camiones_camiones_logo.png"
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
app.register_blueprint(nomina_bp)
app.register_blueprint(celulares_bp)
app.register_blueprint(usuarios_bp)
app.register_blueprint(equipos_bp)


@app.before_request
def antes():
    if request.endpoint == "static":
        return
    revisar_csrf()
    g.usuario = None
    g.permisos = frozenset()
    g.roles_nombres = {}
    uid = session.get("uid")
    if uid:
        u = Q.usuario_por_id(uid)
        if u and u["activo"] and u["rol"]:
            g.permisos = frozenset(R.permisos_de(u["rol"]))
            u["ver_todos"] = "sgcs.todos" in g.permisos
            g.usuario = u
            g.roles_nombres = R.nombres_roles()
        else:
            session.pop("uid", None)


@app.context_processor
def inyectar():
    return dict(csrf_token=csrf_token, usuario=g.get("usuario"), ROLES=g.get("roles_nombres", {}),
                puede=tiene, puede_alguno=tiene_alguno,
                mostrar=etiquetas.mostrar, etiquetas=etiquetas,
                permitir_registro=getattr(config, "PERMITIR_REGISTRO", True),
                logo_url=getattr(config, "LOGO_URL", None) or url_for("static", filename="logo.png"))


def iniciar_sesion(uid):
    session.clear()
    session["uid"] = uid
    session.permanent = True


def validar_cuenta(nombre, correo, clave, clave2):
    e = []
    if not nombre or len(nombre) < 3:
        e.append("Escribe el nombre completo.")
    if not RE_CORREO.match(correo) or len(correo) > 190:
        e.append("Escribe un correo electrónico válido.")
    if len(clave) < 8:
        e.append("La contraseña debe tener al menos 8 caracteres.")
    if clave != clave2:
        e.append("Las contraseñas no coinciden.")
    return e


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("inicio"))
    if not Q.hay_usuarios():
        return redirect(url_for("configurar"))
    error = None
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()[:190]
        clave = request.form.get("clave", "")[:200]
        u = Q.usuario_por_correo(correo)
        ahora = datetime.now()
        if u and u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
            error = "Cuenta bloqueada temporalmente por intentos fallidos. Intenta de nuevo en unos minutos."
        elif u and u["activo"] and verificar_clave(u["password_hash"], clave):
            Q.login_exitoso(u["id"], ahora)
            destino = destino_seguro(request.args.get("siguiente"), url_for("inicio"))
            iniciar_sesion(u["id"])
            return redirect(destino)
        else:
            if u:
                Q.login_fallido(u["id"], u["intentos"], ahora + timedelta(minutes=15))
            error = "Correo o contraseña incorrectos."
    return render_template("login.html", error=error)


@app.route("/salir", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/configurar", methods=["GET", "POST"])
def configurar():
    """Crea el primer administrador. Solo funciona mientras no exista ningún usuario."""
    if Q.hay_usuarios():
        abort(404)
    errores = []
    if config.SECRET_KEY.startswith("CAMBIA"):
        errores.append("Antes de continuar, cambia SECRET_KEY en config.py por un texto largo y aleatorio.")
    v = {}
    if request.method == "POST" and not errores:
        v = {k: request.form.get(k, "").strip() for k in ("nombre", "correo")}
        v["correo"] = v["correo"].lower()
        errores = validar_cuenta(v["nombre"], v["correo"], request.form.get("clave", ""),
                                 request.form.get("clave2", ""))
        if not errores:
            uid = Q.crear_usuario(v["nombre"][:200], v["correo"], request.form["clave"], "administrador")
            iniciar_sesion(uid)
            flash("Administrador creado. ¡Bienvenido!")
            return redirect(url_for("inicio"))
    return render_template("cuenta.html", titulo="Configuración inicial: crear administrador",
                           boton="Crear administrador", errores=errores, v=v)


@app.route("/registro", methods=["GET", "POST"])
def registro_usuario():
    """Autoregistro: crea cuentas con rol Vinculante."""
    if not getattr(config, "PERMITIR_REGISTRO", True):
        abort(404)
    if g.usuario:
        return redirect(url_for("inicio"))
    if not Q.hay_usuarios():
        return redirect(url_for("configurar"))
    errores, v = [], {}
    if request.method == "POST":
        if request.form.get("web"):
            abort(400)
        v = {k: request.form.get(k, "").strip() for k in ("nombre", "correo")}
        v["correo"] = v["correo"].lower()
        errores = validar_cuenta(v["nombre"], v["correo"], request.form.get("clave", ""),
                                 request.form.get("clave2", ""))
        if not errores and Q.usuario_por_correo(v["correo"]):
            errores.append("Ya existe una cuenta con ese correo.")
        if not errores:
            uid = Q.crear_usuario(v["nombre"][:200], v["correo"], request.form["clave"], "vinculante")
            iniciar_sesion(uid)
            return redirect(url_for("inicio"))
    return render_template("cuenta.html", titulo="Crear cuenta", boton="Crear cuenta",
                           errores=errores, v=v, trampa=True)


@app.route("/")
def inicio():
    if not g.usuario:
        return render_template("bienvenida.html")
    return render_template("inicio.html")


@app.route("/tecnologia")
@requiere_permiso("celulares.consultar", "equipos.consultar")
def tecnologia():
    return render_template("tecnologia.html")


@app.route("/sgcs")
@requiere_permiso("sgcs.formulario", "sgcs.consultar", "sgcs.exportar")
def sgcs():
    return render_template("sgcs.html")


def _entero(s):
    d = re.sub(r"[^\d-]", "", s or "")
    return int(d) if re.fullmatch(r"-?\d+", d) else None


def leer_formulario():
    datos = {}
    for k in list(request.form.keys())[:400]:
        if len(k) > 40 or k == "csrf":
            continue
        v = request.form.get(k, "").strip()
        if k == "firma_img":
            datos[k] = v if v.startswith("data:image/png;base64,") and len(v) < 400000 else ""
        else:
            datos[k] = v[:3000] if k in CAMPOS_LARGOS else v[:300]
    for n in (1, 2):
        a, p = _entero(datos.get("fin%d_activos" % n)), _entero(datos.get("fin%d_pasivos" % n))
        if a is not None and p is not None:
            datos["fin%d_patrimonio" % n] = str(a - p)
    return datos


def validar(d):
    e = []
    if not d.get("fecha"):
        e.append("Indica la fecha de diligenciamiento.")
    if not (d.get("es_cliente") or d.get("es_proveedor")):
        e.append("Marca si la vinculación es como Cliente y/o Proveedor.")
    if d.get("solicitud") not in ("nuevo", "actualizacion"):
        e.append("Indica si es una vinculación Nueva o una Actualización.")
    tp = d.get("tipo_persona")
    if tp == "natural":
        for k, n in (("pn_nombre", "el nombre completo"), ("pn_tipo_id", "el tipo de identificación"),
                     ("pn_num_id", "el número de identificación")):
            if not d.get(k):
                e.append("Persona natural: falta %s." % n)
    elif tp == "juridica":
        for k, n in (("pj_razon", "la razón social"), ("pj_nit", "el NIT"),
                     ("rl_nombre", "el nombre del representante legal"),
                     ("rl_tipo_id", "el tipo de identificación del representante legal"),
                     ("rl_num_id", "el número de identificación del representante legal")):
            if not d.get(k):
                e.append("Persona jurídica: falta %s." % n)
    else:
        e.append("Selecciona si eres Persona Natural o Persona Jurídica.")
    if not d.get("acepta_datos"):
        e.append("Debes aceptar la autorización de tratamiento de datos personales (sección 10).")
    if not d.get("firma_nombre") or not d.get("firma_cc"):
        e.append("Escribe el nombre y la C.C. de quien firma (sección 12).")
    return e


@app.route("/vinculacion", methods=["GET", "POST"])
@requiere_permiso("sgcs.formulario")
def formulario():
    if request.method == "GET":
        return render_template("formulario.html", v={"fecha": date.today().isoformat()},
                               errores=[], textos=textos)
    if request.form.get("web"):
        abort(400)
    d = leer_formulario()
    errores = validar(d)
    if errores:
        return render_template("formulario.html", v=d, errores=errores, textos=textos), 400
    db = get_db()
    try:
        rid = guardar_registro(db, secrets.token_urlsafe(24), d, usuario_id=g.usuario["id"])
    except Exception:
        app.logger.exception("No se pudo guardar el registro")
        errores = ["No se pudo guardar el formulario. Intenta de nuevo en unos minutos."]
        return render_template("formulario.html", v=d, errores=errores, textos=textos), 500
    finally:
        db.close()
    return redirect(url_for("registro_listo", rid=rid))


def leer_filtros():
    def fecha_ok(s):
        return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or "") else None
    tipo = request.args.get("tipo")
    return {"q": (request.args.get("q") or "").strip()[:100] or None,
            "tipo": tipo if tipo in ("natural", "juridica") else None,
            "desde": fecha_ok(request.args.get("desde")),
            "hasta": fecha_ok(request.args.get("hasta"))}


@app.route("/registros")
@requiere_permiso("sgcs.consultar")
def registros():
    filtros = leer_filtros()
    total = Q.contar_registros(filtros, g.usuario)
    paginas = max(1, math.ceil(total / Q.POR_PAGINA))
    try:
        pagina = min(max(1, int(request.args.get("pagina", 1))), paginas)
    except ValueError:
        pagina = 1
    filas = Q.listar_registros(filtros, g.usuario, pagina)
    return render_template("registros.html", filas=filas, filtros=filtros, total=total,
                           pagina=pagina, paginas=paginas)


@app.route("/registros/exportar")
@requiere_permiso("sgcs.exportar")
def exportar():
    libro = generar_excel(Q.datos_exportacion(leer_filtros(), g.usuario))
    nombre = "CC_Gestion_registros_%s.xlsx" % date.today().strftime("%Y%m%d")
    return Response(libro, mimetype=EXCEL_MIME,
                    headers={"Content-Disposition": 'attachment; filename="%s"' % nombre})


@app.route("/registros/<int:rid>")
@requiere_permiso("sgcs.consultar")
def registro_detalle(rid):
    info = Q.obtener_registro(rid, g.usuario)
    if not info:
        abort(404)
    return render_template("registro_detalle.html", **info)


@app.route("/registros/<int:rid>/listo")
@requiere_permiso("sgcs.formulario", "sgcs.consultar")
def registro_listo(rid):
    info = Q.obtener_registro(rid, g.usuario)
    if not info:
        abort(404)
    return render_template("gracias.html", r=info["r"])


@app.route("/registros/<int:rid>/pdf")
@requiere_permiso("sgcs.consultar")
def registro_pdf(rid):
    fila = Q.datos_pdf(rid, g.usuario)
    if not fila:
        abort(404)
    pdf = generar_pdf(json.loads(fila["datos"]))
    limpio = re.sub(r"[^A-Za-z0-9]", "", fila["identificacion"] or "") or "formato"
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="P01FOR007_%s.pdf"' % limpio})


@app.route("/mi-clave", methods=["GET", "POST"])
@login_requerido
def cambiar_clave():
    errores = []
    if request.method == "POST":
        actual = request.form.get("actual", "")[:200]
        nueva = request.form.get("clave", "")[:200]
        repite = request.form.get("clave2", "")[:200]
        fila = Q.usuario_por_correo(g.usuario["correo"])
        ahora = datetime.now()
        if fila["bloqueado_hasta"] and fila["bloqueado_hasta"] > ahora:
            errores.append("Cuenta bloqueada temporalmente por intentos fallidos. Intenta de nuevo en unos minutos.")
        elif not verificar_clave(fila["password_hash"], actual):
            Q.login_fallido(fila["id"], fila["intentos"], ahora + timedelta(minutes=15))
            errores.append("La contraseña actual no es correcta.")
        elif len(nueva) < 8:
            errores.append("La nueva contraseña debe tener al menos 8 caracteres.")
        elif nueva != repite:
            errores.append("Las contraseñas nuevas no coinciden.")
        elif nueva == actual:
            errores.append("La nueva contraseña debe ser diferente de la actual.")
        if not errores:
            Q.cambiar_clave(fila["id"], nueva)
            iniciar_sesion(fila["id"])
            flash("Tu contraseña se cambió correctamente.")
            return redirect(url_for("inicio"))
    return render_template("cambiar_clave.html", errores=errores)


def _error(codigo, titulo, mensaje):
    return render_template("error.html", codigo=codigo, titulo=titulo, mensaje=mensaje), codigo


@app.errorhandler(400)
def e400(e):
    return _error(400, "Solicitud no válida", "Tu sesión pudo haber expirado. Recarga la página e inténtalo de nuevo.")


@app.errorhandler(403)
def e403(e):
    return _error(403, "Sin permiso", "Tu rol no tiene acceso a esta sección.")


@app.errorhandler(404)
def e404(e):
    return _error(404, "Página no encontrada", "El enlace no existe o no tienes acceso a este registro.")
