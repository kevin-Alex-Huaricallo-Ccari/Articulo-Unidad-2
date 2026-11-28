"""Paso 1: API JSON diaria; conserva respuesta original y exporta tabla sin imputar."""
import json
from comun import API, ROOT, config, descargar, ejecutar, guardar_csv, guardar_json

def main():
    c = config()
    series = c['series_diarias']
    codes = '-'.join(series.values())
    url = f"{API}/{codes}/json/{c['inicio_premuestra_diaria']}/{c['fin']}/esp"
    body = descargar(url, ROOT/'datos_crudos/bcrp_respuesta_original.json')
    data = json.loads(body.decode('utf-8-sig'))
    if len(data.get('config',{}).get('series',[])) != len(series):
        raise ValueError('La API no devolvió todas las series solicitadas')
    rows = []
    for p in data.get('periods',[]):
        if len(p['values']) != len(series):
            raise ValueError('Número inesperado de valores en respuesta BCRP')
        rows.append({'fecha':p['name'], **dict(zip(series,p['values']))})
    guardar_csv(ROOT/'datos_crudos/bcrp_crudo.csv',rows)
    guardar_json(ROOT/'datos_crudos/paso01.json', {
        'config':c, 'metadatos':data['config'], 'filas':len(rows), 'url':url,
        'frecuencia':'diaria', 'inicio_premuestra':c['inicio_premuestra_diaria'],
        'series':[{ 'variable':key, 'codigo':code,
                    'nombre_oficial':data['config']['series'][i]['name'],
                    'unidad': 'S/ por USD' if key=='tc_spot' else '% anual'}
                  for i,(key,code) in enumerate(series.items())],
        'fecha_descarga_utc':json.loads(
            (ROOT/'datos_crudos/bcrp_respuesta_original.json.fuente.json').read_text(encoding='utf-8')
        )['descarga_utc']})
    print(f'Paso 1 listo: {len(rows)} registros diarios. Original JSON conservado.')

if __name__ == '__main__': ejecutar(main)
