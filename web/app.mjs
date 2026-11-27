import {buscar, normalizar, fechaMexico, edadDias, ordenarOfertas, enlaceSeguro} from './motor.mjs';
import {cargarDatos, cargarDetalle} from './datos.mjs';
import {baseAPI, buscarSucursales, consultarProducto, registroHistorico, vistaOferta} from './api.mjs';
import {entrada, irA} from './interfaz.mjs';
import {cargarModelo, referenciaProducto, evaluarPrecio, textoEvaluacion, prediccionProducto} from './modelo.mjs';

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
const api = baseAPI(document.querySelector('meta[name="sconto-api"]')?.content);
const productosFisicos = new Map();
let consultaFisica = '', evidencia;
const razones = {canal_fisico:'Referencia de establecimiento físico', fuente_sin_verificacion_directa:'Fuente sin verificación directa',
  fecha_insuficiente:'Hora real del precio sin confirmar', dato_vencido:'Venció la comprobación', identidad_incompleta:'Falta verificar SKU, vendedor o condición',
  disponibilidad_sin_confirmar:'Disponibilidad sin verificar', sin_stock_confirmado:'Sin disponibilidad confirmada',
  total_no_comparable:'Falta total comparable con cargos', historia_insuficiente:'Faltan días comparables en la referencia'};
let datos, carga, cargando = false, ultimoIntento = 0, fechaMostrada = fechaMexico(), recargarTrasActualizacion = false;
let categoria = 'todos', consulta = '', tienda = '', limite = 12, limiteOfertas = 8, anterior = '#/', promptInstalar, registro;
let porProducto = new Map(), ofertasPorProducto = new Map();
let modelo = null, modeloCargado = false;
let productosVisibles = '', posicionResultados = 0, tarjetaAnterior = '', ultimaVista = '';
const seleccionHistoria = new Map();
const fichas = new Map();
let solicitudRuta = 0;
const categorias = {todos:'Todo el catálogo', modelo:'Con predicción del modelo', foco:'Para tu compra', laptop:'Computadoras y laptops', celular:'Celulares', tablet:'Tabletas', audifonos:'Audífonos', audio:'Bocinas y audio', pantalla:'Pantallas', proyector:'Proyectores', camara:'Cámaras y lentes', streaming:'Streaming', hogar:'Hogar inteligente', otros:'Otra tecnología'};
function categoriaProducto(p) { return p.categoria_app || (laptop(p) ? 'laptop' : audifonos(p) ? 'audifonos' : p.familia === 'asistente' ? 'hogar' : p.familia || 'otros'); }

