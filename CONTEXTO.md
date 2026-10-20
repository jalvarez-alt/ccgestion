# CONTEXTO — ccgestion (C&C Gestión · Camiones y Camiones Ltda.)

> Resumen para retomar el proyecto en otro chat o con otra persona. Actualizado: 2026-10-19.
> **No contiene contraseñas ni tokens** (están en `config.py`, `sftp.json` y `whatsapp-service/.env`, que no se versionan).

## 1. Qué es
Aplicación web interna en **Flask (Python) + MySQL**, en español, para la empresa de transportes Camiones y Camiones.
- **Producción:** https://gestion.camionesycamiones.com.co (hosting **Namecheap**, cPanel + Passenger).
- **Repositorio:** https://github.com/jalvarez-alt/ccgestion (rama `main`).
- Dependencias Python (`requirements.txt`): flask, pymysql, reportlab, openpyxl.

## 2. Módulos
| Módulo | Archivos principales | Notas |
|---|---|---|
| Núcleo / S.G.C.S. | `app.py`, `consultas.py`, `guardar.py`, `pdf_gen.py`, `excel.py`, `etiquetas.py`, `textos.py` | Login, formulario de vinculación, registros, PDF, Excel |
| Nómina | `nomina.py`, `nomina_db.py`, `nomina_calculo.py`, `nomina_pdf.py`, `nomina_excel.py`, `correo.py` | Periodos, liquidación, desprendibles por PDF y correo |
| Celulares | `celulares.py`, `celulares_db.py`, `celulares_excel.py` | Inventario, reasignación, bajas |
| Equipos | `equipos.py`, `equipos_db.py`, `equipos_excel.py` | Inventario y software |
| Usuarios y roles | `usuarios.py`, `personas_db.py`, `roles_db.py`, `seguridad.py` | Permisos por rol (`seguridad.PERMISOS`) |
| **WhatsApp** | `whatsapp.py`, `whatsapp_db.py`, `templates/whatsapp/`, `whatsapp-service/` | Ver sección 5 |

Otros: `db.py` (conexión), `config.py` (no versionado; plantilla en `config.example.py`), `importar_*.py`, `passenger_wsgi.py`.

## 3. Entornos
**Local (Windows 11, `D:\ccgestion`)**
- Python 3.12 instalado solo para el usuario. Arrancar: `python -m flask --app app run --port 5000` → http://127.0.0.1:5000
- MySQL = **XAMPP (MariaDB 10.4)** en `C:\xampp\mysql`, puerto 3306. Si el PC se apaga mal, MySQL no arranca solo y hay que encenderlo (y a veces se pierde el usuario `aqreqjec_ccgestion`: se recrea con GRANT ALL sobre la base `aqreqjec_ccgestion`).
- Los datos de producción se bajaron una vez (29 usuarios, 4 roles); las demás tablas locales son de pruebas.
- `config.py` acepta `CC_DB_HOST`, `CC_DB_USER`, `CC_DB_NAME` como variables de entorno.

**Producción (Namecheap)**
- Solo hay **SFTP** (sin shell). Datos de conexión en `sftp.json` (no versionado). Carpeta: `/home/aqreqjec/ccgestion`.
- Para reiniciar la app: crear/actualizar el archivo `tmp/restart.txt`. Errores: `stderr.log` de esa carpeta.
- Acceso a MySQL remoto solo por túnel SSH; **el entorno de Claude Code bloquea** operar directo sobre la base de producción (túnel). Los cambios de esquema se aplican con la app (auto-migración en `whatsapp_db.asegurar_tablas`) o con SQL en phpMyAdmin.
- **Hora:** `app.py` fija la zona `COT5` (Colombia, UTC-5) y `db.py` fija `time_zone='-05:00'`. Antes el servidor usaba hora de Nueva York (+60 min).
- El hosting **no puede** alojar el servicio de WhatsApp (necesita Chrome y estar siempre encendido).

## 4. Base de datos (tablas relevantes)
- Existentes: `usuarios` (personas y accesos), `roles`, `rol_permisos`, `registros*` (S.G.C.S.), `empleadores`, `empleados`, `nomina_*`, `celulares`, `celular_movimientos`, `equipos`, `equipo_software`.
- **WhatsApp** (`whatsapp_schema.sql`; la app las crea/migra sola):
  - `wa_campanas` (nombre, `plantilla`, `plantilla2` = segundo aviso)
  - `wa_mensajes` (1 fila por contacto y aviso; `aviso` 1/2, `manifiestos`, `estado`, `wa_id`, `chat_id`, `finalizado*`, fechas de envío/entrega/lectura)
  - `wa_items` (una fila por manifiesto: fecha, manifiesto, placa, de cada contacto)
  - `wa_respuestas` (respuestas, liga a `mensaje_id`, `chat_id`, estado del adjunto)
  - `wa_servicio` (latido del servicio: estado, QR, comando)

