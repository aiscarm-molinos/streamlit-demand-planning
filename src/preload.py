# src/preload.py
"""
Lista de fuentes de datos a precargar antes de habilitar la navegación a las
páginas (ver ``pages/0_Inicio.py``). Cada entrada es
``(nombre_para_mostrar, get_fn, demo_fn)`` -- exactamente los mismos pares
que usa cada página vía ``cache.get_or_demo``, así que una vez precargadas
acá, las páginas las leen instantáneo desde el cache de Streamlit (no
disparan una consulta nueva).

El orden importa un poco para la percepción de progreso pero no para la
corrección: ``get_forecast_vs_actual`` y ``get_forecast_vs_actual_producto``
reutilizan internamente el cache ya tibio de
``get_forecast_waterfall_mensual``/``get_historico_ventas_mensual``, así que
no vuelven a pegarle a SAP.
"""

from src import cache
from src.data import demo_data

FUENTES = [
    ("Maestro de productos", cache.get_product_master, demo_data.producto_master_demo),
    ("Maestro de clientes", cache.get_customer_master, demo_data.customer_master_demo),
    ("Categoría de producto (Athena)", cache.get_categoria_producto, demo_data.categoria_producto_demo),
    ("Histórico y Forecast (Tablero Forecast IBP)", cache.get_historico_y_forecast_ancho, demo_data.historico_y_forecast_ancho_demo),
    ("Entregado (Histórico de Ventas)", cache.get_historico_ventas_mensual, demo_data.entregado_actual_demo),
    ("Estimado Comercial", cache.get_estimado_comercial, demo_data.estimado_comercial_demo),
    ("Plan Anual", cache.get_plan_anual, demo_data.plan_anual_demo),
    ("Entregado/Pendiente (E+P)", cache.get_entregado_pendiente, demo_data.entregado_pendiente_demo),
    ("Margen Unitario", cache.get_margen_unitario, demo_data.margen_unitario_demo),
    ("Forecast Consensuado vs Histórico (Accuracy)", cache.get_forecast_vs_actual, demo_data.forecast_vs_actual_demo),
    ("Forecast vs Histórico por Producto (Segmentación SKU)", cache.get_forecast_vs_actual_producto, demo_data.forecast_vs_actual_producto_demo),
]