function notificar(texto) {
  $('toast').textContent = texto; $('toast').hidden = false;
  entrada($('toast'), 0);
  clearTimeout(notificar.timer);
  notificar.timer = setTimeout(() => { $('toast').hidden = true; }, 4000);
}
function audifonos(p) { return /AUDIFONOS|AIRPODS|HEADSET|4GAMERS/.test(normalizar(p.nombre)); }
function laptop(p) { return /LAPTOP|COMPUTADORA/.test(normalizar(p.nombre)) || p.familia === 'laptop'; }
function categoriaNombre(p) { return p.categoria_app_nombre || categorias[categoriaProducto(p)] || 'Tecnología'; }
function ilustracion(p) {
  const cont = el('span');
  const tipo = categoriaProducto(p);
  const dibujo = tipo === 'celular'
    ? '<rect x="61" y="7" width="58" height="110" rx="10"/><path d="M68 22h44v75H68z" fill="currentColor" opacity=".08"/><path d="M82 15h16m-12 93h8"/>'
    : tipo === 'tablet'
    ? '<rect x="39" y="9" width="102" height="106" rx="8"/><path d="M47 22h86v77H47z" fill="currentColor" opacity=".08"/><circle cx="90" cy="107" r="2"/>'
    : tipo === 'camara'
    ? '<path d="M58 36l10-15h43l10 15h25v65H34V36z"/><circle cx="90" cy="65" r="25"/><circle cx="90" cy="65" r="15"/><path d="M125 47h10"/>'
    : tipo === 'audio'
    ? '<rect x="58" y="9" width="64" height="108" rx="9"/><circle cx="90" cy="38" r="13"/><circle cx="90" cy="83" r="23"/><circle cx="90" cy="83" r="9"/>'
    : tipo === 'hogar'
    ? '<path d="M25 62l65-47 65 47M42 51v61h96V51M74 112V78h32v34"/><path d="M77 48a22 22 0 0 1 26 0m-20 9a12 12 0 0 1 14 0"/>'
    : laptop(p)
    ? '<rect x="28" y="18" width="124" height="76" rx="5"/><path d="M36 27h108v58H36z" fill="currentColor" opacity=".09"/><path d="M18 105h144l-10 9H28z"/><path d="M75 105h30"/>'
    : audifonos(p)
    ? '<path d="M43 69V55a47 47 0 0 1 94 0v14"/><path d="M51 58v-6a39 39 0 0 1 78 0v6"/><rect x="35" y="60" width="24" height="43" rx="10"/><rect x="121" y="60" width="24" height="43" rx="10"/><path d="M59 70v23m62-23v23"/>'
    : '<rect x="36" y="18" width="108" height="82" rx="7"/><path d="M44 27h92v63H44z" fill="currentColor" opacity=".09"/><path d="M72 113h36m-18-13v13"/>';
  cont.innerHTML = '<svg viewBox="0 0 180 125" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + dibujo + '</svg>';
  return cont.firstElementChild;
}
function badge(oferta) {
  const b = el('span', undefined, 'badge ' + (tonos[oferta?.indicador] || 'missing'));
  const icono = el('span', {precio_favorable:'↘', precio_alto:'↗', sin_senal_clara:'↔'}[oferta?.indicador] || '?', 'signal-icon');
  icono.setAttribute('aria-hidden', 'true');
  b.append(icono, el('span', etiquetas[oferta?.indicador] || 'Evidencia insuficiente'));
  return b;
}
function ofertasProducto(id, hoy = fechaMexico()) { return ordenarOfertas(ofertasPorProducto.get(id) || [], hoy).map(o => registroHistorico(o, hoy)); }
function coincideTienda(o, filtro) { return !filtro || normalizar(o.plataforma).toLowerCase() === filtro; }
function registroEnTienda(id, filtro = '', hoy = fechaMexico()) { return ofertasProducto(id, hoy).find(o => coincideTienda(o, filtro)); }
function estadoConexion() {
  if (!datos) return;
  const edad = edadDias(datos.fecha_corte, fechaMexico()), vieja = edad === null || edad < 0 || edad > 1;
  $('estado-datos').textContent = 'Corte ' + corto(datos.fecha_corte) + ' ' + datos.fecha_corte.slice(0, 4) + ' · ' + datos.productos.length + ' productos';
  const mensajes = [];
  if (!navigator.onLine || carga?.copia) mensajes.push('Usas la última copia guardada. No se pudo confirmar una actualización.');
  if (vieja) mensajes.push('El catálogo muestra registros históricos fechados. La vigencia se calcula por comprobación de cada oferta.');
  if (!carga?.guardado) mensajes.push('No se pudo guardar la copia sin conexión en este navegador.');
  $('aviso').textContent = mensajes.join(' ');
  $('aviso').hidden = !mensajes.length;
  $('estado-datos').dataset.estado = vieja ? 'antiguo' : !navigator.onLine || carga?.copia ? 'copia' : 'listo';
}
async function actualizar(manual = false) {
  if (cargando) return;
  cargando = true; ultimoIntento = Date.now(); $('refrescar').disabled = true;
  $('refrescar').classList.add('is-loading'); $('refrescar-texto').textContent = 'Actualizando';
  try {
    carga = await cargarDatos(); datos = carga.datos; fichas.clear(); evidencia = undefined;
    porProducto = new Map(datos.productos.map(p => [p.producto_canonico_id, p]));
    ofertasPorProducto = new Map();
    for (const o of datos.ofertas) {
      if (!ofertasPorProducto.has(o.producto_canonico_id)) ofertasPorProducto.set(o.producto_canonico_id, []);
      ofertasPorProducto.get(o.producto_canonico_id).push(o);
    }
    $('error').hidden = true; $('busqueda').disabled = false;
    if (!modeloCargado) { modelo = await cargarModelo(); modeloCargado = true; }
    renderCategorias(); estadoConexion(); await ruta(false);
    if (manual) notificar(carga.copia ? 'Sin actualización disponible. Conservamos la copia guardada.' : 'Datos comprobados · corte ' + datos.fecha_corte + '.');
  } catch (error) {
    if (!datos) {
      $('error-texto').textContent = error.message; $('error').hidden = false; $('inicio').hidden = true; $('detalle').hidden = true;
      $('estado-datos').textContent = 'Datos no disponibles';
    } else { notificar('Conservamos la copia anterior. ' + error.message); }
  } finally { cargando = false; $('refrescar').disabled = false; $('refrescar').classList.remove('is-loading'); $('refrescar-texto').textContent = 'Actualizar'; }
}
function hashBusqueda() {
  const q = new URLSearchParams();
  if (consulta) q.set('q', consulta);
  if (categoria !== 'todos') q.set('categoria', categoria);
  if (tienda) q.set('tienda', tienda);
  return '#/' + (q.size ? '?' + q.toString() : '');
}
function guardarBusqueda() { anterior = hashBusqueda(); history.replaceState(null, '', anterior); }
function renderCategorias() {
  const conteos = new Map();
  for (const p of datos.productos) conteos.set(categoriaProducto(p), (conteos.get(categoriaProducto(p)) || 0) + 1);
  for (const b of $('categorias').querySelectorAll('button')) {
    const id = b.dataset.category, cuenta = id === 'todos' ? datos.productos.length : conteos.get(id) || 0;
    b.replaceChildren(el('span', id === 'laptop' ? 'Computadoras' : categorias[id]), el('span', ' ' + cuenta, 'category-count'));
  }
  const otras = $('otras-categorias'); otras.replaceChildren();
  const inicial = el('option', 'Más categorías'); inicial.value = ''; otras.append(inicial);
  for (const [id, nombre] of Object.entries(categorias)) if (!['todos','laptop','celular','tablet','audifonos'].includes(id)) {
    const cuenta = id === 'foco' ? datos.productos.filter(p => p.foco_compra && !p.es_paquete).length : conteos.get(id) || 0;
    if (cuenta) { const opcion = el('option', nombre + ' · ' + cuenta); opcion.value = id; otras.append(opcion); }
  }
}
function filtrarProductos() {
  let lista = consulta.trim() ? buscar(consulta, datos.productos, datos.busqueda) : [...datos.productos];
  lista = lista.filter(p => categoria === 'todos' || categoriaProducto(p) === categoria || categoria === 'foco' && (laptop(p) || audifonos(p)) && !p.es_paquete
    || categoria === 'modelo' && Boolean(prediccionProducto(modelo, p.producto_canonico_id)));
  if (tienda) lista = lista.filter(p => (ofertasPorProducto.get(p.producto_canonico_id) || []).some(o => normalizar(o.plataforma).toLowerCase() === tienda));
  if (!consulta.trim()) {
    const hoy = fechaMexico(), recientes = new Set(lista.filter(p => registroEnTienda(p.producto_canonico_id, tienda, hoy)?.dias === 0).map(p => p.producto_canonico_id));
    lista.sort((a, b) => Number(recientes.has(b.producto_canonico_id)) - Number(recientes.has(a.producto_canonico_id)) || (b.ultima_fecha_observada || '').localeCompare(a.ultima_fecha_observada || '') || Number(laptop(b)) - Number(laptop(a)) || a.nombre.localeCompare(b.nombre, 'es'));
  }
  return lista;
}
function renderProductos(desde = 0) {
  $('busqueda').value = consulta; $('tienda').value = tienda;
  $('busqueda-fisica').hidden = !api || consulta.length < 3;
  if (consultaFisica !== consulta) {
    $('resultados-fisicos').replaceChildren();
    $('estado-busqueda-fisica').textContent = '';
  }
  $('otras-categorias').value = ['todos','laptop','celular','tablet','audifonos'].includes(categoria) ? '' : categoria;
  for (const b of $('categorias').querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.category === categoria));
  const lista = filtrarProductos();
  $('titulo-resultados').textContent = consulta ? 'Resultados para “' + consulta + '”' : 'Tecnología para tu próxima compra';
  $('conteo').textContent = lista.length + (lista.length === 1 ? ' producto' : ' productos');
  const activos = [consulta && '“' + consulta + '”', tienda && (tienda === 'sears' ? 'Sears' : 'Liverpool'), categoria !== 'todos' ? categorias[categoria] : ''].filter(Boolean);
  $('filtros-activos').hidden = !activos.length;
  $('descripcion-filtros').textContent = activos.join(' · ');
  $('quitar-busqueda').hidden = !consulta;
  $('sin-resultados-titulo').textContent = consulta && consulta.length < 3 ? 'Escribe al menos 3 caracteres' : 'No encontramos coincidencias';
  $('sin-resultados-texto').textContent = activos.length > 1 ? 'Prueba quitando algún filtro o usando sólo la marca y el modelo. Nuestro catálogo es limitado.' : 'Prueba con la marca y el modelo. Nuestro catálogo es limitado: no significa que el producto no exista.';
  const clave = [consulta, categoria, tienda, limite, datos.fecha_corte].join('|');
  const animar = productosVisibles !== clave; productosVisibles = clave;
  $('productos').replaceChildren(); $('productos').setAttribute('aria-busy', 'false');
  for (const p of lista.slice(0, limite)) {
    const a = el('a', undefined, 'product-card'); a.href = '#/producto/' + encodeURIComponent(p.producto_canonico_id) + (tienda ? '?tienda=' + tienda : '');
    a.dataset.producto = p.producto_canonico_id;
    const art = el('div', undefined, 'product-art');
    art.append(el('span', categoriaNombre(p), 'art-label'), ilustracion(p), el('span', '↗', 'art-arrow'));
    const pred = prediccionProducto(modelo, p.producto_canonico_id);
    if (pred) art.append(el('span', pred.acierto ? '✦ Modelo acertó' : '✦ Modelo falló', 'model-tag ' + (pred.acierto ? 'hit' : 'miss')));
    const body = el('div', undefined, 'card-body'), registro = registroEnTienda(p.producto_canonico_id, tienda);
    const tiendas = new Set((ofertasPorProducto.get(p.producto_canonico_id) || []).map(o => o.plataforma));
    body.append(el('span', p.marca || categoriaNombre(p), 'card-brand'), el('h3', p.nombre),
      el('p', (tiendas.size ? tiendas.size + (tiendas.size === 1 ? ' tienda con registro' : ' tiendas con registro') : 'Sin ofertas por tienda') + (p.es_paquete ? ' · paquete' : ''), 'card-meta'));
    const pie = el('div', undefined, 'card-price'), precio = el('div');
    precio.append(el('small', registro ? 'Registro · ' + registro.plataforma + ' · ' + registro.fecha_precio : 'Precio pendiente'), el('strong', registro ? money(registro.precio) : 'Ver historia'));
    pie.append(precio); body.append(pie);
    if (p.ultima_fecha_observada) body.append(el('small', 'Último registro: ' + p.ultima_fecha_observada, 'card-date'));
    a.append(art, body); $('productos').append(a);
  }
  $('sin-resultados').hidden = lista.length > 0; $('ver-mas').hidden = lista.length <= limite;
  if (animar) entrada(Array.from($('productos').children).slice(desde));
  if (!lista.length) entrada($('sin-resultados'));
}
function svg(tag, attrs, texto) {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (texto !== undefined) n.textContent = texto;
  return n;
}
function grafico(p) {
  const ficha = fichas.get(p.producto_canonico_id) || datos;
  const s = ficha.series.find(s => s.producto_canonico_id === p.producto_canonico_id && s.contexto === 'minimo_multitienda');
  const ref = ficha.referencias.find(r => r.serie_id === s?.serie_id && r.evento_id === datos.evento_actual);
  const puntos = ficha.precios_diarios.filter(r => r.serie_id === s?.serie_id).sort((a, b) => a.fecha_precio.localeCompare(b.fecha_precio));
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
  if (ref?.cobertura_base && ref?.base_cerrada) {
    dibujo.append(svg('line', {x1: L, x2: W - R, y1: y(ref.mediana_base), y2: y(ref.mediana_base), stroke: '#8c985d', 'stroke-dasharray': '5 5', 'stroke-width': 1.5}));
  }
  for (const p of puntos) {
    const punto = svg('circle', {cx: x(Date.parse(p.fecha_precio)), cy: y(p.precio_mediano), r: 3.1, fill: '#245d4d', opacity: .8});
    punto.append(svg('title', {}, p.fecha_precio + ': ' + money(p.precio_mediano))); dibujo.append(punto);
  }
  const guia = svg('line', {y1: T, y2: H - B, stroke: '#245d4d', 'stroke-dasharray': '3 4', opacity: .45});
  const activo = svg('circle', {r: 5.5, fill: '#245d4d', stroke: '#fffefb', 'stroke-width': 2});
  dibujo.append(guia, activo);
  const lectura = el('output', undefined, 'chart-reading'); lectura.setAttribute('for', 'dia-historial');
  const fecha = el('span'), valor = el('strong'); lectura.append(fecha, valor);
  const control = el('input'); control.type = 'range'; control.id = 'dia-historial'; control.min = 0; control.max = puntos.length - 1; control.step = 1;
  control.setAttribute('aria-label', 'Día del historial'); control.disabled = puntos.length < 2;
  const seleccionar = i => {
    const p = puntos[i]; seleccionHistoria.set(s.producto_canonico_id, p.fecha_precio);
    control.value = i; control.setAttribute('aria-valuetext', p.fecha_precio + ', ' + money(p.precio_mediano));
    fecha.textContent = corto(p.fecha_precio) + ' ' + p.fecha_precio.slice(0, 4); valor.textContent = money(p.precio_mediano);
    guia.setAttribute('x1', x(Date.parse(p.fecha_precio))); guia.setAttribute('x2', x(Date.parse(p.fecha_precio)));
    activo.setAttribute('cx', x(Date.parse(p.fecha_precio))); activo.setAttribute('cy', y(p.precio_mediano));
  };
  control.addEventListener('input', () => seleccionar(Number(control.value)));
  dibujo.addEventListener('pointerdown', e => {
    const rect = dibujo.getBoundingClientRect(), pos = (e.clientX - rect.left) / rect.width * W;
    const i = puntos.reduce((mejor, p, i) => Math.abs(x(Date.parse(p.fecha_precio)) - pos) < Math.abs(x(Date.parse(puntos[mejor].fecha_precio)) - pos) ? i : mejor, 0);
    seleccionar(i);
  });
  const guardada = puntos.findIndex(d => d.fecha_precio === seleccionHistoria.get(p.producto_canonico_id));
  seleccionar(guardada < 0 ? puntos.length - 1 : guardada);
  $('grafico').append(dibujo, lectura, control, el('p', 'Toca la gráfica o desliza para explorar los días observados. La línea discontinua marca la mediana de la base cuando hay cobertura.', 'chart-help'));
  const tabla = el('table'), cabecera = el('tr'); cabecera.append(el('th', 'Fecha'), el('th', 'Mínimo observado'));
  const thead = el('thead'), tbody = el('tbody'); thead.append(cabecera);
  for (const p of [...puntos].reverse()) { const fila = el('tr'); fila.append(el('td', p.fecha_precio), el('td', money(p.precio_mediano))); tbody.append(fila); }
  tabla.append(thead, tbody); $('tabla-historia').append(tabla);
}
function explicacion(o) {
  if (o.identidad_oferta === 'conflicto') return 'La descripción tiene una variante distinta. No la usamos para comparar este producto.';
  if (o.identidad_oferta !== 'compatible_texto') return 'Faltan datos para confirmar que sea la misma variante.';
  return 'El nombre coincide con el catálogo. SKU, fecha de actualización de la tienda y costo final requieren comprobación.';
}
function renderOfertas(id, animar = false) {
  const filtro = $('tienda-ofertas').value;
  const lista = ofertasProducto(id).filter(o => !filtro || normalizar(o.plataforma).toLowerCase() === filtro);
  $('conteo-ofertas').textContent = lista.length + (lista.length === 1 ? ' registro online' : ' registros online') + (filtro ? ' en ' + (filtro === 'sears' ? 'Sears' : 'Liverpool') : '');
  $('ofertas').replaceChildren();
  for (const [i, o] of lista.slice(0, limiteOfertas).entries()) {
    const art = el('article', undefined, 'offer' + (i === 0 && o.comparable ? ' first' : ''));
    const top = el('div', undefined, 'offer-top'), vendedor = el('div'), precio = el('strong', money(o.precio, o.moneda), 'offer-price');
    vendedor.append(el('div', o.plataforma || 'Tienda', 'offer-store'),
      el('p', 'Vende ' + (o.vendedor_o_cadena || 'vendedor no identificado') + (o.tipo_vendedor === 'tercero' ? ' · tercero' : ''), 'offer-seller'), badge(o));
    precio.append(el('small', o.moneda + ' · precio publicado')); top.append(vendedor, precio);
    const bottom = el('div', undefined, 'offer-bottom');
    bottom.append(el('span', 'Registro del ' + o.fecha_precio + ' · ' + o.antiguedad));
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
    art.append(el('p', explicacion(o), 'offer-explanation'), bottom, detalle); $('ofertas').append(art);
  }
  if (!lista.length) $('ofertas').append(el('p', 'No hay ofertas registradas para este producto en la tienda seleccionada.', 'notice'));
  $('mas-ofertas').hidden = lista.length <= limiteOfertas;
  if (animar) entrada($('ofertas').children);
}
function renderResumen(id) {
  const filtro = $('tienda-ofertas').value, nombreTienda = filtro === 'sears' ? 'Sears' : 'Liverpool';
  const ofertas = evidencia?.id === id && evidencia.estado === 'disponible' ? evidencia.ofertas.map(o => vistaOferta(o)) : [];
  const mejor = ofertas.find(o => o.estado !== 'evidencia_insuficiente' && o.total !== null && coincideTienda(o, filtro));
  const box = $('resumen'); box.replaceChildren(); box.classList.toggle('warning', !mejor);
  box.dataset.signal = tonos[mejor?.estado] || 'missing';
  const texto = el('div');
  if (mejor) {
    texto.append(badge({indicador:mejor.estado}), el('h2', 'Oferta con costo confirmado'),
      el('p', mejor.plataforma + ' · ' + mejor.fecha));
    const precio = el('div', money(mejor.total), 'summary-price'); precio.append(el('small', 'Costo total confirmado')); box.append(texto, precio);
  } else {
    const c = fichas.has(id) ? contextoPrecio(id) : null;
    box.dataset.signal = 'neutral'; box.classList.remove('warning');
    texto.append(el('p', 'Sin oferta en línea verificada' + (filtro ? ' en ' + nombreTienda : '') + ' hoy', 'eyebrow'),
      el('h2', '¿Viste un precio? Compáralo con su historia.'),
      el('p', c?.puntos?.length ? `Tenemos ${c.puntos.length} días de precios de este producto. Escribe el precio que encontraste y te decimos si es favorable, alto o normal.`
        : 'Revisa la historia disponible y confirma el precio final en la tienda.'));
    box.append(texto);
  }
}

