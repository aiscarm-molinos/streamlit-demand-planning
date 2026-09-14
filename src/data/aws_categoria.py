# src/data/aws_categoria.py
"""
Categoría de producto (grupo_material_3) vía AWS Athena -- tabla
"AWS - Categoria" del Power BI Accuracy. Join liviano entre el maestro de
materiales y su agrupación, no una query transaccional pesada.
"""

import pandas as pd

from src.data.aws_ejecutar_query import ejecutar_query

_QUERY = """
SELECT
    m.sku,
    m.familia,
    g.grupo_material_3
FROM "molinos_datalake_datapreparation"."sap_materiales" m
LEFT JOIN "molinos_datalake_datapreparation"."sap_grupo_materiales" g
    ON m.sku = g.sku
WHERE m.tipo_producto = 'Producto terminado'
    AND g.grupo_material_3 IS NOT NULL
    AND g.grupo_material_3 <> ''
"""


def categoria_producto_datalake() -> pd.DataFrame:
    """Devuelve columnas: sku, familia, grupo_material_3."""
    return ejecutar_query(_QUERY)
