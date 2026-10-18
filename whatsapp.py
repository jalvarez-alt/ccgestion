"""Mensajes masivos por WhatsApp (Blueprint): campañas, historial de envíos y respuestas.

El envío real lo hace el servicio Node de la carpeta whatsapp-service/ (whatsapp-web.js), que
corre aparte; esta app le entrega los mensajes y él avisa de cada resultado/respuesta por webhook.
"""
import secrets
from datetime import date, datetime

from flask import Blueprint, Response, abort, flash, g, jsonify, redirect, render_template, request, url_for

import config
import whatsapp_db as W
from importar_inventario import _alias
from importar_personas import _matriz, filas_de
from nomina_excel import _hoja
from seguridad import requiere_permiso, tiene

bp = Blueprint("whatsapp", __name__, url_prefix="/whatsapp")
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WEBHOOKS = ("whatsapp.webhook_estado", "whatsapp.webhook_respuesta", "whatsapp.webhook_archivo", "whatsapp.webhook_latido")

COLUMNAS = [("manifiesto", "Manifiesto", "MF-123456"), ("cliente", "Cliente", "Transportes Ejemplo S.A.S."),
            ("orden_cargue", "Orden de cargue", "OC-7890"), ("remesa", "Remesa", "RM-4567"),
            ("telefono", "Teléfono", "3001234567"), ("contacto", "Contacto", "Juan Pérez")]
ALIAS = _alias(
    ("manifiesto", ["manifiesto", "mft", "nummanifiesto", "numeromanifiesto"]),
    ("cliente", ["cliente", "razonsocial", "empresa"]),
    ("orden_cargue", ["ordencargue", "ordendecargue", "oc", "ordencarga"]),
    ("remesa", ["remesa", "numremesa", "numeroremesa"]),
    ("telefono", ["telefono", "celular", "whatsapp", "numero", "movil", "tel"]),
    ("contacto", ["contacto", "nombre", "nombrecontacto"]))
MAX_FILAS = 1000


def _cfg(nombre, defecto=None):
    return getattr(config, nombre, defecto)


# ---------------------------------------------------------------- acceso
@bp.before_request
def acceso():
    if request.endpoint in WEBHOOKS:
        enviado = request.headers.get("X-WA-Token", "").encode()
        esperado = (_cfg("WA_TOKEN") or "").encode()
        if not esperado or not secrets.compare_digest(enviado, esperado):
            abort(403)
        return
    if not g.get("usuario"):
        return redirect(url_for("login", siguiente=request.path))
    if not tiene("whatsapp.consultar"):
        abort(403)


@bp.app_context_processor
def _ctx():
    return dict(WA_ESTADOS=W.ESTADOS)


# ---------------------------------------------------------------- servicio Node
# El servicio (whatsapp-service/) consulta a esta app cada pocos segundos (POST /whatsapp/webhook/latido):
# informa su estado y recibe los mensajes "en cola". No hace falta abrir ningún puerto hacia el servicio.
def estado_servicio():
    return W.estado_servicio()


# ---------------------------------------------------------------- pantallas
@bp.route("/")
def lista():
    est, error = estado_servicio()
    return render_template("whatsapp/lista.html", campanas=W.campanas(), est=est, error_servicio=error)


@bp.route("/conexion")
@requiere_permiso("whatsapp.enviar")
def conexion():
    est, error = estado_servicio()
    return render_template("whatsapp/conexion.html", est=est, error_servicio=error)


@bp.route("/conexion/cerrar", methods=["POST"])
@requiere_permiso("whatsapp.enviar")
def cerrar_sesion():
    W.pedir_cierre()
    flash("Se pidió cerrar la sesión de WhatsApp. En unos segundos aparecerá un QR nuevo para volver a conectar.")
    return redirect(url_for("whatsapp.conexion"))


def leer_archivo(archivo):
    hojas, error = _matriz(archivo.filename, archivo.read())
    if error:
        return None, [error]
    filas, error = filas_de(next(iter(hojas.values())), ALIAS, "telefono", [c for c, _, _ in COLUMNAS])
    if error:
        return None, [error]
    if len(filas) > MAX_FILAS:
        return None, ["El archivo tiene más de %d filas. Divídelo en partes." % MAX_FILAS]
    pais = _cfg("WA_PAIS", "57")
    buenas, errores, vistos = [], [], set()
    for f in filas:
        tel, e = W.normalizar_telefono(f["telefono"], pais)
        if e:
            errores.append("Fila %d: %s" % (f["_fila"], e))
            continue
        if not f["manifiesto"]:
            errores.append("Fila %d: falta el manifiesto" % f["_fila"])
            continue
        clave = (f["manifiesto"], tel)
        if clave in vistos:
            errores.append("Fila %d: el manifiesto %s ya está para ese teléfono" % (f["_fila"], f["manifiesto"]))
            continue
        vistos.add(clave)
        buenas.append({**{c: f[c][:200] or None for c, _, _ in COLUMNAS}, "telefono": tel})
    return buenas, errores


