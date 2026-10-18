"""Inventario de equipos de cómputo (Blueprint)."""
import re
from datetime import date

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

import equipos_db as E
import importar_inventario as IMP
import personas_db as P
from equipos_excel import generar_excel_equipos
from seguridad import requiere_permiso, tiene

bp = Blueprint("equipos", __name__, url_prefix="/equipos")
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.before_request
def solo_autorizados():
    from flask import g
    if not g.get("usuario"):
        return redirect(url_for("login", siguiente=request.path))
    if not tiene("equipos.consultar"):
        abort(403)


@bp.app_context_processor
def _ctx():
    return dict(TIPOS_EQ=E.TIPOS, COMPUTO=E.COMPUTO, ESTADOS_EQ=E.ESTADOS, LICENCIAS=E.LICENCIAS, SW_ESTADOS=E.SW_ESTADOS)


def texto(nombre, largo):
    return (request.form.get(nombre) or "").strip()[:largo] or None


def gb(valor):
    """'16', '16 GB' -> 16; '1 TB' -> 1000."""
    v = (valor or "").strip().lower().replace(",", ".")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(gb|tb)?$", v)
    if not m:
        return None, bool(v)
    n = float(m.group(1)) * (1000 if m.group(2) == "tb" else 1)
    return int(round(n)), False


def fecha(s):
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def equipo_o_404(eid):
    return E.obtener(eid) or abort(404)


def filtros():
    a = request.args
    return {"q": (a.get("q") or "").strip()[:100] or None,
            "tipo": a.get("tipo") if a.get("tipo") in E.TIPOS else None,
            "estado": a.get("estado") if a.get("estado") in E.ESTADOS else None,
            "ciudad": (a.get("ciudad") or "").strip()[:100] or None,
            "software": (a.get("software") or "").strip()[:100] or None}


@bp.route("/")
def lista():
    f = filtros()
    return render_template("equipos/lista.html", filas=E.listar(f), f=f, r=E.resumen(), ciudades=E.ciudades())


def leer_equipo(eid=None):
    f = request.form
    tipo = f.get("tipo") if f.get("tipo") in E.TIPOS else None
    d = {"codigo": re.sub(r"\s", "", f.get("codigo", ""))[:30], "tipo": tipo, "marca": texto("marca", 60),
         "modelo": texto("modelo", 80), "serie": texto("serial", 60), "procesador": texto("procesador", 100),
         "ciudad": texto("ciudad", 100), "sistema_operativo": texto("sistema_operativo", 100),
         "office": texto("office", 100), "antivirus": texto("antivirus", 100),
         "estado": f.get("estado") if f.get("estado") in E.ESTADOS else "activo",
         "observaciones": texto("observaciones", 2000)}
    e = []
    d["ram_gb"], mal_ram = gb(f.get("ram_gb"))
    d["ssd_gb"], mal_ssd = gb(f.get("ssd_gb"))
    if mal_ram or mal_ssd:
        e.append("RAM y SSD se escriben en GB (ej.: 16 o 512) o en TB (ej.: 1 TB).")
    if not d["codigo"]:
        e.append("Escribe el ID de inventario.")
    elif E.duplicado(d["codigo"], eid):
        e.append("Ya existe un equipo con ese ID de inventario.")
    if not tipo:
        e.append("Elige el tipo de equipo.")
    texto_p = texto("usuario", 200)
    d["persona_id"] = P.resolver(texto_p) if texto_p else None
    if texto_p and not d["persona_id"]:
        e.append("El usuario asignado debe ser una persona de la lista (créala primero en Usuarios si no existe).")
    if tipo and tipo not in E.COMPUTO:     # los periféricos no llevan estos datos
        for c in ("procesador", "ram_gb", "ssd_gb", "sistema_operativo", "office", "antivirus"):
            d[c] = None
    return d, e, texto_p


@bp.route("/nuevo", methods=["GET", "POST"])
@bp.route("/<int:eid>/editar", methods=["GET", "POST"])
@requiere_permiso("equipos.gestionar")
def formulario(eid=None):
    if eid:
        actual = equipo_o_404(eid)
        actual["usuario_txt"] = P.etiqueta({"nombre": actual["usuario"], "num_id": actual["usuario_doc"],
                                            "id": actual["persona_id"]}) if actual["persona_id"] else ""
    else:
        actual = {"estado": "activo", "codigo": E.siguiente_codigo(), "usuario_txt": ""}
    errores = []
    if request.method == "POST":
        d, errores, texto_p = leer_equipo(eid)
        if not errores:
            if eid:
                E.actualizar(eid, d)
                flash("Equipo actualizado.")
            else:
                eid = E.crear(d)
                flash("Equipo registrado. Agrega abajo el software instalado.")
            return redirect(url_for("equipos.detalle", eid=eid))
        actual = {**actual, **d, "usuario_txt": texto_p or ""}
    return render_template("equipos/form.html", v=actual, errores=errores, eid=eid, personas=P.opciones(),
                           ciudades=E.ciudades())


