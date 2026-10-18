"""Envío de correos por SMTP (Gmail, Outlook o el correo del hosting)."""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import config


def configurado():
    return bool(getattr(config, "SMTP_HOST", "") and getattr(config, "SMTP_USER", "")
                and getattr(config, "SMTP_PASS", "")
                and not str(getattr(config, "SMTP_PASS", "")).startswith("CAMBIA"))


def enviar(destino, asunto, texto, adjunto=None, nombre_adjunto="adjunto.pdf"):
    """Envía un correo. Lanza una excepción con un mensaje claro si algo falla."""
    if not configurado():
        raise RuntimeError("El correo no está configurado: completa los datos SMTP en config.py.")
    host = config.SMTP_HOST
    puerto = int(getattr(config, "SMTP_PORT", 587))
    seguridad = getattr(config, "SMTP_SEGURIDAD", "starttls")
    remitente = getattr(config, "SMTP_REMITENTE", config.SMTP_USER)
    nombre = getattr(config, "SMTP_NOMBRE", "C&C Gestión")

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((nombre, remitente))
    msg["To"] = destino
    msg.set_content(texto)
    if adjunto:
        msg.add_attachment(adjunto, maintype="application", subtype="pdf", filename=nombre_adjunto)

    try:
        if seguridad == "ssl":
            servidor = smtplib.SMTP_SSL(host, puerto, timeout=25, context=ssl.create_default_context())
        else:
            servidor = smtplib.SMTP(host, puerto, timeout=25)
        with servidor:
            if seguridad != "ssl":
                servidor.ehlo()
                servidor.starttls(context=ssl.create_default_context())
                servidor.ehlo()
            servidor.login(config.SMTP_USER, config.SMTP_PASS)
            servidor.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("El servidor rechazó el usuario o la contraseña (en Gmail usa una contraseña de aplicación).")
    except (TimeoutError, ConnectionError, OSError) as e:
        raise RuntimeError("No se pudo conectar con %s:%s (%s). El hosting puede estar bloqueando las "
                           "conexiones SMTP salientes." % (host, puerto, e.__class__.__name__))
    except smtplib.SMTPRecipientsRefused:
        raise RuntimeError("El servidor rechazó la dirección de destino.")
    except smtplib.SMTPException as e:
        raise RuntimeError("Error SMTP: %s" % e.__class__.__name__)