@bp.route("/nueva", methods=["GET", "POST"])
@requiere_permiso("whatsapp.enviar")
def nueva():
    v = {"nombre": "Cumplidos pendientes " + date.today().strftime("%d/%m/%Y"), "plantilla": W.PLANTILLA_DEFECTO}
    errores = []
    if request.method == "POST":
        v = {"nombre": (request.form.get("nombre") or "").strip()[:150],
             "plantilla": (request.form.get("plantilla") or "").strip()[:1500]}
        arch = request.files.get("archivo")
        if not v["nombre"]:
            errores.append("Escribe un nombre para la campaña.")
        if not v["plantilla"]:
            errores.append("Escribe el texto del mensaje.")
        if not arch or not arch.filename:
            errores.append("Selecciona el archivo .xlsx o .csv con los pendientes.")
        if not errores:
            filas, errores = leer_archivo(arch)
            if not errores and not filas:
                errores = ["El archivo no tiene filas para enviar."]
            if not errores:
                cid = W.crear_campana(v["nombre"], v["plantilla"], g.usuario["nombre"], filas)
                flash("Campaña creada con %d mensajes. Revísalos y pulsa «Enviar» cuando estés listo." % len(filas))
                return redirect(url_for("whatsapp.detalle", cid=cid))
    return render_template("whatsapp/nueva.html", v=v, errores=errores[:60], mas_errores=max(0, len(errores) - 60),
                           columnas=COLUMNAS)


@bp.route("/plantilla")
@requiere_permiso("whatsapp.enviar")
def plantilla():
    from openpyxl import Workbook
    from io import BytesIO
    wb = Workbook()
    wb.remove(wb.active)
    ws = _hoja(wb, "Pendientes", [t for _, t, _ in COLUMNAS], [[e for _, _, e in COLUMNAS]])
    for col in ("A", "C", "D", "E"):
        for celda in ws[col][1:]:
            celda.number_format = "@"
    hoja = wb.create_sheet("Instrucciones")
    for linea in ("Una fila por mensaje. La fila 1 son los títulos: no los cambies. Borra la fila de ejemplo.",
                  "Obligatorios: Manifiesto y Teléfono. Cliente, Orden de cargue y Remesa se muestran en el mensaje.",
                  "Teléfono: 10 dígitos de celular colombiano (3001234567) o con indicativo (573001234567).",
                  "Contacto (opcional): nombre de quien recibe el mensaje, para saludarlo.",
                  "Formatea Manifiesto, Orden de cargue y Remesa como TEXTO para no perder ceros a la izquierda."):
        hoja.append([linea])
    hoja.column_dimensions["A"].width = 110
    buf = BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), mimetype=EXCEL_MIME,
                    headers={"Content-Disposition": 'attachment; filename="plantilla_whatsapp_pendientes.xlsx"'})


def campana_o_404(cid):
    return W.campana(cid) or abort(404)


@bp.route("/<int:cid>")
def detalle(cid):
    c = campana_o_404(cid)
    estado = request.args.get("estado")
    est, error = estado_servicio()
    msgs = W.mensajes(cid, estado)
    conteo = {}
    for m in W.mensajes(cid):
        conteo[m["estado"]] = conteo.get(m["estado"], 0) + 1
    return render_template("whatsapp/campana.html", c=c, msgs=msgs, conteo=conteo, filtro=estado, est=est,
                           error_servicio=error, resp=W.respuestas_de_campana(cid))


@bp.route("/<int:cid>/enviar", methods=["POST"])
@requiere_permiso("whatsapp.enviar")
def enviar(cid):
    campana_o_404(cid)
    est, error = estado_servicio()
    if error or est.get("estado") != "listo":
        flash(error or "WhatsApp no está conectado. Ve a «Conexión» y escanea el QR.")
        return redirect(url_for("whatsapp.detalle", cid=cid))
    estados = ("pendiente", "error") if request.form.get("reintentar") == "1" else ("pendiente",)
    pendientes = [m for m in W.mensajes(cid) if m["estado"] in estados]
    if not pendientes:
        flash("No hay mensajes por enviar.")
        return redirect(url_for("whatsapp.detalle", cid=cid))
    ids = [m["id"] for m in pendientes]
    W.marcar_en_cola(ids)
    flash("%d mensajes en cola. El servicio los toma en unos segundos y los envía uno a uno con pausas aleatorias; "
          "esta página se puede cerrar." % len(ids))
    return redirect(url_for("whatsapp.detalle", cid=cid))


