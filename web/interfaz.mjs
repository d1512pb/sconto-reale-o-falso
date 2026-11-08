const movimientoReducido = matchMedia('(prefers-reduced-motion: reduce)');
const animaciones = new Set();

export function entrada(elementos, escalon = 30) {
  if (movimientoReducido.matches) return;
  const lista = elementos instanceof Element ? [elementos] : Array.from(elementos);
  lista.forEach((nodo, i) => {
    if (!nodo.animate) return;
    for (const anterior of nodo.getAnimations()) anterior.cancel();
    const animacion = nodo.animate([
      {opacity: 0, translate: '0 10px'},
      {opacity: 1, translate: '0 0'}
    ], {duration: 300, delay: Math.min(i, 5) * escalon, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'backwards'});
    animaciones.add(animacion);
    animacion.finished.then(() => animaciones.delete(animacion), () => animaciones.delete(animacion));
  });
}

export function irA(nodo) {
  nodo.scrollIntoView({behavior: movimientoReducido.matches ? 'instant' : 'smooth', block: 'start'});
  if (nodo.hasAttribute('tabindex')) nodo.focus({preventScroll: true});
}

movimientoReducido.addEventListener('change', () => {
  if (movimientoReducido.matches) for (const animacion of animaciones) animacion.cancel();
});
