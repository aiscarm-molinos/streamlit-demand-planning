# pages/1_Historico_de_ventas.py
"""
Réplica de "Histórico de ventas" (Tablero Forecast IBP) -- según captura
real: bar chart con 2 series (Histórico = ADJUSTEDACTUALSQTY para todo el
histórico, Entregado = ACTUALSQTY SOLO del mes en curso -- a pedido del
usuario, "Entregado" no se muestra para meses pasados, solo para poder
comparar el avance del mes actual contra el ritmo histórico), Mix Productos
por Gran Negocio, e Histórico/Volumen por Área Comercial (Area Comercial se
resuelve vía merge con el maestro de clientes, igual que en Ranking Clientes
-- confirmado que ZAREAGC es rápido).
"""

import streamlit as st
import pandas as pd

from src import cache, charts
from src.data import demo_data
from src.filters import render_sidebar_filters, apply_filters
from src.utils.listas_periodos import periodos_historicos_mes, periodos_futuros_mes

st.title("📈 Histórico de ventas")

# Formato ANCHO (ver cache.get_historico_y_forecast_ancho): se filtra PRIMERO
# y recién ahí se toma la columna Histórico Ajustado -- no hace falta
# "explotar" a Tipo/Valor para esta página, que solo usa esa única serie.
df_ancho, es_demo, error = cache.get_or_demo(cache.get_historico_y_forecast_ancho, demo_data.historico_y_forecast_ancho_demo)
df_entregado, es_demo_ent, _ = cache.get_or_demo(cache.get_historico_ventas_mensual, demo_data.entregado_actual_demo)
if es_demo or es_demo_ent:
    st.warning(f"Mostrando datos de EJEMPLO (no hay conexión real a SAP IBP{f': {error}' if error else ''}). Es solo para previsualizar el diseño.", icon="🧪")

df_master, es_demo_master, _ = cache.get_or_demo(cache.get_customer_master, demo_data.customer_master_demo)
if not es_demo_master and "ZAREAGC" in df_master.columns and "ZAREACOMERCIAL" in df_master.columns:
    # Una fila por ZAREAGC (ver cache.mapa_area_comercial) -- nunca mergear
    # el maestro completo sin colapsar, fanoutea filas (hasta 31x).
    mapa_area = cache.mapa_area_comercial(df_master)
    df_ancho = df_ancho.merge(mapa_area, on="ZAREAGC", how="left")
    df_entregado = df_entregado.merge(mapa_area, on="ZAREAGC", how="left")

df_categoria, es_demo_categoria, _ = cache.get_or_demo(cache.get_categoria_producto, demo_data.categoria_producto_demo)
if not es_demo_categoria and "sku" in df_categoria.columns and "grupo_material_3" in df_categoria.columns:
    mapa_categoria = df_categoria[["sku", "grupo_material_3"]].drop_duplicates().rename(columns={"sku": "PRDID", "grupo_material_3": "Categoria"})
    df_ancho = df_ancho.merge(mapa_categoria, on="PRDID", how="left")
    df_entregado = df_entregado.merge(mapa_categoria, on="PRDID", how="left")

filtros = render_sidebar_filters(df_ancho, key_prefix="hist")
df_ancho_f = apply_filters(df_ancho, filtros)
df_entregado_f = apply_filters(df_entregado, filtros) if not df_entregado.empty else df_entregado

meses_hist = periodos_historicos_mes(cache.MESES_HISTORICOS)
df_hist = df_ancho_f[df_ancho_f["PERIODID3"].isin(meses_hist)].rename(columns={"ADJUSTEDACTUALSQTY": "Valor"})

if df_hist.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

# --- KPIs ---
anio_actual = pd.Timestamp.today().year
ventas_ytd = df_hist.loc[df_hist["Date"].dt.year == anio_actual, "Valor"].sum()

serie_mensual = df_hist.groupby("Date", as_index=False)["Valor"].sum().sort_values("Date")
serie_mensual["var_pct"] = serie_mensual["Valor"].pct_change()

historico_promedio_mensual = serie_mensual["Valor"].mean()