## 5. Módulo WhatsApp (mensajes masivos de documentos pendientes)
**Arquitectura**
- **Servicio Node** (`whatsapp-service/`, `whatsapp-web.js`, **vía no oficial**: riesgo de bloqueo del número) corre en el **PC de la oficina** y debe estar encendido: `whatsapp-service\iniciar_whatsapp.bat` (o `npm start`).
- El servicio **solo hace conexiones salientes**: cada ~10 s envía un latido a `POST /whatsapp/webhook/latido` de producción (con token `X-WA-Token`), recibe los mensajes «en cola» y reporta resultados/respuestas por webhooks (`estado`, `respuesta`, `archivo`, `lid`). No hay túnel ni puertos abiertos. La cola vive en la BD.
- El QR se escanea desde la app: **WhatsApp → Conexión (QR)**. La sesión queda en `whatsapp-service/.wwebjs_auth/`.
- Si no hay latido por más de 60 s la app muestra el servicio como apagado.

**Funciones**
- **Campañas:** archivo plano con columnas **Fecha, Manifiesto, Placa, Celular, Contacto** (plantilla descargable). Un contacto con varios manifiestos recibe **un solo mensaje**; las líneas con `{fecha}`, `{num}`, `{placa}` se repiten por manifiesto, `{x}` = cantidad, `{nombre_conductor}` = contacto. Se crea sin enviar; se confirma con «Enviar».
- **Segundo aviso:** casilla «Habilitar segundo aviso» al crear la campaña (texto editable). Botón «Enviar segundo aviso» → solo a quienes **no han respondido** (opción de incluir a los que sí) y **no finalizados**.
- **Finalizar contacto:** botón por contacto (y selección múltiple) = ya entregó el documento; sale del segundo aviso y cancela lo que siga en cola. Reversible con «Reabrir».
- **Historial:** estados pendiente / en cola / enviado / entregado / leído / error, fechas, exportación a Excel (envíos, manifiestos, respuestas).
- **Respuestas** (menú WhatsApp → Respuestas): muestra el celular al que se envió, desde cuál respondieron, contacto, manifiestos y placas; **filtros** por placa, contacto, manifiesto, celular y campaña.
- **IDs internos (@lid):** WhatsApp a veces identifica al contacto con un ID interno en vez del celular. El servicio lo traduce (`getContactLidAndPhone`), guarda el `chat_id` al enviar y corrige/liga automáticamente las respuestas antiguas sin celular.
- **Permisos:** `whatsapp.consultar` (ver) y `whatsapp.enviar` (crear campañas, enviar, finalizar, conexión). El administrador tiene todos.

**Adjuntos → OneDrive (código hecho, NO operativo)**
- Imágenes → PDF (A4), PDF tal cual; nombre = manifiesto(s); carpeta = cliente (reutiliza la existente; hoy el archivo ya no trae cliente → `Sin identificar`); cola local `cola_archivos/` si falla la subida; enlace en la app. Usa **Microsoft Graph** (credenciales de aplicación).
- Pendiente de Microsoft: registrar app en Entra, permiso `Files.ReadWrite.All` con consentimiento de administrador, completar `GRAPH_*` en `whatsapp-service/.env` y verificar con `npm run probar-onedrive`. Pasos en `whatsapp-service/README.md`. Se descartó Google Drive y la carpeta sincronizada.

## 6. Pendientes y problemas conocidos
1. **Descarga de adjuntos falla** (`error al guardar: r`): `msg.downloadMedia()` de `whatsapp-web.js` 1.34.7 no es compatible con la versión actual de WhatsApp Web. Mientras no se arregle **no se guarda ningún adjunto** (las respuestas de texto sí). Idea: fijar una versión de WhatsApp Web compatible (`webVersionCache`) y reintentar.
2. **OneDrive sin conectar** (ver sección 5).
3. **Datos antiguos con +1 h:** ejecutar **una sola vez** `whatsapp_corregir_hora.sql` en phpMyAdmin (con respaldo). Otros módulos (nómina, registros) también tienen datos antiguos con +1 h; no están en ese SQL.
4. El servicio de WhatsApp se apaga si se reinicia el PC o se cierra la sesión de Claude Code que lo encendió; encenderlo con `iniciar_whatsapp.bat`.
5. Las columnas de nómina/registros con hora y el campo «cliente» en WhatsApp (ya no viene en el archivo) están sin resolver.

## 7. Git y forma de trabajo
- Commits en español con la línea `Co-Authored-By: Claude …`. Siempre revisar que no se suban secretos (`.gitignore` excluye `config.py`, `sftp.json`, `*.sql` salvo los de WhatsApp, `.env`, logs, `tmp/`, `node_modules/`, `cola_archivos/`).
- Flujo habitual: probar en **local** → subir a producción por SFTP (archivos cambiados + `tmp/restart.txt`) → verificar → commit y push.
- Los despliegues a producción y cambios de esquema se confirman con el usuario.

## 8. Historial reciente (2026-10)
- Traído el proyecto desde Namecheap, base de datos local y git.
- Módulo WhatsApp: campañas, historial y respuestas; servicio con sondeo (sin túnel); adjuntos → OneDrive (código).
- Mensaje por conductor con varios manifiestos + segundo aviso; archivo plano Fecha/Manifiesto/Placa/Celular/Contacto.
- Respuestas con número y filtros; traducción de IDs internos; hora de Colombia; botón Finalizar por contacto.
