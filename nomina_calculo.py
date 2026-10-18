"""Motor de cálculo de nómina quincenal (Colombia). Sin dependencias de web ni base de datos.

Los porcentajes y valores legales NO están fijos aquí: se leen de la tabla de parámetros
(vigentes por fecha). Aquí solo está la mecánica de cálculo.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

D = Decimal

# Tarifa ARL por nivel de riesgo (% sobre el IBC)
ARL = {1: D("0.522"), 2: D("1.044"), 3: D("2.436"), 4: D("4.350"), 5: D("6.960")}

# Tipos de novedad: código -> (nombre, unidad, grupo)
TIPOS = {
    "hed":  ("Hora extra diurna", "horas", "horas"),
    "hen":  ("Hora extra nocturna", "horas", "horas"),
    "rn":   ("Recargo nocturno", "horas", "horas"),
    "rdo":  ("Recargo dominical/festivo (ordinaria)", "horas", "horas"),
    "hedd": ("Hora extra diurna dominical/festiva", "horas", "horas"),
    "hend": ("Hora extra nocturna dominical/festiva", "horas", "horas"),
    "rndo": ("Recargo nocturno dominical/festivo", "horas", "horas"),
    "comision":         ("Comisión (salarial)", "valor", "valor"),
    "bono_salarial":    ("Bono salarial", "valor", "valor"),
    "bono_no_salarial": ("Bono no salarial", "valor", "valor"),
    "descuento":        ("Descuento (libranza, préstamo, otro)", "valor", "valor"),
    "vacaciones":       ("Vacaciones disfrutadas", "días", "dias"),
    "incap_general":    ("Incapacidad enfermedad general", "días", "dias"),
    "incap_laboral":    ("Incapacidad accidente de trabajo", "días", "dias"),
    "lic_maternidad":   ("Licencia de maternidad", "días", "dias"),
    "lic_paternidad":   ("Licencia de paternidad", "días", "dias"),
    "lic_no_remunerada": ("Licencia no remunerada", "días", "dias"),
    "ausencia":         ("Ausencia / día no trabajado", "días", "dias"),
}
HORAS = ("hed", "hen", "rn", "rdo", "hedd", "hend", "rndo")
DIAS_AUSENTE = ("vacaciones", "incap_general", "incap_laboral", "lic_maternidad",
                "lic_paternidad", "lic_no_remunerada", "ausencia")
SIN_COTIZAR = ("lic_no_remunerada", "ausencia")


def r0(x):
    """Redondea al peso (mitad hacia arriba)."""
    return int(D(x).quantize(D("1"), rounding=ROUND_HALF_UP))


def _p(par, clave):
    return D(str(par[clave]))


def _pc(par, clave):
    return _p(par, clave) / D(100)


def a_fecha(v):
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def rango_periodo(anio, mes, quincena):
    ultimo = monthrange(anio, mes)[1]
    if quincena == 1:
        return date(anio, mes, 1), date(anio, mes, 15)
    return date(anio, mes, 16), date(anio, mes, ultimo)


def _dia_comercial(f):
    """Día del mes en base comercial de 30 días (el último día del mes cuenta como 30)."""
    if f.day == monthrange(f.year, f.month)[1]:
        return 30
    return min(f.day, 30)


def dias_base(ingreso, retiro, anio, mes, quincena):
    """Días comerciales (máx. 15) en que el empleado estuvo vinculado dentro de la quincena."""
    ini_f, fin_f = rango_periodo(anio, mes, quincena)
    ingreso, retiro = a_fecha(ingreso), a_fecha(retiro)
    if ingreso > fin_f or (retiro and retiro < ini_f):
        return 0
    d_ini = 1 if quincena == 1 else 16
    d_fin = 15 if quincena == 1 else 30
    if ingreso > ini_f:
        d_ini = _dia_comercial(ingreso)
    if retiro and retiro < fin_f:
        d_fin = _dia_comercial(retiro)
    return max(0, d_fin - d_ini + 1)


def tarifa_fsp(ibc_mensual, smmlv):
    """Fondo de Solidaridad Pensional: % según el IBC mensual expresado en SMMLV."""
    n = ibc_mensual / smmlv
    if n < 4:
        return D(0)
    if n < 16:
        return D("1.0")
    if n < 17:
        return D("1.2")
    if n < 18:
        return D("1.4")
    if n < 19:
        return D("1.6")
    if n < 20:
        return D("1.8")
    return D("2.0")


def calcular(emp, novedades, anio, mes, quincena, par, exonerado):
    """Liquida una quincena para un empleado.

    emp: dict con salario, nivel_riesgo, fecha_ingreso, fecha_retiro
    novedades: lista de dicts {tipo, cantidad, valor, previos, nota}
    par: dict de parámetros vigentes (ver tabla nomina_parametros)
    """
    smmlv = _p(par, "smmlv")
    aux_mes = _p(par, "aux_transporte")
    salario = D(str(emp["salario"]))
    salario_dia = salario / 30
    valor_hora = salario / (D(str(par["horas_semana"])) * 5)

    db_ = dias_base(emp["fecha_ingreso"], emp.get("fecha_retiro"), anio, mes, quincena)
    res = {"dias_base": db_, "conceptos": [], "advertencias": []}
    if db_ == 0:
        res["vinculado"] = False
        return res
    res["vinculado"] = True

    dias = {k: D(0) for k in DIAS_AUSENTE}
    previos = {k: 0 for k in DIAS_AUSENTE}
    horas = {k: D(0) for k in HORAS}
    comisiones, bonos_sal, bonos_nosal = [], [], []
    descuentos = []
    for n in novedades:
        t = n["tipo"]
        cant = D(str(n.get("cantidad") or 0))
        val = D(str(n.get("valor") or 0))
        if t in HORAS:
            horas[t] += cant
        elif t in DIAS_AUSENTE:
            dias[t] += cant
            previos[t] = max(previos[t], int(n.get("previos") or 0))
        elif t == "comision":
            comisiones.append((n.get("nota"), val))
        elif t == "bono_salarial":
            bonos_sal.append((n.get("nota"), val))
        elif t == "bono_no_salarial":
            bonos_nosal.append((n.get("nota"), val))
        elif t == "descuento":
            descuentos.append((n.get("nota"), val))

    total_ausente = sum(dias.values())
    dias_trab = D(db_) - total_ausente
    if dias_trab < 0:
        res["advertencias"].append("Las novedades de días (%s) superan los días de la quincena (%d). "
                                   "Se liquidan 0 días trabajados." % (total_ausente, db_))
        dias_trab = D(0)
    dias_cot = D(db_) - sum(dias[k] for k in SIN_COTIZAR)
    if dias_cot < 0:
        dias_cot = D(0)

    lineas = res["conceptos"]

    def add(codigo, nombre, valor, tipo="devengo", cantidad=None, salarial=True, recobrable=False):
        v = r0(valor)
        if v == 0:
            return 0
        lineas.append({"codigo": codigo, "nombre": nombre, "valor": v, "tipo": tipo,
                       "cantidad": float(cantidad) if cantidad is not None else None,
                       "salarial": salarial, "recobrable": recobrable})
        return v

    salarial_sin_incap = 0   # salario, vacaciones, extras, comisiones, bonos salariales
    incap_total = 0
    recobrable = 0

    # --- salario del periodo
    pay = add("salario", "Salario básico", salario_dia * dias_trab, cantidad=dias_trab)
    salarial_sin_incap += pay
    salario_pagado = pay
    v = add("vacaciones", "Vacaciones disfrutadas", salario_dia * dias["vacaciones"],
            cantidad=dias["vacaciones"])
    salarial_sin_incap += v
    salario_pagado += v

    # --- horas extras y recargos
    f_ext_d, f_ext_n = _pc(par, "rec_extra_diurna"), _pc(par, "rec_extra_nocturna")
    f_noc, f_dom = _pc(par, "rec_nocturno"), _pc(par, "rec_dominical")
    factores = {
        "hed": 1 + f_ext_d, "hen": 1 + f_ext_n, "rn": f_noc, "rdo": f_dom,
        "hedd": 1 + f_ext_d + f_dom, "hend": 1 + f_ext_n + f_dom, "rndo": f_noc + f_dom,
    }
    for t in HORAS:
        if horas[t]:
            salarial_sin_incap += add(t, TIPOS[t][0], valor_hora * factores[t] * horas[t],
                                      cantidad=horas[t])

    # --- comisiones y bonos
    for nota, val in comisiones:
        salarial_sin_incap += add("comision", "Comisión" + (" - " + nota if nota else ""), val)
    for nota, val in bonos_sal:
        salarial_sin_incap += add("bono_salarial", "Bono salarial" + (" - " + nota if nota else ""), val)
    no_salarial = 0
    for nota, val in bonos_nosal:
        no_salarial += add("bono_no_salarial", "Bono no salarial" + (" - " + nota if nota else ""),
                           val, salarial=False)

    # --- incapacidades y licencias (la empresa las paga y recobra a EPS/ARL)
    min_dia = smmlv / 30

    def dia_incap(t, k):  # k = número de día consecutivo de la incapacidad (1, 2, 3...)
        if t == "incap_general":
            pct = D("0.6667") if k <= 90 else D("0.5")
            return max(salario_dia * pct, min_dia), k <= 2
        if t == "incap_laboral":
            return max(salario_dia, min_dia), k <= 1
        return max(salario_dia, min_dia), False       # licencias maternidad / paternidad

    for t in ("incap_general", "incap_laboral", "lic_maternidad", "lic_paternidad"):
        n_dias = int(dias[t])
        if n_dias <= 0:
            continue
        emp_total = rec_total = D(0)
        emp_dias = rec_dias = 0
        for i in range(1, n_dias + 1):
            valor_dia, a_cargo_empleador = dia_incap(t, previos[t] + i)
            if a_cargo_empleador:
                emp_total += valor_dia
                emp_dias += 1
            else:
                rec_total += valor_dia
                rec_dias += 1
        if emp_dias:
            incap_total += add(t, TIPOS[t][0] + " (a cargo del empleador)", emp_total, cantidad=emp_dias)
        if rec_dias:
            val = add(t + "_rec", TIPOS[t][0] + " (recobrable a EPS/ARL)", rec_total,
                      cantidad=rec_dias, recobrable=True)
            incap_total += val
            recobrable += val
        if int(dias[t]) != dias[t]:
            res["advertencias"].append("%s: los días deben ser enteros." % TIPOS[t][0])

    salarial_total = salarial_sin_incap + incap_total

    # --- auxilio de transporte (solo salario básico hasta 2 SMMLV, por días trabajados)
    aux = 0
    if salario <= 2 * smmlv:
        aux = add("aux_transporte", "Auxilio de transporte", aux_mes / 30 * dias_trab,
                  cantidad=dias_trab, salarial=False)

    total_devengado = salarial_total + aux + no_salarial

    # --- IBC (base de seguridad social)
    remuneracion = salarial_total + no_salarial
    exceso_40 = max(D(0), D(no_salarial) - D("0.4") * D(remuneracion))   # Ley 1393 art. 30
    ibc = D(salarial_total) + exceso_40
    if exceso_40 > 0:
        res["advertencias"].append("Los pagos no salariales superan el 40%% de la remuneración: el exceso "
                                   "($%s) se incluyó en el IBC." % "{:,}".format(r0(exceso_40)).replace(",", "."))
    ibc_min = smmlv * dias_cot / 30
    ibc_max = 25 * smmlv * D(db_) / 30
    if dias_cot > 0 and ibc < ibc_min:
        ibc = ibc_min
    ibc = min(ibc, ibc_max)
    ibc = D(r0(ibc))
    ibc_mensual = ibc * 30 / dias_cot if dias_cot > 0 else D(0)

    # --- deducciones del empleado
    ded = []
    salud = r0(ibc * _pc(par, "salud_empleado"))
    pension = r0(ibc * _pc(par, "pension_empleado"))
    fsp_pct = tarifa_fsp(ibc_mensual, smmlv) if ibc_mensual > 0 else D(0)
    fsp = r0(ibc * fsp_pct / 100)
    for cod, nom, val in (("salud", "Aporte salud empleado", salud),
                          ("pension", "Aporte pensión empleado", pension),
                          ("fsp", "Fondo de solidaridad pensional", fsp)):
        if val:
            lineas.append({"codigo": cod, "nombre": nom, "valor": val, "tipo": "deduccion",
                           "cantidad": None, "salarial": False, "recobrable": False})
    otras = 0
    for nota, val in descuentos:
        otras += add("descuento", "Descuento" + (" - " + nota if nota else ""), val, tipo="deduccion")
    total_ded = salud + pension + fsp + otras
    neto = total_devengado - total_ded
    if neto < 0:
        res["advertencias"].append("El neto a pagar es negativo: revisa los descuentos.")

    # --- aportes del empleador
    exo = bool(exonerado) and ibc_mensual < 10 * smmlv
    base_para = max(0, salarial_total - incap_total)
    aportes = {
        "pension": r0(ibc * _pc(par, "pension_empleador")),
        "salud": 0 if exo else r0(ibc * _pc(par, "salud_empleador")),
        "arl": r0(ibc * ARL.get(int(emp.get("nivel_riesgo") or 1), ARL[1]) / 100),
        "caja": r0(D(base_para) * _pc(par, "caja")),
        "sena": 0 if exo else r0(D(base_para) * _pc(par, "sena")),
        "icbf": 0 if exo else r0(D(base_para) * _pc(par, "icbf")),
    }
    aportes["total"] = sum(aportes.values())

    # --- provisiones de prestaciones sociales
    base_prest = D(salarial_total + aux)
    cesantias = r0(base_prest * _pc(par, "cesantias"))
    prov = {
        "prima": r0(base_prest * _pc(par, "prima")),
        "cesantias": cesantias,
        "intereses": r0(D(cesantias) * _pc(par, "intereses")),
        "vacaciones": r0(D(salario_pagado) * _pc(par, "vacaciones")),
    }
    prov["total"] = sum(prov.values())

    res.update({
        "dias_trabajados": float(dias_trab), "salario_devengado": salario_pagado,
        "total_devengado": total_devengado, "ibc": int(ibc),
        "total_deducciones": total_ded, "neto": neto,
        "salud_empleado": salud, "pension_empleado": pension, "fsp": fsp,
        "aportes": aportes, "provisiones": prov, "recobrable": recobrable,
    })
    return res
