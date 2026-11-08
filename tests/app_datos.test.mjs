import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {cargarDatos, cargarDetalle} from '../web/datos.mjs';

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

test('Las fichas verificadas no mezclan productos ni cortes y el almacenamiento está limitado', async () => {
  globalThis.location = {href:'https://prueba.example/sconto/#/producto/P0'};
  const almacen = new Map(), respuestas = new Map();
  globalThis.caches = {open:async () => ({match:async k => almacen.get(k)?.clone(), put:async (k,r) => almacen.set(k,r), keys:async () => [...almacen.keys()], delete:async k => almacen.delete(k)})};
  const catalogo = {version:'sconto-app-v2', fecha_corte:'2026-11-07', detalles:{}};
  for (let i=0;i<42;i++) {
    const id='P'+i, contenido=JSON.stringify({version:'sconto-producto-v1',producto_canonico_id:id,fecha_corte:catalogo.fecha_corte,ofertas:[],precios_diarios:[]});
    const hash=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(contenido))).toString('hex');
    const archivo='producto.'+hash.slice(0,16)+'.json'; catalogo.detalles[id]={archivo,sha256:hash}; respuestas.set(archivo,contenido);
  }
  globalThis.fetch = async url => new Response(respuestas.get(url));
  for (let i=0;i<42;i++) assert.equal((await cargarDetalle(catalogo,'P'+i)).producto_canonico_id,'P'+i);
  assert.equal(almacen.size,40);
  globalThis.fetch=async () => {throw Error('Sin red');};
  assert.equal((await cargarDetalle(catalogo,'P41')).producto_canonico_id,'P41');
  await assert.rejects(cargarDetalle(catalogo,'P0'), /Conéctate/);
  await assert.rejects(cargarDetalle({...catalogo,fecha_corte:'2026-11-08'},'P41'), /Conéctate/);
  const cambiado={...catalogo,detalles:{...catalogo.detalles,P0:catalogo.detalles.P41}};
  await assert.rejects(cargarDetalle(cambiado,'P0'), /Conéctate/);
});
