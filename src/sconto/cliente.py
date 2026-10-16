"""Cliente HTTP respetuoso, común a todas las fuentes.

Reglas (README, "Scraping responsable"):
- user-agent honesto con contacto académico;
- robots.txt se consulta antes de cada ruta;
- pausa con jitter entre peticiones al mismo host (3–8 s por defecto);
- 429/503 → espera exponencial y pocos reintentos; CAPTCHA/403 → `Bloqueado`, sin reintentar en bucle;
- sin login, sin proxies, sin evadir protecciones.
"""
from __future__ import annotations

import logging
import os
import random
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

from sconto.rutas import RAIZ

load_dotenv(RAIZ / '.env')
log = logging.getLogger(__name__)

_contacto = os.environ.get('SCONTO_CONTACTO', '').strip()
USER_AGENT = ('ScontoRealeOFalso/0.1 (proyecto academico ESCOM-IPN, Mineria de Datos; uso no comercial'
              + (f'; contacto: {_contacto}' if _contacto else '') + ')')

MARCAS_CAPTCHA = ('captcha', 'validatecaptcha', 'robot check', 'are you a robot', 'verifica que eres humano',
                  'unusual traffic', 'actividad inusual', 'cf-challenge', 'challenge-platform')


class Bloqueado(Exception):
    """La fuente respondió con CAPTCHA/403/bloqueo: se registra y se reintenta otro día."""


class NoPermitido(Exception):
    """robots.txt no permite la ruta para nuestro user-agent."""


class Cliente:
    def __init__(self, pausa=(3.0, 8.0), reintentos=3, timeout=(20, 60), respetar_robots=True,
                 user_agent=USER_AGENT, detectar_captcha=True):
        self.pausa = pausa
        self.reintentos = reintentos
        self.timeout = timeout
        self.respetar_robots = respetar_robots
        self.detectar_captcha = detectar_captcha
        self.sesion = requests.Session()
        self.sesion.headers.update({'User-Agent': user_agent, 'Accept-Language': 'es-MX,es;q=0.9'})
        self._ultimo = {}
        self._robots = {}

    def _robots_permite(self, url):
        partes = urlsplit(url)
        host = f'{partes.scheme}://{partes.netloc}'
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.sesion.get(host + '/robots.txt', timeout=self.timeout)
                if r.status_code >= 400:
                    rp.allow_all = True  # sin robots.txt publicado
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp.allow_all = True
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.sesion.headers['User-Agent'], url)

    def _esperar(self, host):
        previo = self._ultimo.get(host)
        if previo is not None:
            espera = random.uniform(*self.pausa) - (time.monotonic() - previo)
            if espera > 0:
                time.sleep(espera)
        self._ultimo[host] = time.monotonic()

    def get(self, url, **kw) -> requests.Response:
        if self.respetar_robots and not self._robots_permite(url):
            raise NoPermitido(url)
        host = urlsplit(url).netloc
        kw.setdefault('timeout', self.timeout)
        for intento in range(self.reintentos + 1):
            self._esperar(host)
            try:
                r = self.sesion.get(url, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                if intento == self.reintentos:
                    raise
                log.warning('red %s en %s; reintento %s', type(e).__name__, url, intento + 1)
                time.sleep(min(300, 10 * 2 ** intento))
                continue
            if r.status_code in (429, 503) and intento < self.reintentos:
                espera = r.headers.get('Retry-After')
                espera = int(espera) if espera and espera.isdigit() else 15 * 2 ** intento
                log.warning('HTTP %s en %s; espera %ss', r.status_code, url, espera)
                time.sleep(min(espera, 600))
                continue
            if r.status_code == 403:
                raise Bloqueado(f'403 {url}')
            if self.detectar_captcha and 'html' in r.headers.get('content-type', ''):
                inicio = r.text[:20000].lower()
                if any(m in inicio for m in MARCAS_CAPTCHA):
                    raise Bloqueado(f'captcha {url}')
            if r.status_code in (429, 503):
                raise Bloqueado(f'{r.status_code} persistente {url}')
            return r
        raise RuntimeError('inalcanzable')
