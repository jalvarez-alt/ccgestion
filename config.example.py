# ------------------------------------------------------------
# CONFIGURACION de C&C Gesti贸n
# Edita los valores entre comillas y guarda. No compartas este archivo.
# Los datos de la base los ves en cPanel > MySQL Databases.
# ------------------------------------------------------------
import os
DB_HOST = os.environ.get("CC_DB_HOST", "localhost")
DB_USER = os.environ.get("CC_DB_USER", "aqreqjec_ccgestion")      # usuario COMPLETO con prefijo, ej: abcd1234_ccuser
DB_PASS = "CAMBIA_contrase帽a"
DB_NAME = os.environ.get("CC_DB_NAME", "aqreqjec_ccgestion")        # base COMPLETA con prefijo, ej: abcd1234_ccgestion

# Texto largo y aleatorio (30 caracteres o mas, letras y numeros mezclados)
SECRET_KEY = "CAMBIA_texto_largo_aleatorio"

# True = cualquiera puede crear una cuenta (rol Vinculante) desde la pantalla de inicio de sesion.
# False = solo el administrador crea usuarios.
PERMITIR_REGISTRO = True

# Opcional: logo en la cabecera (por defecto usa el de camionesycamiones.com.co)
# LOGO_URL = "https://camionesycamiones.com.co/wp-content/uploads/2025/08/camiones_camiones_logo.png"

# ------------------------------------------------------------
# CORREO (desprendibles de nómina). Opcional: sin esto todo funciona menos el envío.
# Opción A - Gmail: SMTP_HOST "smtp.gmail.com", puerto 587, "starttls".
#   Requiere verificación en 2 pasos y una "contraseña de aplicación" (16 letras), NO tu clave normal.
# Opción B - Outlook/Microsoft 365: "smtp.office365.com", puerto 587, "starttls".
#   (Microsoft puede exigir habilitar SMTP autenticado para el buzón.)
# Opción C - buzón del hosting (recomendado si Namecheap bloquea Gmail/Outlook), ej. nomina@camionesycamiones.com.co:
#   host = "mail.camionesycamiones.com.co", puerto 465, "ssl" (datos en cPanel > Email Accounts > Connect Devices).
# ------------------------------------------------------------
#SMTP_HOST = "smtp.gmail.com"
#SMTP_PORT = 587
#SMTP_SEGURIDAD = "starttls"            # "starttls" (puerto 587) o "ssl" (puerto 465)
#SMTP_USER = "CAMBIA_correo_que_envia@gmail.com"
#SMTP_PASS = "CAMBIA_contraseña_de_aplicacion"
#SMTP_REMITENTE = "CAMBIA_correo_que_envia@gmail.com"   # normalmente igual a SMTP_USER
#SMTP_NOMBRE = "Nómina Camiones y Camiones"