function renderEvidencia(id) {
  const fisico = id.startsWith('PROFECO-BF26-');
  const contenedor = $('evidencia-api'), resultados = $('resultados-api');
  contenedor.hidden = !api || evidencia?.id !== id;
  if (contenedor.hidden) return;
  resultados.replaceChildren();
  $('titulo-evidencia-api').textContent = fisico ? 'Precios diarios de sucursales físicas · PROFECO' : 'Comprobaciones de ofertas online';
  const estado = $('estado-api');
  if (evidencia.estado !== 'disponible') {
    estado.textContent = evidencia.estado === 'consultando' ? 'Consultando…' :
      (evidencia.estado === 'sin_conexion' ? 'Sin conexión.' : 'El servicio de consulta no respondió.') +
      (fisico ? ' Vuelve a intentar para consultar las sucursales.' : ' Puedes seguir usando los registros del catálogo.');
    return;
  }
  if (fisico) {
    estado.textContent = evidencia.historia.length ? 'Fecha de levantamiento en sucursal. La hora del precio es desconocida.' : 'Sin registros físicos en el servicio.';
    for (const fila of evidencia.historia) {
      const art = el('article', undefined, 'offer');
      art.append(el('strong', fila.vendedor || 'Sucursal física'), el('p', fila.fecha_precio + ' · ' + money(fila.precio)));
      resultados.append(art);
    }
    return;
  }
  const filtro = $('tienda-ofertas').value;
  const ofertas = evidencia.ofertas.filter(o => coincideTienda(o, filtro));
  // Sin comprobaciones en línea el panel no aporta: el comparador de precio cubre ese caso.
  if (!ofertas.length) { contenedor.hidden = true; return; }
  estado.textContent = '';
  for (const oferta of ofertas) {
    const o = vistaOferta(oferta), art = el('article', undefined, 'offer');
    art.append(el('strong', o.plataforma || 'Tienda'), badge({indicador:o.estado}),
      el('p', 'Vendedor ' + (o.vendedor || 'sin confirmar') + ' · SKU ' + (o.variante || 'sin confirmar') + ' · ' + (o.condicion || 'condición sin confirmar')),
      el('p', 'Precio publicado ' + money(o.precio) + ' · Total ' + (o.total === null ? 'sin confirmar' : money(o.total))));
    art.append(el('p', o.disponibilidad === 'en_stock' ? 'Disponibilidad confirmada al cotejar' : o.disponibilidad ? 'Sin disponibilidad confirmada' : 'Disponibilidad sin verificar'));
    art.append(el('p', 'Dato ' + o.fecha + (o.vigente ? '' : ' · vigencia sin confirmar')));
    if (o.consultado) art.append(el('p', 'Consulta ' + o.consultado));
    if (o.actualizado) art.append(el('p', 'Actualización declarada por la fuente ' + o.actualizado));
    if (o.ahorro !== null && Number.isFinite(o.referencia?.mediana)) {
      art.append(el('p', Math.abs(o.ahorro).toFixed(1) + '% ' + (o.ahorro < 0 ? 'por encima' : 'por debajo') + ' de la mediana de ' + money(o.referencia.mediana)));
    }
    const motivos = o.motivos.map(m => razones[m]).filter(Boolean);
    if (motivos.length) art.append(el('p', motivos.join(' · '), 'muted'));
    if (o.enlace) {
      const enlace = el('a', 'Ver anuncio original ↗');
      enlace.href = o.enlace; enlace.target = '_blank'; enlace.rel = 'noopener noreferrer'; art.append(enlace);
    }
    resultados.append(art);
  }
}

