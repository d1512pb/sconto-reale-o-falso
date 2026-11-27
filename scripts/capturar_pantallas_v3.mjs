// Capturas de la app v3 esperando a que los datos carguen (Chrome DevTools Protocol, sin dependencias).
// Uso: node scripts/capturar_pantallas_v3.mjs http://localhost:8787 "../../periodo 3/capturas"
import {spawn} from 'node:child_process';
import {mkdirSync, mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE = (process.argv[2] || 'http://localhost:8787').replace(/\/$/, '');
const SALIDA = resolve(process.argv[3] || 'capturas');
const PUERTO = 9333;
const listo = `(() => { const e = document.getElementById('estado-datos'); return !!e && /Corte/.test(e.textContent); })()`;
const CAPTURAS = [
  // nombre, ruta, ancho, alto, escala, condición extra, desplazamiento a un elemento
  ['01_inicio_escritorio', '/', 1366, 1000, 1, listo],
  ['02_filtro_prediccion_escritorio', '/#/?categoria=modelo', 1366, 1000, 1, `${listo} && document.querySelectorAll('.model-tag').length > 0`, 'filtros-activos'],
  ['03_precio_escritorio', '/#/producto/P4-4054?precio=5499', 1366, 1100, 1, `${listo} && document.querySelector('.meter') !== null`, 'evaluador'],
  ['04_prediccion_escritorio', '/#/producto/P4-4054?precio=5499', 1366, 1000, 1, `${listo} && !document.getElementById('prediccion').hidden`, 'prediccion'],
  ['05_historial_escritorio', '/#/producto/P4-4054', 1366, 1000, 1, `${listo} && document.querySelector('#grafico svg') !== null`, 'historia'],
  ['06_tarjeta_modelo_escritorio', '/#/modelo', 1366, 2600, 1, `${listo} && document.querySelector('#contenido-modelo .metric-table') !== null`],
  ['07_api_docs_escritorio', '/docs', 1366, 1150, 1, `document.querySelector('.opblock') !== null`],
  ['08_inicio_celular', '/', 412, 915, 2, listo],
  ['09_precio_celular', '/#/producto/P4-2467?precio=799', 412, 915, 2, `${listo} && document.querySelector('.meter') !== null`, 'evaluador'],
  ['10_prediccion_celular', '/#/producto/P4-2467?precio=799', 412, 915, 2, `${listo} && !document.getElementById('prediccion').hidden`, 'prediccion'],
];

const espera = ms => new Promise(r => setTimeout(r, ms));
mkdirSync(SALIDA, {recursive: true});
const perfil = mkdtempSync(join(tmpdir(), 'sconto-cdp-'));
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
  `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`, 'about:blank'], {stdio: 'ignore'});

async function objetivo() {
  for (let i = 0; i < 60; i++) {
    try {
      const lista = await (await fetch(`http://127.0.0.1:${PUERTO}/json`)).json();
      const pagina = lista.find(t => t.type === 'page');
      if (pagina) return pagina.webSocketDebuggerUrl;
    } catch { /* Chrome todavía arranca */ }
    await espera(500);
  }
  throw Error('Chrome no respondió');
}

const ws = new WebSocket(await objetivo());
await new Promise(r => ws.addEventListener('open', r, {once: true}));
let id = 0; const pendientes = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && pendientes.has(m.id)) { pendientes.get(m.id)(m); pendientes.delete(m.id); } });
const cdp = (method, params = {}) => new Promise(r => { const n = ++id; pendientes.set(n, r); ws.send(JSON.stringify({id: n, method, params})); });
const evaluar = async expr => (await cdp('Runtime.evaluate', {expression: expr, returnByValue: true, awaitPromise: true})).result?.result?.value;

await cdp('Page.enable'); await cdp('Runtime.enable');
for (const [nombre, ruta, ancho, alto, escala, condicion, ancla] of CAPTURAS) {
  await cdp('Emulation.setDeviceMetricsOverride', {width: ancho, height: alto, deviceScaleFactor: escala, mobile: ancho < 600});
  await cdp('Page.navigate', {url: 'about:blank'}); await espera(300);
  await cdp('Page.navigate', {url: BASE + ruta});
  let ok = false;
  for (let i = 0; i < 120 && !ok; i++) { await espera(500); ok = await evaluar(condicion).catch(() => false); }
  if (ancla) await evaluar(`document.getElementById('${ancla}')?.scrollIntoView({block: 'start', behavior: 'instant'}); true`);
  await espera(1600);  // animaciones de entrada
  const {result} = await cdp('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  writeFileSync(join(SALIDA, `${nombre}.png`), Buffer.from(result.data, 'base64'));
  console.log(nombre, ok ? 'ok' : 'SIN CONDICION');
}
ws.close(); chrome.kill();
await espera(800);
try { rmSync(perfil, {recursive: true, force: true}); } catch { /* perfil temporal */ }
