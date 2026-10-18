"""Inventario de celulares (Blueprint). Roles: Administrador y Usuario."""
import re
from datetime import date

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

import celulares_db as C
import importar_inventario as IMP
from celulares_excel import generar_excel_celulares
import personas_db as P
from seguridad import requiere_permiso, tiene

bp = Blueprint("celulares", __name__, url_prefix="/celulares")
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.before_request
def solo_autorizados():
    u = g.get("usuario")
    if not u:
        return redirect(url_for("login", siguiente=request.path))
    if not tiene("celulares.consultar"):
        abort(403)


@bp.app_context_processor
def _ctx():
    return dict(MOTIVOS_BAJA=C.MOTIVOS_BAJA, ACTAS=C.ACTAS, TIPOS_MOV=C.TIPOS_MOV)


@bp.app_template_filter("cop")
def _cop(n):
    try:
        return "$ " + "{:,}".format(int(n)).replace(",", ".")
    except (TypeError, ValueError):
        return ""


def fecha(s):
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def texto(nombre, largo):
    return (request.form.get(nombre) or "").strip()[:largo] or None


def cel_o_404(cid):
    return C.obtener(cid) or abort(404)


def filtros():
    est = request.args.get("estado")
    return {"q": (request.args.get("q") or "").strip()[:100] or None,
            "estado": est if est in ("activos", "asignado", "disponible", "baja", "todos") else "activos",
            "marca": (request.args.get("marca") or "").strip()[:60] or None,
            "operador": (request.args.get("operador") or "").strip()[:40] or None}


@bp.route("/")
def lista():
    f = filtros()
    return render_template("celulares/lista.html", filas=C.listar(f), f=f, r=C.resumen(),
                           marcas=C.valores_distintos("marca"), operadores=C.valores_distintos("operador"))


def leer_celular(cid=None):
    f = request.form
    d = {"fecha_compra": fecha(f.get("fecha_compra")), "marca": texto("marca", 60), "modelo": texto("modelo", 80),
         "imei1": re.sub(r"\s", "", f.get("imei1", ""))[:20] or None,
         "imei2": re.sub(r"\s", "", f.get("imei2", ""))[:20] or None,
         "sn": re.sub(r"\s", "", f.get("sn", ""))[:40] or None,
         "acta": f.get("acta") if f.get("acta") in C.ACTAS else "pendiente",
         "observaciones": texto("observaciones", 2000), "linea": texto("linea", 20),
         "operador": texto("operador", 40)}
    vp = re.sub(r"[^\d]", "", f.get("valor_plan", ""))
    d["valor_plan"] = int(vp) if vp else 0
    e = []
    if not d["marca"]:
        e.append("Escribe la marca.")
    if not d["modelo"]:
        e.append("Escribe el modelo.")
    if f.get("fecha_compra") and not d["fecha_compra"]:
        e.append("La fecha de compra no es válida.")
    if d["fecha_compra"] and d["fecha_compra"] > date.today():
        e.append("La fecha de compra no puede ser futura.")
    for campo, nombre in (("imei1", "IMEI 1"), ("imei2", "IMEI 2")):
        if d[campo] and not re.fullmatch(r"\d{14,16}", d[campo]):
            e.append("%s debe tener entre 14 y 16 dígitos." % nombre)
    if d["imei1"] and d["imei1"] == d["imei2"]:
        e.append("IMEI 1 e IMEI 2 no pueden ser iguales.")
    if C.duplicado("imei1", d["imei1"], cid):
        e.append("Ya existe un celular con ese IMEI 1.")
    if C.duplicado("sn", d["sn"], cid):
        e.append("Ya existe un celular con ese SN.")
    if d["linea"] and not re.fullmatch(r"\+?[\d\s-]{7,20}", d["linea"]):
        e.append("La línea asignada solo debe tener números.")
    return d, e


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:cid>/editar", methods=["GET", "POST"])
@requiere_permiso("celulares.gestionar")
def formulario(cid=None):
    actual = cel_o_404(cid) if cid else {"acta": "pendiente", "valor_plan": 0}
    errores = []
    if request.method == "POST":
        d, errores = leer_celular(cid)
        usuario = texto("usuario_actual", 150) if not cid else None
        persona_id = P.resolver(usuario) if usuario else None
        if usuario and not persona_id:
            errores.append("El usuario debe ser una persona de la lista (créala primero en Usuarios si no existe).")
        if not errores:
            if cid:
                C.actualizar(cid, d)
                flash("Celular actualizado.")
            else:
                cid = C.crear(d, persona_id, date.today().isoformat(), g.usuario["nombre"])
                flash("Celular registrado en el inventario.")
            return redirect(url_for("celulares.detalle", cid=cid))
        actual = {**d, "usuario_actual": usuario}
    return render_template("celulares/form.html", v=actual, errores=errores, cid=cid,
                           personas=P.opciones(), marcas=C.valores_distintos("marca"),
                           operadores=C.valores_distintos("operador"))