function renderFichaFisica(id, foco) {
  const p = productosFisicos.get(id);
  $('nombre-producto').textContent = p?.nombre || 'Referencia PROFECO ' + id.split('-').at(-1);
  $('categoria-producto').textContent = 'Tienda física';
  $('ilustracion').replaceChildren(); $('atributos').textContent = '';
  $('resumen').replaceChildren(badge(null), el('p', 'La consulta física informa precios de sucursal por fecha. La recomendación online requiere la ficha vigente del anuncio.'));
  $('resumen').classList.add('warning'); $('resumen').dataset.signal = 'missing';
  $('atajos-detalle').hidden = true; document.querySelector('.detail-grid').hidden = true;
  if (foco) $('nombre-producto').focus({preventScroll:true});
}
function renderDetalle(id, foco, completo = true) {
  const p = porProducto.get(id);
  $('atajos-detalle').hidden = !p || !completo;
  if (!p) {
    $('nombre-producto').textContent = 'Producto no encontrado'; $('categoria-producto').textContent = 'Consulta';
    $('ilustracion').replaceChildren(); $('atributos').textContent = '';
    $('resumen').replaceChildren(el('p', 'Este producto no está en el catálogo de esta copia. Vuelve a la búsqueda.'));
    document.querySelector('.detail-grid').hidden = true; return;
  }
  document.querySelector('.detail-grid').hidden = !completo;
  $('nombre-producto').textContent = p.nombre; $('categoria-producto').textContent = categoriaNombre(p);
  $('ilustracion').replaceChildren(ilustracion(p)); $('atributos').textContent = 'Confirma la variante y el código del fabricante antes de comprar.' + (p.es_paquete ? ' Este registro corresponde a un paquete.' : '');
  renderResumen(id);
  if (!completo) return;
  grafico(p); renderOfertas(id); renderEvaluador(id); renderPrediccion(id);
  if (foco) $('nombre-producto').focus({preventScroll: true});
}

