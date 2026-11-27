// Captura un archivo HTML local a PNG con Chrome sin ventana. Uso: node scripts/capturar_html.mjs entrada.html salida.png 1600 900
import {spawn} from 'node:child_process';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const [entrada, salida, ancho = '1600', alto = '900'] = process.argv.slice(2);
const PUERTO = 9334, espera = ms => new Promise(r => setTimeout(r, ms));
const perfil = mkdtempSync(join(tmpdir(), 'sconto-html-'));
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', ['--headless=new', '--disable-gpu', '--hide-scrollbars',
  `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`, 'about:blank'], {stdio: 'ignore'});
let url;
for (let i = 0; i < 60 && !url; i++) {
  try { url = (await (await fetch(`http://127.0.0.1:${PUERTO}/json`)).json()).find(t => t.type === 'page')?.webSocketDebuggerUrl; } catch { /* arranca */ }
  if (!url) await espera(500);
}
const ws = new WebSocket(url); await new Promise(r => ws.addEventListener('open', r, {once: true}));
let id = 0; const pend = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
const cdp = (method, params = {}) => new Promise(r => { const n = ++id; pend.set(n, r); ws.send(JSON.stringify({id: n, method, params})); });
await cdp('Emulation.setDeviceMetricsOverride', {width: Number(ancho), height: Number(alto), deviceScaleFactor: 2, mobile: false});
await cdp('Page.navigate', {url: pathToFileURL(resolve(entrada)).href});
await espera(1500);
const {result} = await cdp('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
writeFileSync(resolve(salida), Buffer.from(result.data, 'base64'));
ws.close(); chrome.kill(); await espera(500);
try { rmSync(perfil, {recursive: true, force: true}); } catch { /* temporal */ }
console.log('ok', salida);
