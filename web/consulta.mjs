export function comparar(ref, precio, tachado=null, pct=null, misma=false) {
  if(!Number.isFinite(precio)||precio<=0) throw Error('Escribe un precio mayor que cero.');
  if(tachado!==null&&(!Number.isFinite(tachado)||tachado<=0)) throw Error('El tachado debe ser mayor que cero.');
  if(pct!==null&&(!Number.isFinite(pct)||pct < -100 || pct > 100)) throw Error('El porcentaje debe estar entre −100 y 100.');
  const r={estado:'evidencia_insuficiente',diferencia:null,brecha:null,implicito:tachado===null?null:100*(1-precio/tachado)};
  if(!ref||!ref.cobertura_base||!ref.base_cerrada||ref.moneda!=='MXN'||ref.canal!=='en_linea') return r;
  if(!Number.isFinite(ref.mediana_base)||ref.mediana_base<=0||!Number.isFinite(ref.p25_base)||!Number.isFinite(ref.p75_base)) return r;
  r.diferencia=100*(1-precio/ref.mediana_base);
  r.estado=precio<ref.p25_base?'debajo_del_rango':precio>ref.p75_base?'encima_del_rango':'dentro_del_rango';
  if(ref.contexto==='serie_vendedor'&&misma&&pct!==null) r.brecha=pct-r.diferencia;
  return r;
}
