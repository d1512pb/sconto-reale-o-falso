import {buscar, normalizar, fechaMexico, edadDias, ordenarOfertas, enlaceSeguro} from './motor.mjs';
import {cargarDatos} from './datos.mjs';

const $ = id => document.getElementById(id);
const el = (tag, texto, clase) => {
  const nodo = document.createElement(tag);
  if (texto !== undefined) nodo.textContent = texto;
  if (clase) nodo.className = clase;
  return nodo;
};
const money = (valor, moneda = 'MXN') => new Intl.NumberFormat('es-MX', {style: 'currency', currency: moneda}).format(valor);
const corto = fecha => new Date(fecha + 'T12:00:00Z').toLocaleDateString('es-MX', {day: 'numeric', month: 'short', timeZone: 'UTC'});
const etiquetas = {precio_favorable: 'Precio favorable', precio_alto: 'Precio alto', sin_senal_clara: 'Sin señal clara', evidencia_insuficiente: 'Evidencia insuficiente'};
const tonos = {precio_favorable: 'good', precio_alto: 'high', sin_senal_clara: 'neutral', evidencia_insuficiente: 'missing'};
let datos, carga, cargando = false, ultimoIntento = 0, fechaMostrada = fechaMexico(), recargarTrasActualizacion = false;
let categoria = 'foco', consulta = '', tienda = '', limite = 12, limiteOfertas = 8, anterior = '#/', promptInstalar, registro;
let porProducto = new Map(), ofertasPorProducto = new Map();

