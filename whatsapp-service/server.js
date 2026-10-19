// Servicio de WhatsApp para C&C Gestión (whatsapp-web.js).
// ccgestion le entrega los mensajes por HTTP; este servicio los envía de a uno con pausas aleatorias
// y avisa a ccgestion (webhooks) de cada resultado, confirmación de lectura y respuesta recibida.
const fs = require('fs');
const onedrive = require('./onedrive');
const archivos = require('./archivos');
const QRCode = require('qrcode');
const { Client, LocalAuth } = require('whatsapp-web.js');

const PORT = parseInt(process.env.PORT || '3100', 10);
const TOKEN = process.env.WA_TOKEN || '';
const FLASK_URL = (process.env.FLASK_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');
const PAUSA_MIN = parseFloat(process.env.PAUSA_MIN || '8') * 1000;
const PAUSA_MAX = parseFloat(process.env.PAUSA_MAX || '20') * 1000;
const LOTE_TAMANO = parseInt(process.env.LOTE_TAMANO || '30', 10);     // cada N mensajes, descanso largo
const LOTE_PAUSA = parseFloat(process.env.LOTE_PAUSA || '90') * 1000;

if (!TOKEN || TOKEN.length < 16) {
  console.error('Falta WA_TOKEN (mínimo 16 caracteres) en el archivo .env');
  process.exit(1);
}

const estado = { estado: 'iniciando', qr: null, numero: null };
const cola = [];
let procesando = false;
let enviadosEnLote = 0;

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const azar = (a, b) => a + Math.random() * (b - a);

async function avisar(ruta, cuerpo) {
  for (let i = 0; i < 4; i++) {
    try {
      const r = await fetch(FLASK_URL + '/whatsapp/webhook/' + ruta, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-WA-Token': TOKEN },
        body: JSON.stringify(cuerpo),
      });
      if (r.ok) return await r.json().catch(() => true);
      console.error('Webhook', ruta, 'respondió', r.status);
    } catch (e) {
      console.error('Webhook', ruta, 'falló:', e.message);
    }
    await dormir(2000 * (i + 1));
  }
  return false;
}

const FATAL = /detached Frame|Target closed|Session closed|Execution context was destroyed|Protocol error|Navigating frame/i;
let reiniciando = false;

async function reiniciar(borrarSesion = false) {
  if (reiniciando) return;
  reiniciando = true;
  estado.estado = 'reiniciando';
  estado.qr = null;
  estado.numero = null;
  try {
    try { await Promise.race([client.destroy(), dormir(10000)]); } catch (e) { console.error('destroy:', e.message); }
    if (borrarSesion) {
      try { fs.rmSync('./.wwebjs_auth', { recursive: true, force: true, maxRetries: 5, retryDelay: 500 }); }
      catch (e) { console.error('No se pudo borrar la sesión:', e.message); }
    }
    client = crearCliente();
    await client.initialize();
  } catch (e) {
    console.error('Error al reiniciar:', e.message);
    estado.estado = 'error';
  } finally {
    reiniciando = false;
  }
}

