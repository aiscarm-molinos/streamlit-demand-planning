# pages/6_Segmentacion_SKU.py
"""
Réplica de "Segmentación de SKU" (Tablero Forecast Accuracy IBP).

Columnas y orden exactos según captura de pantalla real: SKU, Descripción
SKU, Entrega, Margen Unitario (USD), % Mix Margen (SKU), FCST Estadístico,
FCST Consensuado, Acc. FCST Estadístico Ponderado, Acc. FCST Consensuado
Ponderado, Desvío Accuracy (pp.), Segmento SKU. Todo calculado sobre los
meses elegidos en "Meses a analizar" (sidebar, sección Período), igual que
"Reporte Accuracy" -- ver src/filters.py::render_sidebar_accuracy.
"""

import streamlit as st

from src import alertas, cache, charts, filters
from src.data import demo_data
from src.accuracy import SEGMENTOS_INFO, MESES_PROX_FCST, forecast_proximos_4m
from src.utils.listas_periodos import periodos_empezando_en
from src.filters import apply_filters

st.title("🧩 Segmentación de SKU")

df_producto, es_demo, error = cache.get_or_demo(cache.get_forecast_vs_actual_producto, demo_data.forecast_vs_actual_producto_demo)
if es_demo:
    st.warning(f"Mostrando datos de EJEMPLO (no hay conexión real a SAP IBP{f': {error}' if error else ''}). Es solo para previsualizar el diseño.", icon="🧪")

df_master, es_demo_master, _ = cache.get_or_demo(cache.get_customer_master, demo_data.customer_master_demo)
if not es_demo_master and "ZAREAGC" in df_master.columns and "ZAREACOMERCIAL" in df_master.columns:
    # Una fila por ZAREAGC (ver cache.mapa_area_comercial) -- nunca mergear
    # el maestro completo sin colapsar, fanoutea filas (hasta 31x).
    mapa_area = cache.mapa_area_comercial(df_master)
    df_producto = df_producto.merge(mapa_area, on="ZAREAGC", how="left")

df_categoria, es_demo_categoria, _ = cache.get_or_demo(cache.get_categoria_producto, demo_data.categoria_producto_demo)
if not es_demo_categoria and "sku" in df_categoria.columns and "grupo_material_3" in df_categoria.columns:
    mapa_categoria = df_categoria[["sku", "grupo_material_3"]].drop_duplicates().rename(columns={"sku": "PRDID", "grupo_material_3": "Categoria"})
    df_producto = df_producto.merge(mapa_categoria, on="PRDID", how="left")

filtros, meses_analisis = filters.render_sidebar_accuracy(df_producto, key_prefix="seg")
df_f = apply_filters(df_producto, filtros)

if df_f.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()
if not meses_analisis:
    st.warning("Elegí al menos un mes en \"Meses a analizar\" (sidebar) para calcular accuracy.")
    st.stop()

df_meses = df_f[df_f["PERIODID3"].isin(meses_analisis)]

meses_prox4m = periodos_empezando_en(MESES_PROX_FCST, meses_analisis[-1])
df_forecast_prox4m = forecast_proximos_4m(df_f, meses_prox4m)

tabla = cache.calcular_tabla_segmentacion(df_meses, df_forecast_prox4m)

df_master, _, _ = cache.get_or_demo(cache.get_product_master, demo_data.producto_master_demo)
tabla = tabla.merge(df_master[["PRDID", "PRDDESCR"]].drop_duplicates(), on="PRDID", how="left").rename(columns={"PRDDESCR": "Descripción SKU"})

# Dos pasos porque df_meses viene a grano PRDID x ZAREAGC x mes (para poder
# filtrar por Area Comercial/Area GC): primero suma por mes (colapsando
# ZAREAGC), y recién ahí promedia por PRDID -- promediar directo sin este
# paso intermedio sesgaría el promedio por la cantidad de Area/GC de cada
# SKU, no por la cantidad de meses elegidos.
por_mes = df_meses.groupby(["PRDID", "PERIODID3"], as_index=False).agg(
    ForecastEstadistico=("ForecastEstadistico", "sum"),
    ForecastConsensuado=("ForecastConsensuado", "sum"),
    Actual=("Actual", "sum"),
)
avg_por_mes = por_mes.groupby("PRDID", as_index=False).agg(
    **{
        "FCST Estadístico": ("ForecastEstadistico", "mean"),
        "FCST Consensuado": ("ForecastConsensuado", "mean"),
        "Entrega": ("Actual", "mean"),
    }
)
tabla = tabla.merge(avg_por_mes, on="PRDID", how="left")

