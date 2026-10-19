"""WhatsApp: campañas de mensajes masivos, historial de envíos y respuestas."""
import re
from datetime import datetime

from consultas import _ejecutar
from db import get_db

ESTADOS = {"pendiente": "Pendiente", "en_cola": "En cola", "enviado": "Enviado", "entregado": "Entregado",
           "leido": "Leído", "error": "Error"}
# Orden para que un estado "menor" nunca pise a uno "mayor" (p. ej. leído no vuelve a entregado).
RANGO = {"pendiente": 0, "en_cola": 1, "error": 1, "enviado": 2, "entregado": 3, "leido": 4}
# ack de whatsapp-web.js: 1 enviado, 2 entregado, 3 leído, 4 reproducido
ACK = {1: "enviado", 2: "entregado", 3: "leido", 4: "leido"}

# Las líneas que llevan {fecha}, {num} o {placa} se repiten una vez por cada manifiesto del contacto.
PLANTILLA_DEFECTO = (
    "Hola {nombre_conductor} 👋, te saluda Transportes Camiones y Camiones Ltda.\n\n"
    "Tienes {x} manifiesto(s) pendiente(s) por entregar documentación:\n"
    "- {fecha} - Manifiesto {num} - Placa {placa}\n\n"
    "Recuerda que al entregar estos documentos podemos:\n"
    "✅ Agilizar el pago de tu saldo pendiente\n"
    "✅ Resolver a tiempo cualquier novedad del viaje\n\n"
    "Puedes enviarlos por Correspondencia a la CL 15 # 23-10 Yumbo, Oficina en EDS Primax.\n\n"
    "Responde este mensaje con las fotos de los soportes e indícanos cuando se hara el envio.")

PLANTILLA_SEGUNDO = (
    "Hola {nombre_conductor}, seguimos pendientes de la documentación de:\n"
    "- {fecha} - Manifiesto {num} - Placa {placa}\n\n"
    "Mientras no recibamos estos documentos, no podemos avanzar con el pago de tu saldo ni gestionar novedades del viaje.\n\n"
    "Recuerda que puedes enviarlos por Correspondencia apenas termines tu ruta, sin necesidad de regresar a Yumbo.\n\n"
    "Quedamos atentos 🙏")

_CREADAS = False

_TABLAS = [
    """CREATE TABLE IF NOT EXISTS wa_campanas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(150) NOT NULL,
        plantilla TEXT NOT NULL,
        plantilla2 TEXT NULL,
        creada_por VARCHAR(150) NULL,
        creada_en DATETIME NOT NULL
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS wa_mensajes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        campana_id INT NOT NULL,
        aviso TINYINT NOT NULL DEFAULT 1,
        manifiesto VARCHAR(60) NULL,
        manifiestos TEXT NULL,
        cliente VARCHAR(200) NULL,
        orden_cargue VARCHAR(60) NULL,
        remesa VARCHAR(60) NULL,
        contacto VARCHAR(150) NULL,
        telefono VARCHAR(20) NOT NULL,
        texto TEXT NOT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        wa_id VARCHAR(120) NULL,
        error VARCHAR(255) NULL,
        creado_en DATETIME NOT NULL,
        enviado_en DATETIME NULL,
        entregado_en DATETIME NULL,
        leido_en DATETIME NULL,
        INDEX (campana_id), INDEX (telefono), INDEX (wa_id), INDEX (manifiesto)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS wa_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        campana_id INT NOT NULL,
        telefono VARCHAR(20) NOT NULL,
        contacto VARCHAR(150) NULL,
        fecha DATE NULL,
        manifiesto VARCHAR(60) NOT NULL,
        placa VARCHAR(30) NULL,
        INDEX (campana_id), INDEX (telefono)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS wa_respuestas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mensaje_id INT NULL,
        telefono VARCHAR(20) NOT NULL,
        texto TEXT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'chat',
        wa_id VARCHAR(120) NULL,
        recibida_en DATETIME NOT NULL,
        INDEX (mensaje_id), INDEX (telefono), UNIQUE KEY uq_wa_id (wa_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS wa_servicio (
        id TINYINT PRIMARY KEY,
        estado VARCHAR(20) NOT NULL,
        qr MEDIUMTEXT NULL,
        numero VARCHAR(30) NULL,
        en_cola INT NOT NULL DEFAULT 0,
        comando VARCHAR(20) NULL,
        actualizado DATETIME NOT NULL
    ) CHARACTER SET utf8mb4""",
]
VIGENCIA_LATIDO = 60     # segundos sin señal del servicio => se considera apagado


