import test from 'node:test';
import assert from 'node:assert/strict';
import {fechaMexico, edadDias, ofertaVigente, ordenarOfertas, enlaceSeguro} from '../web/motor.mjs';

const oferta = {obs_id:'A', precio:900, fecha_precio:'2026-11-07', moneda:'MXN', identidad_oferta:'compatible_texto', indicador:'precio_favorable', ahorro_referencia_pct:10, brecha_pp:null};
test('La vigencia usa el día de México y vence también sin conexión', () => {
  assert.equal(fechaMexico(new Date('2026-11-08T05:59:00Z')), '2026-11-07');
  assert.equal(fechaMexico(new Date('2026-11-08T06:01:00Z')), '2026-11-08');
  assert.equal(ofertaVigente(oferta, '2026-11-08').indicador, 'precio_favorable');
  for (const fecha of ['2026-11-06', '2026-11-09', 'invalida']) {
    const o = ofertaVigente(oferta, fecha);
    assert.equal(o.indicador, 'evidencia_insuficiente');
    assert.equal(o.ahorro_referencia_pct, null);
    assert.equal(o.brecha_pp, null);
    assert.equal(o.comparable, false);
  }
  assert.equal(edadDias('2026-02-31', '2026-03-01'), null);
});
test('No promociona ofertas de variante o moneda diferente', () => {
  for (const cambio of [{identidad_oferta:'conflicto'}, {identidad_oferta:'pendiente'}, {moneda:'USD'}, {precio:0}]) {
    assert.equal(ofertaVigente({...oferta, ...cambio}, '2026-11-07').indicador, 'evidencia_insuficiente');
  }
});
test('Ordena evidencia reciente antes que un precio antiguo más bajo', () => {
  const filas = [ {...oferta, obs_id:'B', precio:1, fecha_precio:'2026-11-01'}, oferta, {...oferta, obs_id:'C', precio:2, identidad_oferta:'conflicto'} ];
  assert.deepEqual(ordenarOfertas(filas, '2026-11-07').map(o => o.obs_id), ['A','B','C']);
});
test('Sólo se permiten enlaces web a las tiendas', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,prueba', '/relativo', 'file:///C:/secreto']) assert.equal(enlaceSeguro(url), null);
  assert.equal(enlaceSeguro('https://www.sears.com.mx/producto/3868552/'), 'https://www.sears.com.mx/producto/3868552/');
});
