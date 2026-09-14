# pages/4_Propuestas_FCST.py
"""Réplica de "Propuestas de Forecast" (Tablero Forecast IBP) -- acá sí se
muestran las 7 versiones del waterfall completo (a diferencia de "Forecast -
Estimado", que solo muestra 2), con selector de Tipo -- preseleccionado en
"Historico Ajustado", "01 - Forecast Estadístico" y "12 - Estimado
Consensuado" (a pedido del usuario; antes venían las 8 categorías elegidas
por default, saturando el gráfico)."""

import streamlit as st

from src import cache, charts
from src.data import demo_data
from src.filters import render_sidebar_filters, apply_filters
from src.utils.listas_periodos import periodos_futuros_mes

TIPOS_DEFAULT = ["Historico Ajustado", "01 - Forecast Estadístico", "12 - Estimado Consensuado"]

st.title("📝 Propuestas de Forecast")

df_ancho, es_demo, error = cache.get_or_demo(cache.get_historico_y_forecast_ancho, demo_data.historico_y_forecast_ancho_demo)
if es_demo:
    st.warning(f"Mostrando datos de EJEMPLO (no hay conexión real a SAP IBP{f': {error}' if error else ''}). Es solo para previsualizar el diseño.", icon="🧪")

df_ep, es_demo_ep, _ = cache.get_or_demo(cache.get_entregado_pendiente, demo_data.entregado_pendiente_demo)

df_categoria, es_demo_categoria, _ = cache.get_or_demo(cache.get_categoria_producto, demo_data.categoria_producto_demo)
if not es_demo_categoria and "sku" in df_categoria.columns and "grupo_material_3" in df_categoria.columns:
    mapa_categoria = df_categoria[["sku", "grupo_material_3"]].drop_duplicates().rename(columns={"sku": "PRDID", "grupo_material_3": "Categoria"})
    df_ancho = df_ancho.merge(mapa_categoria, on="PRDID", how="left")
    if not df_ep.empty:
        df_ep = df_ep.merge(mapa_categoria, on="PRDID", how="left")

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

serie = df_f.groupby(["Date", "Tipo"], as_index=False)["Valor"].sum()
st.plotly_chart(charts.line_chart(serie, "Date", "Valor", "Tipo", title="Suma de Valor"), width="stretch")

st.divider()

mes_actual = periodos_futuros_mes(1)[0]
mes_actual_ep = df_ep["PERIODID3"].min() if not df_ep.empty else None

c1, c2 = st.columns(2)
with c1:
    # ZFCSTESTIMADO (mismo key figure que "12 - Estimado Consensuado" del
    # gráfico de arriba) -- antes usaba ZFCSTCOMERCIALESTIMADO
    # (`get_estimado_comercial`), un key figure distinto ("Ajuste Comercial"),
    # por eso el número no coincidía con lo que mostraba el gráfico (mismo
    # fix que en "2_Forecast.py").
    actual = df_ancho_f.loc[df_ancho_f["PERIODID3"] == mes_actual, "ZFCSTESTIMADO"].sum()
    charts.kpi_card("Forecast/Estimado Actual" + (" 🧪" if es_demo else ""), f"{actual:,.0f}")
with c2:
    df_ep_f = apply_filters(df_ep, filtros) if not df_ep.empty else df_ep
    entregado_pendiente = df_ep_f.loc[df_ep_f["PERIODID3"] == mes_actual_ep, "ZENTREGAPENDIENTEMTH"].sum() if not df_ep_f.empty else 0
    charts.kpi_card("Entregado + Pendiente" + (" 🧪" if es_demo_ep else ""), f"{entregado_pendiente:,.0f}")
