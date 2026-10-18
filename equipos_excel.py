"""Excel del inventario de equipos de cómputo."""
from io import BytesIO

from openpyxl import Workbook

from equipos_db import ESTADOS, LICENCIAS, SW_ESTADOS, TIPOS
from nomina_excel import _hoja


def generar_excel_equipos(equipos, software):
    wb = Workbook()
    wb.remove(wb.active)
    _hoja(wb, "Equipos", ["ID inventario", "Tipo", "Marca", "Modelo", "Serial", "Procesador", "RAM (GB)", "SSD (GB)",
                          "Usuario asignado", "Documento", "Ciudad", "Sistema operativo", "Microsoft Office",
                          "Antivirus", "Estado", "N.º programas", "Observaciones"],
          [[e["codigo"], TIPOS.get(e["tipo"], e["tipo"]), e["marca"] or "", e["modelo"] or "", e["serie"] or "",
            e["procesador"] or "", e["ram_gb"] if e["ram_gb"] is not None else "",
            e["ssd_gb"] if e["ssd_gb"] is not None else "", e["usuario"] or "", e["usuario_doc"] or "",
            e["ciudad"] or "", e["sistema_operativo"] or "", e["office"] or "", e["antivirus"] or "",
            ESTADOS.get(e["estado"], e["estado"]), e["n_software"], e["observaciones"] or ""] for e in equipos])
    ids = {e["id"] for e in equipos}
    _hoja(wb, "Software instalado", ["ID inventario", "Tipo de equipo", "Usuario asignado", "Programa", "Versión",
                                     "Tipo de licencia", "Estado", "Vence", "Notas"],
          [[s["codigo"], TIPOS.get(s["tipo"], s["tipo"]), s["usuario"] or "", s["nombre"], s["version"] or "",
            LICENCIAS.get(s["tipo_licencia"], s["tipo_licencia"] or ""), SW_ESTADOS.get(s["estado"], s["estado"]),
            s["vencimiento"].isoformat() if s["vencimiento"] else "", s["notas"] or ""]
           for s in software if s["equipo_id"] in ids])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