function crearCliente() {
const cl = new Client({
  authStrategy: new LocalAuth({ dataPath: './.wwebjs_auth' }),
  puppeteer: { headless: true, executablePath: process.env.CHROME_PATH || undefined, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
});

cl.on('qr', async (qr) => {
  estado.estado = 'qr';
  estado.qr = await QRCode.toDataURL(qr, { margin: 1, width: 280 });
  console.log('Esperando que escanees el QR (ábrelo en ccgestion > WhatsApp > Conexión).');
});
cl.on('authenticated', () => { estado.estado = 'autenticado'; estado.qr = null; });
cl.on('auth_failure', (m) => { estado.estado = 'error_autenticacion'; console.error('Fallo de autenticación:', m); });
cl.on('ready', () => {
  estado.estado = 'listo';
  estado.qr = null;
  estado.numero = client.info && client.info.wid ? client.info.wid.user : null;
  console.log('WhatsApp listo como', estado.numero);
  procesarCola();
});
cl.on('disconnected', (motivo) => {
  estado.estado = 'desconectado';
  estado.numero = null;
  console.error('WhatsApp desconectado:', motivo);
  setTimeout(() => reiniciar(), 5000);
});

// Estados de entrega/lectura de lo que enviamos (1 enviado, 2 entregado, 3 leído, 4 reproducido)
cl.on('message_ack', (msg, ack) => {
  if (!msg.fromMe) return;
  avisar('estado', { wa_id: msg.id._serialized, ack });
});

// Respuestas de los clientes (se ignoran grupos, estados y mensajes propios)
cl.on('message', async (msg) => {
  try {
    if (msg.fromMe || msg.isStatus || msg.from.endsWith('@g.us') || msg.from === 'status@broadcast') return;
    const de = msg.from;                       // "5730...@c.us" o, para cuentas con ID interno, "9262...@lid"
    let telefono = de.split('@')[0];
    if (de.endsWith('@lid')) {
      const real = await resolverLid(de);      // traduce el ID interno al celular real
      if (real) telefono = real;
      else {
        try { const c = await msg.getContact(); if (c && c.number && c.number !== telefono) telefono = c.number; } catch (_) { /* queda el ID */ }
      }
    }
    let citado = null;
    if (msg.hasQuotedMsg) {
      try { citado = (await msg.getQuotedMessage()).id._serialized; } catch (_) { /* sin cita */ }
    }
    const conAdjunto = msg.hasMedia && ['image', 'document'].includes(msg.type);
    const resp = await avisar('respuesta', {
      telefono, texto: msg.body || '', tipo: msg.type || 'chat', wa_id: msg.id._serialized,
      citado_id: citado, ts: msg.timestamp, tiene_archivo: conAdjunto, chat_id: de,
    });
    if (conAdjunto && resp && resp.respuesta_id) procesarAdjunto(msg, resp, telefono);
  } catch (e) {
    console.error('Error procesando respuesta:', e.message);
  }
});

return cl;
}
let client = crearCliente();

// ---- adjuntos recibidos -> OneDrive (nombre = manifiesto, carpeta = cliente) ----
async function subirDeCola(a, rid) {
  try {
    const r = await onedrive.subir(a.cliente, a.nombre, a.buffer, a.mimetype);
    archivos.quitarDeCola(rid);
    console.log('Guardado en OneDrive:', r.carpeta + '/' + r.nombre);
    await avisar('archivo', { respuesta_id: rid, estado: 'guardado', nombre: r.nombre, url: r.url });
  } catch (e) {
    console.error('OneDrive falló para respuesta', rid, e.message);
    await avisar('archivo', { respuesta_id: rid, estado: 'subiendo', error: 'Reintentando: ' + e.message.slice(0, 200) });
  }
}

async function procesarAdjunto(msg, resp, telefono) {
  const rid = resp.respuesta_id;
  try {
    const media = await msg.downloadMedia();
    if (!media) return avisar('archivo', { respuesta_id: rid, estado: 'error', error: 'No se pudo descargar el adjunto de WhatsApp' });
    if (!archivos.admitido(media.mimetype)) {
      return avisar('archivo', { respuesta_id: rid, estado: 'omitido', error: 'tipo ' + media.mimetype });
    }
    const m = resp.mensaje || {};
    const a = await archivos.preparar({ media, manifiesto: m.manifiesto, cliente: m.cliente, telefono });
    archivos.guardarEnCola(rid, a);          // respaldo local hasta confirmar que quedó en OneDrive
    await subirDeCola(a, rid);
  } catch (e) {
    console.error('Error con el adjunto', rid, e.stack || e.message);
    await avisar('archivo', { respuesta_id: rid, estado: 'error', error: String(e.message).slice(0, 200) });
  }
}

let reintentando = false;
async function reintentarCola() {
  if (reintentando) return;
  reintentando = true;
  try {
    for (const a of archivos.pendientesEnCola()) await subirDeCola(a, a.respuestaId);
  } catch (e) { console.error('Cola de archivos:', e.message); }
  finally { reintentando = false; }
}
setInterval(reintentarCola, 5 * 60 * 1000);
setTimeout(reintentarCola, 15000);

async function enviarUno(m) {
  const id = await client.getNumberId(String(m.telefono));
  if (!id) return avisar('estado', { id: m.id, ok: false, error: 'Ese número no tiene WhatsApp' });
  const enviado = await client.sendMessage(id._serialized, m.texto, { sendSeen: false });
  // La librería a veces envía el mensaje pero no devuelve su modelo: se da por enviado (sin seguimiento de lectura).
  // Si WhatsApp usa un ID interno (@lid) para este chat, se informa para poder ligar las respuestas.
  const chat = enviado && enviado.to && String(enviado.to).endsWith('@lid') ? enviado.to : null;
  return avisar('estado', { id: m.id, ok: true, wa_id: enviado && enviado.id ? enviado.id._serialized : null, chat });
}

// Celular real de un ID interno de WhatsApp ("9262...@lid"). null si no se puede resolver.
async function resolverLid(lid) {
  try {
    const r = await client.getContactLidAndPhone([lid]);
    const pn = r && r[0] && r[0].pn;
    return pn ? String(pn).split('@')[0] : null;
  } catch (e) {
    return null;
  }
}
const lidProbados = new Map();          // lid -> momento del último intento (no reintentar cada 10 s)

async function procesarCola() {
  if (procesando) return;
  procesando = true;
  try {
    while (cola.length && estado.estado === 'listo') {
      const m = cola.shift();
      try {
        await enviarUno(m);
      } catch (e) {
        console.error('Error enviando', m.id, e.stack || e.message);
        if (FATAL.test(String(e.message)) && (m.intentos || 0) < 2) {   // el navegador interno se cayó: reinicia y reintenta
          m.intentos = (m.intentos || 0) + 1;
          cola.unshift(m);
          reiniciar();
          break;
        }
        await avisar('estado', { id: m.id, ok: false, error: String(e.message).slice(0, 200) });
      }
      enviadosEnLote++;
      if (!cola.length) break;
      if (enviadosEnLote >= LOTE_TAMANO) {
        enviadosEnLote = 0;
        await dormir(azar(LOTE_PAUSA, LOTE_PAUSA * 1.5));
      } else {
        await dormir(azar(PAUSA_MIN, PAUSA_MAX));
      }
    }
  } finally {
    procesando = false;
  }
}

// ---- comunicación con ccgestion: el servicio SOLO hace conexiones salientes (no abre ningún puerto) ----
// Cada POLL_SEG segundos avisa su estado/QR y recibe los mensajes que estén "en cola" y las órdenes pendientes.
const POLL = parseFloat(process.env.POLL_SEG || '10') * 1000;
const vistos = new Map();            // id -> momento en que se tomó (evita enviar dos veces el mismo mensaje)
const VISTO_MIN = 10 * 60 * 1000;

async function cerrarSesion() {
  // Si WhatsApp Web está colgado, logout() falla: en ese caso se fuerza cerrando el navegador y borrando la sesión local.
  try { await Promise.race([client.logout(), dormir(15000).then(() => { throw new Error('tiempo agotado'); })]); }
  catch (e) { console.error('logout falló, se fuerza:', e.message); }
  reiniciar(true);
}

// Compara la hora que usa ccgestion (servidor) con la de este PC y avisa en el log si no coinciden.
let ultimoDesfase = null;
function revisarHora(textoServidor, ahora) {
  if (!textoServidor) return;
  const servidor = new Date(textoServidor.replace(' ', 'T'));        // hora local "sin zona" del servidor
  if (isNaN(servidor)) return;
  const min = Math.round((servidor.getTime() - ahora) / 60000);
  const desfase = Math.abs(min) <= 2 ? 0 : min;
  if (desfase !== ultimoDesfase) {
    ultimoDesfase = desfase;
    console.log(desfase === 0 ? 'Hora del servidor ccgestion: correcta (igual a este PC)'
      : 'Hora del servidor ccgestion DESFASADA: ' + (desfase > 0 ? '+' : '') + desfase + ' min respecto a este PC (' + textoServidor + ')');
  }
}

async function sondear() {
  try {
    const r = await avisar('latido', {
      estado: estado.estado, qr: estado.estado === 'qr' ? estado.qr : null, numero: estado.numero, en_cola: cola.length,
    });
    if (!r || typeof r !== 'object') return;
    const ahora = Date.now();
    revisarHora(r.ahora, ahora);
    for (const [id, t] of vistos) if (ahora - t > VISTO_MIN) vistos.delete(id);
    if (Array.isArray(r.vigentes)) {          // lo que ya no está en cola en ccgestion (cancelado) se descarta
      const vigentes = new Set(r.vigentes);
      for (let k = cola.length - 1; k >= 0; k--) {
        if (!vigentes.has(cola[k].id)) { vistos.delete(cola[k].id); cola.splice(k, 1); }
      }
    }
    for (const m of r.mensajes || []) {
      if (vistos.has(m.id) || !Number.isInteger(m.id) || !/^\d{10,15}$/.test(String(m.telefono)) || !m.texto) continue;
      vistos.set(m.id, ahora);
      cola.push(m);
    }
    // Respuestas guardadas con ID interno y sin celular: se intenta traducirlas y ccgestion las corrige/liga.
    for (const [lid, t] of lidProbados) if (ahora - t > 60 * 60 * 1000) lidProbados.delete(lid);
    for (const lid of r.lids || []) {
      if (lidProbados.has(lid) || estado.estado !== 'listo') continue;
      lidProbados.set(lid, ahora);
      const real = await resolverLid(lid + '@lid');
      if (real && real !== lid) { console.log('ID interno', lid, '->', real); await avisar('lid', { lid, telefono: real }); } else console.log('ID interno', lid, 'sin celular disponible');
    }
    if (cola.length) procesarCola();
    if (r.comando === 'cerrar') await cerrarSesion();
  } catch (e) {
    console.error('Sondeo:', e.message);
  }
}

async function ciclo() {
  await sondear();
  setTimeout(ciclo, POLL);
}

console.log('Servicio WhatsApp -> ' + FLASK_URL);
ciclo();
client.initialize().catch((e) => { console.error(e); estado.estado = 'error'; });
