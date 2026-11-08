import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {cargarDatos} from '../web/datos.mjs';

test('Conserva una copia íntegra, rechaza descargas alteradas y admite volver a abrir sin red', async () => {
  if (!globalThis.crypto) Object.defineProperty(globalThis, 'crypto', {value:webcrypto});
  globalThis.location = {href:'https://prueba.example/sconto/#/producto/P1'};
  const almacen = new Map();
  globalThis.caches = {open: async () => ({put:async (k,r) => almacen.set(k,r), match:async k => almacen.get(k)?.clone()})};
  const bytes = JSON.stringify({version:'sconto-app-v1',fecha_corte:'2026-11-07',productos:[],ofertas:[],busqueda:{}});
  const hash = Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(bytes))).toString('hex');
  const snapshot = {archivo:'datos.'+hash.slice(0,16)+'.json',sha256:hash};
  globalThis.fetch = async url => new Response(url==='snapshot.json'?JSON.stringify(snapshot):bytes);
  const primera = await cargarDatos();
  assert.equal(primera.copia, false); assert.equal(primera.guardado,true);
  globalThis.fetch = async url => new Response(url==='snapshot.json'?JSON.stringify(snapshot):'alterado');
  const alterada = await cargarDatos();
  assert.equal(alterada.copia,true); assert.equal(alterada.datos.fecha_corte,'2026-11-07');
  globalThis.fetch = async () => {throw Error('Sin red');};
  assert.equal((await cargarDatos()).copia,true);
  almacen.clear();
  await assert.rejects(cargarDatos(),/primera consulta necesita conexión/);
});
