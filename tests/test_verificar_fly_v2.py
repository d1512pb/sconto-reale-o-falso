from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


_ruta = Path(__file__).resolve().parents[1] / 'scripts' / 'verificar_fly_v2.py'
_spec = importlib.util.spec_from_file_location('verificar_fly_v2', _ruta)
fly = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fly)


def test_solo_consulta_cli_oficial_y_omite_datos_de_identidad():
    llamadas = []
    salidas = [b'cuenta-privada@example.test',
               b'Name : nombre privado\r\nSlug : personal\r\nType : PERSONAL\r\n',
               b'[{"name":"app-privada"}]']

    def fake(args, **kwargs):
        llamadas.append(args[1:])
        assert kwargs['capture_output'] and kwargs['stdin'] == subprocess.DEVNULL
        return subprocess.CompletedProcess(args, 0, salidas.pop(0), b'DIAGNOSTICO_PRIVADO')

    estado = fly.verificar('flyctl', ejecutar=fake, entorno={})
    assert llamadas == [['auth', 'whoami'], ['orgs', 'show', 'personal'],
                        ['apps', 'list', '--org', 'personal', '--json']]
    assert estado == dict(sesion_autenticada=True, organizacion='personal', aplicaciones=1)


def test_error_nunca_incluye_salida_ni_identidad(monkeypatch, capsys):
    def fake(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, b'IDENTIDAD_QUEDA_PRIVADA', b'TOKEN_SIMULADO_NO_MOSTRAR')

    monkeypatch.setattr(fly.shutil, 'which', lambda nombre: 'flyctl')
    monkeypatch.setattr(fly, 'verificar', lambda cli: fly._cli(cli, ('auth', 'whoami'), fake))
    assert fly.main([]) == 2
    salida = capsys.readouterr()
    assert json.loads(salida.out)['verificado'] is False
    assert 'TOKEN_SIMULADO' not in salida.out + salida.err and 'IDENTIDAD_QUEDA_PRIVADA' not in salida.out


def test_override_impide_cualquier_llamada_al_cli():
    with pytest.raises(fly.VerificacionFlyError, match='credencial de entorno'):
        fly.verificar('flyctl', ejecutar=lambda *a, **kw: pytest.fail('CLI llamado'),
                      entorno={'FLY_API_TOKEN': 'valores no utilizados'})


def test_solo_aprueba_con_facturacion_verificada_y_debajo_del_limite():
    assert fly.presupuesto()['api_usd'] == '2.44'
    assert not fly.presupuesto(Decimal('0.00'), True, False)['dentro_del_presupuesto']
    assert fly.presupuesto(Decimal('1.55'), True, True)['dentro_del_presupuesto']
    assert not fly.presupuesto(Decimal('1.56'), True, True)['dentro_del_presupuesto']
    respaldo = fly.presupuesto(Decimal('0.30'), True, True, salida_gb=Decimal('7'))
    assert respaldo['api_usd'] == '2.56' and respaldo['total_usd'] == '2.86'
    assert respaldo['dentro_del_presupuesto']
    anterior = fly.presupuesto(Decimal('0'), True, True, salida_gb=Decimal('7'), memoria=512)
    assert anterior['api_usd'] == '4.11' and not anterior['dentro_del_presupuesto']
