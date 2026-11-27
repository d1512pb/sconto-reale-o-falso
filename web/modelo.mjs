// Sconto v3 · comparador de precio, predicción del modelo y tarjeta del modelo.
// Todo se calcula con los datos del corte; funciona sin conexión si la ficha ya se abrió.

export const VERSION_MODELO = 'sconto-modelo-app-v1';
export const ATIPICO = 0.5;

export async function cargarModelo() {
  try {
    const r = await fetch('modelo.json', {cache: 'no-cache', signal: AbortSignal.timeout(15000)});
    if (!r.ok) throw Error('sin modelo');
    const m = await r.json();
    return m?.version === VERSION_MODELO ? m : null;
  } catch {
    try {
      const copia = await caches.match(new URL('modelo.json', location.href.split('#')[0]).href);
      const m = copia && await copia.json();
      return m?.version === VERSION_MODELO ? m : null;
    } catch { return null; }
  }
}

function cuantil(valores, q) {
  const v = [...valores].sort((a, b) => a - b);
  if (!v.length) return NaN;
  const pos = (v.length - 1) * q, i = Math.floor(pos), f = pos - i;
  return v[i] + (i + 1 < v.length ? f * (v[i + 1] - v[i]) : 0);
}

// Referencia del producto: mínimo multitienda diario dentro de la base del evento actual.
export function referenciaProducto(ficha, producto, evento) {
  const s = ficha?.series?.find(x => x.producto_canonico_id === producto && x.contexto === 'minimo_multitienda');
  if (!s) return null;
  const ref = ficha.referencias?.find(r => r.serie_id === s.serie_id && r.evento_id === evento?.evento_id);
  const puntos = (ficha.precios_diarios || []).filter(p => p.serie_id === s.serie_id && Number.isFinite(p.precio_mediano))
    .sort((a, b) => a.fecha_precio.localeCompare(b.fecha_precio));
  const base = puntos.filter(p => evento && p.fecha_precio >= evento.base_inicio && p.fecha_precio <= evento.base_fin);
  const ultimo = puntos.at(-1);
  // Precios por debajo de la mitad de la mediana son atípicos (0.6 % de los días): casi siempre otro producto o un error de captura.
  const mediana = ref?.mediana_base, validos = Number.isFinite(mediana) ? puntos.filter(p => p.precio_mediano >= ATIPICO * mediana) : puntos;
  return {serie: s, ref, puntos, base, atipicos: puntos.length - validos.length,
    minimo: validos.length ? Math.min(...validos.map(p => p.precio_mediano)) : NaN,
    ultimo: ultimo ? {fecha: ultimo.fecha_precio, precio: ultimo.precio_mediano} : null};
}

// Misma regla que la app y el notebook: ahorro >= umbral y precio <= P25 (favorable); simétrico para alto.
export function evaluarPrecio(precio, contexto, reglas = {}) {
  const umbral = reglas.umbral_pct ?? 5, minFechas = reglas.min_fechas_base ?? 4, minAmplitud = reglas.min_amplitud_dias ?? 21;
  if (!Number.isFinite(precio) || precio <= 0) return {estado: 'invalido', motivo: 'Escribe un precio mayor que cero.'};
  const ref = contexto?.ref;
  const base = contexto?.base?.map(p => p.precio_mediano) || [];
  if (!ref || !ref.cobertura_base || !ref.base_cerrada || (ref.n_fechas_base ?? base.length) < minFechas || (ref.amplitud_base_dias ?? 0) < minAmplitud) {
    return {estado: 'evidencia_insuficiente', precio,
      motivo: `Este producto no tiene una base comparable: se necesitan al menos ${minFechas} días con precio en ${minAmplitud} días o más.`};
  }
  const mediana = ref.mediana_base, p25 = ref.p25_base ?? cuantil(base, .25), p75 = ref.p75_base ?? cuantil(base, .75);
  const ahorro = 100 * (1 - precio / mediana);
  const estado = ahorro >= umbral && precio <= p25 ? 'precio_favorable'
    : ahorro <= -umbral && precio >= p75 ? 'precio_alto' : 'sin_senal_clara';
  const masBaratoQue = base.length ? 100 * base.filter(v => v > precio).length / base.length : null;
  const masCaroQue = base.length ? 100 * base.filter(v => v < precio).length / base.length : null;
  return {estado, precio, ahorro, mediana, p25, p75, umbral, masBaratoQue, masCaroQue,
    minimo: contexto.minimo, atipicos: contexto.atipicos || 0, ultimo: contexto.ultimo, n_base: ref.n_fechas_base, base_inicio: ref.base_inicio, base_fin: ref.base_fin};
}

export function textoEvaluacion(r, money) {
  if (r.estado === 'invalido' || r.estado === 'evidencia_insuficiente') return [r.motivo];
  const lineas = [];
  const dif = Math.abs(r.ahorro).toFixed(1);
  lineas.push(`${r.ahorro >= 0 ? dif + '% por debajo' : dif + '% por encima'} de la mediana habitual (${money(r.mediana)}, del ${r.base_inicio} al ${r.base_fin}).`);
  if (r.estado === 'precio_favorable') lineas.push(`Además está en el cuarto más barato de los días observados (P25 = ${money(r.p25)}).`);
  else if (r.estado === 'precio_alto') lineas.push(`Además está en el cuarto más caro de los días observados (P75 = ${money(r.p75)}).`);
  else if (r.ahorro >= r.umbral) lineas.push(`Ahorra al menos ${r.umbral}%, pero no baja del cuartil inferior (${money(r.p25)}): no lo distinguimos de una variación normal.`);
  else lineas.push(`La diferencia es menor a ${r.umbral}%: en semanas normales los precios se mueven así sin que haya oferta.`);
  if (r.masBaratoQue !== null) lineas.push(r.masBaratoQue >= r.masCaroQue
    ? `Es más barato que el ${Math.round(r.masBaratoQue)}% de los ${r.n_base} días de la base.`
    : `Es más caro que el ${Math.round(r.masCaroQue)}% de los ${r.n_base} días de la base.`);
  if (Number.isFinite(r.minimo)) lineas.push(`Mínimo histórico observado: ${money(r.minimo)}${r.atipicos ? ` (omitimos ${r.atipicos} ${r.atipicos === 1 ? 'día' : 'días'} con precios atípicos, menores a la mitad de la mediana)` : ''}${r.ultimo ? ` · último registro ${money(r.ultimo.precio)} el ${r.ultimo.fecha}` : ''}.`);
  return lineas;
}

export function prediccionProducto(modelo, id) {
  return modelo?.predicciones?.[id] || null;
}