@bp.route("/<int:cid>/reponer", methods=["POST"])
@requiere_permiso("whatsapp.enviar")
def reponer(cid):
    """Cancela lo que sigue en cola (los que ya salieron no se tocan)."""
    campana_o_404(cid)
    W.reponer_en_cola(cid)
    flash("Los mensajes en cola volvieron a «Pendiente».")
    return redirect(url_for("whatsapp.detalle", cid=cid))


@bp.route("/<int:cid>/exportar")
def exportar(cid):
    from io import BytesIO
    from openpyxl import Workbook
    c = campana_o_404(cid)
    fmt = lambda d: d.strftime("%Y-%m-%d %H:%M") if d else ""
    msgs = W.mensajes(cid)
    wb = Workbook()
    wb.remove(wb.active)
    _hoja(wb, "Envíos", ["Manifiesto", "Cliente", "Orden de cargue", "Remesa", "Contacto", "Teléfono", "Estado",
                         "Enviado", "Entregado", "Leído", "Respuestas", "Última respuesta", "Error"],
          [[m["manifiesto"] or "", m["cliente"] or "", m["orden_cargue"] or "", m["remesa"] or "", m["contacto"] or "",
            m["telefono"], W.ESTADOS.get(m["estado"], m["estado"]), fmt(m["enviado_en"]), fmt(m["entregado_en"]),
            fmt(m["leido_en"]), m["n_resp"], m["ultima_resp"] or "", m["error"] or ""] for m in msgs])
    _hoja(wb, "Respuestas", ["Recibida", "Manifiesto", "Cliente", "Orden de cargue", "Remesa", "Teléfono", "Respuesta", "Archivo en OneDrive", "Enlace"],
          [[fmt(r["recibida_en"]), r["manifiesto"] or "", r["cliente"] or "", r["orden_cargue"] or "",
            r["remesa"] or "", r["telefono"], r["texto"] or "(%s)" % r["tipo"], r["archivo_nombre"] or "",
            r["archivo_url"] or ""] for r in W.respuestas_de_campana(cid)])
    buf = BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), mimetype=EXCEL_MIME, headers={
        "Content-Disposition": 'attachment; filename="CC_Gestion_whatsapp_%d_%s.xlsx"' % (c["id"], date.today().strftime("%Y%m%d"))})


@bp.route("/respuestas")
def todas_respuestas():
    return render_template("whatsapp/respuestas.html", filas=W.respuestas())


# ---------------------------------------------------------------- webhooks (los llama el servicio Node)
@bp.route("/webhook/estado", methods=["POST"])
def webhook_estado():
    d = request.get_json(silent=True) or {}
    if "ack" in d:
        W.confirmacion(d.get("wa_id"), int(d["ack"]))
    elif d.get("id"):
        W.resultado_envio(int(d["id"]), bool(d.get("ok")), d.get("wa_id"), d.get("error"))
    return jsonify(ok=True)


@bp.route("/webhook/respuesta", methods=["POST"])
def webhook_respuesta():
    d = request.get_json(silent=True) or {}
    tel = "".join(ch for ch in str(d.get("telefono", "")) if ch.isdigit())[:20]
    if not tel:
        return jsonify(ok=False), 400
    try:
        cuando = datetime.fromtimestamp(int(d.get("ts") or 0)) if d.get("ts") else W.ahora()
    except (ValueError, OSError):
        cuando = W.ahora()
    rid, m = W.guardar_respuesta(tel, d.get("texto"), str(d.get("tipo") or "chat"), d.get("wa_id"), d.get("citado_id"),
                                 cuando, con_archivo=bool(d.get("tiene_archivo")))
    # El servicio usa el manifiesto/cliente para nombrar y ubicar el adjunto en OneDrive
    return jsonify(ok=True, respuesta_id=rid, mensaje=({"manifiesto": m["manifiesto"], "cliente": m["cliente"]} if m else None))


@bp.route("/webhook/archivo", methods=["POST"])
def webhook_archivo():
    d = request.get_json(silent=True) or {}
    if not str(d.get("respuesta_id", "")).isdigit():
        return jsonify(ok=False), 400
    W.resultado_archivo(int(d["respuesta_id"]), d.get("estado"), d.get("nombre"), d.get("url"), d.get("error"))
    return jsonify(ok=True)


@bp.route("/webhook/latido", methods=["POST"])
def webhook_latido():
    """Señal periódica del servicio: estado/QR; responde con los mensajes por enviar y órdenes pendientes."""
    d = request.get_json(silent=True) or {}
    qr = d.get("qr") if isinstance(d.get("qr"), str) and d["qr"].startswith("data:image/png;base64,") else None
    comando, mensajes, vigentes = W.latido(str(d.get("estado") or "desconocido")[:20], qr,
                                          str(d.get("numero") or "")[:30] or None, int(d.get("en_cola") or 0))
    return jsonify(ok=True, comando=comando, mensajes=mensajes, vigentes=vigentes)
