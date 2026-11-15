import test from 'node:test';
import assert from 'node:assert/strict';
import {baseAPI, buscarSucursales, consultarProducto, registroHistorico, vistaOferta} from '../web/api.mjs';

const origen = 'https://sconto.example';
const ahora = Date.parse('2026-11-14T20:00:00Z');
const oferta = {producto_id:'P1', offer_id:'O1', canal:'en_linea', moneda:'MXN', precio:900,
  costo_total_confirmado:950, precision_temporal:'instante', observed_at:'2026-11-14T19:40:00.001Z',
  fetched_at_utc:'2026-11-14T19:41:00Z', decision:{estado:'precio_favorable', motivos:[], ahorro_pct:10,
    vigente_hasta_utc:'2026-11-14T21:40:00Z', referencia:{mediana:1055.56}}};
const json = datos => Response.json({version:'sconto-api-v1', ...datos});

test('Configura origen HTTPS o loopback explícito sin credenciales', () => {
  assert.equal(baseAPI('/', `${origen}/sconto/`), origen);
  assert.equal(baseAPI('https://api.example', `${origen}/sconto/`), 'https://api.example');
  assert.equal(baseAPI('http://127.0.0.1:8000', 'http://127.0.0.1:8080/'), 'http://127.0.0.1:8000');
  for (const url of ['javascript:alert(1)', 'http://api.example', 'https://user@api.example', 'https://api.example/v1', 'http://127.0.0.1:8000']) {
    assert.equal(baseAPI(url, `${origen}/sconto/`), null);
  }
});

test('Pide una versión actual sin caché y conserva la identidad de la ficha', async () => {
  let veces = 0;
  const fetcher = async (url, opciones) => {
    assert.equal(url, `${origen}/v1/products/P1/offers?limit=30`);
    assert.equal(opciones.cache, 'no-store');
    assert.equal(opciones.credentials, 'omit');
    return json({producto_id:'P1', ofertas:[{...oferta, precio:900 - veces++}, {...oferta, producto_id:'OTRO'}, {...oferta, canal:'tienda_fisica'}]});
  };
  assert.equal((await consultarProducto(origen, 'P1', {fetcher})).ofertas[0].precio, 900);
  const resultado = await consultarProducto(origen, 'P1', {fetcher});
  assert.equal(resultado.ofertas.length, 1);
  assert.equal(resultado.ofertas[0].precio, 899);
});

test('Bloquea el indicador al vencer y mantiene observación y descarga como fechas diferentes', () => {
  const actual = vistaOferta(oferta, ahora);
  assert.equal(actual.estado, 'precio_favorable');
  assert.equal(actual.total, 950);
  assert.match(actual.fecha, /hace 19 min/);
  assert.notEqual(actual.consultado, actual.fecha);
  const vencida = vistaOferta(oferta, Date.parse('2026-11-14T21:40:00Z'));
  assert.equal(vencida.estado, 'evidencia_insuficiente');
  assert.ok(vencida.motivos.includes('dato_vencido'));
  assert.equal(vencida.ahorro, null);
  assert.equal(vistaOferta({...oferta, precision_temporal:'dia'}, ahora).estado, 'evidencia_insuficiente');
  assert.equal(vistaOferta({...oferta, observed_at:'2026-11-14T19:40:00'}, ahora).estado, 'evidencia_insuficiente');
  assert.equal(registroHistorico({fecha_precio:'2026-11-14', indicador:'precio_favorable'}, '2026-11-14').indicador, 'evidencia_insuficiente');
});

test('El fallo de API, la ficha inconsistente y la desconexión no crean ofertas', async () => {
  const escenarios = [async () => new Response('', {status:503}), async () => json({producto_id:'Otro', ofertas:[]}),
    async () => { throw new TypeError('Conexión cerrada'); }];
  for (const fetcher of escenarios) {
    assert.deepEqual(await consultarProducto(origen, 'P1', {fetcher}), {estado:'error', ofertas:[], historia:[]});
  }
  assert.deepEqual(await consultarProducto(origen, 'P1', {enLinea:false, fetcher:async () => assert.fail()}),
    {estado:'sin_conexion', ofertas:[], historia:[]});
});

test('Consulta física explícita con IDs y fecha separados de la ficha online', async () => {
  const id = 'PROFECO-BF26-35251';
  const productos = await buscarSucursales(origen, '82XQ0009LM', {fetcher:async url => {
    assert.match(url, /canal=tienda_fisica/);
    return json({productos:[{producto_id:id, nombre:'Lenovo'}, {producto_id:'P1', nombre:'Otro'}]});
  }});
  assert.equal(productos.length, 1);
  const consulta = await consultarProducto(origen, id, {fetcher:async url => {
    assert.match(url, /PROFECO-BF26-35251\/history/);
    return json({producto_id:id, precios_diarios:[{fecha_precio:'2026-11-13', precio:7000, moneda:'MXN', canal:'tienda_fisica'},
      {fecha_precio:'2026-11-13', precio:7000, moneda:'MXN', canal:'en_linea'}]});
  }});
  assert.equal(consulta.ofertas.length, 0);
  assert.equal(consulta.historia.length, 1);
});
