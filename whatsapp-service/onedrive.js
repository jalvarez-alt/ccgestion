// Subida a OneDrive con Microsoft Graph (credenciales de aplicación, sin inicio de sesión de usuario).
// Requiere una app registrada en Entra ID con el permiso de aplicación Files.ReadWrite.All (con consentimiento
// de administrador). Ver README.
const TENANT = process.env.GRAPH_TENANT_ID || '';
const CLIENT_ID = process.env.GRAPH_CLIENT_ID || '';
const CLIENT_SECRET = process.env.GRAPH_CLIENT_SECRET || '';
const USUARIO = process.env.GRAPH_USER || '';                 // correo (UPN) del dueño del OneDrive
const BASE = (process.env.GRAPH_BASE_FOLDER || '').replace(/^\/+|\/+$/g, '');   // carpeta que contiene las de clientes
const GRAPH = 'https://graph.microsoft.com/v1.0';
const TROZO = 327680 * 16;                                    // 5 MB (múltiplo de 320 KiB, exigido por Graph)

const configurado = () => !!(TENANT && CLIENT_ID && CLIENT_SECRET && USUARIO);

let token = null;
let tokenVence = 0;

async function obtenerToken() {
  if (token && Date.now() < tokenVence - 60000) return token;
  const r = await fetch(`https://login.microsoftonline.com/${encodeURIComponent(TENANT)}/oauth2/v2.0/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: CLIENT_ID, client_secret: CLIENT_SECRET, grant_type: 'client_credentials',
      scope: 'https://graph.microsoft.com/.default',
    }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error('Microsoft rechazó las credenciales: ' + (j.error_description || r.status).toString().split('\r')[0]);
  token = j.access_token;
  tokenVence = Date.now() + (j.expires_in || 3600) * 1000;
  return token;
}

async function graph(ruta, opciones = {}) {
  const t = await obtenerToken();
  const r = await fetch(ruta.startsWith('http') ? ruta : GRAPH + ruta, {
    ...opciones, headers: { Authorization: 'Bearer ' + t, ...(opciones.headers || {}) },
  });
  return r;
}

const base = () => `/users/${encodeURIComponent(USUARIO)}/drive`;
const segmentos = (ruta) => ruta.split('/').filter(Boolean).map(encodeURIComponent).join('/');

// Nombres válidos para OneDrive: sin \ / : * ? " < > | y sin punto/espacio al final.
function limpiarNombre(s, largo = 120) {
  return String(s || '').replace(/[\\/:*?"<>|\u0000-\u001f]/g, ' ').replace(/\s+/g, ' ').trim().replace(/[. ]+$/, '').slice(0, largo);
}

const normalizar = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');

// ---- carpetas de clientes: se reutiliza la que ya existe (sin importar mayúsculas/tildes/puntuación) ----
let cacheCarpetas = null;
let cacheHasta = 0;

async function listarCarpetas(forzar) {
  if (!forzar && cacheCarpetas && Date.now() < cacheHasta) return cacheCarpetas;
  const ruta = BASE ? `${base()}/root:/${segmentos(BASE)}:/children` : `${base()}/root/children`;
  let url = `${ruta}?$select=name,folder&$top=999`;
  const nombres = [];
  while (url) {
    const r = await graph(url);
    if (r.status === 404) break;                              // la carpeta base aún no existe: se creará al subir
    if (!r.ok) throw new Error('No se pudo leer la carpeta de OneDrive (' + r.status + ')');
    const j = await r.json();
    (j.value || []).forEach((x) => { if (x.folder) nombres.push(x.name); });
    url = j['@odata.nextLink'] || null;
  }
  cacheCarpetas = nombres;
  cacheHasta = Date.now() + 5 * 60 * 1000;
  return nombres;
}

async function carpetaDeCliente(cliente) {
  const limpio = limpiarNombre(cliente) || 'Sin identificar';
  const clave = normalizar(limpio);
  for (const forzar of [false, true]) {
    const hallada = (await listarCarpetas(forzar)).find((n) => normalizar(n) === clave);
    if (hallada) return hallada;
    if (cacheCarpetas && cacheCarpetas.includes(limpio)) return limpio;
  }
  cacheCarpetas = null;                                       // la carpeta nueva se creará al subir
  return limpio;
}

// Sube el archivo; si ya existe uno con ese nombre OneDrive lo renombra (MF-001 1.pdf) en vez de pisarlo.
async function subir(cliente, nombreArchivo, buffer, mimetype) {
  if (!configurado()) throw new Error('OneDrive no está configurado (faltan variables GRAPH_* en .env)');
  const carpeta = await carpetaDeCliente(cliente);
  const ruta = [BASE, carpeta, limpiarNombre(nombreArchivo, 150)].filter(Boolean).join('/');
  const conflicto = '@microsoft.graph.conflictBehavior=rename';
  let item;
  if (buffer.length < 4 * 1024 * 1024) {
    const r = await graph(`${base()}/root:/${segmentos(ruta)}:/content?${conflicto}`, {
      method: 'PUT', headers: { 'Content-Type': mimetype || 'application/octet-stream' }, body: buffer,
    });
    if (!r.ok) throw new Error('OneDrive respondió ' + r.status + ': ' + (await r.text()).slice(0, 150));
    item = await r.json();
  } else {
    const s = await graph(`${base()}/root:/${segmentos(ruta)}:/createUploadSession`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item: { '@microsoft.graph.conflictBehavior': 'rename' } }),
    });
    if (!s.ok) throw new Error('OneDrive no abrió la subida (' + s.status + ')');
    const { uploadUrl } = await s.json();
    for (let ini = 0; ini < buffer.length; ini += TROZO) {
      const fin = Math.min(ini + TROZO, buffer.length);
      const r = await fetch(uploadUrl, {                      // la URL de sesión ya trae su autorización
        method: 'PUT',
        headers: { 'Content-Length': String(fin - ini), 'Content-Range': `bytes ${ini}-${fin - 1}/${buffer.length}` },
        body: buffer.subarray(ini, fin),
      });
      if (!r.ok && r.status !== 202) throw new Error('Falló la subida a OneDrive (' + r.status + ')');
      if (fin === buffer.length) item = await r.json();
    }
  }
  cacheCarpetas = null;
  return { nombre: item.name, url: item.webUrl, carpeta };
}

// Prueba de conexión: credenciales, lectura de la carpeta base y una subida de prueba (que se borra).
async function probar() {
  if (!configurado()) throw new Error('Faltan variables GRAPH_* en .env (GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_USER)');
  const pasos = [];
  await obtenerToken();
  pasos.push('1/4 Microsoft aceptó las credenciales');
  const carpetas = await listarCarpetas(true);
  pasos.push('2/4 Carpeta base «' + (BASE || '(raíz del OneDrive)') + '»: ' + (carpetas.length
    ? carpetas.length + ' carpeta(s) de clientes encontradas, p. ej. ' + carpetas.slice(0, 3).join(', ')
    : 'vacía o inexistente (se creará al subir el primer archivo; revisa que el nombre sea el correcto)'));
  const r = await subir('_prueba_ccgestion', 'prueba.txt', Buffer.from('prueba de conexión ccgestion'), 'text/plain');
  pasos.push('3/4 Subida de prueba correcta: ' + r.url);
  const ruta = [BASE, '_prueba_ccgestion'].filter(Boolean).join('/');
  const borrado = await graph(base() + '/root:/' + segmentos(ruta), { method: 'DELETE' });
  pasos.push(borrado.ok ? '4/4 Carpeta de prueba borrada' : '4/4 No se pudo borrar la carpeta de prueba: bórrala a mano (_prueba_ccgestion)');
  return pasos;
}

module.exports = { configurado, subir, limpiarNombre, probar };
