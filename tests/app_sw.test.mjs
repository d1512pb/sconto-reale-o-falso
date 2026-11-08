import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('Una actualización descarga recursos nuevos aunque exista una copia HTTP antigua', async () => {
  const eventos = new Map(), almacen = new Map();
  const scope = 'https://ejemplo.test/sconto/';
  const cache = {async addAll(peticiones) {
    for (const p of peticiones) {
      const url = typeof p === 'string' ? new URL(p, scope).href : p.url;
      almacen.set(url, p.cache === 'reload' ? 'version nueva' : 'copia HTTP antigua');
    }
  }};
  const contexto = vm.createContext({URL, Request,
    caches: {async open() {return cache;}},
    self: {registration: {scope}, addEventListener(nombre, fn) {eventos.set(nombre, fn);}}
  });
  vm.runInContext(await readFile(new URL('../web/sw.js', import.meta.url), 'utf8'), contexto);
  let instalacion;
  eventos.get('install')({waitUntil(promesa) {instalacion = promesa;}});
  await instalacion;
  assert.equal(almacen.get(scope + 'motor.mjs'), 'version nueva');
  assert.equal(almacen.get(scope + 'index.html'), 'version nueva');
  assert.ok(almacen.size > 2);
});
