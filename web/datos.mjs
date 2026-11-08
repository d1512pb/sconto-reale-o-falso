const CACHE = 'sconto-datos-v1';

async function comprobar(bytes, sha) {
  const calculado = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
  if (calculado !== sha) throw Error('Los datos se están actualizando. Inténtalo de nuevo en unos momentos.');
  const datos = JSON.parse(new TextDecoder().decode(bytes));
  if (datos.version !== 'sconto-app-v1' || !Array.isArray(datos.productos) || !Array.isArray(datos.ofertas) || !datos.busqueda) throw Error('La versión de los datos no es compatible.');
  return datos;
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
