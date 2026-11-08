"""Iconos originales de Sconto, reproducibles sin descargar recursos externos."""
from pathlib import Path
from PIL import Image, ImageDraw

destino = Path(__file__).resolve().parents[1] / 'web/icons'
destino.mkdir(parents=True, exist_ok=True)
svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="100" fill="#245d4d"/><path d="M326 167H225c-61 0-68 81-4 88l63 7c65 7 61 83-5 83H175" fill="none" stroke="#f6f7f1" stroke-width="33" stroke-linecap="round"/><path d="M311 320l40 40m-40 0h40v-40" fill="none" stroke="#b7ce88" stroke-width="17" stroke-linecap="round" stroke-linejoin="round"/></svg>'
(destino / 'logo.svg').write_text(svg, encoding='utf-8')
imagen = Image.new('RGB', (1024, 1024), '#245d4d')
d = ImageDraw.Draw(imagen)
# La marca queda dentro del área segura de los iconos maskable.
puntos = [(326, 167), (225, 167), (205, 171), (188, 184), (182, 202), (185, 222), (200, 243),
          (221, 255), (284, 262), (305, 269), (320, 286), (323, 306), (317, 326), (300, 341), (279, 345), (175, 345)]
d.line([(x*2, y*2) for x, y in puntos], fill='#f6f7f1', width=66, joint='curve')
for x,y in (puntos[0],puntos[-1]): d.ellipse((x*2-33,y*2-33,x*2+33,y*2+33),fill='#f6f7f1')
d.line([(622,640),(702,720),(622,720),(702,720),(702,640)],fill='#b7ce88',width=34,joint='curve')
for nombre, tam in [('icon-192.png',192),('icon-512.png',512),('apple-touch-icon.png',180)]:
    imagen.resize((tam,tam),Image.Resampling.LANCZOS).save(destino/nombre)
