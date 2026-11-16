import {edadDias, enlaceSeguro, fechaMexico} from './motor.mjs';

const VERSION = 'sconto-api-v1';
const ESTADOS = new Set(['precio_favorable', 'precio_alto', 'sin_senal_clara', 'evidencia_insuficiente']);
const ID = /^[A-Za-z0-9_-]{1,80}$/;
const UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const formatoHora = new Intl.DateTimeFormat('es-MX', {dateStyle:'medium', timeStyle:'medium', timeZone:'America/Mexico_City'});
const positivo = monto => Number.isFinite(monto) && monto > 0;
const fechaHora = valor => typeof valor === 'string' && UTC.test(valor) ? Date.parse(valor) : NaN;

export function baseAPI(valor, pagina = location.href) {
  if (!valor) return null;
  try {
    const actual = new URL(pagina), base = new URL(valor, actual);
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname) && base.hostname === actual.hostname;
    if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
        (base.protocol !== 'https:' && !(base.protocol === 'http:' && loopback))) return null;
    return base.origin;
  } catch { return null; }
}

async function respuesta(base, ruta, fetcher) {
  const respuesta = await fetcher(base + ruta, {cache:'no-store', credentials:'omit', redirect:'error', signal:AbortSignal.timeout(6500)});
  if (!respuesta.ok) throw Error('API no disponible');
  const datos = await respuesta.json();
  if (datos?.version !== VERSION) throw Error('Respuesta incompatible');
  return datos;
}

export async function consultarProducto(base, id, {fetcher = fetch, enLinea = true} = {}) {
  if (!base || !ID.test(id)) return {estado:'sin_configurar', ofertas:[], historia:[]};
  if (!enLinea) return {estado:'sin_conexion', ofertas:[], historia:[]};
  const fisico = id.startsWith('PROFECO-BF26-');
  const tipo = fisico ? 'history' : 'offers';
  try {
    const datos = await respuesta(base, `/v1/products/${encodeURIComponent(id)}/${tipo}?limit=30`, fetcher);
    const filas = fisico ? datos.precios_diarios : datos.ofertas;
    if (datos.producto_id !== id || !Array.isArray(filas) || filas.length > 30) throw Error('Producto incorrecto');
    const ofertas = fisico ? [] : filas.filter(o => o && o.producto_id === id && o.canal === 'en_linea' &&
      typeof o.offer_id === 'string' && o.moneda === 'MXN' && positivo(o.precio));
    const hoy = fechaMexico();
    const historia = fisico ? filas.filter(o => {
      const edad = edadDias(o?.fecha_precio, hoy);
      return o?.canal === 'tienda_fisica' && o.moneda === 'MXN' && positivo(o.precio) && edad !== null && edad >= 0;
    }) : [];
    return {estado:'disponible', ofertas, historia};
  } catch { return {estado:'error', ofertas:[], historia:[]}; }
}

export function vistaOferta(oferta, ahora = Date.now()) {
  const decision = oferta.decision || {};
  const observado = oferta.precision_temporal === 'instante' ? fechaHora(oferta.observed_at) : NaN;
  const valido = Number.isFinite(observado) && observado <= ahora;
  const vencimiento = fechaHora(decision.vigente_hasta_utc);
  const vigente = valido && Number.isFinite(vencimiento) && vencimiento > ahora;
  const minutos = valido ? Math.floor((ahora - observado) / 60000) : null;
  const antiguedad = minutos === null ? '' : minutos < 1 ? 'hace menos de un minuto' : minutos < 60 ? `hace ${minutos} min` :
    minutos < 1440 ? `hace ${Math.floor(minutos / 60)} h` : `hace ${Math.floor(minutos / 1440)} días`;
  const motivos = Array.isArray(decision.motivos) ? decision.motivos.filter(m => typeof m === 'string') : [];
  const fecha = valido ? formatoHora.format(observado) + ' CDMX · ' + antiguedad : oferta.fecha_precio || 'Hora del precio sin confirmar';
  const fuenteActualizo = fechaHora(oferta.source_updated_at), consulta = fechaHora(oferta.fetched_at_utc);
  const enlace = enlaceSeguro(oferta.enlace);
  return {...oferta, enlace, fecha, vigente, estado: vigente && ESTADOS.has(decision.estado) ? decision.estado : 'evidencia_insuficiente',
    actualizado: Number.isFinite(fuenteActualizo) ? formatoHora.format(fuenteActualizo) + ' CDMX' : null,
    consultado: Number.isFinite(consulta) ? formatoHora.format(consulta) + ' CDMX' : null,
    motivos: valido && Number.isFinite(vencimiento) && !vigente && !motivos.includes('dato_vencido') ? [...motivos, 'dato_vencido'] : motivos,
    ahorro: vigente && Number.isFinite(decision.ahorro_pct) ? decision.ahorro_pct : null,
    referencia: vigente ? decision.referencia : null,
    total: positivo(oferta.costo_total_confirmado) ? oferta.costo_total_confirmado : null};
}

export function registroHistorico(oferta, hoy = fechaMexico()) {
  const dias = edadDias(oferta.fecha_precio, hoy);
  return {...oferta, dias,
    antiguedad: dias === null || dias < 0 ? 'antigüedad desconocida' : dias === 0 ? 'hoy' : dias === 1 ? 'hace 1 día' : `hace ${dias} días`,
    indicador:'evidencia_insuficiente', comparable:false, vigente:false};
}

export async function buscarSucursales(base, consulta, {fetcher = fetch, enLinea = true} = {}) {
  if (!base || !enLinea || typeof consulta !== 'string' || consulta.trim().length < 3) return null;
  try {
    const params = new URLSearchParams({q:consulta.slice(0, 100), canal:'tienda_fisica', limit:'12'});
    const {productos} = await respuesta(base, '/v1/products?' + params, fetcher);
    if (!Array.isArray(productos) || productos.length > 12) return null;
    return productos.filter(p => typeof p?.nombre === 'string' && /^PROFECO-BF26-\d+$/.test(p.producto_id));
  } catch { return null; }
}
