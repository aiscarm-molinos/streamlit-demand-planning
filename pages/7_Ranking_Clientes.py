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

import pandas as pd
import streamlit as st

from src import alertas, cache, charts, filters
from src.data import demo_data
from src.accuracy import acc_bias_consensuado
from src.filters import apply_filters
from src.utils.listas_periodos import periodid3_a_fecha, periodos_terminando_en

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

# Ventana previa, mismo largo que "Meses a analizar", terminando justo antes
# del primer mes elegido -- para detectar cuentas cuya accuracy CAYÓ, no solo
# su nivel actual (ver alertas.py).
mes_anterior_al_primero = (periodid3_a_fecha(meses_analisis[0]) - pd.DateOffset(months=1)).strftime("%y-%b")
meses_previos = periodos_terminando_en(len(meses_analisis), mes_anterior_al_primero)
df_prev = df_f[df_f["PERIODID3"].isin(meses_previos)]

UMBRAL_CAIDA_PP = -10  # puntos porcentuales -- misma magnitud que el corte medio/malo de accuracy (20pp de ancho)

st.subheader("Ranking por Área Comercial")
cols_tabla = st.columns(len(divisiones))
for col, division in zip(cols_tabla, divisiones):
    with col:
        st.caption(division)
        df_div = df_meses[df_meses["ZBIGDIVISION"] == division]
        if "ZAREACOMERCIAL" in df_div.columns:
            acc_areacom = acc_bias_consensuado(df_div, ["ZAREACOMERCIAL"])[["ZAREACOMERCIAL", "Accuracy", "Bias"]]
            acc_areacom = acc_areacom.rename(columns={"Accuracy": "Accuracy FCST Consensuado"})

            df_div_prev = df_prev[df_prev["ZBIGDIVISION"] == division]
            acc_prev = acc_bias_consensuado(df_div_prev, ["ZAREACOMERCIAL"])[["ZAREACOMERCIAL", "Accuracy"]].rename(columns={"Accuracy": "_AccuracyAnterior"})
            acc_areacom = acc_areacom.merge(acc_prev, on="ZAREACOMERCIAL", how="left")
            acc_areacom["Δ pp. vs. período anterior"] = (acc_areacom["Accuracy FCST Consensuado"] - acc_areacom["_AccuracyAnterior"]) * 100
            acc_areacom = acc_areacom.drop(columns=["_AccuracyAnterior"]).sort_values("Accuracy FCST Consensuado", ascending=False)
            acc_areacom = acc_areacom.rename(columns={"ZAREACOMERCIAL": "Área Comercial"})

            st.dataframe(
                acc_areacom.style.format(
                    {"Accuracy FCST Consensuado": "{:.2%}", "Bias": "{:+.1%}", "Δ pp. vs. período anterior": "{:+.1f}"},
                    na_rep="—",
                )
                .pipe(alertas.aplicar_semaforo_accuracy, columnas=["Accuracy FCST Consensuado"])
                .map(alertas.color_bias_direccion, subset=["Bias"])
                .map(lambda v: f"color: {charts.MALO}; font-weight: 600" if pd.notna(v) and v <= UMBRAL_CAIDA_PP else "", subset=["Δ pp. vs. período anterior"]),
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("Sin Area Comercial disponible")

st.divider()
st.subheader("Ranking por Área/GC")
cols_chart = st.columns(len(divisiones))
for col, division in zip(cols_chart, divisiones):
    with col:
        df_div = df_meses[df_meses["ZBIGDIVISION"] == division]
        acc_areagc = acc_bias_consensuado(df_div, ["ZAREAGC"])[["ZAREAGC", "Accuracy", "Bias"]]
        # Excluye áreas sin accuracy calculable para ESTA división (ej.
        # "Sub-Productos"/"Otros" que existen como ZAREAGC pero no tienen
        # volumen en esta Gran División puntual) -- a pedido del usuario,
        # ocupaban espacio en el gráfico sin mostrar ninguna barra.
        acc_areagc = acc_areagc.dropna(subset=["Accuracy"])
        acc_areagc = acc_areagc.rename(columns={"ZAREAGC": "Área/GC"})
        st.plotly_chart(
            charts.ranking_semaforo(acc_areagc, "Área/GC", "Accuracy", title=f"{division} - Accuracy por Cuentas", hover_data={"Bias": ":+.1%"}),
            width="stretch",
        )
