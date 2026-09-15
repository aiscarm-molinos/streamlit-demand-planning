# pages/5_Reporte_Accuracy.py
"""
Réplica de "Reporte de Proyección Accuracy" (Tablero Forecast Accuracy IBP).

Estructura real (según captura de pantalla + informe "Reporte – Ranking
Forecast Accuracy.docx" pasados por el usuario):
- Sidebar "Período" (multiselect "Meses a analizar", ver
  ``src/filters.py::render_sidebar_accuracy``): Accuracy/Bias ponderado se
  calculan sobre EXACTAMENTE los meses elegidos ahí (por default, los
  últimos ``accuracy.MESES_ANALISIS_DEFAULT`` con venta -- a pedido del
  usuario, esto reemplazó la ventana fija U4M/"últimos 4 meses cerrados" del
  informe original: ahora el usuario elige libremente qué meses entran).
- "Evolución Mensual del Accuracy & Bias": Accuracy Estadístico, Accuracy
  Consensuado y Bias Consensuado por Gran División, mes a mes dentro de los
  meses elegidos.
- "Accuracy & Bias Ponderado": las mismas 3 métricas pero agregadas en un
  solo valor sobre todos los meses elegidos (no por mes).
- Tabla "Segmento": Cantidad SKU, % Volumen y Accuracy Proyectado
  (acumulativo, fila por fila) por segmento -- desglosada por Gran División
  (una tabla por cada una de `filters.GRANDES_DIVISIONES_VALIDAS`, columnas
  lado a lado, a pedido del usuario) en vez de mostrar solo la división
  elegida en el sidebar -- ver src/accuracy.py::resumen_segmentos. Por eso
  esta sección IGNORA el filtro "Gran División" del sidebar (que en el
  resto de la página sí aplica, incluidas "Evolución Mensual" y "Accuracy &
  Bias Ponderado") y en cambio respeta el resto de los filtros (Clientes,
  Categoria, Familia, meses elegidos).
"""

import streamlit as st
import pandas as pd

from src import alertas, cache, charts, filters
from src.data import demo_data
from src.accuracy import (
    acc_bias_consensuado,
    acc_estadistico,
    resumen_segmentos,
    forecast_proximos_4m,
    MESES_PROX_FCST,
)
from src.utils.listas_periodos import periodos_empezando_en
from src.filters import apply_filters

st.title("📊 Reporte de Proyección Accuracy")

df, es_demo, error = cache.get_or_demo(cache.get_forecast_vs_actual_producto, demo_data.forecast_vs_actual_producto_demo)
if es_demo:
    st.warning(f"Mostrando datos de EJEMPLO (no hay conexión real a SAP IBP{f': {error}' if error else ''}). Es solo para previsualizar el diseño.", icon="🧪")

df_master, es_demo_master, _ = cache.get_or_demo(cache.get_customer_master, demo_data.customer_master_demo)
if not es_demo_master and "ZAREAGC" in df_master.columns and "ZAREACOMERCIAL" in df_master.columns:
    # Una fila por ZAREAGC (ver cache.mapa_area_comercial) -- nunca mergear
    # el maestro completo sin colapsar, fanoutea filas (hasta 31x).
    mapa_area = cache.mapa_area_comercial(df_master)
    df = df.merge(mapa_area, on="ZAREAGC", how="left")

df_categoria, es_demo_categoria, _ = cache.get_or_demo(cache.get_categoria_producto, demo_data.categoria_producto_demo)
if not es_demo_categoria and "sku" in df_categoria.columns and "grupo_material_3" in df_categoria.columns:
    mapa_categoria = df_categoria[["sku", "grupo_material_3"]].drop_duplicates().rename(columns={"sku": "PRDID", "grupo_material_3": "Categoria"})
    df = df.merge(mapa_categoria, on="PRDID", how="left")

filtros, meses_analisis = filters.render_sidebar_accuracy(df, key_prefix="acc")
df_f = apply_filters(df, filtros)

if df_f.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()
if not meses_analisis:
    st.warning("Elegí al menos un mes en \"Meses a analizar\" (sidebar) para calcular accuracy.")
    st.stop()

df_meses = df_f[df_f["PERIODID3"].isin(meses_analisis)]

if df_meses.empty:
    st.warning("No hay datos para los meses elegidos.")
    st.stop()

# --- Resumen general (todas las divisiones filtradas, agregado en un único
# número) -- antes había que leer la tabla pivot completa para sacar el
# número que probablemente se pregunte primero. groupby([]) no anda en
# pandas ("No group keys passed!"), por eso la columna dummy "_Total".
resumen_total = acc_bias_consensuado(df_meses.assign(_Total="Total"), ["_Total"]).iloc[0]
texto_bias, color_bias_badge = alertas.etiqueta_bias(resumen_total["Bias"])
c1, c2, c3 = st.columns(3)
with c1:
    charts.kpi_card("Accuracy Consensuado (general)", f"{resumen_total['Accuracy']:.1%}")
with c2:
    charts.kpi_card("Bias Consensuado (general)", f"{resumen_total['Bias']:+.1%}")
