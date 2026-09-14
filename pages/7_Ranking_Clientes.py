# pages/7_Ranking_Clientes.py
"""
Réplica de "Ranking por Área Comercial" + "Ranking por Área GC" (Tablero
Forecast Accuracy IBP) -- según captura real, ambos rankings van separados
por Gran División (columnas lado a lado), sobre los meses elegidos en
"Meses a analizar" (sidebar, sección Período).

Grano: ZAREAGC (confirmado rápido contra SAP, ~8s) -- Area Comercial se
resuelve haciendo merge contra el maestro de clientes.

Esta es la única página que llama a ``render_sidebar_accuracy`` con
``incluir_gran_division=False``: como el diseño real ya muestra las 3
Grandes Divisiones válidas (`filters.GRANDES_DIVISIONES_VALIDAS`) en
simultáneo (una columna por división), un selectbox de una sola división no
tendría sentido acá -- en cambio, ``divisiones`` se restringe directo a esa
lista fija (nunca una 4ta división como "MP, Semi y Subproductos").
"""

import streamlit as st

from src import cache, charts, filters
from src.data import demo_data
from src.accuracy import acc_bias_consensuado
from src.filters import apply_filters

st.title("🏆 Ranking por Área Comercial / Área GC")

df, es_demo, error = cache.get_or_demo(cache.get_forecast_vs_actual, demo_data.forecast_vs_actual_demo)
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

filtros, meses_analisis = filters.render_sidebar_accuracy(df, key_prefix="rank", incluir_gran_division=False)
df_f = apply_filters(df, filtros)

if df_f.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()
if not meses_analisis:
    st.warning("Elegí al menos un mes en \"Meses a analizar\" (sidebar) para calcular accuracy.")
    st.stop()

df_meses = df_f[df_f["PERIODID3"].isin(meses_analisis)]

if df_meses.empty or "ZBIGDIVISION" not in df_meses.columns:
    st.warning("No hay datos para los meses elegidos.")
    st.stop()

divisiones = [d for d in filters.GRANDES_DIVISIONES_VALIDAS if d in df_meses["ZBIGDIVISION"].dropna().unique()]
if not divisiones:
    st.warning("No hay Gran División para los filtros elegidos.")
    st.stop()

st.subheader("Ranking por Área Comercial")
cols_tabla = st.columns(len(divisiones))
for col, division in zip(cols_tabla, divisiones):
    with col:
        st.caption(division)
        df_div = df_meses[df_meses["ZBIGDIVISION"] == division]
        if "ZAREACOMERCIAL" in df_div.columns:
            acc_areacom = acc_bias_consensuado(df_div, ["ZAREACOMERCIAL"])[["ZAREACOMERCIAL", "Accuracy"]]
            acc_areacom = acc_areacom.rename(columns={"Accuracy": "Accuracy FCST Consensuado"}).sort_values("Accuracy FCST Consensuado", ascending=False)
            st.dataframe(acc_areacom.style.format({"Accuracy FCST Consensuado": "{:.2%}"}), width="stretch", hide_index=True)
        else:
            st.caption("Sin Area Comercial disponible")

st.divider()
st.subheader("Ranking por Área/GC")
cols_chart = st.columns(len(divisiones))
for col, division in zip(cols_chart, divisiones):
    with col:
        df_div = df_meses[df_meses["ZBIGDIVISION"] == division]
        acc_areagc = acc_bias_consensuado(df_div, ["ZAREAGC"])[["ZAREAGC", "Accuracy"]]
        st.plotly_chart(
            charts.ranking_semaforo(acc_areagc, "ZAREAGC", "Accuracy", title=f"{division} - Accuracy por Cuentas"),
            width="stretch",
        )
