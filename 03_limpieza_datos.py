"""Paso 3: matriz diaria al cierre, con alineación de publicaciones verificables."""
import json
import math
import statistics
from datetime import date, datetime, timezone
from comun import ROOT, config, ejecutar, fecha, forward_teorico, guardar_csv, guardar_json, leer_csv, numero

FINAL = ['fecha','tc_spot','tasa_mn','tasa_me','saldo_forwards',
         'tc_forward_teorico','punto_swap_teorico','volatilidad_spot',
         'periodo_referencia_saldo','fecha_disponibilidad_supuesta_saldo',
         'antiguedad_meses_saldo','saldo_t1_exacto','origen_saldo',
         'retorno_log_diario','n_retornos_ventana']


def alinear_saldos(spot_dates, monthly):
    """Último saldo neto cuyo mes siguiente ya comenzó; equivalente a merge_asof backward."""
    events = []
    for row in monthly:
        if numero(row['posicion_neta_forwards']) is None:
            continue
        period = date.fromisoformat(row['periodo_referencia'])
        available = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
        events.append((available, row))
    events.sort(key=lambda x:x[0])
    if len({e[0] for e in events}) != len(events):
        raise ValueError('Conflicto: dos saldos con la misma fecha de disponibilidad')
    result = {}
    i = 0
    latest = None
    for d in spot_dates:
        while i < len(events) and events[i][0] <= d:
            latest = events[i]
            i += 1
        result[d] = latest
    return result


