"""Congela copias de bronze y verifica el ETL diario contra el paquete gold del mismo día."""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import file_digest
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd

from sconto.colab import cargar_paquete
from sconto.dataset import FUENTES_OBS
from sconto.v2_corte import conciliar_por_fuente

ROOT = Path(__file__).resolve().parents[1]


def sha256(ruta):
    with ruta.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def copiar_verificado(origen, destino, relativo):
    antes = sha256(origen / relativo)
    (destino / relativo).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen / relativo, destino / relativo)
    if sha256(destino / relativo) != antes or sha256(origen / relativo) != antes:
        raise ValueError(f'Entrada cambió al fijar el corte: {relativo.as_posix()}')
    return antes


def ejecutar(args):
    origen, salida = args.origen.resolve(strict=True), args.salida.resolve()
    if salida.is_relative_to(origen) or origen.is_relative_to(salida):
        raise ValueError('El origen y la reconstrucción deben ser carpetas distintas')
    salida.mkdir(parents=True, exist_ok=False)
    rutas = [Path('config') / nombre for nombre in ('eventos.yaml', 'productos_objetivo.csv', 'preciometro_diarios.csv')]
    for fuente in FUENTES_OBS:
        rutas.extend(ruta.relative_to(origen) for ruta in sorted((origen / 'data/bronze' / fuente).glob('*.parquet')))
    entradas = {r.as_posix(): copiar_verificado(origen, salida, r) for r in rutas}
    codigo = Path(__file__).resolve().parents[1] / 'src'
    if (origen / '.git').exists():
        revision = subprocess.check_output(['git', '-C', str(origen), 'rev-parse', 'HEAD'], text=True).strip()
    else:
        revision = None
    entorno = os.environ | {'SCONTO_RAIZ': str(salida), 'PYTHONPATH': str(codigo), 'PYTHONIOENCODING': 'utf-8'}
    fecha = args.fecha.isoformat()
    comando = [sys.executable, '-c', 'from sconto.dataset import construir; import sys; construir(sys.argv[1])', fecha]
    print('Bronze copiado y firmado, iniciando el ETL diario.', flush=True)
    subprocess.run(comando, env=entorno, check=True)
    archivo = salida / ('sconto_entrada_v2_' + fecha + '.zip')
    crear_entrada = [sys.executable, '-m', 'sconto.cuaderno', '--gold', str(args.gold.resolve(strict=True)),
                     '--salida', str(archivo), '--fecha-corte', fecha]
    subprocess.run(crear_entrada, env=entorno, check=True, stdout=subprocess.DEVNULL)
    referencia = cargar_paquete(args.gold)
    gold = {nombre: pd.read_parquet(salida / 'data/gold' / (nombre + '.parquet')) for nombre in referencia}
    for nombre, esperado in referencia.items():
        pd.testing.assert_frame_equal(gold[nombre], esperado, check_dtype=False, check_exact=True, obj=nombre)
    bruto = pd.concat([pd.read_parquet(salida / r, columns=['fuente', 'fecha_captura'])
                       for r in rutas if r.suffix == '.parquet'], ignore_index=True)
    if pd.to_datetime(bruto.fecha_captura, errors='coerce').gt(pd.Timestamp(fecha)).any():
        raise ValueError('Bronze contiene filas posteriores; selecciona el origen del corte')
    conciliacion = conciliar_por_fuente(bruto, gold)
    if conciliacion.diferencia.ne(0).any():
        raise ValueError('No concilia por fuente')
    conciliacion.to_csv(salida / 'conciliacion_fuentes.csv', index=False)

    resultado = dict(revision_origen=revision, fecha_corte=fecha, origen_entradas=entradas,
                     sha256_entrada_notebook=sha256(archivo), sha256_gold_referencia=sha256(args.gold),
                     sha256_manifiesto_gold=sha256(salida / 'data/gold/manifiesto.json'),
                     equivalencia_tablas=sorted(gold))
    if args.contraste:
        previo = cargar_paquete(args.contraste)
        fechas = pd.to_datetime(bruto.fecha_captura, errors='raise')
        previo_ultimo = pd.to_datetime(previo['observaciones'].fecha_captura, errors='raise').max()
        fecha_contraste = pd.Timestamp(args.fecha_contraste)
        if fecha_contraste > pd.Timestamp(fecha):
            raise ValueError('La fecha de contraste debe quedar dentro del corte fijado')
        contraste = conciliar_por_fuente(bruto.loc[fechas.le(fecha_contraste)], previo)
        nuevas = bruto.loc[fechas.gt(previo_ultimo) & fechas.le(fecha_contraste)].groupby(
            ['fecha_captura', 'fuente'], as_index=False).size()
        contraste.to_csv(salida / 'contraste_cortes.csv', index=False)
        nuevas.to_csv(salida / 'capturas_entre_cortes.csv', index=False)
        resultado['contraste'] = dict(ultimo_dia_gold=str(previo_ultimo.date()),
                                      ultimo_dia_bronze=args.fecha_contraste,
                                      diferencia=int(contraste.diferencia.sum()))
    prueba = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(ROOT / 'tests/test_dataset.py')],
                            env=entorno, capture_output=True, text=True, encoding='utf-8', cwd=ROOT)
    (salida / 'prueba_dataset.txt').write_text(prueba.stdout + prueba.stderr, encoding='utf-8')
    resultado['codigo_salida_pruebas'] = prueba.returncode
    (salida / 'manifiesto_corte.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2),
                                                encoding='utf-8')
    print(conciliacion.to_string(index=False), flush=True)
    print(prueba.stdout, flush=True)
    if prueba.returncode:
        raise RuntimeError('La prueba de conciliación existente falló. Revisa prueba_dataset.txt')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origen', type=Path, required=True)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--fecha', type=date.fromisoformat, required=True)
    parser.add_argument('--gold', type=Path, required=True)
    parser.add_argument('--contraste', type=Path)
    parser.add_argument('--fecha-contraste')
    opciones = parser.parse_args()
    if bool(opciones.contraste) != bool(opciones.fecha_contraste):
        parser.error('El contraste requiere paquete gold y fecha bronze')
    ejecutar(opciones)
