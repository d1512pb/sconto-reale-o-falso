from datetime import datetime, timezone
import json

import pytest

from sconto.presupuesto_fly_v2 import ARCHIVO, LIMITE_SALIDA_BYTES, PresupuestoFly


NOVIEMBRE = datetime(2026, 11, 30, 23, 59, tzinfo=timezone.utc)
DICIEMBRE = datetime(2026, 12, 1, 0, 1, tzinfo=timezone.utc)
ARRANQUE_1 = 'b4ef5733-8b32-4a73-aa7e-1aab02810ab5'
ARRANQUE_2 = 'ad3a2a66-c0b1-4e52-b23b-ca815ed34b76'


class Medidor:
    def __init__(self, raiz):
        self.raiz = raiz
        self.red = raiz / 'red'
        self.arranque = raiz / 'arranque'
        self.registro = raiz / ARCHIVO
        self.momento = NOVIEMBRE
        self.arranque.write_text(ARRANQUE_1 + '\n', encoding='ascii')

    def presupuesto(self):
        return PresupuestoFly(self.raiz, red=self.red, arranque=self.arranque, reloj=lambda: self.momento)

    def contar(self, **interfaces):
        lineas = ['Inter-|   Receive | Transmit', ' face |bytes |bytes']
        for nombre, tx in interfaces.items():
            lineas.append(f'{nombre}: 42 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0')
        self.red.write_text('\n'.join(lineas) + '\n', encoding='ascii')

    def datos(self):
        return json.loads(self.registro.read_text(encoding='utf-8'))


def test_contabiliza_tx_sin_loopback_ni_duplicar_muestra(tmp_path):
    m = Medidor(tmp_path)
    m.contar(lo=15_000_000_000, eth0=120, tap0=50)
    presupuesto = m.presupuesto()
    assert presupuesto.continuar()
    assert presupuesto.continuar()
    assert m.datos()['bytes_mes'] == 170
    m.contar(lo=15_000_000_123, eth0=130, tap0=60)
    assert presupuesto.continuar()
    assert m.datos()['bytes_mes'] == 190


def test_conserva_consumo_al_reiniciar_programa_y_maquina(tmp_path):
    m = Medidor(tmp_path)
    m.contar(eth0=900)
    assert m.presupuesto().continuar()
    m.contar(eth0=1000)
    assert m.presupuesto().continuar()
    assert m.datos()['bytes_mes'] == 1000
    m.arranque.write_text(ARRANQUE_2, encoding='ascii')
    m.contar(eth0=110)
    assert m.presupuesto().continuar()
    assert m.datos()['bytes_mes'] == 1110


def test_corta_en_limite_y_conserva_bloqueo_hasta_mes_utc_siguiente(tmp_path):
    m = Medidor(tmp_path)
    m.contar(eth0=LIMITE_SALIDA_BYTES - 1)
    assert m.presupuesto().continuar()
    m.contar(eth0=LIMITE_SALIDA_BYTES)
    assert not m.presupuesto().continuar()
    assert m.datos()['detenido']
    m.arranque.write_text(ARRANQUE_2, encoding='ascii')
    m.contar(eth0=2)
    assert not m.presupuesto().continuar()
    m.momento = DICIEMBRE
    assert m.presupuesto().continuar()
    assert m.datos()['mes_utc'] == '2026-12'
    assert m.datos()['bytes_mes'] == 2


def test_cambia_mes_utc_sin_recontar_entero_del_mismo_arranque(tmp_path):
    m = Medidor(tmp_path)
    m.contar(eth0=3700)
    assert m.presupuesto().continuar()
    m.contar(eth0=3800)
    m.momento = DICIEMBRE
    assert m.presupuesto().continuar()
    assert m.datos()['bytes_mes'] == 100


@pytest.mark.parametrize('caso', ['sin_proc', 'incompleto', 'arranque_invalido', 'retroceso'])
def test_cierra_medidor_invalido_y_no_se_reanuda_en_el_mismo_mes(tmp_path, caso):
    m = Medidor(tmp_path)
    m.contar(eth0=100)
    assert m.presupuesto().continuar()
    if caso == 'sin_proc':
        m.red.unlink()
    elif caso == 'incompleto':
        m.red.write_text('red corrupta', encoding='ascii')
    elif caso == 'arranque_invalido':
        m.arranque.write_text('arranque corrupto', encoding='ascii')
    else:
        m.contar(eth0=2)
    assert not m.presupuesto().continuar()
    assert m.datos()['detenido']
    m.arranque.write_text(ARRANQUE_1, encoding='ascii')
    m.contar(eth0=201)
    assert not m.presupuesto().continuar()
    m.momento = DICIEMBRE
    assert m.presupuesto().continuar()
    assert m.datos()['bytes_mes'] == 101


def test_registro_corrupto_se_preserva_y_cierra(tmp_path):
    m = Medidor(tmp_path)
    m.contar(eth0=100)
    original = b'{"bytes_mes":0, "bytes_mes":999}'
    m.registro.write_bytes(original)
    assert not m.presupuesto().continuar()
    assert m.registro.read_bytes() == original