@bp.route("/<int:eid>")
def detalle(eid):
    e = equipo_o_404(eid)
    return render_template("equipos/detalle.html", e=e, sw=E.software(eid))


@bp.route("/<int:eid>/software", methods=["POST"])
@requiere_permiso("equipos.gestionar")
def guardar_software(eid):
    equipo_o_404(eid)
    f = request.form
    ids, nombres = f.getlist("sw_id"), f.getlist("sw_nombre")
    n = len(nombres)
    col = lambda k: (f.getlist(k) + [""] * n)[:n]
    versiones, lics, ests, vences, notas = col("sw_version"), col("sw_licencia"), col("sw_estado"), col("sw_vence"), col("sw_notas")
    ids = (ids + [""] * n)[:n]
    borrar = {int(x) for x in f.getlist("sw_borrar") if x.isdigit()}
    filas, errores = [], []
    for i in range(n):
        nombre = nombres[i].strip()[:150]
        sid = int(ids[i]) if ids[i].isdigit() else None
        if sid in borrar:
            continue
        if not nombre:
            if sid:
                errores.append("Un programa existente quedó sin nombre (marca «Quitar» si quieres eliminarlo).")
            continue        # fila nueva vacía: se ignora
        venc = vences[i].strip()
        if venc and not fecha(venc):
            errores.append("La fecha de vencimiento de «%s» no es válida." % nombre)
        filas.append({"id": sid, "nombre": nombre, "version": versiones[i].strip()[:60] or None,
                      "tipo_licencia": lics[i] if lics[i] in E.LICENCIAS else None,
                      "estado": ests[i] if ests[i] in E.SW_ESTADOS else "activo",
                      "vencimiento": fecha(venc), "notas": notas[i].strip()[:200] or None})
    if errores:
        for m in errores:
            flash(m)
    else:
        E.guardar_software(eid, filas, borrar)
        flash("Software instalado actualizado.")
    return redirect(url_for("equipos.detalle", eid=eid))


@bp.route("/exportar")
def exportar():
    equipos = E.listar(filtros())
    if not equipos:
        flash("No hay equipos con esos filtros para exportar.")
        return redirect(url_for("equipos.lista"))
    return Response(generar_excel_equipos(equipos, E.software()), mimetype=EXCEL_MIME, headers={
        "Content-Disposition": 'attachment; filename="CC_Gestion_equipos_%s.xlsx"' % date.today().strftime("%Y%m%d")})


@bp.route("/plantilla")
@requiere_permiso("equipos.gestionar")
def plantilla_importar():
    return Response(IMP.plantilla_equipos(), mimetype=EXCEL_MIME,
                    headers={"Content-Disposition": 'attachment; filename="plantilla_equipos.xlsx"'})


@bp.route("/importar", methods=["GET", "POST"])
@requiere_permiso("equipos.gestionar")
def importar():
    ctx = dict(titulo="Cargar equipos de cómputo desde un archivo", volver=url_for("equipos.lista"),
               plantilla=url_for("equipos.plantilla_importar"),
               descripcion="Sube un Excel con la hoja «Equipos» y, si quieres, la hoja «Software» (varios programas por equipo). Quien ya exista (mismo ID de inventario) se actualiza; el software se agrega o actualiza por equipo + programa + versión.",
               columnas="Equipos: ID de inventario · Tipo de equipo · Marca · Modelo · Serie · Procesador · Memoria RAM · Almacenamiento SSD · Usuario asignado · Ciudad · Sistema operativo · Microsoft Office · Antivirus · Estado · Observaciones. "
                        "Software: ID de inventario · Programa · Versión · Tipo de licencia · Estado · Vencimiento · Notas.")
    if request.method == "GET":
        return render_template("importar.html", res=None, **ctx)
    arch = request.files.get("archivo")
    if not arch or not arch.filename:
        flash("Selecciona un archivo .xlsx o .csv.")
        return render_template("importar.html", res=None, **ctx), 400
    paquete, error = IMP.leer_equipos(arch.filename, arch.read())
    if error:
        flash(error)
        return render_template("importar.html", res=None, **ctx), 400
    guardar = request.form.get("solo_validar") != "1"
    res = IMP.procesar_equipos(paquete, guardar=guardar)
    return render_template("importar.html", res=res, guardado=guardar, **ctx)
