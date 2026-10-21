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
from urllib.parse import urljoin, urlsplit

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

    def __init__(self, mensaje, respuesta=None):
        super().__init__(mensaje)
        self.respuesta = respuesta


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
        self._demora_robots = {}

    def _robots_permite(self, url):
        partes = urlsplit(url)
        host = f'{partes.scheme}://{partes.netloc}'
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._esperar(partes.netloc)
                r = self.sesion.get(host + '/robots.txt', timeout=self.timeout)
                if r.status_code in (404, 410):
                    rp.allow_all = True
                elif r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code != 200:
                    raise NoPermitido(f'No se pudo verificar robots.txt: HTTP {r.status_code} en {host}')
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException as error:
                raise NoPermitido(f'No se pudo verificar robots.txt de {host}') from error
            self._robots[host] = rp
            agente = self.sesion.headers['User-Agent']
            demora = rp.crawl_delay(agente) or rp.crawl_delay('*') or 0
            ritmo = rp.request_rate(agente) or rp.request_rate('*')
            if ritmo and ritmo.requests:
                demora = max(demora, ritmo.seconds / ritmo.requests)
            self._demora_robots[partes.netloc] = demora
        return self._robots[host].can_fetch(self.sesion.headers['User-Agent'], url)

    def _esperar(self, host):
        previo = self._ultimo.get(host)
        if previo is not None:
            espera = max(random.uniform(*self.pausa), self._demora_robots.get(host, 0)) - (time.monotonic() - previo)
            if espera > 0:
                time.sleep(espera)
        self._ultimo[host] = time.monotonic()

    def get(self, url, **kw) -> requests.Response:
        redirecciones = kw.pop('_redirecciones', 0)
        if redirecciones > 5:
            raise Bloqueado(f'Demasiadas redirecciones en {url}')
        if urlsplit(url).scheme not in ('http', 'https'):
            raise ValueError('Sólo se permiten URLs HTTP(S)')
        if self.respetar_robots and not self._robots_permite(url):
            raise NoPermitido(url)
        host = urlsplit(url).netloc
        kw.setdefault('timeout', self.timeout)
        kw['allow_redirects'] = False
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
            if r.status_code == 403:
                raise Bloqueado(f'403 {url}', r)
            if self.detectar_captcha and 'html' in r.headers.get('content-type', ''):
                inicio = r.text[:20000].lower()
                if any(m in inicio for m in MARCAS_CAPTCHA):
                    raise Bloqueado(f'captcha {url}', r)
            if r.is_redirect:
                destino = urljoin(url, r.headers['Location'])
                if any(marca in urlsplit(destino).path.lower() for marca in
                       ('/signin', '/login', '/account-verification', '/validatecaptcha', '/ap/signin')):
                    raise Bloqueado(f'Redirección a verificación/login desde {url}', r)
                siguientes = dict(kw)
                siguientes.pop('params', None)
                if urlsplit(destino).netloc != host:
                    raise Bloqueado(f'Redirección a otro dominio: {destino}', r)
                final = self.get(destino, _redirecciones=redirecciones + 1, **siguientes)
                final.history = [r] + list(final.history)
                return final
            if r.status_code in (429, 503) and intento < self.reintentos:
                espera = r.headers.get('Retry-After')
                espera = int(espera) if espera and espera.isdigit() else 15 * 2 ** intento
                log.warning('HTTP %s en %s; espera %ss', r.status_code, url, espera)
                time.sleep(min(espera, 600))
                continue
            if r.status_code in (429, 503):
                raise Bloqueado(f'{r.status_code} persistente {url}', r)
            return r
        raise RuntimeError('inalcanzable')