def asegurar_tablas():
    """Crea las tablas la primera vez (el resto de la app las tiene creadas a mano en cPanel)."""
    global _CREADAS
    if _CREADAS:
        return
    for sql in _TABLAS:
        _ejecutar(sql, commit=True)
    # Columnas agregadas después de la primera versión (instalaciones anteriores)
    for tabla, cols in (
            ("wa_respuestas", (("archivo_estado", "VARCHAR(12) NULL"), ("archivo_nombre", "VARCHAR(255) NULL"),
                               ("archivo_url", "VARCHAR(800) NULL"), ("archivo_error", "VARCHAR(255) NULL"))),
            ("wa_campanas", (("plantilla2", "TEXT NULL"),)),
            ("wa_mensajes", (("aviso", "TINYINT NOT NULL DEFAULT 1"), ("manifiestos", "TEXT NULL")))):
        existentes = {r["COLUMN_NAME"] for r in _ejecutar(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = %s", [tabla])}
        for col, tipo in cols:
            if col not in existentes:
                _ejecutar("ALTER TABLE %s ADD COLUMN %s %s" % (tabla, col, tipo), commit=True)
    _CREADAS = True


def ahora():
    return datetime.now().replace(microsecond=0)


# ---------------------------------------------------------------- servicio (latido)
def latido(estado, qr, numero, en_cola):
    """Guarda lo que informa el servicio y devuelve (comando, mensajes por enviar, ids vigentes en cola)."""
    asegurar_tablas()
    _ejecutar("INSERT INTO wa_servicio (id, estado, qr, numero, en_cola, actualizado) VALUES (1,%s,%s,%s,%s,%s) "
              "ON DUPLICATE KEY UPDATE estado=VALUES(estado), qr=VALUES(qr), numero=VALUES(numero), "
              "en_cola=VALUES(en_cola), actualizado=VALUES(actualizado)", [estado, qr, numero, en_cola, ahora()],
              commit=True)
    comando = _ejecutar("SELECT comando FROM wa_servicio WHERE id = 1", uno=True)["comando"]
    if comando:
        _ejecutar("UPDATE wa_servicio SET comando = NULL WHERE id = 1", commit=True)
    if estado != "listo":
        return comando, [], []
    filas = _ejecutar("SELECT id, telefono, texto FROM wa_mensajes WHERE estado = 'en_cola' ORDER BY id")
    return comando, filas[:50], [f["id"] for f in filas]


def estado_servicio():
    """(estado, error). 'estado' tiene estado/qr/numero/en_cola; error si no hay señal reciente."""
    asegurar_tablas()
    f = _ejecutar("SELECT * FROM wa_servicio WHERE id = 1", uno=True)
    if not f:
        return {"estado": "apagado"}, "El servicio de WhatsApp aún no se ha conectado a la aplicación."
    segundos = (ahora() - f["actualizado"]).total_seconds()
    if segundos > VIGENCIA_LATIDO:
        return {"estado": "apagado"}, ("El servicio de WhatsApp está apagado (última señal: %s). "
                                       "Enciéndelo con «npm start» en la carpeta whatsapp-service." %
                                       f["actualizado"].strftime("%d/%m/%Y %H:%M"))
    return {"estado": f["estado"], "qr": f["qr"], "numero": f["numero"], "en_cola": f["en_cola"]}, None


def pedir_cierre():
    asegurar_tablas()
    _ejecutar("UPDATE wa_servicio SET comando = 'cerrar' WHERE id = 1", commit=True)


# ---------------------------------------------------------------- teléfonos y texto
def normalizar_telefono(valor, pais="57"):
    """Deja solo dígitos con indicativo de país. Devuelve (telefono, error)."""
    d = re.sub(r"\D", "", valor or "")
    if d.startswith("00"):
        d = d[2:]
    if not d:
        return None, "Falta el teléfono"
    if len(d) == 10 and d.startswith("3"):          # celular colombiano sin indicativo
        d = pais + d
    if not 11 <= len(d) <= 15:
        return None, "Teléfono no válido «%s» (usa 10 dígitos o con indicativo)" % valor
    return d, None


_RE_ITEM = re.compile(r"\{(fecha|num|manifiesto|placa)\}")
VACIO = "—"


def armar_texto(plantilla, contacto, items):
    """Arma el mensaje de un contacto. items: [{fecha (date|None), manifiesto, placa}].
    Las líneas con {fecha}/{num}/{placa} se repiten por cada manifiesto; {nombre_conductor} y {x} (cantidad)
    se reemplazan en el resto. Lo que no se reconoce se deja tal cual."""
    nombre = (contacto or "").strip()
    generales = {"nombre_conductor": nombre, "contacto": nombre, "nombre": nombre,
                 "x": str(len(items)), "cantidad": str(len(items))}

    def sustituir(linea, datos):
        return re.sub(r"\{(\w+)\}", lambda m: datos[m.group(1)] if m.group(1) in datos else m.group(0), linea)

    salida, bloque = [], []

    def volcar():
        for it in items:
            datos = {**generales, "fecha": it["fecha"].strftime("%d/%m/%Y") if it.get("fecha") else VACIO,
                     "num": it["manifiesto"], "manifiesto": it["manifiesto"], "placa": it.get("placa") or VACIO}
            salida.extend(sustituir(l, datos) for l in bloque)
        bloque.clear()

    for linea in plantilla.replace("\r\n", "\n").split("\n"):
        if _RE_ITEM.search(linea):
            bloque.append(linea.rstrip(" -"))        # quita el " - " sobrante al final de la línea de ejemplo
            continue
        if bloque:
            volcar()
        salida.append(sustituir(linea, generales))
    if bloque:
        volcar()
    texto = "\n".join(salida)
    texto = re.sub(r"[ \t]+([,.;:!?])", r"\1", texto)      # "Hola ," -> "Hola," cuando no hay nombre
    texto = re.sub(r"(?<=\S)[ \t]{2,}", " ", texto)
    return "\n".join(l.rstrip() for l in texto.split("\n")).strip()


# ---------------------------------------------------------------- campañas
def crear_campana(nombre, plantilla, plantilla2, usuario, contactos):
    """contactos: [{telefono, contacto, items: [{fecha, manifiesto, placa}]}]. Un mensaje por contacto. Devuelve el id."""
    asegurar_tablas()
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("INSERT INTO wa_campanas (nombre, plantilla, plantilla2, creada_por, creada_en) "
                        "VALUES (%s,%s,%s,%s,%s)", [nombre, plantilla, plantilla2, usuario, ahora()])
            cid = cur.lastrowid
            for c in contactos:
                cur.executemany(
                    "INSERT INTO wa_items (campana_id, telefono, contacto, fecha, manifiesto, placa) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    [[cid, c["telefono"], c["contacto"], i["fecha"], i["manifiesto"], i["placa"]] for i in c["items"]])
                lista = [i["manifiesto"] for i in c["items"]]
                cur.execute(
                    "INSERT INTO wa_mensajes (campana_id, aviso, manifiesto, manifiestos, contacto, telefono, texto, "
                    "creado_en) VALUES (%s,1,%s,%s,%s,%s,%s,%s)",
                    [cid, lista[0][:60], ", ".join(lista), c["contacto"], c["telefono"],
                     armar_texto(plantilla, c["contacto"], c["items"]), ahora()])
        db.commit()
        return cid
    finally:
        db.close()


def items_por_telefono(cid):
    """{telefono: [{fecha, manifiesto, placa}]} de la campaña."""
    d = {}
    for i in _ejecutar("SELECT telefono, contacto, fecha, manifiesto, placa FROM wa_items WHERE campana_id = %s ORDER BY id", [cid]):
        d.setdefault(i["telefono"], []).append(i)
    return d


def candidatos_segundo(cid):
    """(sin_respuesta, con_respuesta): contactos del 1.er aviso ya enviado que aún no tienen 2.º aviso."""
    filas = _ejecutar(
        "SELECT m.*, (SELECT COUNT(*) FROM wa_respuestas r JOIN wa_mensajes x ON x.id = r.mensaje_id "
        "WHERE x.campana_id = m.campana_id AND x.telefono = m.telefono) AS n_resp "
        "FROM wa_mensajes m WHERE m.campana_id = %s AND m.aviso = 1 AND m.estado IN ('enviado','entregado','leido') "
        "AND NOT EXISTS (SELECT 1 FROM wa_mensajes s WHERE s.campana_id = m.campana_id AND s.telefono = m.telefono "
        "AND s.aviso = 2) ORDER BY m.id", [cid])
    return [f for f in filas if not f["n_resp"]], [f for f in filas if f["n_resp"]]


def crear_segundo_aviso(cid, plantilla2, incluir_respondieron=False):
    """Crea (ya en cola) el 2.º aviso para quienes no han respondido. Devuelve cuántos."""
    sin, con = candidatos_segundo(cid)
    destinos = sin + (con if incluir_respondieron else [])
    items = items_por_telefono(cid)
    for d in destinos:
        lista = items.get(d["telefono"]) or []
        if not lista:
            continue
        _ejecutar("INSERT INTO wa_mensajes (campana_id, aviso, manifiesto, manifiestos, contacto, telefono, texto, "
                  "estado, creado_en) VALUES (%s,2,%s,%s,%s,%s,%s,'en_cola',%s)",
                  [cid, d["manifiesto"], d["manifiestos"], d["contacto"], d["telefono"],
                   armar_texto(plantilla2, d["contacto"], lista), ahora()], commit=True)
    return len(destinos)


def campanas():
    asegurar_tablas()
    return _ejecutar(
        "SELECT c.*, SUM(m.aviso = 1) AS total, "
        "SUM(m.estado='pendiente') AS pendientes, SUM(m.estado='en_cola') AS en_cola, "
        "SUM(m.aviso = 1 AND m.estado IN ('enviado','entregado','leido')) AS enviados, "
        "SUM(m.aviso = 1 AND m.estado IN ('entregado','leido')) AS entregados, "
        "SUM(m.aviso = 1 AND m.estado='leido') AS leidos, SUM(m.estado='error') AS errores, "
        "SUM(m.aviso = 2 AND m.estado IN ('enviado','entregado','leido')) AS segundos, "
        "(SELECT COUNT(*) FROM wa_respuestas r JOIN wa_mensajes x ON x.id = r.mensaje_id WHERE x.campana_id = c.id) AS respuestas "
        "FROM wa_campanas c LEFT JOIN wa_mensajes m ON m.campana_id = c.id GROUP BY c.id ORDER BY c.id DESC")


def campana(cid):
    asegurar_tablas()
    return _ejecutar("SELECT * FROM wa_campanas WHERE id = %s", [cid], uno=True)


def mensajes(cid, estado=None):
    sql = ("SELECT m.*, (SELECT COUNT(*) FROM wa_respuestas r WHERE r.mensaje_id = m.id) AS n_resp, "
           "(SELECT r.texto FROM wa_respuestas r WHERE r.mensaje_id = m.id ORDER BY r.id DESC LIMIT 1) AS ultima_resp "
           "FROM wa_mensajes m WHERE m.campana_id = %s")
    params = [cid]
    if estado in ESTADOS:
        sql += " AND m.estado = %s"
        params.append(estado)
    return _ejecutar(sql + " ORDER BY m.id", params)


def mensajes_por_ids(ids):
    if not ids:
        return []
    return _ejecutar("SELECT * FROM wa_mensajes WHERE id IN (%s)" % ",".join(["%s"] * len(ids)), ids)


# tel_enviado = número al que se envió el aviso; r.telefono = número desde el que respondieron.
_PLACAS = ("(SELECT GROUP_CONCAT(DISTINCT i.placa ORDER BY i.id SEPARATOR ', ') FROM wa_items i "
           "WHERE i.campana_id = m.campana_id AND i.telefono = m.telefono) AS placas")


def _like(texto):
    """Patrón LIKE seguro (%texto%) escapando los comodines que escriba el usuario."""
    return "%" + texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def respuestas_de_campana(cid):
    return _ejecutar("SELECT r.*, COALESCE(m.manifiestos, m.manifiesto) AS manifiesto, m.contacto, "
                     "m.telefono AS tel_enviado, " + _PLACAS + " FROM wa_respuestas r "
                     "JOIN wa_mensajes m ON m.id = r.mensaje_id WHERE m.campana_id = %s ORDER BY r.id", [cid])


def respuestas(filtros=None, limite=300):
    """filtros: placa, contacto, manifiesto, celular (cualquiera de los dos números) y campana (id)."""
    asegurar_tablas()
    f = filtros or {}
    donde, params = [], []
    if f.get("placa"):
        donde.append("EXISTS (SELECT 1 FROM wa_items i WHERE i.campana_id = m.campana_id AND i.telefono = m.telefono "
                     "AND i.placa LIKE %s)")
        params.append(_like(f["placa"]))
    if f.get("contacto"):
        donde.append("m.contacto LIKE %s")
        params.append(_like(f["contacto"]))
    if f.get("manifiesto"):
        donde.append("COALESCE(m.manifiestos, m.manifiesto) LIKE %s")
        params.append(_like(f["manifiesto"]))
    if f.get("celular"):
        digitos = re.sub(r"\D", "", f["celular"])
        if digitos:
            donde.append("(m.telefono LIKE %s OR r.telefono LIKE %s)")
            params += [_like(digitos), _like(digitos)]
    if f.get("campana"):
        donde.append("m.campana_id = %s")
        params.append(f["campana"])
    sql = ("SELECT r.*, COALESCE(m.manifiestos, m.manifiesto) AS manifiesto, m.contacto, m.telefono AS tel_enviado, "
           "m.campana_id, c.nombre AS campana, " + _PLACAS + " FROM wa_respuestas r "
           "LEFT JOIN wa_mensajes m ON m.id = r.mensaje_id LEFT JOIN wa_campanas c ON c.id = m.campana_id")
    if donde:
        sql += " WHERE " + " AND ".join(donde)
    return _ejecutar(sql + " ORDER BY r.id DESC LIMIT %s", params + [limite])


def respuestas_de_mensaje(mid):
    return _ejecutar("SELECT * FROM wa_respuestas WHERE mensaje_id = %s ORDER BY id", [mid])


# ---------------------------------------------------------------- cola de envío
def marcar_en_cola(ids):
    if ids:
        _ejecutar("UPDATE wa_mensajes SET estado='en_cola', error=NULL WHERE id IN (%s)" % ",".join(["%s"] * len(ids)),
                  ids, commit=True)


def volver_a_pendiente(ids):
    if ids:
        _ejecutar("UPDATE wa_mensajes SET estado='pendiente' WHERE estado='en_cola' AND id IN (%s)"
                  % ",".join(["%s"] * len(ids)), ids, commit=True)


def reponer_en_cola(cid):
    """Los 'en cola' que el servicio perdió (p. ej. se reinició) vuelven a pendiente."""
    _ejecutar("UPDATE wa_mensajes SET estado='pendiente' WHERE campana_id=%s AND estado='en_cola'", [cid], commit=True)


# ---------------------------------------------------------------- eventos del servicio
def resultado_envio(mid, ok, wa_id=None, error=None):
    if ok:
        _ejecutar("UPDATE wa_mensajes SET estado='enviado', wa_id=%s, error=NULL, enviado_en=%s WHERE id=%s "
                  "AND estado IN ('pendiente','en_cola','error')", [wa_id, ahora(), mid], commit=True)
    else:
        _ejecutar("UPDATE wa_mensajes SET estado='error', error=%s WHERE id=%s AND estado IN ('pendiente','en_cola')",
                  [(error or "Error desconocido")[:255], mid], commit=True)


def confirmacion(wa_id, ack):
    estado = ACK.get(ack)
    if not estado or not wa_id:
        return
    m = _ejecutar("SELECT id, estado FROM wa_mensajes WHERE wa_id = %s", [wa_id], uno=True)
    if not m or RANGO.get(m["estado"], 0) >= RANGO[estado]:
        return
    t = ahora()
    cols = "estado=%s, entregado_en=COALESCE(entregado_en, %s)"
    params = [estado, t]
    if estado == "leido":
        cols += ", leido_en=%s"
        params.append(t)
    _ejecutar("UPDATE wa_mensajes SET " + cols + " WHERE id=%s", params + [m["id"]], commit=True)


def guardar_respuesta(telefono, texto, tipo, wa_id, citado_id, recibida, con_archivo=False):
    """Liga la respuesta al mensaje citado o, si no cita nada, al último enviado a ese teléfono.
    Devuelve (id_respuesta, mensaje) o (None, None) si ya estaba registrada. `mensaje` puede ser None."""
    asegurar_tablas()
    mid = None
    if citado_id:
        m = _ejecutar("SELECT id FROM wa_mensajes WHERE wa_id = %s", [citado_id], uno=True)
        mid = m["id"] if m else None
    if not mid:
        m = _ejecutar("SELECT id FROM wa_mensajes WHERE telefono = %s AND estado IN ('enviado','entregado','leido') "
                      "ORDER BY enviado_en DESC, id DESC LIMIT 1", [telefono], uno=True)
        mid = m["id"] if m else None
    if wa_id and _ejecutar("SELECT id FROM wa_respuestas WHERE wa_id = %s", [wa_id], uno=True):
        return None, None                             # ya registrada
    rid = _ejecutar("INSERT INTO wa_respuestas (mensaje_id, telefono, texto, tipo, wa_id, recibida_en, archivo_estado) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    [mid, telefono, (texto or "")[:4000], tipo[:20], wa_id, recibida, "subiendo" if con_archivo else None],
                    commit=True)
    if mid:   # si respondió, es que lo recibió y lo leyó
        _ejecutar("UPDATE wa_mensajes SET estado='leido', entregado_en=COALESCE(entregado_en, %s), "
                  "leido_en=COALESCE(leido_en, %s) WHERE id=%s AND estado IN ('enviado','entregado')",
                  [recibida, recibida, mid], commit=True)
    mensaje = _ejecutar("SELECT id, COALESCE(manifiestos, manifiesto) AS manifiesto, cliente, telefono FROM wa_mensajes "
                        "WHERE id = %s", [mid], uno=True) if mid else None
    return rid, mensaje


def resultado_archivo(rid, estado, nombre=None, url=None, error=None):
    """El servicio informa si el adjunto quedó en OneDrive (guardado), se omitió o falló."""
    if estado not in ("subiendo", "guardado", "omitido", "error"):
        return
    _ejecutar("UPDATE wa_respuestas SET archivo_estado=%s, archivo_nombre=%s, archivo_url=%s, archivo_error=%s "
              "WHERE id=%s", [estado, (nombre or "")[:255] or None, (url or "")[:800] or None,
                              (error or "")[:255] or None, rid], commit=True)
