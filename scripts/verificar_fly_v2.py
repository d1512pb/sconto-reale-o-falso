"""Verifica el acceso y estima el presupuesto sin obtener la credencial de Fly.io."""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
import os
import re
import shutil
import subprocess


class VerificacionFlyError(RuntimeError):
    """Error apto para mostrar. La salida del CLI nunca forma parte del mensaje."""


def _cli(ejecutable, args, ejecutar, *, respuesta_json=False):
    try:
        resultado = ejecutar([ejecutable, *args], stdin=subprocess.DEVNULL, capture_output=True,
                             timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise VerificacionFlyError('El CLI no está disponible o agotó el tiempo de espera.') from None
    if resultado.returncode:
        raise VerificacionFlyError('Fly no confirmó la consulta. Comprueba tu sesión con flyctl auth login.')
    if not respuesta_json:
        return resultado.stdout.strip()
    try:
        return json.loads(resultado.stdout)
    except (ValueError, UnicodeError):
        raise VerificacionFlyError('El CLI devolvió una respuesta con formato inesperado.') from None


def verificar(ejecutable, *, ejecutar=subprocess.run, entorno=None):
    entorno = os.environ if entorno is None else entorno
    if {'FLY_API_TOKEN', 'FLY_ACCESS_TOKEN'}.intersection(entorno):
        raise VerificacionFlyError('Hay una credencial de entorno configurada. Usa la sesión local del CLI.')
    if not _cli(ejecutable, ('auth', 'whoami'), ejecutar):
        raise VerificacionFlyError('No se encontró una sesión local autenticada.')
    personal = _cli(ejecutable, ('orgs', 'show', 'personal'), ejecutar)
    # El JSON de «orgs list» sólo trae slug y nombre. Los campos del resumen confirman tipo y slug.
    if not (re.search(rb'(?mi)^Slug[ \t]*:[ \t]*personal[ \t]*\r?$', personal)
            and re.search(rb'(?mi)^Type[ \t]*:[ \t]*PERSONAL[ \t]*\r?$', personal)):
        raise VerificacionFlyError('No se confirmó el tipo de la organización personal.')
    apps = _cli(ejecutable, ('apps', 'list', '--org', 'personal', '--json'), ejecutar, respuesta_json=True)
    if apps is None:
        apps = []
    if not isinstance(apps, list):
        raise VerificacionFlyError('El listado de aplicaciones tiene un formato inesperado.')
    return {'sesion_autenticada': True, 'organizacion': 'personal', 'aplicaciones': len(apps)}


def presupuesto(otros=None, pago_por_uso=False, metodo_de_pago=False, *, salida_gb=Decimal('1'), memoria=256):
    # Precios de iad documentados. Dimensiona 31 días y la transferencia prevista en Norteamérica.
    computo = {256: Decimal('2.19'), 512: Decimal('3.69')}[memoria]
    estimado = ((computo + Decimal('0.15')) * 31 / 30 + Decimal('0.02') * salida_gb).quantize(
        Decimal('0.01'), rounding=ROUND_CEILING)
    limite = Decimal('4.00')
    total = estimado + otros if otros is not None else None
    confirmado = pago_por_uso and metodo_de_pago and total is not None
    return {'api_usd': str(estimado), 'total_usd': str(total) if total is not None else None,
            'limite_usd': str(limite), 'facturacion_confirmada': confirmado,
            'dentro_del_presupuesto': confirmado and total < limite}


def _usd(texto):
    try:
        valor = Decimal(texto)
        if valor.is_finite() and valor >= 0:
            return valor
    except InvalidOperation:
        pass
    raise argparse.ArgumentTypeError('Se requiere un importe positivo o cero.')


def main(av=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--otros-usd', type=_usd, help='Proyección mensual de gastos ajenos a esta API, verificada en Billing')
    p.add_argument('--salida-gb', type=_usd, default=Decimal('1'),
                   help='Transferencia saliente mensual proyectada, incluidos los respaldos remotos')
    p.add_argument('--memoria', type=int, choices=(256, 512), default=256,
                   help='Memoria en MB de la única máquina en Ashburn')
    p.add_argument('--pago-por-uso', action='store_true', help='El panel confirma Pay As You Go')
    p.add_argument('--metodo-de-pago', action='store_true', help='El panel confirma un método de pago registrado')
    args = p.parse_args(av)
    cli = shutil.which('flyctl') or shutil.which('fly')
    try:
        if not cli:
            raise VerificacionFlyError('Instala el CLI oficial de Fly.io.')
        estado = verificar(cli)
    except VerificacionFlyError as error:
        print(json.dumps({'verificado': False, 'motivo': str(error)}, ensure_ascii=False))
        return 2
    estado['presupuesto'] = presupuesto(args.otros_usd, args.pago_por_uso, args.metodo_de_pago,
                                        salida_gb=args.salida_gb, memoria=args.memoria)
    print(json.dumps(estado, ensure_ascii=False))
    return 0 if estado['presupuesto']['dentro_del_presupuesto'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