# YoY (mismo mes, año anterior) en vez de "Promedio % Variación Mensual" --
# ese promedio de 24 variaciones mes a mes, sin ajuste estacional, es
# ruidoso (mezcla estacionalidad real con variación real) y no dice mucho
# sobre hacia dónde va el negocio. YoY del último mes cerrado sí compara
# contra un punto de referencia comparable.
ultimo_mes = serie_mensual["Date"].max() if not serie_mensual.empty else None
yoy_pct = float("nan")
if pd.notna(ultimo_mes):
    valor_ultimo_mes = serie_mensual.loc[serie_mensual["Date"] == ultimo_mes, "Valor"].sum()
    mismo_mes_anio_anterior = ultimo_mes - pd.DateOffset(years=1)
    fila_anio_anterior = serie_mensual.loc[serie_mensual["Date"] == mismo_mes_anio_anterior, "Valor"]
    if not fila_anio_anterior.empty and fila_anio_anterior.iloc[0]:
        yoy_pct = valor_ultimo_mes / fila_anio_anterior.iloc[0] - 1

c1, c2, c3 = st.columns(3)
with c1:
    charts.kpi_card("Ventas YTD Actual", f"{ventas_ytd:,.0f}")
with c2:
    charts.kpi_card(
        f"YoY ({ultimo_mes:%b %Y})" if pd.notna(ultimo_mes) else "YoY",
        f"{yoy_pct:+.1%}" if pd.notna(yoy_pct) else "—",
        help="Último mes cerrado vs. mismo mes del año anterior.",
    )
with c3:
    charts.kpi_card("Histórico Promedio Mensual", f"{historico_promedio_mensual:,.0f}")

# Alerta de caída brusca mes a mes -- el bar chart de abajo puede esconder
# una caída puntual entre 24 barras; esto la señala explícitamente.
UMBRAL_CAIDA_BRUSCA = -0.15
if not serie_mensual.empty:
    ultima_var = serie_mensual["var_pct"].iloc[-1]
    if pd.notna(ultima_var) and ultima_var <= UMBRAL_CAIDA_BRUSCA:
        st.error(f"⚠️ Caída brusca en {ultimo_mes:%b %Y}: {ultima_var:+.1%} vs. el mes anterior.", icon="🔴")

st.divider()

col1, col2 = st.columns(2)
with col1:
    serie_historico = serie_mensual.rename(columns={"Valor": "Volumen"}).assign(Serie="Histórico")[["Date", "Volumen", "Serie"]]
    mes_actual = periodos_futuros_mes(1)[0]
    df_entregado_actual = df_entregado_f[df_entregado_f["PERIODID3"] == mes_actual] if not df_entregado_f.empty else df_entregado_f
    if not df_entregado_actual.empty:
        serie_entregado = df_entregado_actual.groupby("Date", as_index=False)["Actual"].sum().rename(columns={"Actual": "Volumen"}).assign(Serie="Entregado")
        serie_combinada = pd.concat([serie_historico, serie_entregado[["Date", "Volumen", "Serie"]]], ignore_index=True)
    else:
        serie_combinada = serie_historico
    st.plotly_chart(charts.bar_chart(serie_combinada, "Date", "Volumen", color="Serie", title="Histórico de Ventas"), width="stretch")
with col2:
    # Barra horizontal en vez de torta: con hasta 8 porciones un pie se
    # vuelve difícil de comparar a simple vista -- una barra ordenada sí.
    mix_productos = df_hist.groupby("ZBIGBUSINESS", as_index=False)["Valor"].sum().nlargest(8, "Valor").sort_values("Valor", ascending=True)
    st.plotly_chart(
        charts.bar_chart(mix_productos, x="Valor", y="ZBIGBUSINESS", orientation="h", title="Mix Productos"),
        width="stretch",
    )

col3, col4 = st.columns(2)
with col3:
    if "ZAREACOMERCIAL" in df_hist.columns:
        serie_por_area = df_hist.groupby(["Date", "ZAREACOMERCIAL"], as_index=False)["Valor"].sum()
        st.plotly_chart(
            charts.area_superpuesta(serie_por_area, "Date", "Valor", "ZAREACOMERCIAL", title="Histórico por Área Comercial"),
            width="stretch",
        )
    else:
        st.caption("Sin Area Comercial disponible")
with col4:
    if "ZAREACOMERCIAL" in df_hist.columns:
        volumen_por_area = df_hist.groupby("ZAREACOMERCIAL", as_index=False)["Valor"].sum().nlargest(8, "Valor")
        st.plotly_chart(charts.pie_chart(volumen_por_area, "ZAREACOMERCIAL", "Valor", title="Volumen por Área Comercial"), width="stretch")
    else:
        st.caption("Sin Area Comercial disponible")
