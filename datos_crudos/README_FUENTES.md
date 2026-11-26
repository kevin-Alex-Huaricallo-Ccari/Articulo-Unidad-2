# Archivos crudos activos y antecedentes

- `bcrp_respuesta_original.json` y `bcrp_crudo.csv`: respuesta API diaria actual, solicitada desde 2014-10-01 hasta 2025-12-31.
- `bcrp_saldos_pagina_original.html` y `bcrp_derivados_crudo.csv`: tabla HTML oficial y extracción mensual actual, desde 2014-01 hasta 2025-12.
- Los archivos `.fuente.json` registran URL, momento UTC, tamaño y hash de los originales.
- `paso01.json` y `paso02.json` registran configuración y metadatos del último procesamiento.

Los antiguos `bcrp_derivados_original.json` y `bcrp_derivados_original.csv`, si aparecen, pertenecen a ejecuciones previas de la API/exportación. La ejecución vigente del paso 2 utiliza scraping de la tabla HTML. El respaldo anterior a este cambio está en `respaldo_antes_rezago_t1_20261122_114447/`.
