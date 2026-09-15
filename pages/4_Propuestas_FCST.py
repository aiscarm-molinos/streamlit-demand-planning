# pages/4_Propuestas_FCST.py
"""Réplica de "Propuestas de Forecast" (Tablero Forecast IBP) -- acá sí se
muestran las 7 versiones del waterfall completo (a diferencia de "Forecast -
Estimado", que solo muestra 2), con selector de Tipo -- preseleccionado en
"Historico Ajustado", "01 - Forecast Estadístico" y "12 - Estimado
Consensuado" (a pedido del usuario; antes venían las 8 categorías elegidas
por default, saturando el gráfico)."""

import pandas as pd
import streamlit as st

from src import cache, charts
from src.data import demo_data
from src.filters import render_sidebar_filters, apply_filters, nivel_producto_mas_desagregado
from src.utils.listas_periodos import periodos_futuros_mes

TIPOS_DEFAULT = ["Historico Ajustado", "01 - Forecast Estadístico", "12 - Estimado Consensuado"]

st.title("📝 Propuestas de Forecast")

df_ancho, es_demo, error = cache.get_or_demo(cache.get_historico_y_forecast_ancho, demo_data.historico_y_forecast_ancho_demo)
if es_demo:
    st.warning(f"Mostrando datos de EJEMPLO (no hay conexión real a SAP IBP{f': {error}' if error else ''}). Es solo para previsualizar el diseño.", icon="🧪")

df_master, es_demo_master, _ = cache.get_or_demo(cache.get_customer_master, demo_data.customer_master_demo)
if not es_demo_master and "ZAREAGC" in df_master.columns and "ZAREACOMERCIAL" in df_master.columns:
    # Una fila por ZAREAGC (ver cache.mapa_area_comercial) -- nunca mergear
    # el maestro completo sin colapsar, fanoutea filas (hasta 31x).
    mapa_area = cache.mapa_area_comercial(df_master)
    df_ancho = df_ancho.merge(mapa_area, on="ZAREAGC", how="left")

df_categoria, es_demo_categoria, _ = cache.get_or_demo(cache.get_categoria_producto, demo_data.categoria_producto_demo)
if not es_demo_categoria and "sku" in df_categoria.columns and "grupo_material_3" in df_categoria.columns:
    mapa_categoria = df_categoria[["sku", "grupo_material_3"]].drop_duplicates().rename(columns={"sku": "PRDID", "grupo_material_3": "Categoria"})
    df_ancho = df_ancho.merge(mapa_categoria, on="PRDID", how="left")

filtros = render_sidebar_filters(df_ancho, key_prefix="prop")
df_ancho_f = apply_filters(df_ancho, filtros)

# Filtrado por sidebar ANTES de explotar a Tipo/Valor (ver cache.melt_historico_y_forecast) --
# esta página sí necesita las 8 categorías completas (selector de Tipo).
df_f = cache.melt_historico_y_forecast(df_ancho_f)

tipos_disponibles = sorted(df_f["Tipo"].dropna().unique().tolist())
default_tipos = [t for t in TIPOS_DEFAULT if t in tipos_disponibles]
tipos_elegidos = st.multiselect("Tipo", tipos_disponibles, default=default_tipos)
df_f = df_f[df_f["Tipo"].isin(tipos_elegidos)]

if df_f.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

nivel_actual = nivel_producto_mas_desagregado(filtros)
if nivel_actual:
    st.caption(nivel_actual)

serie = df_f.groupby(["Date", "Tipo"], as_index=False)["Valor"].sum()
st.plotly_chart(charts.line_chart(serie, "Date", "Valor", "Tipo", title="Suma de Valor"), width="stretch")

st.divider()

mes_actual = periodos_futuros_mes(1)[0]

# "Ajuste Consensuado vs. Estadístico" -- cuánto se aparta (en %) el proceso
# de planificación del modelo estadístico crudo, para el mes en curso. Antes
# esta página repetía los 2 KPIs de "Forecast" (Forecast/Estimado Actual,
# Entregado+Pendiente) sin aportar nada propio -- este es el número que el
# waterfall de "Propuestas" está pensado para responder: ambas columnas
# (ZFCSTESTIMADO, STATISTICALFORECASTQTY) ya están en df_ancho_f, no hace
# falta una fuente de datos nueva.
fila_mes_actual = df_ancho_f[df_ancho_f["PERIODID3"] == mes_actual]
estadistico_actual = fila_mes_actual["STATISTICALFORECASTQTY"].sum()
estimado_actual = fila_mes_actual["ZFCSTESTIMADO"].sum()
ajuste_pct = (estimado_actual / estadistico_actual - 1) if estadistico_actual else float("nan")

st.metric(
    "Ajuste Consensuado vs. Estadístico" + (" 🧪" if es_demo else ""),
    f"{estimado_actual:,.0f}",
    delta=f"{ajuste_pct:+.1%} vs. Estadístico" if pd.notna(ajuste_pct) else None,
    help="12 - Estimado Consensuado vs. 01 - Forecast Estadístico, mes en curso. Mide cuánto se aparta el proceso de planificación del modelo estadístico crudo.",
)
st.caption(f"01 - Forecast Estadístico: {estadistico_actual:,.0f}")
