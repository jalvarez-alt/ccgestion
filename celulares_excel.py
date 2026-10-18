"""Excel del inventario de celulares."""
from io import BytesIO

from openpyxl import Workbook

from celulares_db import ACTAS, MOTIVOS_BAJA, TIPOS_MOV
from nomina_excel import _hoja

CAB = ["Fecha compra", "Marca", "Modelo", "IMEI 1", "IMEI 2", "SN", "Firma/Acta", "Observaciones", "Antigüedad",
       "Años", "Línea asignada", "Usuario actual", "Operador", "Usuario anterior", "Valor plan"]


def _fila(c):
    return [c["fecha_compra"].isoformat() if c["fecha_compra"] else "", c["marca"], c["modelo"], c["imei1"] or "",
            c["imei2"] or "", c["sn"] or "", ACTAS.get(c["acta"], c["acta"]), c["observaciones"] or "",
            c["antiguedad"], c["anios"] if c["anios"] is not None else "", c["linea"] or "",
            c["usuario_actual"] or "", c["operador"] or "", c["usuario_anterior"] or "", c["valor_plan"]]


def generar_excel_celulares(celulares, movimientos):
    wb = Workbook()
    wb.remove(wb.active)
    activos = [c for c in celulares if c["estado"] == "activo"]
    bajas = [c for c in celulares if c["estado"] == "baja"]
    _hoja(wb, "Inventario", CAB + ["Situación"], [_fila(c) + [c["situacion"]] for c in activos], dinero=(14,))
    _hoja(wb, "Dados de baja", CAB + ["Fecha de baja", "Motivo", "Detalle"],
          [_fila(c) + [c["baja_fecha"].isoformat() if c["baja_fecha"] else "",
                       MOTIVOS_BAJA.get(c["baja_motivo"], c["baja_motivo"] or ""), c["baja_nota"] or ""]
           for c in bajas], dinero=(14,))
    ids = {c["id"] for c in celulares}
    _hoja(wb, "Movimientos", ["Fecha", "Marca", "Modelo", "IMEI 1", "Movimiento", "De (usuario anterior)",
                              "A (usuario nuevo)", "Nota", "Registrado por"],
          [[m["fecha"].isoformat(), m["marca"], m["modelo"], m["imei1"] or "", TIPOS_MOV.get(m["tipo"], m["tipo"]),
            m["usuario_anterior"] or "", m["usuario_nuevo"] or "", m["nota"] or "", m["registrado_por"] or ""]
           for m in movimientos if m["celular_id"] in ids])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