function notificar(texto) {
  $('toast').textContent = texto; $('toast').hidden = false;
  clearTimeout(notificar.timer);
  notificar.timer = setTimeout(() => { $('toast').hidden = true; }, 4000);
}
function audifonos(p) { return /AUDIFONOS|AIRPODS|HEADSET|4GAMERS/.test(normalizar(p.nombre)); }
function laptop(p) { return /LAPTOP|COMPUTADORA/.test(normalizar(p.nombre)) || p.familia === 'laptop'; }
function categoriaNombre(p) { return laptop(p) ? 'Laptops' : audifonos(p) ? 'Audífonos' : 'Tecnología'; }
function ilustracion(p) {
  const cont = el('span');
  const dibujo = laptop(p)
    ? '<rect x="28" y="18" width="124" height="76" rx="5"/><path d="M36 27h108v58H36z" fill="currentColor" opacity=".09"/><path d="M18 105h144l-10 9H28z"/><path d="M75 105h30"/>'
    : audifonos(p)
    ? '<path d="M43 69V55a47 47 0 0 1 94 0v14"/><path d="M51 58v-6a39 39 0 0 1 78 0v6"/><rect x="35" y="60" width="24" height="43" rx="10"/><rect x="121" y="60" width="24" height="43" rx="10"/><path d="M59 70v23m62-23v23"/>'
    : '<rect x="36" y="18" width="108" height="82" rx="7"/><path d="M44 27h92v63H44z" fill="currentColor" opacity=".09"/><path d="M72 113h36m-18-13v13"/>';
  cont.innerHTML = '<svg viewBox="0 0 180 125" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + dibujo + '</svg>';
  return cont.firstElementChild;
}
function badge(oferta) {
  return el('span', etiquetas[oferta?.indicador] || 'Evidencia insuficiente', 'badge ' + (tonos[oferta?.indicador] || 'missing'));
}
function ofertasProducto(id) { return ordenarOfertas(ofertasPorProducto.get(id) || [], fechaMexico()); }
function opcionMenor(id) { return ofertasProducto(id).find(o => o.comparable); }
function estadoConexion() {
  if (!datos) return;
  const edad = edadDias(datos.fecha_corte, fechaMexico()), vieja = edad === null || edad < 0 || edad > 1;
  $('estado-datos').textContent = 'Corte ' + corto(datos.fecha_corte) + ' ' + datos.fecha_corte.slice(0, 4) + ' · ' + datos.productos.length + ' productos';
  const mensajes = [];
  if (!navigator.onLine || carga?.copia) mensajes.push('Usas la última copia guardada. No se pudo confirmar una actualización.');
  if (vieja) mensajes.push('Los precios de este corte ya no se consideran recientes. Mostramos su historia sin indicadores de oferta vigente.');
  if (!carga?.guardado) mensajes.push('No se pudo guardar la copia sin conexión en este navegador.');
  $('aviso').textContent = mensajes.join(' ');
  $('aviso').hidden = !mensajes.length;
}
async function actualizar() {
  if (cargando) return;
  cargando = true; ultimoIntento = Date.now(); $('refrescar').disabled = true;
  try {
    carga = await cargarDatos(); datos = carga.datos;
    porProducto = new Map(datos.productos.map(p => [p.producto_canonico_id, p]));
    ofertasPorProducto = new Map();
    for (const o of datos.ofertas) {
      if (!ofertasPorProducto.has(o.producto_canonico_id)) ofertasPorProducto.set(o.producto_canonico_id, []);
      ofertasPorProducto.get(o.producto_canonico_id).push(o);
    }
    $('error').hidden = true; $('busqueda').disabled = false;
    estadoConexion(); ruta(false);
  } catch (error) {
    if (!datos) {
      $('error-texto').textContent = error.message; $('error').hidden = false; $('inicio').hidden = true; $('detalle').hidden = true;
      $('estado-datos').textContent = 'Datos no disponibles';
    } else { notificar('Conservamos la copia anterior. ' + error.message); }
  } finally { cargando = false; $('refrescar').disabled = false; }
}
function hashBusqueda() {
  const q = new URLSearchParams();
  if (consulta) q.set('q', consulta);
  if (categoria !== 'foco') q.set('categoria', categoria);
  if (tienda) q.set('tienda', tienda);
  return '#/' + (q.size ? '?' + q.toString() : '');
}
function guardarBusqueda() { anterior = hashBusqueda(); history.replaceState(null, '', anterior); }
function filtrarProductos() {
  let lista = consulta.trim() ? buscar(consulta, datos.productos, datos.busqueda) : [...datos.productos];
  lista = lista.filter(p => categoria === 'todos' || categoria === 'laptop' && laptop(p) || categoria === 'audifonos' && audifonos(p) || categoria === 'foco' && (laptop(p) || audifonos(p)) && !p.es_paquete);
  if (tienda) lista = lista.filter(p => (ofertasPorProducto.get(p.producto_canonico_id) || []).some(o => normalizar(o.plataforma).toLowerCase() === tienda));
  if (!consulta.trim()) lista.sort((a, b) => Number(!!opcionMenor(b.producto_canonico_id)) - Number(!!opcionMenor(a.producto_canonico_id)) || Number(laptop(b)) - Number(laptop(a)) || a.nombre.localeCompare(b.nombre, 'es'));
  return lista;
}
function renderProductos() {
  $('busqueda').value = consulta; $('tienda').value = tienda;
  for (const b of $('categorias').querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.category === categoria));
  const lista = filtrarProductos();
  $('titulo-resultados').textContent = consulta ? 'Resultados para “' + consulta + '”' : 'Tecnología para tu próxima compra';
  $('conteo').textContent = lista.length + (lista.length === 1 ? ' producto' : ' productos');
  $('productos').replaceChildren(); $('productos').setAttribute('aria-busy', 'false');
  for (const p of lista.slice(0, limite)) {
    const a = el('a', undefined, 'product-card'); a.href = '#/producto/' + encodeURIComponent(p.producto_canonico_id);
    const art = el('div', undefined, 'product-art');
    art.append(el('span', categoriaNombre(p), 'art-label'), ilustracion(p), el('span', '↗', 'art-arrow'));
    const body = el('div', undefined, 'card-body'), mejor = opcionMenor(p.producto_canonico_id);
    const tiendas = new Set((ofertasPorProducto.get(p.producto_canonico_id) || []).map(o => o.plataforma));
    body.append(el('span', p.marca || categoriaNombre(p), 'card-brand'), el('h3', p.nombre),
      el('p', (tiendas.size ? tiendas.size + (tiendas.size === 1 ? ' tienda con registro' : ' tiendas con registro') : 'Sin ofertas por tienda') + (p.es_paquete ? ' · paquete' : ''), 'card-meta'));
    const pie = el('div', undefined, 'card-price'), precio = el('div');
    precio.append(el('small', mejor ? 'Desde · precio reciente' : 'Sin precio comparable reciente'), el('strong', mejor ? money(mejor.precio) : 'Ver historia'));
    pie.append(precio, badge(mejor)); body.append(pie); a.append(art, body); $('productos').append(a);
  }
  $('sin-resultados').hidden = lista.length > 0; $('ver-mas').hidden = lista.length <= limite;
}
function svg(tag, attrs, texto) {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (texto !== undefined) n.textContent = texto;
  return n;
}
function grafico(p) {
  const s = datos.series.find(s => s.producto_canonico_id === p.producto_canonico_id && s.contexto === 'minimo_multitienda');
  const ref = datos.referencias.find(r => r.serie_id === s?.serie_id && r.evento_id === datos.evento_actual);
  const puntos = datos.precios_diarios.filter(r => r.serie_id === s?.serie_id).sort((a, b) => a.fecha_precio.localeCompare(b.fecha_precio));
  $('estadisticas').replaceChildren();
  for (const [titulo, valor, nota] of [
    ['Mediana de la base', ref?.cobertura_base && ref?.base_cerrada ? money(ref.mediana_base) : 'Sin base', 'Referencia histórica'],
    ['Fechas en la base', ref?.n_fechas_base ?? 0, 'Mínimo requerido: 4'],
    ['Amplitud de la base', ref?.amplitud_base_dias != null ? ref.amplitud_base_dias + ' días' : '—', 'Mínimo requerido: 21 días']]) {
    const n = el('div'); n.append(el('small', titulo), el('strong', valor), el('span', nota)); $('estadisticas').append(n);
  }
  $('cobertura').textContent = ref ? 'Base: ' + ref.base_inicio + ' a ' + ref.base_fin + '. Los días sin datos quedan vacíos. El color del evento no implica que ya existan precios en esos días.' : 'Todavía no hay una referencia histórica para este producto.';
  $('grafico').replaceChildren(); $('tabla-historia').replaceChildren();
  if (!puntos.length) { $('grafico').append(el('p', 'Sin días observados para graficar.', 'muted')); return; }
  const evento = datos.ventanas.find(e => e.evento_id === datos.evento_actual);
  const W = Math.max(320, Math.min(700, $('grafico').clientWidth || 700)), H = W < 500 ? 240 : 270, L = W < 500 ? 48 : 62, R = 16, T = 18, B = 34;
  const fechas = puntos.map(p => Date.parse(p.fecha_precio)), precios = puntos.map(p => p.precio_mediano);
  const min = Math.min(...fechas), max = Math.max(...fechas, Date.parse(evento?.fin) || 0, min + 86400000);
  const lo = Math.min(...precios) * .95, hi = Math.max(...precios) * 1.05;
  const x = v => L + (v - min) / (max - min) * (W - L - R), y = v => T + (hi - v) / (hi - lo || 1) * (H - T - B);
  const dibujo = svg('svg', {viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Mínimos diarios observados en MXN; tabla accesible debajo.'});
  if (evento) for (const [inicio, fin, color] of [[evento.base_inicio, evento.base_fin, '#e6eedb'], [evento.evento_inicio, evento.evento_fin, '#cde4d9']]) {
    const a = Math.max(min, Date.parse(inicio)), b = Math.min(max, Date.parse(fin));
    if (b > a) dibujo.append(svg('rect', {x: x(a), y: T, width: x(b) - x(a), height: H - T - B, fill: color}));
  }
  for (let i = 0; i < 4; i++) {
    const v = lo + (hi - lo) * i / 3;
    dibujo.append(svg('line', {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: '#dce3d9'}),
      svg('text', {x: L - 9, y: y(v) + 4, 'text-anchor': 'end', fill: '#617068', 'font-size': 12}, Math.round(v).toLocaleString('es-MX')));
  }
  for (let i = 0; i < 4; i++) {
    const t = min + (max - min) * i / 3;
    dibujo.append(svg('text', {x: x(t), y: H - 8, 'text-anchor': 'middle', fill: '#617068', 'font-size': 12}, corto(new Date(t).toISOString().slice(0, 10))));
  }
  for (const p of puntos) {
    const punto = svg('circle', {cx: x(Date.parse(p.fecha_precio)), cy: y(p.precio_mediano), r: 3.1, fill: '#245d4d', opacity: .8});
    punto.append(svg('title', {}, p.fecha_precio + ': ' + money(p.precio_mediano))); dibujo.append(punto);
  }
  $('grafico').append(dibujo);
  const tabla = el('table'), cabecera = el('tr'); cabecera.append(el('th', 'Fecha'), el('th', 'Mínimo observado'));
  const thead = el('thead'), tbody = el('tbody'); thead.append(cabecera);
  for (const p of [...puntos].reverse()) { const fila = el('tr'); fila.append(el('td', p.fecha_precio), el('td', money(p.precio_mediano))); tbody.append(fila); }
  tabla.append(thead, tbody); $('tabla-historia').append(tabla);
}
function explicacion(o) {
  if (!o.vigente) return 'Dato histórico del ' + o.fecha_precio + '. No se considera una oferta reciente.';
  if (o.identidad_oferta === 'conflicto') return 'La descripción tiene una variante distinta. No la usamos para comparar este producto.';
  if (o.identidad_oferta !== 'compatible_texto') return 'Faltan datos para confirmar que sea la misma variante.';
  if (o.ahorro_referencia_pct == null) return 'Título compatible, pero falta historia suficiente para evaluar este precio.';
  const d = o.ahorro_referencia_pct, contexto = o.contexto_referencia === 'serie_vendedor' ? 'de este vendedor' : 'del mercado';
  return Math.abs(d).toFixed(1) + '% ' + (d >= 0 ? 'por debajo' : 'por encima') + ' de la mediana histórica ' + contexto + '.';
}
function renderOfertas(id) {
  const filtro = $('tienda-ofertas').value;
  const lista = ofertasProducto(id).filter(o => !filtro || normalizar(o.plataforma).toLowerCase() === filtro);
  $('ofertas').replaceChildren();
  for (const [i, o] of lista.slice(0, limiteOfertas).entries()) {
    const art = el('article', undefined, 'offer' + (i === 0 && o.comparable ? ' first' : ''));
    const top = el('div', undefined, 'offer-top'), vendedor = el('div'), precio = el('strong', money(o.precio, o.moneda), 'offer-price');
    vendedor.append(el('div', o.plataforma || 'Tienda', 'offer-store'),
      el('p', 'Vende ' + (o.vendedor_o_cadena || 'vendedor no identificado') + (o.tipo_vendedor === 'tercero' ? ' · tercero' : ''), 'offer-seller'), badge(o));
    precio.append(el('small', o.moneda + ' · precio publicado')); top.append(vendedor, precio);
    const bottom = el('div', undefined, 'offer-bottom');
    bottom.append(el('span', 'Observado ' + o.fecha_precio + (o.vigente ? ' · reciente' : ' · antiguo')));
    const href = enlaceSeguro(o.url);
    if (href) { const a = el('a', 'Ver en tienda ↗'); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.setAttribute('aria-label', 'Ver oferta en ' + o.plataforma + ', vendedor ' + o.vendedor_o_cadena); bottom.append(a); }
    const detalle = el('details'); detalle.append(el('summary', 'Ver descripción y condiciones pendientes'), el('p', o.titulo_oferta || ''), el('p', o.motivo_identidad || 'Identidad pendiente'), el('p', o.condiciones_pendientes));
    art.append(top);
    if (Number.isFinite(o.precio_anterior_anunciado)) {
      const anuncio = el('p', 'Referencia anunciada: ', 'muted');
      anuncio.append(el('s', money(o.precio_anterior_anunciado, o.moneda)));
      if (Number.isFinite(o.pct_descuento_anunciado)) anuncio.append(' · ' + o.pct_descuento_anunciado + '% anunciado');
      art.append(anuncio);
    } else if (Number.isFinite(o.pct_descuento_anunciado)) art.append(el('p', o.pct_descuento_anunciado + '% anunciado', 'muted'));
    if (Number.isFinite(o.brecha_pp)) art.append(el('p', 'Brecha entre anuncio y ahorro histórico: ' + o.brecha_pp.toFixed(1) + ' puntos porcentuales. Es una comparación, no prueba de engaño.', 'muted'));
    art.append(el('p', explicacion(o), 'offer-explanation'), bottom, detalle); $('ofertas').append(art);
  }
  if (!lista.length) $('ofertas').append(el('p', 'No hay ofertas registradas para este producto en la tienda seleccionada.', 'notice'));
  $('mas-ofertas').hidden = lista.length <= limiteOfertas;
}
function renderDetalle(id, foco) {
  const p = porProducto.get(id);
  if (!p) {
    $('nombre-producto').textContent = 'Producto no encontrado'; $('categoria-producto').textContent = 'Consulta';
    $('ilustracion').replaceChildren(); $('atributos').textContent = '';
    $('resumen').replaceChildren(el('p', 'Este producto no está en el catálogo de esta copia. Vuelve a la búsqueda.'));
    document.querySelector('.detail-grid').hidden = true; return;
  }
  document.querySelector('.detail-grid').hidden = false;
  $('nombre-producto').textContent = p.nombre; $('categoria-producto').textContent = categoriaNombre(p);
  $('ilustracion').replaceChildren(ilustracion(p)); $('atributos').textContent = 'Confirma la variante y el código del fabricante antes de comprar.' + (p.es_paquete ? ' Este registro corresponde a un paquete.' : '');
  const mejor = opcionMenor(id), box = $('resumen'); box.replaceChildren(); box.classList.toggle('warning', !mejor);
  const texto = el('div');
  if (mejor) {
    texto.append(badge(mejor), el('h2', mejor.indicador === 'precio_favorable' ? 'Un precio bajo frente a su historia.' : mejor.indicador === 'precio_alto' ? 'El precio reciente supera su referencia.' : mejor.indicador === 'sin_senal_clara' ? 'Una oferta sin señal concluyente.' : 'Tenemos precio; falta más historia.'),
      el('p', explicacion(mejor) + ' Es el menor precio reciente con título compatible de nuestra muestra.'),
      el('p', 'Pendiente confirmar variante, inventario y envío. No es una verificación del precio final.', 'disclaimer'));
    const precio = el('div', money(mejor.precio), 'summary-price'); precio.append(el('small', mejor.plataforma + ' · ' + mejor.fecha_precio)); box.append(texto, precio);
  } else {
    texto.append(badge(null), el('h2', 'Todavía falta evidencia comparable.'), el('p', 'Puedes consultar las ofertas registradas y el historial. No encontramos una oferta reciente con identidad suficiente para compararla.'));
    box.append(texto);
  }
  grafico(p); renderOfertas(id);
  if (foco) $('nombre-producto').focus({preventScroll: true});
}
function productoActual() { try { return decodeURIComponent(location.hash.split('/producto/')[1] || ''); } catch { return ''; } }
function ruta(foco = true) {
  if (!datos) return;
  const detalle = location.hash.startsWith('#/producto/');
  $('inicio').hidden = detalle; $('detalle').hidden = !detalle;
  if (detalle) { $('volver').href = anterior; renderDetalle(productoActual(), foco); }
  else {
    const q = new URLSearchParams(location.hash.split('?')[1] || '');
    consulta = (q.get('q') || '').slice(0, 200); categoria = ['foco', 'todos', 'laptop', 'audifonos'].includes(q.get('categoria')) ? q.get('categoria') : 'foco'; tienda = ['sears', 'liverpool'].includes(q.get('tienda')) ? q.get('tienda') : '';
    anterior = location.hash || '#/'; renderProductos();
  }
  document.title = detalle && porProducto.has(productoActual()) ? porProducto.get(productoActual()).nombre + ' · Sconto' : 'Sconto · Antes de comprar';
  if (foco) window.scrollTo({top: 0, behavior: 'instant'});
}
function iniciarBusqueda(valor) { consulta = valor.trim().slice(0, 200); if (consulta) categoria = 'todos'; limite = 12; guardarBusqueda(); renderProductos(); }
$('busqueda-form').addEventListener('submit', e => { e.preventDefault(); if (datos) iniciarBusqueda($('busqueda').value); });
let espera;
$('busqueda').addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => iniciarBusqueda($('busqueda').value), 220); });
for (const b of document.querySelectorAll('[data-query]')) b.addEventListener('click', () => { if (datos) iniciarBusqueda(b.dataset.query); });
for (const b of $('categorias').querySelectorAll('button')) b.addEventListener('click', () => { if (!datos) return; categoria = b.dataset.category; limite = 12; guardarBusqueda(); renderProductos(); });
$('tienda').addEventListener('change', () => { if (!datos) return; tienda = $('tienda').value; limite = 12; guardarBusqueda(); renderProductos(); });
$('limpiar').addEventListener('click', () => { categoria = 'foco'; tienda = ''; iniciarBusqueda(''); });
$('ver-mas').addEventListener('click', () => { limite += 12; renderProductos(); });
$('tienda-ofertas').addEventListener('change', () => { limiteOfertas = 8; renderOfertas(productoActual()); });
$('mas-ofertas').addEventListener('click', () => { limiteOfertas += 8; renderOfertas(productoActual()); });
$('refrescar').addEventListener('click', actualizar); $('reintentar').addEventListener('click', actualizar);
window.addEventListener('hashchange', () => { limiteOfertas = 8; $('tienda-ofertas').value = ''; ruta(); });
$('compartir').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(location.href); notificar('Enlace copiado.'); } catch { notificar('Puedes copiar la dirección de esta página desde el navegador.'); }
});
$('acerca').addEventListener('click', () => $('informacion').showModal());
$('instalar').addEventListener('click', () => { $('instalar-nativo').hidden = !promptInstalar; $('instalacion').showModal(); });
for (const b of document.querySelectorAll('[data-close]')) b.addEventListener('click', () => b.closest('dialog').close());
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); promptInstalar = e; });
$('instalar-nativo').addEventListener('click', async () => {
  if (!promptInstalar) return;
  await promptInstalar.prompt(); await promptInstalar.userChoice; promptInstalar = null; $('instalar-nativo').hidden = true;
});
function instalada() { return matchMedia('(display-mode: standalone)').matches || navigator.standalone === true; }
if (instalada()) $('instalar').hidden = true;
window.addEventListener('appinstalled', () => { $('instalar').hidden = true; $('instalacion').close(); notificar('Sconto está instalado.'); });
$('actualizar-app').addEventListener('click', () => {
  if (registro?.waiting) { recargarTrasActualizacion = true; registro.waiting.postMessage('ACTIVAR'); }
});
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').then(r => {
    registro = r;
    const revisar = () => { $('actualizacion').hidden = !r.waiting; };
    revisar();
    r.addEventListener('updatefound', () => r.installing?.addEventListener('statechange', revisar));
    let recargando = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (recargando || !navigator.serviceWorker.controller) return;
      if (recargarTrasActualizacion) { recargando = true; location.reload(); }
    });
  }).catch(() => { /* La instalación no impide consultar desde el navegador. */ });
}
for (const evento of ['online', 'offline']) window.addEventListener(evento, () => { estadoConexion(); if (navigator.onLine && Date.now() - ultimoIntento > 60000) actualizar(); });
document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  if (fechaMostrada !== fechaMexico()) { fechaMostrada = fechaMexico(); estadoConexion(); ruta(false); }
  if (Date.now() - ultimoIntento > 600000 && navigator.onLine) actualizar();
});
setInterval(() => { if (datos && fechaMostrada !== fechaMexico()) { fechaMostrada = fechaMexico(); estadoConexion(); ruta(false); } }, 60000);
let redimension;
window.addEventListener('resize', () => {
  clearTimeout(redimension);
  redimension = setTimeout(() => { const p = porProducto.get(productoActual()); if (datos && p) grafico(p); }, 200);
});
await actualizar();