df_margen, es_demo_margen, _ = cache.get_or_demo(cache.get_margen_unitario, demo_data.margen_unitario_demo)
tabla = tabla.merge(df_margen, on="PRDID", how="left")
tabla["Margen Total SKU (USD)"] = tabla["Historico"] * tabla["MargenUnitarioUSD"]
margen_total_todos = tabla["Margen Total SKU (USD)"].sum()
tabla["% Mix Margen (SKU)"] = tabla["Margen Total SKU (USD)"] / margen_total_todos if margen_total_todos else 0.0
if es_demo_margen:
    st.caption("🧪 Margen Unitario de ejemplo (no conectado a SAP IBP).")

tabla["Segmento SKU"] = tabla["Segmento"].map(lambda s: SEGMENTOS_INFO[s]["segmento"] if s in SEGMENTOS_INFO else "Sin datos")
tabla = tabla.rename(columns={
    "PRDID": "SKU",
    "AccEstadistico": "Acc. FCST Estadístico Ponderado",
    "AccConsensuado": "Acc. FCST Consensuado Ponderado",
    "DesvioAccuracyPP": "Desvío Accuracy (pp.)",
    "MargenUnitarioUSD": "Margen Unitario (USD)",
})

st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    segmentos_disponibles = ["Todas"] + sorted(tabla["Segmento SKU"].dropna().unique().tolist())
    segmento_elegido = st.selectbox("Segmento", segmentos_disponibles)
with col2:
    skus_disponibles = ["Todas"] + sorted(tabla["SKU"].dropna().unique().tolist())
    sku_elegido = st.selectbox("SKU", skus_disponibles)
with col3:
    # "Impacto" = Margen Total SKU (USD) x |Desvío Accuracy (pp.)| -- prioriza
    # SKU de alto margen Y mal accuracy por sobre solo alto volumen (Entrega),
    # que no distingue si ese volumen ya está bien pronosticado.
    orden_criterio = st.selectbox("Ordenar por", ["Entrega", "Impacto"])

tabla_mostrar = tabla
if segmento_elegido != "Todas":
    tabla_mostrar = tabla_mostrar[tabla_mostrar["Segmento SKU"] == segmento_elegido]
if sku_elegido != "Todas":
    tabla_mostrar = tabla_mostrar[tabla_mostrar["SKU"] == sku_elegido]

tabla_mostrar = tabla_mostrar.copy()
tabla_mostrar["Impacto"] = tabla_mostrar["Margen Total SKU (USD)"] * tabla_mostrar["Desvío Accuracy (pp.)"].abs()

columnas = [
    c for c in [
        "SKU", "Descripción SKU", "Entrega", "Margen Unitario (USD)", "% Mix Margen (SKU)",
        "FCST Estadístico", "FCST Consensuado",
        "Acc. FCST Estadístico Ponderado", "Acc. FCST Consensuado Ponderado",
        "Desvío Accuracy (pp.)", "Impacto", "Segmento SKU",
    ] if c in tabla_mostrar.columns
]

# Alto dinámico -- que la tabla muestre TODAS las filas del filtro elegido
# sin scroll interno (el alto fijo/chico default de st.dataframe la dejaba
# cortada), con un techo razonable para no volver la página kilométrica si
# el filtro trae miles de SKU.
alto_tabla = min(38 + 35 * (len(tabla_mostrar) + 1), 1200)

tabla_ordenada = tabla_mostrar.sort_values(orden_criterio, ascending=False)
segmento_critico = [SEGMENTOS_INFO["3.2"]["segmento"]]

st.dataframe(
    tabla_ordenada[columnas].style.format(
        {
            "Entrega": "{:,.2f}", "Margen Unitario (USD)": "{:.2f}", "% Mix Margen (SKU)": "{:.2%}",
            "FCST Estadístico": "{:,.2f}", "FCST Consensuado": "{:,.2f}",
            "Acc. FCST Estadístico Ponderado": "{:.2%}", "Acc. FCST Consensuado Ponderado": "{:.2%}",
            "Desvío Accuracy (pp.)": "{:.2f}", "Impacto": "{:,.0f}",
        },
        na_rep="—",
    ).apply(lambda r: alertas.resaltar_fila_critica(r, "Segmento SKU", segmento_critico), axis=1),
    width="stretch",
    height=alto_tabla,
    hide_index=True,
)
st.caption(f"🔴 Fondo resaltado: Segmento {segmento_critico[0]} -- producto crítico que requiere revisión.")
charts.boton_descarga_csv(tabla_ordenada[columnas], "segmentacion_sku.csv", key="dl_segmentacion")