@bp.route("/<int:cid>")
def detalle(cid):
    c = cel_o_404(cid)
    return render_template("celulares/detalle.html", c=c, movs=C.movimientos(cid), hoy=date.today().isoformat(),
                           personas=P.opciones())


@bp.route("/<int:cid>/reasignar", methods=["POST"])
@requiere_permiso("celulares.gestionar")
def reasignar(cid):
    c = cel_o_404(cid)
    if c["estado"] == "baja":
        flash("El celular está dado de baja; reactívalo antes de asignarlo.")
        return redirect(url_for("celulares.detalle", cid=cid))
    texto_p, f = texto("usuario_nuevo", 150), fecha(request.form.get("fecha"))
    nuevo_id = P.resolver(texto_p) if texto_p else None
    if texto_p and not nuevo_id:
        flash("Elige una persona de la lista (si no existe, créala primero en Usuarios).")
    elif not f or f > date.today():
        flash("Escribe una fecha válida (no futura) para el movimiento.")
    elif nuevo_id == c["persona_actual_id"]:
        flash("Ese ya es el usuario actual del celular.")
    else:
        C.reasignar(cid, nuevo_id, f.isoformat(), texto("nota", 300), g.usuario["nombre"])
        flash("Asignado a %s." % P.obtener(nuevo_id)["nombre"] if nuevo_id else "Celular devuelto: queda disponible.")
    return redirect(url_for("celulares.detalle", cid=cid))


@bp.route("/<int:cid>/baja", methods=["POST"])
@requiere_permiso("celulares.gestionar")
def baja(cid):
    c = cel_o_404(cid)
    f, motivo = fecha(request.form.get("fecha")), request.form.get("motivo")
    if c["estado"] == "baja":
        flash("El celular ya está dado de baja.")
    elif not f or f > date.today() or motivo not in C.MOTIVOS_BAJA:
        flash("Indica una fecha válida y el motivo de la baja.")
    else:
        C.dar_baja(cid, f.isoformat(), motivo, texto("nota", 300), g.usuario["nombre"])
        flash("Celular dado de baja.")
    return redirect(url_for("celulares.detalle", cid=cid))


@bp.route("/<int:cid>/reactivar", methods=["POST"])
@requiere_permiso("celulares.reactivar")
def reactivar(cid):
    c = cel_o_404(cid)
    if c["estado"] == "baja":
        C.reactivar(cid, date.today().isoformat(), g.usuario["nombre"])
        flash("Celular reactivado: quedó disponible.")
    return redirect(url_for("celulares.detalle", cid=cid))


@bp.route("/exportar")
def exportar():
    f = filtros()
    celulares = C.listar(f)
    if not celulares:
        flash("No hay celulares con esos filtros para exportar.")
        return redirect(url_for("celulares.lista"))
    libro = generar_excel_celulares(celulares, C.movimientos())
    return Response(libro, mimetype=EXCEL_MIME, headers={
        "Content-Disposition": 'attachment; filename="CC_Gestion_celulares_%s.xlsx"' % date.today().strftime("%Y%m%d")})


@bp.route("/plantilla")
@requiere_permiso("celulares.gestionar")
def plantilla_importar():
    return Response(IMP.plantilla_celulares(), mimetype=EXCEL_MIME,
                    headers={"Content-Disposition": 'attachment; filename="plantilla_celulares.xlsx"'})


@bp.route("/importar", methods=["GET", "POST"])
@requiere_permiso("celulares.gestionar")
def importar():
    ctx = dict(titulo="Cargar celulares desde un archivo", volver=url_for("celulares.lista"),
               plantilla=url_for("celulares.plantilla_importar"),
               descripcion="Sube un Excel (.xlsx) o CSV con el inventario de celulares. Quien ya exista (mismo IMEI 1 o SN) se actualiza; los demás se crean y quedan en el historial de movimientos.",
               columnas="Marca · Modelo · IMEI 1 · IMEI 2 · SN · Fecha de compra · Firma/Acta · Línea asignada · Operador · Valor plan · Usuario actual · Usuario anterior · Estado · Fecha de baja · Motivo de baja · Observaciones. "
                        "Obligatorios: marca, modelo y IMEI 1 o SN. Usuario actual/anterior: documento o nombre de una persona que ya exista en Usuarios.")
    if request.method == "GET":
        return render_template("importar.html", res=None, **ctx)
    arch = request.files.get("archivo")
    if not arch or not arch.filename:
        flash("Selecciona un archivo .xlsx o .csv.")
        return render_template("importar.html", res=None, **ctx), 400
    filas, error = IMP.leer_celulares(arch.filename, arch.read())
    if error:
        flash(error)
        return render_template("importar.html", res=None, **ctx), 400
    guardar = request.form.get("solo_validar") != "1"
    res = IMP.procesar_celulares(filas, g.usuario["nombre"], guardar=guardar)
    return render_template("importar.html", res=res, guardado=guardar, **ctx)
