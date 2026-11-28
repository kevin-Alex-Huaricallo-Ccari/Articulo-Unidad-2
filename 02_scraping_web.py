"""Paso 2: scraping de la tabla HTML oficial BCRP de saldos mensuales."""
import calendar
from datetime import date
from html.parser import HTMLParser
from comun import ROOT, config, descargar, ejecutar, fecha, guardar_csv, guardar_json, numero


class TablaSeries(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_cell = False
        self.cell = []
        self.row = []
        self.rows = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table' and 'series' in attrs.get('class', '').split():
            self.in_table = True
        elif self.in_table and tag == 'tr':
            if self.row:
                self.rows.append(self.row)
            self.row = []
        elif self.in_table and tag in ('td', 'th'):
            self.in_cell = True
            self.cell = []
    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)
    def handle_endtag(self, tag):
        if self.in_table and tag in ('td', 'th') and self.in_cell:
            self.row.append(''.join(self.cell).strip())
            self.in_cell = False
        elif self.in_table and tag == 'table':
            if self.row:
                self.rows.append(self.row)
            self.in_table = False


def main():
    c = config()
    codes = '-'.join(c['series_saldos'].values())
    first_year = date.fromisoformat(c['inicio']).year - 1
    url = (f"https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/"
           f"{codes}/html/{first_year}-01/{c['fin'][:7]}")
    original = ROOT / 'datos_crudos/bcrp_saldos_pagina_original.html'
    body = descargar(url, original)
    if b'<html' not in body[:1000].lower():
        raise ValueError('La respuesta no es HTML')
    parser = TablaSeries()
    parser.feed(body.decode('utf-8', errors='replace'))
    headers = parser.rows[0] if parser.rows else []
    if len(headers) != 4 or not all(x in headers[i].lower() for i, x in
                                     [(1, 'compras'), (2, 'ventas'), (3, 'saldo neto')]):
        raise ValueError('La tabla oficial no contiene las columnas esperadas')
    rows = []
    seen = set()
    for cells in parser.rows[1:]:
        if len(cells) != 4:
            continue
        try:
            period = fecha(cells[0])
        except (KeyError, ValueError):
            continue
        if period in seen:
            raise ValueError(f'Periodo duplicado: {period}')
        seen.add(period)
        values = [numero(v) for v in cells[1:]]
        rows.append({'periodo_referencia': period.isoformat(),
                     'fecha_publicacion': None, 'fecha_disponibilidad': None,
                     'saldo_compras': values[0], 'saldo_ventas': values[1],
                     'posicion_neta_forwards': values[2],
                     'saldo_bruto_calculado': values[0] + values[1]
                       if values[0] is not None and values[1] is not None else None,
                     'unidad': 'millones USD', 'fuente': url})
    if not rows:
        raise ValueError('Tabla HTML sin periodos reconocibles')
    guardar_csv(ROOT / 'datos_crudos/bcrp_derivados_crudo.csv', rows)
    guardar_json(ROOT / 'datos_crudos/paso02.json', {
        'config': c, 'filas': len(rows), 'metodo': 'scraping_tabla_html',
        'pagina_origen': url, 'enlace_descarga': None,
        'original': str(original), 'unidad': 'millones USD',
        'transformaciones': 'Fecha mensual normalizada; saldo bruto calculado como compras + ventas.',
        'fecha_publicacion': 'No aparece en la tabla HTML; no se infiere de la fecha de descarga.',
        'versiones_historicas': 'No identificadas; los valores podrían incluir revisiones posteriores.',
        'columnas_oficiales': headers})
    print(f'Paso 2 listo: {len(rows)} meses extraídos de tabla HTML oficial.')


if __name__ == '__main__':
    ejecutar(main)
