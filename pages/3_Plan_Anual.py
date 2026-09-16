# pages/3_Plan_Anual.py
"""
Réplica de "Planificación Anual vs Avance" (Tablero Forecast IBP) -- según
captura real: un número grande (Histórico + FCST del período filtrado) con
el "Objetivo" (Plan Anual) y el % de brecha al lado, más el área
superpuesta (NO apilada -- Plan Anual y Histórico+FCST se solapan en el
tiempo, apilar los sumaría mal) comparando ambas series mes a mes.

Arranca en enero 2025 (``PLAN_ANUAL_DESDE``) -- a pedido del usuario, el
Plan Anual recién se empezó a conformar desde esa fecha, así que traer
períodos anteriores no tiene sentido de negocio (aunque `get_plan_anual`
técnicamente pida un rango más amplio por diseño, ver `cache.py`). El
filtro "Año" del sidebar (range slider, ver `src/filters.py`) viene
preseleccionado en el año en curso (``anio_default``, colapsa el rango a un
único año) -- se puede volver a ampliar el rango libremente.
"""

import streamlit as st
import pandas as pd

from src import alertas, cache, charts
from src.data import demo_data
from src.filters import render_sidebar_filters, apply_filters
from src.utils.listas_periodos import periodos_historicos_mes

PLAN_ANUAL_DESDE = pd.Timestamp("2025-01-01")

st.title("🗓️ Planificación Anual vs Avance")

df_plan, es_demo_plan, error_plan = cache.get_or_demo(cache.get_plan_anual, demo_data.plan_anual_demo)
df_ancho, es_demo_hf, _ = cache.get_or_demo(cache.get_historico_y_forecast_ancho, demo_data.historico_y_forecast_ancho_demo)

if es_demo_plan or es_demo_hf:
    st.warning(f"Mostrando datos de EJEMPLO (no hay conexión real a SAP IBP{f': {error_plan}' if error_plan else ''}). Es solo para previsualizar el diseño.", icon="🧪")

if not df_plan.empty:
    df_plan = df_plan[df_plan["Date"] >= PLAN_ANUAL_DESDE]
if not df_ancho.empty:
    df_ancho = df_ancho[df_ancho["Date"] >= PLAN_ANUAL_DESDE]

df_master, es_demo_master, _ = cache.get_or_demo(cache.get_customer_master, demo_data.customer_master_demo)
if not es_demo_master and "ZAREAGC" in df_master.columns and "ZAREACOMERCIAL" in df_master.columns:
    # Una fila por ZAREAGC (ver cache.mapa_area_comercial) -- nunca mergear
    # el maestro completo sin colapsar, fanoutea filas (hasta 31x).
    mapa_area = cache.mapa_area_comercial(df_master)
    df_plan = df_plan.merge(mapa_area, on="ZAREAGC", how="left")
    if not df_ancho.empty:
        df_ancho = df_ancho.merge(mapa_area, on="ZAREAGC", how="left")

df_categoria, es_demo_categoria, _ = cache.get_or_demo(cache.get_categoria_producto, demo_data.categoria_producto_demo)
if not es_demo_categoria and "sku" in df_categoria.columns and "grupo_material_3" in df_categoria.columns:
    mapa_categoria = df_categoria[["sku", "grupo_material_3"]].drop_duplicates().rename(columns={"sku": "PRDID", "grupo_material_3": "Categoria"})
    df_plan = df_plan.merge(mapa_categoria, on="PRDID", how="left")
    if not df_ancho.empty:
        df_ancho = df_ancho.merge(mapa_categoria, on="PRDID", how="left")

anio_actual = pd.Timestamp.today().year
filtros = render_sidebar_filters(df_plan, key_prefix="plan", anio_default=[anio_actual])
df_plan_f = apply_filters(df_plan, filtros)
df_ancho_f = apply_filters(df_ancho, filtros) if not df_ancho.empty else df_ancho

if df_plan_f.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

# Una única serie "Histórico + Forecast" sin duplicar ni pasar por el melt
# completo (esta página no necesita las otras 6 versiones del waterfall):
# Histórico Ajustado (observado) en el pasado, Forecast Consensuado
# (DEMANDPLANNINGQTY) en el mes en curso/futuro.
df_hf_f = pd.DataFrame()
if not df_ancho_f.empty:
    meses_hist = periodos_historicos_mes(cache.MESES_HISTORICOS)
    es_pasado = df_ancho_f["PERIODID3"].isin(meses_hist)
    df_hf_f = pd.concat([
        df_ancho_f[es_pasado][["Date", "ADJUSTEDACTUALSQTY"]].rename(columns={"ADJUSTEDACTUALSQTY": "Valor"}),
        df_ancho_f[~es_pasado][["Date", "DEMANDPLANNINGQTY"]].rename(columns={"DEMANDPLANNINGQTY": "Valor"}),
    ], ignore_index=True)

serie_plan = df_plan_f.groupby("Date", as_index=False)["PLANANUAL"].sum().rename(columns={"PLANANUAL": "Valor"})
serie_plan["Serie"] = "Plan Anual"

if not df_hf_f.empty:
    serie_valor = df_hf_f.groupby("Date", as_index=False)["Valor"].sum()
    serie_valor["Serie"] = "Histórico + FCST"
    serie = pd.concat([serie_plan, serie_valor], ignore_index=True)
else:
    serie = serie_plan

total_plan = serie_plan["Valor"].sum()
total_hf = serie_valor["Valor"].sum() if not df_hf_f.empty else 0.0
gap_pct = (total_hf / total_plan - 1) if total_plan else float("nan")

st.metric(
    "Histórico + FCST",
    f"{total_hf:,.0f}",
    delta=f"{gap_pct:.2%}" if pd.notna(gap_pct) else None,
    help="Comparado contra el Objetivo (Plan Anual) del período/división filtrado. Incluye el Forecast Consensuado oficial para los meses futuros.",
)
st.caption(f"Objetivo (Plan Anual): {total_plan:,.0f}")
nivel_gap = alertas.nivel_brecha(gap_pct)
emoji_gap, color_gap = alertas.badge_nivel(nivel_gap)
st.markdown(f"<span style='color:{color_gap}; font-weight:600'>{emoji_gap} Brecha {nivel_gap}</span>", unsafe_allow_html=True)

st.plotly_chart(charts.area_superpuesta(serie, "Date", "Valor", "Serie", title="Plan Anual vs Histórico + FCST"), width="stretch")