with c3:
    st.markdown(f"<div style='padding-top:1.9rem'><span style='color:{color_bias_badge}; font-weight:600'>{texto_bias}</span></div>", unsafe_allow_html=True)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Evolución Mensual del Accuracy & Bias")
    acc_cons_mes = acc_bias_consensuado(df_meses, ["ZBIGDIVISION", "PERIODID3"])
    acc_est_mes = acc_estadistico(df_meses, ["ZBIGDIVISION", "PERIODID3"])
    largo = pd.concat([
        acc_cons_mes[["ZBIGDIVISION", "PERIODID3", "Accuracy"]].assign(Métrica="Accuracy Consensuado").rename(columns={"Accuracy": "Valor"}),
        acc_cons_mes[["ZBIGDIVISION", "PERIODID3", "Bias"]].assign(Métrica="Bias Consensuado").rename(columns={"Bias": "Valor"}),
        acc_est_mes[["ZBIGDIVISION", "PERIODID3", "Accuracy"]].assign(Métrica="Accuracy Estadístico").rename(columns={"Accuracy": "Valor"}),
    ], ignore_index=True)
    pivot_evolucion = pd.pivot_table(largo, index=["ZBIGDIVISION", "Métrica"], columns="PERIODID3", values="Valor")
    pivot_evolucion = pivot_evolucion[[m for m in meses_analisis if m in pivot_evolucion.columns]]
    st.dataframe(
        pivot_evolucion.style.format("{:.2%}").apply(alertas.estilo_pivot_metricas, axis=1),
        width="stretch",
    )

with col2:
    st.subheader("Accuracy & Bias Ponderado (meses seleccionados)")
    acc_cons_tot = acc_bias_consensuado(df_meses, ["ZBIGDIVISION"])
    acc_est_tot = acc_estadistico(df_meses, ["ZBIGDIVISION"])
    ponderado = pd.concat([
        acc_cons_tot[["ZBIGDIVISION", "Accuracy"]].assign(Métrica="Accuracy Consensuado").rename(columns={"Accuracy": "Valor"}),
        acc_cons_tot[["ZBIGDIVISION", "Bias"]].assign(Métrica="Bias Consensuado").rename(columns={"Bias": "Valor"}),
        acc_est_tot[["ZBIGDIVISION", "Accuracy"]].assign(Métrica="Accuracy Estadístico").rename(columns={"Accuracy": "Valor"}),
    ], ignore_index=True)
    pivot_ponderado = pd.pivot_table(ponderado, index=["ZBIGDIVISION", "Métrica"], values="Valor")
    st.dataframe(
        pivot_ponderado.style.format("{:.2%}").apply(alertas.estilo_pivot_metricas, axis=1),
        width="stretch",
    )

st.divider()
st.subheader("Top 10 SKU con peor Accuracy Consensuado")
acc_sku = acc_bias_consensuado(df_meses, ["PRDID"])
df_master_prod, _, _ = cache.get_or_demo(cache.get_product_master, demo_data.producto_master_demo)
acc_sku = acc_sku.merge(df_master_prod[["PRDID", "PRDDESCR"]].drop_duplicates(), on="PRDID", how="left")
top_peores = acc_sku.dropna(subset=["Accuracy"]).nsmallest(10, "Accuracy")[["PRDID", "PRDDESCR", "Accuracy", "Bias"]]
top_peores = top_peores.rename(columns={"PRDDESCR": "Descripción"})
st.dataframe(
    top_peores.style.format({"Accuracy": "{:.1%}", "Bias": "{:+.1%}"}).pipe(alertas.aplicar_semaforo_accuracy, columnas=["Accuracy"]),
    width="stretch",
    hide_index=True,
)
charts.boton_descarga_csv(top_peores, "top_skus_peor_accuracy.csv", key="dl_top_peores")

st.divider()
st.subheader("Segmento")

meses_prox4m = periodos_empezando_en(MESES_PROX_FCST, meses_analisis[-1])

# Ignora el filtro "Gran División" del sidebar a propósito -- ver docstring
# del módulo. Respeta el resto de filtros (Clientes/Categoria/Familia).
filtros_sin_division = {k: v for k, v in filtros.items() if k != "ZBIGDIVISION"}
df_todas_divisiones = apply_filters(df, filtros_sin_division)
df_meses_todas_divisiones = df_todas_divisiones[df_todas_divisiones["PERIODID3"].isin(meses_analisis)]

divisiones = [d for d in filters.GRANDES_DIVISIONES_VALIDAS if d in df_meses_todas_divisiones["ZBIGDIVISION"].dropna().unique()]
if not divisiones:
    st.warning("No hay Gran División para los filtros elegidos.")
else:
    cols_seg = st.columns(len(divisiones))
    for col, division in zip(cols_seg, divisiones):
        with col:
            st.caption(division)
            df_meses_div = df_meses_todas_divisiones[df_meses_todas_divisiones["ZBIGDIVISION"] == division]
            df_full_div = df_todas_divisiones[df_todas_divisiones["ZBIGDIVISION"] == division]
            df_forecast_prox4m_div = forecast_proximos_4m(df_full_div, meses_prox4m)
            tabla_seg_div = cache.calcular_tabla_segmentacion(df_meses_div, df_forecast_prox4m_div)
            resumen_div = resumen_segmentos(tabla_seg_div)
            st.dataframe(
                resumen_div.style.format({"% Volumen": "{:.2%}", "Accuracy Proyectado": "{:.2%}"}, na_rep="—"),
                width="stretch",
                hide_index=True,
            )
