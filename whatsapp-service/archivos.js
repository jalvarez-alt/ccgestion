// Prepara los adjuntos recibidos por WhatsApp y los entrega a OneDrive.
// - Imagen -> PDF (una página A4, orientada y comprimida). PDF -> tal cual. Otros -> tal cual.
// - Nombre: el número de manifiesto. Carpeta: la del cliente.
// - Si OneDrive falla, el archivo espera en ./cola_archivos y se reintenta (no se pierde).
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const { PDFDocument } = require('pdf-lib');
const onedrive = require('./onedrive');

const COLA = path.join(__dirname, 'cola_archivos');
const A4 = [595.28, 841.89];

const EXT_POR_MIME = { 'application/pdf': 'pdf', 'application/msword': 'doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.ms-excel': 'xls', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'text/plain': 'txt' };

// Audio, video y stickers no son soportes de cumplido: no se guardan.
const admitido = (mime) => /^image\/(jpeg|png|webp|gif|heic)/i.test(mime || '') || !!EXT_POR_MIME[mime] ||
  /^application\/(pdf|msword|vnd\.)/i.test(mime || '');

async function imagenAPdf(buffer) {
  const jpg = await sharp(buffer).rotate().resize({ width: 2200, height: 2200, fit: 'inside', withoutEnlargement: true })
    .flatten({ background: '#ffffff' }).jpeg({ quality: 82 }).toBuffer();
  const pdf = await PDFDocument.create();
  const img = await pdf.embedJpg(jpg);
  const horizontal = img.width > img.height;
  const [pw, ph] = horizontal ? [A4[1], A4[0]] : A4;
  const margen = 20;
  const esc = Math.min((pw - 2 * margen) / img.width, (ph - 2 * margen) / img.height, 1);
  const w = img.width * esc, h = img.height * esc;
  const pagina = pdf.addPage([pw, ph]);
  pagina.drawImage(img, { x: (pw - w) / 2, y: (ph - h) / 2, width: w, height: h });
  return Buffer.from(await pdf.save());
}

function sello(fecha = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  return `${fecha.getFullYear()}${p(fecha.getMonth() + 1)}${p(fecha.getDate())}_${p(fecha.getHours())}${p(fecha.getMinutes())}${p(fecha.getSeconds())}`;
}

// Devuelve { buffer, nombre, mimetype, cliente } listo para subir.
async function preparar({ media, manifiesto, cliente, telefono }) {
  const original = Buffer.from(media.data, 'base64');
  const base = onedrive.limpiarNombre(manifiesto) || `Sin_manifiesto_${telefono}_${sello()}`;
  const carpeta = cliente || 'Sin identificar';
  if (/^image\//i.test(media.mimetype)) {
    return { buffer: await imagenAPdf(original), nombre: base + '.pdf', mimetype: 'application/pdf', cliente: carpeta };
  }
  const ext = EXT_POR_MIME[media.mimetype] || (path.extname(media.filename || '').slice(1) || 'bin');
  return { buffer: original, nombre: `${base}.${ext}`, mimetype: media.mimetype, cliente: carpeta };
}

// ---- cola de respaldo para cuando OneDrive no responde ----
function guardarEnCola(respuestaId, a) {
  fs.mkdirSync(COLA, { recursive: true });
  fs.writeFileSync(path.join(COLA, `${respuestaId}.bin`), a.buffer);
  fs.writeFileSync(path.join(COLA, `${respuestaId}.json`),
    JSON.stringify({ respuestaId, nombre: a.nombre, mimetype: a.mimetype, cliente: a.cliente }));
}

function quitarDeCola(respuestaId) {
  for (const ext of ['bin', 'json']) fs.rmSync(path.join(COLA, `${respuestaId}.${ext}`), { force: true });
}

function pendientesEnCola() {
  if (!fs.existsSync(COLA)) return [];
  return fs.readdirSync(COLA).filter((f) => f.endsWith('.json')).map((f) => {
    const meta = JSON.parse(fs.readFileSync(path.join(COLA, f), 'utf8'));
    return { ...meta, buffer: fs.readFileSync(path.join(COLA, f.replace('.json', '.bin'))) };
  });
}

module.exports = { admitido, preparar, guardarEnCola, quitarDeCola, pendientesEnCola };
