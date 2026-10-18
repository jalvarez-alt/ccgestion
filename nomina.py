"""Módulo de nómina (Blueprint). Solo roles Administrador y Nómina."""
import re
from datetime import date

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for)

import correo
import nomina_db as N
from nomina_calculo import TIPOS, a_fecha, calcular
from nomina_excel import MESES, generar_excel_nomina
from nomina_pdf import generar_desprendible, nombre_periodo
import personas_db as P
from seguridad import requiere_permiso, tiene

bp = Blueprint("nomina", __name__, url_prefix="/nomina")
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIPOS_ID = ["C.C.", "C.E.", "T.I.", "PEP", "PPT", "Pasaporte"]
LOTE_CORREOS = 10


@bp.before_request
def solo_nomina():
    u = g.get("usuario")
    if not u:
        return redirect(url_for("login", siguiente=request.path))
    if not tiene("nomina.gestionar"):
        abort(403)


# ----------------------------------------------------------------- utilidades
def entero(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else None


def decimal(s):
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fecha(s):
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def pesos(n):
    try:
        return "$ " + "{:,}".format(int(round(float(n)))).replace(",", ".")
    except (TypeError, ValueError):
        return ""


@bp.app_template_filter("pesos")
def _pesos(n):
    return pesos(n)


@bp.app_context_processor
def _ctx():
    return dict(MESES=MESES, TIPOS=TIPOS, nombre_periodo=nombre_periodo)


def empleador_o_404(eid):
    e = N.obtener_empleador(eid)
    if not e:
        abort(404)
    return e


def periodo_o_404(pid):
    p = N.obtener_periodo(pid)
    if not p:
        abort(404)
    return p


# ----------------------------------------------------------------- panel
@bp.route("/")
def panel():
    return render_template("nomina/panel.html", empleadores=N.listar_empleadores(),
                           periodos=N.listar_periodos()[:8], smtp=correo.configurado())


# ----------------------------------------------------------------- empleadores
def leer_empleador():
    f = request.form
    d = {"nombre": f.get("nombre", "").strip()[:200], "nit": f.get("nit", "").strip()[:30],
         "direccion": f.get("direccion", "").strip()[:200] or None, "ciudad": f.get("ciudad", "").strip()[:100] or None,
         "telefono": f.get("telefono", "").strip()[:40] or None, "email": f.get("email", "").strip()[:190] or None,
         "exonerado": f.get("exonerado") == "1", "activo": f.get("activo", "1") == "1"}
    e = []
    if len(d["nombre"]) < 3:
        e.append("Escribe la razón social del empleador.")
    if not d["nit"]:
        e.append("Escribe el NIT.")
    if d["email"] and not RE_CORREO.match(d["email"]):
        e.append("El correo del empleador no es válido.")
    return d, e


@bp.route("/empleadores/nuevo", methods=["GET", "POST"])
@bp.route("/empleadores/<int:eid>/editar", methods=["GET", "POST"])
def empleador_form(eid=None):
    actual = empleador_o_404(eid) if eid else {"exonerado": 1, "activo": 1}
    errores = []
    if request.method == "POST":
        d, errores = leer_empleador()
        if not errores:
            nuevo = N.guardar_empleador(eid, d)
            flash("Empleador guardado.")
            return redirect(url_for("nomina.empleador", eid=nuevo))
        actual = d
    return render_template("nomina/empleador_form.html", v=actual, errores=errores, eid=eid)


@bp.route("/empleadores/<int:eid>")
def empleador(eid):
    e = empleador_o_404(eid)
    buscar = (request.args.get("q") or "").strip()[:100] or None
    return render_template("nomina/empleador.html", e=e, buscar=buscar,
                           empleados=N.listar_empleados(eid, buscar), periodos=N.listar_periodos(eid))


# ----------------------------------------------------------------- empleados
def leer_empleado(empleador_id, mid=None, persona=None):
    f = request.form
    if persona is None:
        persona = P.obtener(P.resolver(f.get("persona")) or 0)
    d = {"empleador_id": empleador_id, "usuario_id": persona["id"] if persona else None,
         "fecha_ingreso": fecha(f.get("fecha_ingreso")), "fecha_retiro": fecha(f.get("fecha_retiro")),
         "salario": entero(f.get("salario")), "nivel_riesgo": entero(f.get("nivel_riesgo")) or 1,
         "banco": f.get("banco", "").strip()[:100] or None, "cuenta": f.get("cuenta", "").strip()[:40] or None,
         "eps": f.get("eps", "").strip()[:100] or None, "afp": f.get("afp", "").strip()[:100] or None,
         "caja": f.get("caja", "").strip()[:100] or None, "activo": f.get("activo", "1") == "1"}
    e = []
    if not persona:
        e.append("Elige una persona de la lista (si no existe, créala primero en Usuarios).")
    else:
        if not persona["num_id"]:
            e.append("La persona no tiene número de documento; complétalo en Usuarios (es la clave del PDF).")
        if N.existe_vinculo(empleador_id, persona["id"], mid):
            e.append("Esa persona ya está vinculada a este empleador.")
    if not d["fecha_ingreso"]:
        e.append("Escribe una fecha de ingreso válida.")
    if d["fecha_retiro"] and d["fecha_ingreso"] and d["fecha_retiro"] < d["fecha_ingreso"]:
        e.append("La fecha de retiro no puede ser anterior al ingreso.")
    if not d["salario"] or d["salario"] <= 0:
        e.append("Escribe un salario mensual mayor que cero.")
    if d["nivel_riesgo"] not in (1, 2, 3, 4, 5):
        e.append("El nivel de riesgo ARL debe ser de I a V.")
    return d, e


@bp.route("/empleados/nuevo", methods=["GET", "POST"])
@bp.route("/empleados/<int:mid>/editar", methods=["GET", "POST"])
def empleado_form(mid=None):
    if mid:
        actual = N.obtener_empleado(mid) or abort(404)
        eid = actual["empleador_id"]
    else:
        eid = entero(request.values.get("empleador"))
        actual = {"activo": 1, "nivel_riesgo": 1}
    e = empleador_o_404(eid)
    errores = []
    if request.method == "POST":
        persona = P.obtener(actual["usuario_id"]) if mid else None
        d, errores = leer_empleado(eid, mid, persona)
        if not errores:
            N.guardar_empleado(mid, d)
            flash("Empleado guardado.")
            return redirect(url_for("nomina.empleador", eid=eid))
        actual = {**actual, **d, "persona": request.form.get("persona", "")}
    return render_template("nomina/empleado_form.html", v=actual, errores=errores, e=e, mid=mid,
                           personas=P.opciones())


# ----------------------------------------------------------------- parámetros
CAMPOS_PARAM = [("smmlv", "Salario mínimo (SMMLV)", "$"), ("aux_transporte", "Auxilio de transporte", "$"),
                ("uvt", "UVT", "$"), ("horas_semana", "Horas semanales", "h"),
                ("rec_nocturno", "Recargo nocturno", "%"), ("rec_extra_diurna", "Extra diurna", "%"),
                ("rec_extra_nocturna", "Extra nocturna", "%"), ("rec_dominical", "Recargo dominical/festivo", "%"),
                ("salud_empleado", "Salud empleado", "%"), ("pension_empleado", "Pensión empleado", "%"),
                ("salud_empleador", "Salud empleador", "%"), ("pension_empleador", "Pensión empleador", "%"),
                ("caja", "Caja de compensación", "%"), ("sena", "SENA", "%"), ("icbf", "ICBF", "%"),
                ("prima", "Prima", "%"), ("cesantias", "Cesantías", "%"), ("intereses", "Intereses cesantías", "%"),
                ("vacaciones", "Vacaciones", "%")]


@bp.route("/parametros")
def parametros():
    return render_template("nomina/parametros.html", lista=N.listar_parametros(), campos=CAMPOS_PARAM)


@bp.route("/parametros/nuevo", methods=["GET", "POST"])
@bp.route("/parametros/<int:pid>/editar", methods=["GET", "POST"])
def parametro_form(pid=None):
    if pid:
        actual = N.obtener_parametro(pid) or abort(404)
    else:
        vig = N.listar_parametros()
        actual = dict(vig[0]) if vig else {}
        actual.pop("id", None)
        actual["vigente_desde"] = ""
        actual["nota"] = ""
    errores = []
    if request.method == "POST":
        actual = {"vigente_desde": request.form.get("vigente_desde", ""), "nota": request.form.get("nota", "")[:200]}
        vals = {}
        for c, nombre, _ in CAMPOS_PARAM:
            actual[c] = request.form.get(c, "")
            v = decimal(actual[c])
            if v is None and c == "uvt":
                vals[c] = None
            elif v is None or v < 0:
                errores.append("Revisa el valor de: %s." % nombre)
            else:
                vals[c] = v
        vd = fecha(actual["vigente_desde"])
        if not vd:
            errores.append("Escribe la fecha desde la cual aplica.")
        if not errores:
            try:
                N.guardar_parametro(pid, vd.isoformat(), vals, actual["nota"] or None)
            except Exception:
                errores.append("Ya existe un conjunto de parámetros con esa fecha de vigencia.")
            else:
                flash("Parámetros guardados.")
                return redirect(url_for("nomina.parametros"))
    return render_template("nomina/parametro_form.html", v=actual, errores=errores, campos=CAMPOS_PARAM, pid=pid)


# ----------------------------------------------------------------- periodos
@bp.route("/periodos", methods=["GET", "POST"])
def periodos():
    if request.method == "POST":
        eid, anio = entero(request.form.get("empleador_id")), entero(request.form.get("anio"))
        mes, q = entero(request.form.get("mes")), entero(request.form.get("quincena"))
        if not (eid and N.obtener_empleador(eid) and anio and 2020 <= anio <= 2100 and mes and 1 <= mes <= 12
                and q in (1, 2)):
            flash("Revisa el empleador, el año, el mes y la quincena.")
        else:
            pid, nuevo = N.crear_periodo(eid, anio, mes, q, g.usuario["id"])
            if not nuevo:
                flash("Ese periodo ya existía; se abrió el existente.")
            return redirect(url_for("nomina.periodo", pid=pid))
    eid = entero(request.args.get("empleador"))
    return render_template("nomina/periodos.html", lista=N.listar_periodos(eid), empleadores=N.listar_empleadores(True),
                           eid=eid, hoy=date.today())


@bp.route("/periodos/<int:pid>")
def periodo(pid):
    p = periodo_o_404(pid)
    return render_template("nomina/periodo.html", p=p, novedades=N.listar_novedades(pid),
                           liqs=N.liquidaciones_periodo(pid), empleados=N.listar_empleados(p["empleador_id"], solo_activos=True),
                           smtp=correo.configurado())


def periodo_abierto_o_flash(p):
    if p["estado"] != "abierto":
        flash("El periodo está cerrado. Pide a un administrador que lo reabra para modificarlo.")
        return False
    return True


@bp.route("/periodos/<int:pid>/novedad", methods=["POST"])
def novedad_agregar(pid):
    p = periodo_o_404(pid)
    if not periodo_abierto_o_flash(p):
        return redirect(url_for("nomina.periodo", pid=pid))
    f = request.form
    tipo, emp = f.get("tipo"), N.obtener_empleado(entero(f.get("empleado_id")) or 0)
    if tipo not in TIPOS or not emp or emp["empleador_id"] != p["empleador_id"]:
        flash("Elige un empleado y un tipo de novedad válidos.")
        return redirect(url_for("nomina.periodo", pid=pid))
    unidad = TIPOS[tipo][2]
    cantidad, valor = decimal(f.get("cantidad")), entero(f.get("valor"))
    previos = entero(f.get("previos")) or 0
    if unidad == "valor":
        if not valor:
            flash("Escribe el valor de la novedad.")
            return redirect(url_for("nomina.periodo", pid=pid))
        cantidad = 0
    else:
        if not cantidad or cantidad <= 0 or cantidad > 400:
            flash("Escribe una cantidad válida (%s)." % TIPOS[tipo][1])
            return redirect(url_for("nomina.periodo", pid=pid))
        valor = 0
    N.agregar_novedad(pid, emp["id"], tipo, cantidad, valor, previos if tipo.startswith("incap") else 0,
                      f.get("nota", "").strip()[:200] or None)
    flash("Novedad agregada. Vuelve a liquidar para recalcular.")
    return redirect(url_for("nomina.periodo", pid=pid))


@bp.route("/periodos/<int:pid>/novedad/<int:nid>/eliminar", methods=["POST"])
def novedad_eliminar(pid, nid):
    if periodo_abierto_o_flash(periodo_o_404(pid)):
        N.eliminar_novedad(pid, nid)
        flash("Novedad eliminada. Vuelve a liquidar para recalcular.")
    return redirect(url_for("nomina.periodo", pid=pid))


@bp.route("/periodos/<int:pid>/liquidar", methods=["POST"])
def liquidar(pid):
    p = periodo_o_404(pid)
    if not periodo_abierto_o_flash(p):
        return redirect(url_for("nomina.periodo", pid=pid))
    par = N.parametros_vigentes(p["fecha_fin"])
    if not par:
        flash("No hay parámetros legales vigentes para esta fecha. Créalos en «Parámetros».")
        return redirect(url_for("nomina.periodo", pid=pid))
    novedades = N.novedades_por_empleado(pid)
    resultados, omitidos = {}, 0
    for emp in N.listar_empleados(p["empleador_id"]):
        if not emp["activo"] and not emp["fecha_retiro"]:
            continue
        c = calcular(emp, novedades.get(emp["id"], []), p["anio"], p["mes"], p["quincena"], par, bool(p["exonerado"]))
        if c["vinculado"]:
            resultados[emp["id"]] = c
        else:
            omitidos += 1
    N.guardar_liquidaciones(pid, resultados)
    flash("Liquidación calculada para %d empleado(s)%s." % (
        len(resultados), "; %d no estaban vinculados en el periodo" % omitidos if omitidos else ""))
    return redirect(url_for("nomina.periodo", pid=pid))


@bp.route("/periodos/<int:pid>/cerrar", methods=["POST"])
def cerrar(pid):
    p = periodo_o_404(pid)
    if not N.liquidaciones_periodo(pid):
        flash("Liquida el periodo antes de cerrarlo.")
    else:
        N.cambiar_estado_periodo(pid, "cerrado")
        flash("Periodo cerrado.")
    return redirect(url_for("nomina.periodo", pid=pid))


@bp.route("/periodos/<int:pid>/reabrir", methods=["POST"])
@requiere_permiso("nomina.reabrir")
def reabrir(pid):
    periodo_o_404(pid)
    N.cambiar_estado_periodo(pid, "abierto")
    flash("Periodo reabierto.")
    return redirect(url_for("nomina.periodo", pid=pid))


# ----------------------------------------------------------------- liquidaciones, PDF y correo
def _pdf(liq):
    p = N.obtener_periodo(liq["periodo_id"])
    e = N.obtener_empleador(p["empleador_id"])
    emp = {"nombre": liq["nombre"], "num_id": liq["num_id"], "tipo_id": liq["tipo_id"], "cargo": liq["cargo"],
           "salario": liq["salario"], "banco": liq["banco"], "cuenta": liq["cuenta"]}
    return p, e, emp


@bp.route("/liquidaciones/<int:lid>")
def liquidacion(lid):
    liq = N.obtener_liquidacion(lid) or abort(404)
    p = periodo_o_404(liq["periodo_id"])
    return render_template("nomina/liquidacion.html", l=liq, c=liq["calculo"], p=p, smtp=correo.configurado())


@bp.route("/liquidaciones/<int:lid>/pdf")
def liquidacion_pdf(lid):
    liq = N.obtener_liquidacion(lid) or abort(404)
    p, e, emp = _pdf(liq)
    pdf = generar_desprendible(e, emp, p, liq["calculo"])
    nombre = "desprendible_%s_%s%02d_Q%d.pdf" % (re.sub(r"\W", "", liq["num_id"]), p["anio"], p["mes"], p["quincena"])
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": 'inline; filename="%s"' % nombre})


def enviar_uno(liq, p, e):
    """Devuelve (ok, mensaje)."""
    if not liq["email"]:
        N.marcar_envio(liq["id"], "El empleado no tiene correo registrado.")
        return False, "sin correo"
    _, _, emp = _pdf(liq)
    pdf = generar_desprendible(e, emp, p, liq["calculo"], clave=liq["num_id"])
    texto = ("Hola %s,\n\nAdjuntamos tu desprendible de pago de nómina de %s correspondiente a la %s.\n\n"
             "Para abrir el archivo PDF usa como contraseña tu número de documento (sin puntos ni espacios).\n\n"
             "Este mensaje es confidencial. Si encuentras diferencias, comunícate con el área de nómina.\n\n%s"
             % (liq["nombre"].split(" ")[0].title(), e["nombre"], nombre_periodo(p), e["nombre"]))
    nombre = "desprendible_%s%02d_Q%d.pdf" % (p["anio"], p["mes"], p["quincena"])
    try:
        correo.enviar(liq["email"], "Desprendible de pago - %s" % nombre_periodo(p), texto, pdf, nombre)
    except Exception as ex:
        N.marcar_envio(liq["id"], str(ex))
        return False, str(ex)
    N.marcar_envio(liq["id"])
    return True, ""


@bp.route("/liquidaciones/<int:lid>/enviar", methods=["POST"])
def liquidacion_enviar(lid):
    liq = N.obtener_liquidacion(lid) or abort(404)
    p = periodo_o_404(liq["periodo_id"])
    ok, msg = enviar_uno(liq, p, N.obtener_empleador(p["empleador_id"]))
    flash("Desprendible enviado a %s." % liq["email"] if ok else "No se pudo enviar: %s" % msg)
    return redirect(request.form.get("volver") if (request.form.get("volver") or "").startswith("/nomina/")
                    else url_for("nomina.liquidacion", lid=lid))


@bp.route("/periodos/<int:pid>/enviar", methods=["POST"])
def enviar_pendientes(pid):
    p = periodo_o_404(pid)
    e = N.obtener_empleador(p["empleador_id"])
    if not correo.configurado():
        flash("El correo no está configurado. Completa los datos SMTP en config.py.")
        return redirect(url_for("nomina.periodo", pid=pid))
    pendientes = [l for l in N.liquidaciones_periodo(pid) if not l["correo_enviado"]]
    enviados, fallos = 0, 0
    for liq in pendientes[:LOTE_CORREOS]:
        ok, msg = enviar_uno(liq, p, e)
        enviados += ok
        fallos += (not ok)
        if not ok and ("conectar" in msg.lower() or "autentic" in msg.lower()):
            break  # error de conexión/credenciales: no tiene sentido seguir
    restantes = len(pendientes) - enviados - fallos
    flash("Enviados: %d. Con error: %d. %s" % (enviados, fallos, (
        "Quedan %d pendientes; vuelve a pulsar el botón." % restantes) if restantes > 0 else ""))
    return redirect(url_for("nomina.periodo", pid=pid))


@bp.route("/correo/prueba", methods=["POST"])
def correo_prueba():
    destino = g.usuario["correo"]
    try:
        correo.enviar(destino, "Prueba de correo - C&C Gestión", "Si lees esto, el envío de correos funciona.")
        flash("Correo de prueba enviado a %s." % destino)
    except Exception as ex:
        flash("No se pudo enviar: %s" % ex)
    return redirect(url_for("nomina.panel"))


# ----------------------------------------------------------------- consultas y Excel
def filtros():
    return {"empleador_id": entero(request.args.get("empleador")), "anio": entero(request.args.get("anio")),
            "mes": entero(request.args.get("mes")), "quincena": entero(request.args.get("quincena")),
            "buscar": (request.args.get("q") or "").strip()[:100] or None}


@bp.route("/consultas")
def consultas():
    f = filtros()
    filas = N.consultar(**f)
    tot = {k: sum(x[k] or 0 for x in filas) for k in ("total_devengado", "total_deducciones", "neto",
                                                       "aportes_empleador", "provisiones")}
    return render_template("nomina/consultas.html", filas=filas[:500], total=len(filas), tot=tot, f=f,
                           empleadores=N.listar_empleadores(), hoy=date.today())


@bp.route("/exportar")
def exportar():
    filas = N.consultar(**filtros())
    if not filas:
        flash("No hay liquidaciones con esos filtros para exportar.")
        return redirect(url_for("nomina.consultas"))
    return Response(generar_excel_nomina(filas), mimetype=EXCEL_MIME, headers={
        "Content-Disposition": 'attachment; filename="CC_Gestion_nomina_%s.xlsx"' % date.today().strftime("%Y%m%d")})
