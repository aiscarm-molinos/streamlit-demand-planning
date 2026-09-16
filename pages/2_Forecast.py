# pages/2_Forecast.py
"""
Réplica de "Forecast - Estimado" (Tablero Forecast IBP) -- según captura
real: a diferencia de "Propuestas de Forecast" (que muestra las 7 versiones
del waterfall), acá el área solo muestra 2 series: "Historico Ajustado"
(pasado) y "12 - Estimado Consensuado" (futuro).
"""

import streamlit as st

from src import cache, charts
from src.data import demo_data
from src.filters import render_sidebar_filters, apply_filters, nivel_producto_mas_desagregado
from src.utils.listas_periodos import periodos_futuros_mes, periodid3_a_fecha

st.title("🔮 Forecast - Estimado")

df_ancho, es_demo, error = cache.get_or_demo(cache.get_historico_y_forecast_ancho, demo_data.historico_y_forecast_ancho_demo)
if es_demo:
    st.warning(f"Mostrando datos de EJEMPLO (no hay conexión real a SAP IBP{f': {error}' if error else ''}). Es solo para previsualizar el diseño.", icon="🧪")

df_ep, es_demo_ep, _ = cache.get_or_demo(cache.get_entregado_pendiente, demo_data.entregado_pendiente_demo)

df_master, es_demo_master, _ = cache.get_or_demo(cache.get_customer_master, demo_data.customer_master_demo)
if not es_demo_master and "ZAREAGC" in df_master.columns and "ZAREACOMERCIAL" in df_master.columns:
    # Una fila por ZAREAGC (ver cache.mapa_area_comercial) -- nunca mergear
    # el maestro completo sin colapsar, fanoutea filas (hasta 31x).
    mapa_area = cache.mapa_area_comercial(df_master)
    df_ancho = df_ancho.merge(mapa_area, on="ZAREAGC", how="left")
    if not df_ep.empty:
        df_ep = df_ep.merge(mapa_area, on="ZAREAGC", how="left")

df_categoria, es_demo_categoria, _ = cache.get_or_demo(cache.get_categoria_producto, demo_data.categoria_producto_demo)
if not es_demo_categoria and "sku" in df_categoria.columns and "grupo_material_3" in df_categoria.columns:
    mapa_categoria = df_categoria[["sku", "grupo_material_3"]].drop_duplicates().rename(columns={"sku": "PRDID", "grupo_material_3": "Categoria"})
    df_ancho = df_ancho.merge(mapa_categoria, on="PRDID", how="left")
    if not df_ep.empty:
        df_ep = df_ep.merge(mapa_categoria, on="PRDID", how="left")

filtros = render_sidebar_filters(df_ancho, key_prefix="fcst")
df_ancho_f = apply_filters(df_ancho, filtros)

if df_ancho_f.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

# Filtrado por sidebar ANTES de explotar a Tipo/Valor, y solo pedimos el
# tipo de forecast que esta página muestra (ZFCSTESTIMADO = "12 - Estimado
# Consensuado") -- no las otras 6 versiones del waterfall (ver
# cache.melt_historico_y_forecast).
df_f = cache.melt_historico_y_forecast(df_ancho_f, tipos_forecast=("ZFCSTESTIMADO",))

nivel_actual = nivel_producto_mas_desagregado(filtros)
if nivel_actual:
    st.caption(nivel_actual)

serie = df_f.groupby(["Date", "Tipo"], as_index=False)["Valor"].sum()
# area_superpuesta (no area_chart_por_tipo/apilada): Historico Ajustado y
# "12 - Estimado Consensuado" NO se solapan en el tiempo (por diseño, ver
# cache.melt_historico_y_forecast), así que no hay nada que "apilar" -- con
# px.area (apilado) el trace de Historico Ajustado terminaba con un salto
# visual a 0 justo en el mes de corte (Plotly interpola el área apilada
# contra el dominio combinado de ambas series). Con traces independientes
# (una por Tipo, cada una con su propio fill a cero) la transición queda
# limpia, igual que ya se ve en "Plan Anual vs Histórico + FCST".
mes_actual = periodos_futuros_mes(1)[0]
# Sin título (a pedido del usuario, 2026-09-18): "Valor por Tipo" se
# superponía visualmente con la leyenda horizontal (ambos anclados cerca
# del borde superior del gráfico, ver charts._base_layout) -- la leyenda
# ya identifica las series (Histórico Ajustado / 12 - Estimado Consensuado).
fig_serie = charts.area_superpuesta(serie, "Date", "Valor", "Tipo")
# Marca dónde termina lo cerrado y arranca el mes en curso -- sin esto hay
# que leer el eje de fechas para ubicar "dónde estamos parados" en el área.
# ``add_vline`` (con pd.Timestamp o con string) rompe acá con
# "unsupported operand type(s) for +: 'int' and 'str'" -- bug conocido de
# Plotly calculando la posición de la shape contra un eje de fechas en una
# figura armada a mano (go.Figure, no px). ``add_shape`` con yref="paper" no
# pasa por ese cálculo y funciona bien.
_x_mes_actual = periodid3_a_fecha(mes_actual)
fig_serie.add_shape(
    type="line", x0=_x_mes_actual, x1=_x_mes_actual, y0=0, y1=1, yref="paper",
    line=dict(dash="dot", color=charts.NEUTRO, width=1),
)
fig_serie.add_annotation(x=_x_mes_actual, y=1, yref="paper", text="Mes en curso", showarrow=False, yanchor="bottom")
st.plotly_chart(fig_serie, width="stretch")

st.divider()
mes_actual_ep = df_ep["PERIODID3"].min() if not df_ep.empty else None

c1, c2, c3 = st.columns(3)
with c1:
    # ZFCSTESTIMADO (mismo key figure que la serie "12 - Estimado Consensuado"
    # del gráfico de arriba) -- antes usaba ZFCSTCOMERCIALESTIMADO
    # (`get_estimado_comercial`), un key figure distinto ("Ajuste Comercial"),
    # por eso el número no coincidía con lo que mostraba el gráfico.
    actual = df_ancho_f.loc[df_ancho_f["PERIODID3"] == mes_actual, "ZFCSTESTIMADO"].sum()
    charts.kpi_card("Forecast/Estimado Actual" + (" 🧪" if es_demo else ""), f"{actual:,.0f}")
with c2:
    df_ep_f = apply_filters(df_ep, filtros) if not df_ep.empty else df_ep
    entregado_pendiente = df_ep_f.loc[df_ep_f["PERIODID3"] == mes_actual_ep, "ZENTREGAPENDIENTEMTH"].sum() if not df_ep_f.empty else 0
    charts.kpi_card("Entregado + Pendiente" + (" 🧪" if es_demo_ep else ""), f"{entregado_pendiente:,.0f}")
with c3:
    df_ep_f = apply_filters(df_ep, filtros) if not df_ep.empty else df_ep
    entregado = df_ep_f.loc[df_ep_f["PERIODID3"] == mes_actual_ep, "ZENTREGADO"].sum() if not df_ep_f.empty else 0
    charts.kpi_card("Entregado Mes en curso" + (" 🧪" if es_demo_ep else ""), f"{entregado:,.0f}")
