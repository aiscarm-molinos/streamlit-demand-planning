# pages/10_Curvas_Backtesting.py
"""
Curvas de backtesting: Real vs Predicción a lo largo del tiempo, por
entidad, para el entrenamiento activo (ver ``experimentos_sagemaker_estado.py``).

Fuente: ``reports/accuracy_forecast_mensual.csv`` del ``model.tar`` -- una
fila por (Modelo, Fecha, NIVEL_DE_PLANIFICACION, VALOR_NIVEL), con Real,
Predicción y Accuracy_% de ese mes (ver CLAUDE.md, verificado contra un
.tar real: 360 filas = 7 PRDID + 3 PRDFAMILY + 2 ZINDFAMILY + 2 ZBRAND + 1
ZBIGBUSINESS, 24 meses cada uno).

Tabla de triage (2026-09-20, a pedido del usuario): antes de elegir una
entidad a mano, una tabla ordenable de las 129 filas de
``reports/modelos_forecast_mensual.csv`` (una por combinación
Nivel/Entidad/Modelo, con su Accuracy AVG) -- clickeable para saltar
directo a su curva, en vez de tener que adivinar qué combinación mirar
entre 129 posibles.
"""

import pandas as pd
import streamlit as st

from src import charts
from src import experimentos_sagemaker_estado as estado
from src import nivel_planificacion as niveles
from src.data import model_tar_explorer as tarexp

st.title("📉 Curvas de Backtesting")
st.caption("Real vs Predicción a lo largo del tiempo -- accuracy_forecast_mensual.csv")

tar, contenido, info = estado.requerir_tar_activo()

miembro = tarexp.buscar_miembro("accuracy_forecast_mensual.csv", contenido.reports)
if miembro is None:
    st.warning("Este entrenamiento no tiene `reports/accuracy_forecast_mensual.csv`.", icon="⚠️")
    st.stop()

df = tarexp.leer_tabla(tar, miembro)
df["Fecha"] = pd.to_datetime(df["Fecha"])

miembro_modelos = tarexp.buscar_miembro("modelos_forecast_mensual.csv", contenido.reports)
df_modelos = tarexp.leer_tabla(tar, miembro_modelos) if miembro_modelos is not None else None

st.divider()

# --------------------------------------------------
# Triage: las N combinaciones Nivel/Entidad/Modelo de esta corrida,
# ordenables por accuracy -- para detectar los peores casos sin tener que
# elegir a ciegas entre las 2 listas de abajo.
# --------------------------------------------------
pendiente = estado.consumir_entidad_seleccionada()

if df_modelos is not None and not df_modelos.empty:
    col_accuracy = next((c for c in df_modelos.columns if c.lower().startswith("accuracy")), None)

    with st.expander(f"🔍 Triage -- {len(df_modelos)} modelos de esta corrida (ordená por columna, clic en una fila para verla abajo)", expanded=True):
        df_triage = df_modelos.copy()
        df_triage["Nivel"] = df_triage["NIVEL_DE_PLANIFICACION"].map(niveles.etiqueta_nivel)
        cols_mostrar = ["Nivel", "VALOR_NIVEL", "Modelo"] + ([col_accuracy] if col_accuracy else [])
        df_triage = df_triage[cols_mostrar].rename(columns={"VALOR_NIVEL": "Entidad"})
        if col_accuracy:
            df_triage = df_triage.sort_values(col_accuracy)

        seleccion = st.dataframe(
            df_triage,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="triage_backtesting",
        )
        charts.boton_descarga_csv(df_modelos, "modelos_forecast_mensual.csv", key="descarga_modelos_triage")

        filas_sel = seleccion.selection.rows if seleccion is not None else []
        if filas_sel:
            fila_click = df_modelos.iloc[filas_sel[0]]
            pendiente = {"nivel": fila_click["NIVEL_DE_PLANIFICACION"], "valor": str(fila_click["VALOR_NIVEL"])}

col1, col2 = st.columns(2)
with col1:
    niveles_disponibles = sorted(df["NIVEL_DE_PLANIFICACION"].unique())
    index_nivel = (
        niveles_disponibles.index(pendiente["nivel"])
        if pendiente and pendiente["nivel"] in niveles_disponibles
        else 0
    )
    nivel = st.selectbox("Nivel de planificación", niveles_disponibles, index=index_nivel, format_func=niveles.etiqueta_nivel)
with col2:
    valores_nivel = sorted(df.loc[df["NIVEL_DE_PLANIFICACION"] == nivel, "VALOR_NIVEL"].astype(str).unique())
    index_valor = (
        valores_nivel.index(pendiente["valor"])
        if pendiente and pendiente.get("nivel") == nivel and pendiente["valor"] in valores_nivel
        else 0
    )
    valor = st.selectbox("Entidad", valores_nivel, index=index_valor)

df_entidad = df[(df["NIVEL_DE_PLANIFICACION"] == nivel) & (df["VALOR_NIVEL"].astype(str) == valor)].sort_values("Fecha")

modelos = sorted(df_entidad["Modelo"].unique())
if len(modelos) > 1:
    modelo = st.selectbox("Modelo", modelos)
    df_entidad = df_entidad[df_entidad["Modelo"] == modelo]
else:
    st.caption(f"Modelo: **{modelos[0]}**")

if df_entidad.empty:
    st.info("No hay datos de backtesting para esta combinación.")
    st.stop()

col_a, col_b, col_c = st.columns(3)
col_a.metric("Accuracy promedio", f"{df_entidad['Accuracy_%'].mean():.1f}%")
col_b.metric("Meses backtesteados", len(df_entidad))
col_c.metric("Peor mes", f"{df_entidad['Accuracy_%'].min():.1f}%")

df_largo = df_entidad.melt(id_vars=["Fecha"], value_vars=["Real", "Prediccion"], var_name="Serie", value_name="Valor")
df_largo["Serie"] = df_largo["Serie"].replace({"Prediccion": "Predicción"})
st.plotly_chart(charts.line_chart(df_largo, x="Fecha", y="Valor", color="Serie"), width="stretch")

col_acc, col_bias = st.columns(2)
with col_acc:
    st.subheader("Accuracy mensual")
    st.plotly_chart(charts.bar_chart(df_entidad, x="Fecha", y="Accuracy_%"), width="stretch")
with col_bias:
    st.subheader("Error (Real - Predicción)")
    st.caption("Sesgo sistemático (siempre sobre/sub-estimando) vs. error aleatorio -- Accuracy_% solo mira magnitud, no dirección.")
    df_error = df_entidad.assign(Error=df_entidad["Real"] - df_entidad["Prediccion"])
    st.plotly_chart(charts.bias_bar_chart(df_error, x="Fecha", y="Error"), width="stretch")

charts.boton_descarga_csv(df_entidad, f"backtesting_{nivel}_{valor}.csv", key="descarga_entidad")
