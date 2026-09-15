# pages/10_Curvas_Backtesting.py
"""
Curvas de backtesting: Real vs Predicción a lo largo del tiempo, por
entidad, para el entrenamiento activo (ver ``experimentos_sagemaker_estado.py``).

Fuente: ``reports/accuracy_forecast_mensual.csv`` del ``model.tar`` -- una
fila por (Modelo, Fecha, NIVEL_DE_PLANIFICACION, VALOR_NIVEL), con Real,
Predicción y Accuracy_% de ese mes (ver CLAUDE.md, verificado contra un
.tar real: 360 filas = 7 PRDID + 3 PRDFAMILY + 2 ZINDFAMILY + 2 ZBRAND + 1
ZBIGBUSINESS, 24 meses cada uno).
"""

import pandas as pd
import streamlit as st

from src import charts
from src import experimentos_sagemaker_estado as estado
from src.data import model_tar_explorer as tarexp

st.title("📉 Curvas de Backtesting")
st.caption("Real vs Predicción a lo largo del tiempo -- accuracy_forecast_mensual.csv")

tar, contenido, info = estado.requerir_tar_activo()

miembro = next((m for m in contenido.reports if m.nombre.endswith("accuracy_forecast_mensual.csv")), None)
if miembro is None:
    st.warning("Este entrenamiento no tiene `reports/accuracy_forecast_mensual.csv`.", icon="⚠️")
    st.stop()

df = tarexp.leer_tabla(tar, miembro)
df["Fecha"] = pd.to_datetime(df["Fecha"])

st.divider()

col1, col2 = st.columns(2)
with col1:
    nivel = st.selectbox("Nivel de planificación", sorted(df["NIVEL_DE_PLANIFICACION"].unique()))
with col2:
    valores_nivel = sorted(df.loc[df["NIVEL_DE_PLANIFICACION"] == nivel, "VALOR_NIVEL"].astype(str).unique())
    valor = st.selectbox("Entidad", valores_nivel)

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

st.subheader("Accuracy mensual")
st.plotly_chart(charts.bar_chart(df_entidad, x="Fecha", y="Accuracy_%"), width="stretch")
