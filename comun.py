"""Funciones compartidas. Descarga con TLS, trazabilidad y cálculos sin pandas."""
import calendar
import csv
import hashlib
import io
import json
import math
import re
import statistics
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = 'https://estadisticas.bcrp.gob.pe/estadisticas/series/api'
MESES = dict(zip(['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'], range(1,13)))
MESES.update(dict(zip(['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'],range(1,13))))
MESES['set'] = 9

def config():
    c = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
    if date.fromisoformat(c['inicio']) > date.fromisoformat(c['fin']):
        raise ValueError('inicio debe ser anterior a fin')
    if c['plazo_dias'] not in (30,60,90) or c['base_dias'] not in (360,365):
        raise ValueError('Use plazo de 30, 60 o 90 días y base de 360 o 365')
    if c.get('saldo_modo') != 'rezago_mensual_t1':
        raise ValueError('saldo_modo debe ser rezago_mensual_t1')
    if c.get('saldo_definicion') != 'neto_total':
        raise ValueError('saldo_definicion debe ser neto_total (PN09550TM)')
    if date.fromisoformat(c['inicio_premuestra_diaria']) >= date.fromisoformat(c['inicio']):
        raise ValueError('La pre-muestra diaria debe comenzar antes del estudio')
    if not isinstance(c.get('ventana_volatilidad_dias'), int) or c['ventana_volatilidad_dias'] < 2:
        raise ValueError('ventana_volatilidad_dias debe ser entero mayor que 1')
    if c.get('indicadores_al_cierre') is not True:
        raise ValueError('Este flujo calcula indicadores al cierre; use indicadores_al_cierre=true')
    return c

def guardar_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def guardar_csv(path, rows, fields=None):
    rows = list(rows)
    if not rows and fields is None:
        raise ValueError('No hay datos para exportar')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def leer_csv(path):
    if not path.exists():
        raise FileNotFoundError(f'Falta {path.name}. Ejecute los pasos previos.')
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def descargar(url, destino):
    # En este equipo las variables de proxy apuntan a un proxy local no disponible.
    # La API BCRP es accesible directamente, así que no heredamos ese proxy roto.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for intento in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'ProyectoAcademicoCobertura/1.0'})
            with opener.open(req, timeout=60) as r:
                body = r.read()
            if not body:
                raise ValueError('Respuesta vacía')
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(body)
            guardar_json(destino.with_suffix(destino.suffix+'.fuente.json'), {
                'url':url, 'descarga_utc':datetime.now(timezone.utc).isoformat(),
                'sha256':hashlib.sha256(body).hexdigest(), 'bytes':len(body)})
            return body
        except Exception as error:
            if intento == 2:
                raise RuntimeError(f'No se pudo descargar {url}: {error}') from error
            time.sleep(1+intento)

def numero(valor):
    s = str(valor).strip().replace('\u00a0','').replace(' ','')
    if s.lower() in ('','n.d.','n.d','nd','nan','none','-','s.d.'):
        return None
    # BCRP usa punto decimal; una coma es separador de miles.
    result = float(s.replace(',',''))
    return result if math.isfinite(result) else None

def fecha(valor):
    s = str(valor).strip().lower()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    m = re.fullmatch(r'(\d{1,2})[.\-/ ]([a-z]{3})[.\-/ ](\d{2}|\d{4})',s)
    if m:
        d, mo, y = m.groups()
        year = int(y) if len(y)==4 else 2000+int(y)
        return date(year, MESES[mo], int(d))
    m = re.fullmatch(r'([a-z]{3})[.\-/ ]?(\d{2}|\d{4})',s)
    if m:
        mo, y = m.groups()
        year = int(y) if len(y)==4 else 2000+int(y)
        month = MESES[mo]
        return date(year, month, calendar.monthrange(year, month)[1])
    raise ValueError(f'Fecha BCRP no reconocida: {valor!r}')

def fin_mes(d):
    return date(d.year,d.month,calendar.monthrange(d.year,d.month)[1])

def parsear_csv_bcrp(body, variables):
    text = body.decode('utf-8-sig')
    if '<html' in text.lower() or '<!doctype' in text.lower():
        raise ValueError('El servidor entregó HTML en lugar de CSV')
    out = []
    for delimiter in [',',';','\t']:
        out = []
        for row in csv.reader(io.StringIO(text), delimiter=delimiter):
            if not row: continue
            try: d = fecha(row[0])
            except (ValueError, KeyError): continue
            if len(row) != len(variables)+1:
                continue
            out.append({'fecha':d.isoformat(), **dict(zip(variables,row[1:]))})
        if out: return out
    raise ValueError('CSV sin filas reconocibles; revise original y formato del portal')

def forward_teorico(spot, mn, me, dias, base):
    den = 1+(me/100)*(dias/base)
    if spot<=0 or den<=0:
        raise ValueError('Spot o denominador de paridad inválido')
    return spot*(1+(mn/100)*(dias/base))/den

def efectividad(no_cubierto, cubierto):
    if len(no_cubierto)!=len(cubierto) or len(cubierto)<3:
        raise ValueError('Se requieren al menos tres pares comparables')
    var = statistics.variance(no_cubierto)
    if var == 0:
        raise ValueError('Varianza sin cobertura igual a cero')
    return 1-statistics.variance(cubierto)/var

def ejecutar(main):
    try: main()
    except Exception as error:
        raise SystemExit(f'ERROR: {error}') from error
