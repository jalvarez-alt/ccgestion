# Servicio de WhatsApp (ccgestion)

Envía los mensajes masivos con `whatsapp-web.js` (WhatsApp Web automatizado, **no oficial**) y avisa a ccgestion
del resultado de cada envío, las confirmaciones de entrega/lectura y las respuestas.

> ⚠️ WhatsApp no autoriza el envío masivo automatizado con esta vía: el número puede ser bloqueado.
> Usa un número exclusivo para la empresa, envía solo a clientes que ya te conocen, pocos mensajes por día
> y mantén las pausas aleatorias (`PAUSA_MIN`/`PAUSA_MAX`).

## Requisitos
- Node.js 20.6 o superior, y Google Chrome/Chromium (lo descarga `npm install` automáticamente).
- Este servicio debe estar **siempre encendido** mientras se envía o se esperan respuestas. No corre en el hosting
  compartido de Namecheap: va en un PC/servidor propio.
- El servicio **solo hace conexiones salientes** hacia ccgestion (`FLASK_URL`, cada `POLL_SEG` segundos): informa su estado/QR y
  recibe los mensajes en cola. No necesita túnel ni abrir puertos, y la cola vive en la base de datos de ccgestion.

## Puesta en marcha
1. `cd whatsapp-service && npm install`
2. Copia `.env.example` a `.env` y pon el mismo `WA_TOKEN` que en `config.py`.
3. `npm start`
4. En ccgestion: menú **WhatsApp → Conexión (QR)** y escanea el QR desde *WhatsApp → Dispositivos vinculados*.
   La sesión queda guardada en `.wwebjs_auth/` (no se versiona).

## Notas
- La cola está en la base de datos: si el servicio se apaga o reinicia, retoma los mensajes «en cola» al volver. Si no hay señal del servicio por más de 60 s, ccgestion lo muestra como apagado.
- Las respuestas se ligan al envío citado o, si no cita, al último mensaje enviado a ese número.

## Adjuntos -> OneDrive
Cuando un cliente responde con una **foto o un documento**, el servicio lo guarda en OneDrive:
- Carpeta: `GRAPH_BASE_FOLDER/<nombre del cliente>/` (reutiliza la carpeta que ya exista, sin importar mayúsculas, tildes
  ni puntuación; si no existe la crea).
- Nombre: el **número de manifiesto** (`MF-001.pdf`). Si ya hay uno igual, OneDrive agrega un número (`MF-001 1.pdf`).
- Las imágenes se convierten a PDF (A4); los PDF se suben tal cual; Word/Excel se suben tal cual. Audio, video y stickers no se guardan.
- Si no se puede ligar a un manifiesto, queda en `Sin identificar/Sin_manifiesto_<telefono>_<fecha>.pdf`.
- Si OneDrive falla, el archivo espera en `cola_archivos/` y se reintenta cada 5 minutos (se borra al subirse).
- En ccgestion (Campañas y Respuestas) cada respuesta muestra el enlace «📎 MF-001.pdf (OneDrive)». No se guarda nada en ccgestion.

### Registrar la app en Microsoft (una sola vez, requiere administrador de Microsoft 365)
1. https://entra.microsoft.com → Aplicaciones → Registros de aplicaciones → Nuevo registro (cuenta de este directorio).
2. Copia **Id. de aplicación (cliente)** → `GRAPH_CLIENT_ID` y **Id. de directorio (inquilino)** → `GRAPH_TENANT_ID`.
3. Certificados y secretos → Nuevo secreto de cliente → copia el **valor** → `GRAPH_CLIENT_SECRET`.
4. Permisos de API → Microsoft Graph → **Permisos de aplicación** → `Files.ReadWrite.All` → «Conceder consentimiento de administrador».
5. `GRAPH_USER` = correo del dueño del OneDrive donde está la carpeta; `GRAPH_BASE_FOLDER` = carpeta que contiene las de los clientes.

> `Files.ReadWrite.All` da acceso a los archivos de **todos** los usuarios del directorio. Para limitarlo a una sola
> carpeta/usuario, pide al administrador restringirlo (p. ej. con *Selected Sites/Resource-specific consent* en SharePoint).
> Guarda el secreto solo en `.env` (no se versiona) y renuévalo antes de que venza.
