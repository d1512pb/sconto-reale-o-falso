export const normalizar = texto => String(texto ?? '').normalize('NFKD').replace(/\p{M}/gu, '').toUpperCase().replace(/\s+/g, ' ').trim();

export function atributos(texto) {
  texto = normalizar(texto).replace(/AIRPODS\s*([234])\s*PRO/g, 'AIRPODS PRO $1').replace(/AIRPODS\s*PRO\s*\(?\s*([234])(?:RA|DA|A|ER)\.?/g, 'AIRPODS PRO $1 ');
  const resultado = {}, ram = /\b(\d+)\s*GB\s*(?:DE\s*)?RAM\b/;
  const patrones = {ram, disco: /\b(\d+)\s*(GB|TB)\s*(?:DE\s*)?(?:SSD|HDD|EMMC)\b/, cpu: /\b(I[3579](?:-\d{4,5}[A-Z]*)?|RYZEN\s*[3579])\b/, airpods: /\bAIRPODS\s*(PRO\s*)?([234])\b/, color: /\b(AZUL|NEGRO|BLANCO|GRIS|PLATA|ROSA)\b/};
  for (const [clave, patron] of Object.entries(patrones)) {
    const m = texto.match(patron);
    if (m) resultado[clave] = clave === 'disco' ? String(Number(m[1]) * (m[2] === 'TB' ? 1024 : 1)) : clave === 'airpods' ? (m[1] ? 'PRO' : 'NORMAL') + m[2] : m[1].replaceAll(' ', '');
  }
  resultado.paquete = /\b(?:PAQUETE|COMBO|HERVIDOR|CAFETERA)\b/.test(texto);
  const iphone = texto.match(/\bIPHONE\s*(\d{1,2}|SE)\s*(PRO\s*MAX|PRO|PLUS|MINI|AIR|E)?\b/);
  const galaxy = texto.match(/\bGALAXY\s*(TAB\s*)?([AS]\d{1,3})\s*(ULTRA|PLUS|FE\+?|LITE|\+)?/);
  const ipad = texto.match(/\bIPAD\s+(AIR|PRO|MINI)\b/);
  if (iphone) resultado.iphone = iphone[1] + (iphone[2] || '').replaceAll(' ', '');
  if (galaxy) resultado.galaxy = (galaxy[1] ? 'TAB' : '') + galaxy[2] + (galaxy[3] || '').replace('+', 'PLUS');
  if (ipad) resultado.ipad_tipo = ipad[1];
  if (!resultado.disco) {
    const capacidades = [...texto.replace(new RegExp(ram, 'g'), '').matchAll(/\b(\d+)\s*(GB|TB)\b/g)].map(m => Number(m[1]) * (m[2] === 'TB' ? 1024 : 1)).filter(n => n >= 32);
    if (capacidades.length === 1) resultado.disco = String(capacidades[0]);
  }
  return resultado;
}

function conflicto(a, b) {
  return Object.keys(a).some(k => k in b && a[k] !== b[k] && !(k === 'cpu' && (a[k].startsWith(b[k]) || b[k].startsWith(a[k]))));
}

// SequenceMatcher sin autojunk: los tokens de producto son cortos.
function parecido(a, b) {
  const pendientes = [[0, a.length, 0, b.length]];
  let iguales = 0;
  while (pendientes.length) {
    const [a0, a1, b0, b1] = pendientes.pop();
    let inicioA = a0, inicioB = b0, tam = 0, anteriores = new Map();
    for (let i = a0; i < a1; i++) {
      const siguientes = new Map();
      for (let j = b0; j < b1; j++) if (a[i] === b[j]) {
        const n = (anteriores.get(j - 1) || 0) + 1;
        siguientes.set(j, n);
        if (n > tam) { inicioA = i - n + 1; inicioB = j - n + 1; tam = n; }
      }
      anteriores = siguientes;
    }
    if (tam) {
      iguales += tam;
      if (a0 < inicioA && b0 < inicioB) pendientes.push([a0, inicioA, b0, inicioB]);
      if (inicioA + tam < a1 && inicioB + tam < b1) pendientes.push([inicioA + tam, a1, inicioB + tam, b1]);
    }
  }
  return 2 * iguales / (a.length + b.length || 1);
}

export function buscar(consulta, productos, indice, limite = productos.length) {
  const texto = normalizar(consulta).slice(0, 200);
  if (texto.length < 3) return [];
  const vector = new Map(), palabras = texto.split(' ');
  for (const palabra of palabras) {
    const w = ' ' + palabra + ' ';
    for (let n = 3; n <= 5; n++) {
      for (let i = 0; i <= Math.max(0, w.length - n); i++) {
        const j = indice.vocabulario[w.slice(i, i + n)];
        if (j !== undefined) vector.set(j, (vector.get(j) || 0) + 1);
      }
      if (w.length <= n) break;
    }
  }
  let norma = 0;
  for (const [j, n] of vector) { const v = n * indice.idf[j]; vector.set(j, v); norma += v * v; }
  norma = Math.sqrt(norma);
  if (!norma) return [];
  const especificacion = atributos(texto), tokens = (texto.match(/[A-Z0-9]+/g) || []).filter(p => p.length >= 3);
  const porId = new Map(productos.map(p => [p.producto_canonico_id, p])), m = indice.matriz_csr, resultados = [];
  indice.ids.forEach((id, fila) => {
    const p = porId.get(id);
    if (!p || conflicto(especificacion, atributos(p.nombre))) return;
    const nombre = normalizar(p.nombre).match(/[A-Z0-9]+/g) || [];
    if (!tokens.some(t => nombre.includes(t) || (t.length >= 4 && nombre.some(n => parecido(t, n) >= .85)))) return;
    let similitud = 0;
    for (let j = m.indptr[fila]; j < m.indptr[fila + 1]; j++) similitud += (vector.get(m.indices[j]) || 0) / norma * m.data[j];
    if (similitud >= .15) resultados.push({...p, similitud});
  });
  return resultados.sort((a, b) => b.similitud - a.similitud || a.producto_canonico_id.localeCompare(b.producto_canonico_id)).slice(0, limite);
}

export function fechaMexico(ahora = new Date()) {
  const partes = new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(ahora);
  const dato = tipo => partes.find(p => p.type === tipo).value;
  return `${dato('year')}-${dato('month')}-${dato('day')}`;
}

export function edadDias(fecha, hoy) {
  const valido = valor => /^\d{4}-\d{2}-\d{2}$/.test(valor || '') && Number.isFinite(Date.parse(valor)) && new Date(valor).toISOString().slice(0, 10) === valor;
  return valido(fecha) && valido(hoy) ? (Date.parse(hoy) - Date.parse(fecha)) / 86400000 : null;
}

export function ofertaVigente(oferta, hoy = fechaMexico()) {
  const edad = edadDias(oferta.fecha_precio, hoy), vigente = edad !== null && edad >= 0 && edad <= 1;
  const comparable = vigente && oferta.identidad_oferta === 'compatible_texto' && oferta.moneda === 'MXN' && Number.isFinite(oferta.precio) && oferta.precio > 0;
  return {...oferta, edad, vigente, comparable,
    indicador: comparable ? oferta.indicador : 'evidencia_insuficiente',
    ahorro_referencia_pct: comparable ? oferta.ahorro_referencia_pct : null,
    brecha_pp: comparable ? oferta.brecha_pp : null};
}

export function ordenarOfertas(ofertas, hoy = fechaMexico()) {
  const prioridad = o => o.comparable ? 0 : o.vigente && o.identidad_oferta !== 'conflicto' ? 1 : o.identidad_oferta === 'conflicto' ? 3 : 2;
  return ofertas.map(o => ofertaVigente(o, hoy)).sort((a, b) => prioridad(a) - prioridad(b) || a.precio - b.precio || a.obs_id.localeCompare(b.obs_id));
}

export function enlaceSeguro(url) {
  try { const u = new URL(url); return ['https:', 'http:'].includes(u.protocol) ? u.href : null; } catch { return null; }
}
