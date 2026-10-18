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

PLANTILLA_DEFECTO = (
    "Hola{contacto_saludo}, le escribimos de Camiones y Camiones. Tenemos pendiente el cumplido del documento "
    "del siguiente servicio:\n\n"
    "Cliente: {cliente}\nManifiesto: {manifiesto}\nOrden de cargue: {orden_cargue}\nRemesa: {remesa}\n\n"
    "Por favor responda este mensaje con el soporte o indíquenos la fecha en que lo entregará. ¡Gracias!")

_CREADAS = False

_TABLAS = [
    """CREATE TABLE IF NOT EXISTS wa_campanas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(150) NOT NULL,
        plantilla TEXT NOT NULL,
        creada_por VARCHAR(150) NULL,
        creada_en DATETIME NOT NULL
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS wa_mensajes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        campana_id INT NOT NULL,
        manifiesto VARCHAR(60) NULL,
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
    # Columnas del adjunto guardado en OneDrive (se agregan a las instalaciones anteriores)
    existentes = {r["COLUMN_NAME"] for r in _ejecutar(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'wa_respuestas'")}
    for col, tipo in (("archivo_estado", "VARCHAR(12) NULL"), ("archivo_nombre", "VARCHAR(255) NULL"),
                      ("archivo_url", "VARCHAR(800) NULL"), ("archivo_error", "VARCHAR(255) NULL")):
        if col not in existentes:
            _ejecutar("ALTER TABLE wa_respuestas ADD COLUMN %s %s" % (col, tipo), commit=True)
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


def armar_texto(plantilla, d):
    """Reemplaza {campo} por su valor; lo desconocido se deja tal cual."""
    contacto = (d.get("contacto") or "").strip()
    datos = dict(d, contacto_saludo=(" " + contacto) if contacto else "")
    return re.sub(r"\{(\w+)\}", lambda m: str(datos.get(m.group(1)) or "") if m.group(1) in datos else m.group(0),
                  plantilla).strip()


# ---------------------------------------------------------------- campañas
def crear_campana(nombre, plantilla, usuario, filas):
    """filas: dicts con manifiesto, cliente, orden_cargue, remesa, contacto, telefono. Devuelve el id."""
    asegurar_tablas()
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("INSERT INTO wa_campanas (nombre, plantilla, creada_por, creada_en) VALUES (%s,%s,%s,%s)",
                        [nombre, plantilla, usuario, ahora()])
            cid = cur.lastrowid
            cur.executemany(
                "INSERT INTO wa_mensajes (campana_id, manifiesto, cliente, orden_cargue, remesa, contacto, telefono, "
                "texto, creado_en) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [[cid, f["manifiesto"], f["cliente"], f["orden_cargue"], f["remesa"], f["contacto"], f["telefono"],
                  armar_texto(plantilla, f), ahora()] for f in filas])
        db.commit()
        return cid
    finally:
        db.close()


def campanas():
    asegurar_tablas()
    return _ejecutar(
        "SELECT c.*, COUNT(m.id) AS total, "
        "SUM(m.estado='pendiente') AS pendientes, SUM(m.estado='en_cola') AS en_cola, "
        "SUM(m.estado IN ('enviado','entregado','leido')) AS enviados, SUM(m.estado IN ('entregado','leido')) AS entregados, "
        "SUM(m.estado='leido') AS leidos, SUM(m.estado='error') AS errores, "
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


def respuestas_de_campana(cid):
    return _ejecutar("SELECT r.*, m.manifiesto, m.cliente, m.orden_cargue, m.remesa FROM wa_respuestas r "
                     "JOIN wa_mensajes m ON m.id = r.mensaje_id WHERE m.campana_id = %s ORDER BY r.id", [cid])


def respuestas(limite=300):
    asegurar_tablas()
    return _ejecutar(
        "SELECT r.*, m.manifiesto, m.cliente, m.orden_cargue, m.remesa, m.campana_id, c.nombre AS campana "
        "FROM wa_respuestas r LEFT JOIN wa_mensajes m ON m.id = r.mensaje_id "
        "LEFT JOIN wa_campanas c ON c.id = m.campana_id ORDER BY r.id DESC LIMIT %s", [limite])


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
    mensaje = _ejecutar("SELECT id, manifiesto, cliente, telefono FROM wa_mensajes WHERE id = %s", [mid], uno=True) if mid else None
    return rid, mensaje


def resultado_archivo(rid, estado, nombre=None, url=None, error=None):
    """El servicio informa si el adjunto quedó en OneDrive (guardado), se omitió o falló."""
    if estado not in ("subiendo", "guardado", "omitido", "error"):
        return
    _ejecutar("UPDATE wa_respuestas SET archivo_estado=%s, archivo_nombre=%s, archivo_url=%s, archivo_error=%s "
              "WHERE id=%s", [estado, (nombre or "")[:255] or None, (url or "")[:800] or None,
                              (error or "")[:255] or None, rid], commit=True)
