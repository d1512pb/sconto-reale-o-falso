const CACHE = 'sconto-datos-v1';

async function comprobar(bytes, sha, detalle = false) {
  const calculado = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
  if (calculado !== sha) throw Error('Los datos se están actualizando. Inténtalo de nuevo en unos momentos.');
  const datos = JSON.parse(new TextDecoder().decode(bytes));
  if (detalle ? datos.version !== 'sconto-producto-v1' || !Array.isArray(datos.ofertas) || !Array.isArray(datos.precios_diarios)
    : !['sconto-app-v1', 'sconto-app-v2'].includes(datos.version) || !Array.isArray(datos.productos) || !Array.isArray(datos.ofertas) || !datos.busqueda) throw Error('La versión de los datos no es compatible.');
  return datos;
}

export async function cargarDetalle(catalogo, id) {
  if (catalogo.version === 'sconto-app-v1') return catalogo;
  const archivo = catalogo.detalles?.[id];
  if (!archivo || !/^producto\.[a-f0-9]{16}\.json$/.test(archivo.archivo) || !/^[a-f0-9]{64}$/.test(archivo.sha256)) throw Error('Este producto no tiene una ficha disponible.');
  const clave = new URL(archivo.archivo, location.href.split('#')[0]).href;
  let cache;
  try { cache = await caches.open('sconto-fichas-v1'); } catch { /* La consulta en línea sigue disponible. */ }
  const validar = async bytes => {
    const ficha = await comprobar(bytes, archivo.sha256, true);
    if (ficha.producto_canonico_id !== id || ficha.fecha_corte !== catalogo.fecha_corte) throw Error('La ficha no corresponde a este producto o corte.');
    return ficha;
  };
  const guardada = cache && await cache.match(clave);
  if (guardada) try { return await validar(await guardada.arrayBuffer()); } catch { /* Una copia dañada se descarga de nuevo. */ }
  try {
    const respuesta = await fetch(archivo.archivo, {cache:'no-cache', signal:AbortSignal.timeout(25000)});
    if (!respuesta.ok) throw Error('Ficha no disponible');
    const bytes = await respuesta.arrayBuffer(), ficha = await validar(bytes);
    if (cache) try {
      await cache.put(clave, new Response(bytes, {headers:{'Content-Type':'application/json'}}));
      const claves = await cache.keys();
      for (const antigua of claves.slice(0, Math.max(0, claves.length - 40))) await cache.delete(antigua);
    } catch { /* Una cuota agotada no impide leer la ficha. */ }
    return ficha;
  } catch {
    throw Error('No pudimos cargar esta ficha. Conéctate y vuelve a intentar. Sin conexión puedes abrir las últimas 40 fichas guardadas de este corte.');
  }
}

export async function cargarDatos() {
  const clave = new URL('./ultima-copia-verificada', location.href.split('#')[0]).href;
  let cache;
  try { cache = await caches.open(CACHE); } catch { /* La consulta en línea no depende del almacenamiento. */ }
  try {
    const r = await fetch('snapshot.json', {cache: 'no-store', signal: AbortSignal.timeout(15000)});
    if (!r.ok) throw Error('No se pudo consultar la actualización.');
    const snapshot = await r.json();
    if (!/^datos\.[a-f0-9]{16}\.json$/.test(snapshot.archivo) || !/^[a-f0-9]{64}$/.test(snapshot.sha256)) throw Error('No se reconoce la publicación.');
    const response = await fetch(snapshot.archivo, {cache: 'no-cache', signal: AbortSignal.timeout(45000)});
    if (!response.ok) throw Error('No se pudo descargar la actualización.');
    const bytes = await response.arrayBuffer(), datos = await comprobar(bytes, snapshot.sha256);
    let guardado = false;
    if (cache) try {
      await cache.put(clave, new Response(bytes, {headers: {'Content-Type': 'application/json', 'X-Sconto-SHA256': snapshot.sha256}}));
      guardado = true;
    } catch { /* Una cuota agotada no invalida los datos descargados. */ }
    return {datos, guardado, copia: false};
  } catch (error) {
    const copia = cache && await cache.match(clave);
    if (!copia) throw Error('No pudimos cargar los precios. Conéctate a internet y vuelve a intentar; la primera consulta necesita conexión.');
    const datos = await comprobar(await copia.arrayBuffer(), copia.headers.get('X-Sconto-SHA256'));
    return {datos, guardado: true, copia: true, aviso: error.message};
  }
}