def main():
    c = config()
    for step in ('01','02'):
        path = ROOT / f'datos_crudos/paso{step}.json'
        if json.loads(path.read_text(encoding='utf-8'))['config'] != c:
            raise ValueError('Configuración cambiada: repita pasos 1 y 2')
    daily = {}
    duplicates = []
    for row in leer_csv(ROOT/'datos_crudos/bcrp_crudo.csv'):
        d = fecha(row['fecha'])
        if d in daily:
            duplicates.append(d.isoformat())
            continue
        if not c['inicio_premuestra_diaria'] <= d.isoformat() <= c['fin']:
            continue
        daily[d] = {k: numero(row[k]) for k in ('tc_spot','tasa_mn','tasa_me')}
    if duplicates:
        raise ValueError(f'Fechas diarias duplicadas: {duplicates[:5]}')
    spot_dates = sorted(d for d,r in daily.items() if r['tc_spot'] is not None and r['tc_spot'] > 0)
    if not spot_dates:
        raise ValueError('No hay cotizaciones spot válidas')
    monthly = leer_csv(ROOT/'datos_crudos/bcrp_derivados_crudo.csv')
    periods = [r['periodo_referencia'] for r in monthly]
    if len(periods) != len(set(periods)):
        raise ValueError('Periodos mensuales duplicados')
    aligned = alinear_saldos(spot_dates, monthly)
    window = c['ventana_volatilidad_dias']
    rets = []
    previous = None
    out = []
    for d in spot_dates:
        r = daily[d]
        spot = r['tc_spot']
        ret = math.log(spot/previous) if previous is not None else None
        if ret is not None:
            rets.append(ret)
        previous = spot
        hist = rets[-window:]
        vol = statistics.stdev(hist)*math.sqrt(252)*100 if len(hist)==window and ret is not None else None
        fwd = (forward_teorico(spot,r['tasa_mn'],r['tasa_me'],c['plazo_dias'],c['base_dias'])
               if r['tasa_mn'] is not None and r['tasa_me'] is not None else None)
        event = aligned[d]
        source_row = event[1] if event else None
        balance = numero(source_row['posicion_neta_forwards']) if source_row else None
        reference = date.fromisoformat(source_row['periodo_referencia']) if source_row else None
        age = (d.year-reference.year)*12+d.month-reference.month if reference else None
        if d.isoformat() < c['inicio']:
            continue
        out.append({'fecha':d.isoformat(), **r, 'saldo_forwards':balance,
                    'tc_forward_teorico':fwd,'punto_swap_teorico':fwd-spot if fwd is not None else None,
                    'volatilidad_spot':vol,
                    'periodo_referencia_saldo':source_row['periodo_referencia'] if source_row else None,
                    'fecha_disponibilidad_supuesta_saldo':event[0].isoformat() if event else None,
                    'antiguedad_meses_saldo':age,'saldo_t1_exacto':age==1 if age is not None else None,
                    'origen_saldo':'PN09550TM_rezago_mensual_t1_supuesto' if event else None,
                    'retorno_log_diario':ret,'n_retornos_ventana':len(hist)})
    if not out:
        raise ValueError('No hay fechas spot dentro del periodo solicitado')
    dest = ROOT/'datos_procesados'
    monthly_final = [r for r in monthly if c['inicio'][:7] <= r['periodo_referencia'][:7] <= c['fin'][:7]]
    guardar_csv(dest/'datos_procesados_2024200502H.csv',out,FINAL)
    guardar_csv(dest/'diarios_limpios.csv',out,FINAL)
    guardar_csv(dest/'saldos_mensuales_limpios.csv',monthly_final)
    missing = {k:sum(r[k] is None for r in out) for k in FINAL if k not in
               ('fecha','periodo_referencia_saldo','fecha_disponibilidad_supuesta_saldo',
                'origen_saldo')}
    guardar_json(dest/'calidad.json',{'config':c,'filas_diarias_crudas':len(daily),
        'filas_spot_procesadas':len(out),'rango':[out[0]['fecha'],out[-1]['fecha']],
        'periodo_solicitado':[c['inicio'],c['fin']],
        'rango_premuestra_spot':[spot_dates[0].isoformat(),
            max((d for d in spot_dates if d.isoformat()<c['inicio']),default=spot_dates[0]).isoformat()],
        'filas_saldos_crudas':len(monthly),'filas_saldos_estudio':len(monthly_final),
        'ausentes_por_columna':missing,
        'duplicados_diarios':duplicates,'duplicados_mensuales':0,
        'meses_con_fecha_publicacion':sum(bool(r['fecha_publicacion']) for r in monthly),
        'saldo_modo':c['saldo_modo'],'saldo_definicion':'saldo neto oficial PN09550TM, millones USD',
        'filas_sin_saldo':sum(r['saldo_forwards'] is None for r in out),
        'filas_saldo_antiguedad_mayor_un_mes':sum((r['antiguedad_meses_saldo'] or 0)>1 for r in out),
        'volatilidad':{'ventana_retornos':window,'minimo_retornos':window,'ddof':1,
                       'anualizacion':'sqrt(252)*100','unidad':'% anualizada',
                       'huecos':'retorno entre cotizaciones disponibles; sin imputación'},
        'ejecuciones':{
            '01':{'fecha_utc':json.loads((ROOT/'datos_crudos/paso01.json').read_text(encoding='utf-8')).get('fecha_descarga_utc'),'resultado':'correcto'},
            '02':{'fecha_utc':json.loads((ROOT/'datos_crudos/bcrp_saldos_pagina_original.html.fuente.json').read_text(encoding='utf-8')).get('descarga_utc'),'resultado':'correcto'},
            '03':{'fecha_utc':datetime.now(timezone.utc).isoformat(),'resultado':'correcto'}},
        'datos_revisados':'Posibles: tabla histórica actual; versiones de publicación no reconstruidas.',
        'linaje':{'observadas':['tc_spot','tasa_mn','tasa_me','saldo_compras','saldo_ventas','posicion_neta_forwards'],
                  'agregadas':['saldo_bruto_calculado'],
                  'estimadas':['tc_forward_teorico','punto_swap_teorico','volatilidad_spot']},
        'limitaciones':['Fechas históricas de publicación no disponibles en la tabla HTML.',
                        'La disponibilidad desde el primer día del mes siguiente es supuesta.',
                        'Las tasas interbancarias son proxies del plazo forward.']})
    print(f'Paso 3 listo: {len(out)} días con spot; saldo en {sum(r["saldo_forwards"] is not None for r in out)} días.')


if __name__ == '__main__':
    ejecutar(main)