// ---------------------------------------------------------------- v3: comparador de precio y modelo
const pct = (v, d = 1) => (Number.isFinite(v) ? (100 * v).toFixed(d) : '—');
let evaluadorProducto = '';
function contextoPrecio(id) {
  const evento = datos.ventanas.find(e => e.evento_id === datos.evento_actual);
  return referenciaProducto(fichas.get(id), id, evento);
}
function renderEvaluador(id) {
  if (evaluadorProducto !== id) { $('precio-visto').value = ''; $('resultado-evaluador').replaceChildren(); evaluadorProducto = id; }
  const c = contextoPrecio(id);
  $('precio-visto').placeholder = c?.ref?.mediana_base ? 'Ej. ' + Math.round(c.ref.mediana_base * .93) : 'Ej. 3499';
  const rapidos = $('precios-rapidos'); rapidos.replaceChildren();
  if (!c?.ref?.mediana_base) return;
  rapidos.append(el('span', 'Probar con:', 'quick-label'));
  for (const [texto, valor] of [['Mínimo histórico', c.minimo], ['Mediana habitual', c.ref.mediana_base], ['10% más caro', c.ref.mediana_base * 1.1]]) {
    if (!Number.isFinite(valor)) continue;
    const b = el('button', undefined, 'quick-price'); b.type = 'button';
    b.append(el('small', texto), el('strong', money(Math.round(valor))));
    b.addEventListener('click', () => { $('precio-visto').value = String(Math.round(valor)); mostrarEvaluacion(id); });
    rapidos.append(b);
  }
}
function medidor(r) {
  const valores = [r.precio, r.p25, r.mediana, r.p75, r.minimo].filter(Number.isFinite);
  const lo = Math.min(...valores) * .97, hi = Math.max(...valores) * 1.03, x = v => ((v - lo) / (hi - lo || 1) * 100).toFixed(1) + '%';
  const barra = el('div', undefined, 'meter');
  barra.setAttribute('aria-hidden', 'true');
  const zona = el('span', undefined, 'meter-band'); zona.style.left = x(r.p25); zona.style.width = `calc(${x(r.p75)} - ${x(r.p25)})`;
  barra.append(zona);
  for (const [v, clase, texto] of [[r.mediana, 'meter-median', 'Mediana'], [r.precio, 'meter-price', 'Tu precio']]) {
    const m = el('span', undefined, clase); m.style.left = x(v); m.append(el('small', texto)); barra.append(m);
  }
  return barra;
}
function mostrarEvaluacion(id) {
  const valor = Number(String($('precio-visto').value).replace(/[^\d.]/g, ''));
  const r = evaluarPrecio(valor, contextoPrecio(id), modelo?.reglas);
  const caja = $('resultado-evaluador'); caja.replaceChildren();
  caja.dataset.signal = tonos[r.estado] || 'missing';
  if (r.estado === 'invalido') { caja.append(el('p', r.motivo, 'muted')); return; }
  const cabeza = el('div', undefined, 'verdict-head');
  cabeza.append(badge({indicador: r.estado}), el('strong', money(r.precio)));
  caja.append(cabeza);
  if (r.estado !== 'evidencia_insuficiente') {
    caja.append(medidor(r));
    const marca = caja.querySelector('.meter-price'), mediana = caja.querySelector('.meter-median');
    if (marca && mediana && !matchMedia('(prefers-reduced-motion: reduce)').matches)
      marca.animate([{left: mediana.style.left}, {left: marca.style.left}], {duration: 750, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'backwards', delay: 120});
  }
  const lista = el('ul'); for (const linea of textoEvaluacion(r, money)) lista.append(el('li', linea));
  caja.append(lista);
  const u = modelo?.umbrales?.regla_app;
  if (u && r.estado !== 'evidencia_insuficiente') caja.append(el('p', `Por qué ${u.umbral_pct}%: en el Buen Fin ${pct(u.pct_buen_fin / 100, 0)}% de los precios cumplieron esta regla, contra ${pct(u.pct_semanas_normales / 100, 0)}% en semanas normales (QQP 2018–2025).`, 'muted'));
  caja.append(el('p', 'Confirma variante, vendedor, envío y precio total antes de comprar. El historial es el mínimo entre tiendas, no el de una sola tienda.', 'muted'));
  entrada(caja.children);
}
function renderPrediccion(id) {
  const p = prediccionProducto(modelo, id);
  $('prediccion').hidden = !p;
  if (!p) return;
  const caja = $('contenido-prediccion'); caja.replaceChildren();
  const parecidos = Math.round(p.pct_bajaron_parecidos ?? 100 * p.prob_bajada), general = Math.round(modelo.tasa_general_bajada ?? 60);
  const meta = el('div', undefined, 'prediction-meter');
  const barra = el('span'); barra.style.width = '0%'; meta.append(barra);
  requestAnimationFrame(() => requestAnimationFrame(() => { barra.style.width = parecidos + '%'; }));
  const marca = el('i'); marca.style.left = general + '%'; marca.title = 'Promedio general'; meta.append(marca);
  caja.append(el('p', `Antes del Buen Fin 2026 este producto tenía un patrón de precios parecido al de ${p.casos_parecidos?.toLocaleString('es-MX') ?? 'varias'} series de Buen Fin anteriores (2018–2025). De ellas bajó el ${parecidos}%; en general baja el ${general}%.`), meta,
    el('p', p.prediccion ? 'Predicción del modelo: bajará.' : 'Predicción del modelo: no bajará.', 'prediction-call'));
  if (Number.isFinite(p.bajada_pct)) {
    const real = p.bajo ? `Resultado observado: bajó ${Math.abs(p.bajada_pct).toFixed(1)}% frente a las dos semanas previas.` : `Resultado observado: no bajó (${p.bajada_pct <= 0 ? 'subió o se mantuvo' : 'sin cambio'}).`;
    caja.append(el('p', real), el('p', p.acierto ? '✓ El modelo acertó en este producto.' : '✗ El modelo falló en este producto.', p.acierto ? 'hit' : 'miss'));
  }
  caja.append(el('p', `${modelo.modelo.familia} entrenado con ${modelo.modelo.entrenamiento}. En datos que no vio, acierta con balanced accuracy de ${pct(modelo.modelo.bal_acc_2026, 0)}% en 2026.`, 'muted'));
}
function tablaMetricas(filas, conjunto) {
  const t = el('table', undefined, 'metric-table'), cab = el('tr');
  for (const h of ['Modelo', 'Accuracy', 'Bal. acc.', 'F1', 'AUC']) cab.append(el('th', h));
  const thead = el('thead'); thead.append(cab); const tbody = el('tbody');
  for (const f of filas.filter(f => f.conjunto === conjunto)) {
    const tr = el('tr'); if (f.familia === modelo.modelo.familia) tr.className = 'chosen';
    const celda = el('td', undefined, 'bar-cell'), barra = el('i');
    barra.style.width = Math.max(0, (f.balanced_accuracy - .4) / .6 * 100).toFixed(0) + '%';
    celda.append(barra, el('span', pct(f.balanced_accuracy)));
    tr.append(el('td', f.familia), el('td', pct(f.accuracy)), celda, el('td', pct(f.f1)), el('td', Number.isFinite(f.auc) ? f.auc.toFixed(2) : '—'));
    tbody.append(tr);
  }
  t.append(thead, tbody); return t;
}
function renderModeloDialogo() {
  const caja = $('contenido-modelo'); caja.replaceChildren();
  if (!modelo) { caja.append(el('p', 'La tarjeta del modelo no está disponible en esta copia.', 'muted')); return; }
  caja.append(el('p', modelo.pregunta), el('p', modelo.etiqueta, 'muted'));
  const esquema = el('ol', undefined, 'schema');
  for (const e of modelo.esquema) { const li = el('li'); li.append(el('strong', e.etapa + ' · '), e.descripcion); esquema.append(li); }
  caja.append(el('h3', 'Entrenamiento, validación y prueba'), esquema);
  for (const conjunto of modelo.conjuntos) { caja.append(el('h3', conjunto), tablaMetricas(modelo.metricas, conjunto)); }
  caja.append(el('p', `Modelo elegido con la validación 2022–2024 (sin mirar la prueba): ${modelo.modelo.familia} · ${modelo.modelo.variante}.`, 'muted'));
  if (modelo.importancias?.length) {
    const lista = el('ul'); for (const v of modelo.importancias.slice(0, 4)) lista.append(el('li', `${v.descripcion}: ${pct(v.importancia, 0)}%`));
    caja.append(el('h3', 'Qué mira el modelo'), lista);
  }
  const u = modelo.umbrales;
  caja.append(el('h3', 'Por qué 5%, P25 y cuatro fechas'));
  const reglas = el('ul');
  reglas.append(el('li', `Umbral: con ${u.regla_app.umbral_pct}% y P25, ${pct(u.regla_app.pct_buen_fin / 100, 0)}% de los precios del Buen Fin cumplen la regla contra ${pct(u.regla_app.pct_semanas_normales / 100, 0)}% de semanas normales (J de Youden ${u.regla_app.youden_j.toFixed(1)}; máximo ${u.regla_app.mejor_j.toFixed(1)} en ${u.regla_app.mejor_umbral}%). Entre 1% y 6% la separación es casi igual; 5% da menos falsas alarmas que 2% y con 10% se pierde una de cada cinco rebajas reales.`),
    el('li', `P25: exigir además el cuartil inferior reduce las falsas alarmas de ${pct(u.regla_app.normal_sin_p25 / 100, 1)}% a ${pct(u.regla_app.pct_semanas_normales / 100, 1)}% de semanas normales.`),
    el('li', `Cuatro fechas: con ${u.fechas.k} fechas la mediana de referencia se equivoca menos de 5% en ${pct(1 - u.fechas.pct_error_mayor_5 / 100, 0)}% de las series; con 3 fechas el error del percentil 90 sube a ${u.fechas.error_p90_k3.toFixed(1)}%.`),
    el('li', `Semana del evento: el precio cae en promedio ${Math.abs(u.estudio.evento).toFixed(1)}% y se recupera a la semana siguiente (${u.estudio.despues >= 0 ? '+' : ''}${u.estudio.despues.toFixed(1)}%).`));
  caja.append(reglas);
  caja.append(el('h3', 'Arquitectura'), el('p', modelo.arquitectura), el('p', modelo.limites, 'muted'));
  if (api) { const a = el('a', 'Probar la API del modelo ↗'); a.href = 'docs'; a.target = '_blank'; a.rel = 'noopener noreferrer'; caja.append(a); }
}
function productoActual() { try { return decodeURIComponent((location.hash.split('/producto/')[1] || '').split('?')[0]); } catch { return ''; } }
async function ruta(foco = true) {
  if (!datos) return;
  const solicitud = ++solicitudRuta, catalogo = datos;
  const detalle = location.hash.startsWith('#/producto/');
  $('inicio').hidden = detalle; $('detalle').hidden = !detalle;
  $('carga-detalle').hidden = true;
  if (detalle) {
    const filtro = new URLSearchParams(location.hash.split('?')[1] || '').get('tienda');
    $('tienda-ofertas').value = ['sears', 'liverpool'].includes(filtro) ? filtro : '';
    const id = productoActual(); $('volver').href = anterior;
    const fisico = Boolean(api && /^PROFECO-BF26-\d+$/.test(id));
    if (api && (fisico || porProducto.has(id)) && (evidencia?.id !== id || evidencia.estado !== 'disponible')) {
      evidencia = {id, estado:'consultando'};
      consultarProducto(api, id, {enLinea:navigator.onLine}).then(resultado => {
        if (solicitud !== solicitudRuta) return;
        evidencia = {id, ...resultado};
        renderEvidencia(id);
        if (!fisico) renderResumen(id);
      });
    }
    renderEvidencia(id);
    if (fisico) {
      renderFichaFisica(id, foco); document.title = $('nombre-producto').textContent + ' · Sconto';
      if (foco) window.scrollTo({top:0, behavior:'instant'});
      ultimaVista = 'detalle'; return;
    }
    if (porProducto.has(id) && !fichas.has(id)) {
      renderDetalle(id, foco, false);
      $('carga-detalle').hidden = false; $('reintentar-detalle').hidden = true;
      $('mensaje-detalle').textContent = 'Cargando historial y ofertas de este producto…';
      try {
        const ficha = await cargarDetalle(catalogo, id);
        if (solicitud !== solicitudRuta || catalogo !== datos) return;
        fichas.set(id, ficha); ofertasPorProducto.set(id, ficha.ofertas.filter(o => o.producto_canonico_id === id));
      } catch (error) {
        if (solicitud !== solicitudRuta) return;
        $('mensaje-detalle').textContent = error.message; $('reintentar-detalle').hidden = false; return;
      }
    }
    $('carga-detalle').hidden = true; renderDetalle(id, foco);
  }
  else {
    const q = new URLSearchParams(location.hash.split('?')[1] || '');
    consulta = (q.get('q') || '').slice(0, 200); categoria = Object.hasOwn(categorias, q.get('categoria')) ? q.get('categoria') : 'todos'; tienda = ['sears', 'liverpool'].includes(q.get('tienda')) ? q.get('tienda') : '';
    anterior = location.hash || '#/'; renderProductos();
  }
  document.title = detalle && porProducto.has(productoActual()) ? porProducto.get(productoActual()).nombre + ' · Sconto' : 'Sconto · Antes de comprar';
  if (foco) {
    const volver = !detalle && ultimaVista === 'detalle' && location.hash === anterior;
    window.scrollTo({top: volver ? posicionResultados : 0, behavior: 'instant'});
    if (volver) Array.from($('productos').children).find(a => a.dataset.producto === tarjetaAnterior)?.focus({preventScroll: true});
    entrada(detalle ? [document.querySelector('.product-heading'), $('resumen'), $('atajos-detalle')] : $('resultados'));
  }
  ultimaVista = detalle ? 'detalle' : 'inicio';
}
function iniciarBusqueda(valor, mostrar = false) {
  clearTimeout(espera); consulta = valor.trim().slice(0, 200); if (consulta) categoria = 'todos'; limite = 12;
  guardarBusqueda(); renderProductos();
  if (mostrar) { $('busqueda').blur(); irA($('resultados')); }
}
$('buscar-fisico').addEventListener('click', async () => {
  const termino = consulta;
  const estado = $('estado-busqueda-fisica'), lista = $('resultados-fisicos');
  $('buscar-fisico').disabled = true;
  estado.textContent = 'Consultando referencias físicas…';
  lista.replaceChildren();
  const productos = await buscarSucursales(api, termino, {enLinea:navigator.onLine});
  $('buscar-fisico').disabled = false;
  if (termino !== consulta) return;
  consultaFisica = termino;
  estado.textContent = productos === null ? 'La consulta física no está disponible.' :
    productos.length ? 'Referencias físicas, por sucursal' : 'No hay referencias físicas para esta búsqueda.';
  productos?.forEach(p => {
    productosFisicos.set(p.producto_id, p);
    const fila = el('li'), enlace = el('a', p.nombre);
    enlace.href = '#/producto/' + encodeURIComponent(p.producto_id); fila.append(enlace); lista.append(fila);
  });
});
$('busqueda-form').addEventListener('submit', e => { e.preventDefault(); if (datos) iniciarBusqueda($('busqueda').value, true); });
let espera;
$('busqueda').addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(() => iniciarBusqueda($('busqueda').value), 220); });
for (const b of document.querySelectorAll('[data-query]')) b.addEventListener('click', () => { if (datos) iniciarBusqueda(b.dataset.query, true); });
for (const b of $('categorias').querySelectorAll('button')) b.addEventListener('click', () => { if (!datos) return; categoria = b.dataset.category; limite = 12; guardarBusqueda(); renderProductos(); });
$('tienda').addEventListener('change', () => { if (!datos) return; tienda = $('tienda').value; limite = 12; guardarBusqueda(); renderProductos(); });
$('otras-categorias').addEventListener('change', () => { if (!datos) return; categoria = $('otras-categorias').value || 'todos'; limite = 12; guardarBusqueda(); renderProductos(); });
$('limpiar').addEventListener('click', () => { categoria = 'todos'; tienda = ''; iniciarBusqueda(''); });
$('quitar-filtros').addEventListener('click', () => { categoria = 'todos'; tienda = ''; iniciarBusqueda(''); });
$('quitar-busqueda').addEventListener('click', () => { iniciarBusqueda(''); $('busqueda').focus(); });
$('productos').addEventListener('click', e => { const a = e.target.closest('a[data-producto]'); if (a) { posicionResultados = window.scrollY; tarjetaAnterior = a.dataset.producto; } });
for (const a of document.querySelectorAll('.brand')) a.addEventListener('click', () => { posicionResultados = 0; tarjetaAnterior = ''; });
$('ver-mas').addEventListener('click', () => {
  const anterior = limite; limite += 12; renderProductos(anterior);
  $('productos').children[anterior]?.focus({preventScroll: true});
});
$('tienda-ofertas').addEventListener('change', () => {
  const filtro = $('tienda-ofertas').value, id = productoActual();
  history.replaceState(null, '', '#/producto/' + encodeURIComponent(id) + (filtro ? '?tienda=' + filtro : ''));
  limiteOfertas = 8; renderResumen(id); renderOfertas(id, true); renderEvidencia(id);
});
$('mas-ofertas').addEventListener('click', () => { limiteOfertas += 8; renderOfertas(productoActual()); });
$('refrescar').addEventListener('click', () => actualizar(true)); $('reintentar').addEventListener('click', () => actualizar(true));
$('reintentar-detalle').addEventListener('click', () => ruta(false));
window.addEventListener('hashchange', () => { limiteOfertas = 8; ruta(); });
for (const b of document.querySelectorAll('[data-scroll]')) b.addEventListener('click', () => irA($(b.dataset.scroll)));
$('compartir').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(location.href); notificar('Enlace copiado.'); } catch { notificar('Puedes copiar la dirección de esta página desde el navegador.'); }
});
$('acerca').addEventListener('click', () => $('informacion').showModal());
$('form-evaluador').addEventListener('submit', e => { e.preventDefault(); if (datos) mostrarEvaluacion(productoActual()); });
for (const b of [$('ver-modelo'), $('abrir-modelo')]) b.addEventListener('click', () => { renderModeloDialogo(); $('modelo-dialogo').showModal(); });
$('enlace-api').hidden = !api;
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
for (const evento of ['online', 'offline']) window.addEventListener(evento, () => {
  estadoConexion(); evidencia = undefined;
  if (navigator.onLine && Date.now() - ultimoIntento > 60000) actualizar();
  else ruta(false);
});
function renovarVigencia() {
  if (!datos || !location.hash.startsWith('#/producto/')) return;
  const id = productoActual();
  if (evidencia?.id === id && evidencia.estado === 'disponible' && porProducto.has(id)) {
    renderEvidencia(id); renderResumen(id);
  }
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  if (fechaMostrada !== fechaMexico()) { fechaMostrada = fechaMexico(); estadoConexion(); ruta(false); }
  if (Date.now() - ultimoIntento > 600000 && navigator.onLine) actualizar();
  renovarVigencia();
});
setInterval(() => {
  if (datos && fechaMostrada !== fechaMexico()) { fechaMostrada = fechaMexico(); estadoConexion(); ruta(false); }
  else renovarVigencia();
}, 60000);
let redimension;
window.addEventListener('resize', () => {
  clearTimeout(redimension);
  redimension = setTimeout(() => { const p = porProducto.get(productoActual()); if (datos && p) grafico(p); }, 200);
});
await actualizar();
