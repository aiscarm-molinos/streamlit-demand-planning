# pages/11_Nivel_Planificacion.py
"""
Nivel de Planificación: cuántas veces cada nivel de la jerarquía de
producto (PRDID/PRDFAMILY/ZINDFAMILY/ZBRAND/ZBIGBUSINESS) resultó elegido
como el de menor error para una entidad (PRDFAMILY), y el accuracy de ese
nivel elegido -- para el entrenamiento activo (ver
``experimentos_sagemaker_estado.py``).

Fuentes: ``reports/mejor_nivel_planificacion_por_entidad.csv`` (nivel
elegido + error por entidad), ``reports/modelos_forecast_mensual.csv``
(accuracy por nivel/valor) y el dataset (preprocessed_forecast_mensual,
para resolver a qué valor de cada nivel pertenece cada entidad -- ver
``src/nivel_planificacion.py``, que hace el join real).
"""

import pandas as pd
import streamlit as st

from src import charts
from src import experimentos_sagemaker_estado as estado
from src import nivel_planificacion as niveles
from src.data import model_tar_explorer as tarexp

st.title("🧭 Nivel de Planificación")
st.caption("Nivel de la jerarquía de producto elegido como mejor, por entidad -- mejor_nivel_planificacion_por_entidad.csv")

tar, contenido, info = estado.requerir_tar_activo()


def _buscar(nombre_sufijo: str, lista):
    return next((m for m in lista if m.nombre.endswith(nombre_sufijo)), None)


m_mejor_nivel = _buscar("mejor_nivel_planificacion_por_entidad.csv", contenido.reports)
m_modelos = _buscar("modelos_forecast_mensual.csv", contenido.reports)
m_dataset = next((m for m in contenido.dataset if m.extension in tarexp.EXTENSIONES_TABLA), None)

faltantes = [
    nombre
    for nombre, m in [
        ("reports/mejor_nivel_planificacion_por_entidad.csv", m_mejor_nivel),
        ("reports/modelos_forecast_mensual.csv", m_modelos),
        ("dataset (preprocessed_forecast_mensual)", m_dataset),
    ]
    if m is None
]
if faltantes:
    st.warning(f"Este entrenamiento no tiene: {', '.join(faltantes)}.", icon="⚠️")
    st.stop()

df_mejor_nivel = tarexp.leer_tabla(tar, m_mejor_nivel)
df_modelos = tarexp.leer_tabla(tar, m_modelos)
df_dataset = tarexp.leer_tabla(tar, m_dataset)

st.divider()

st.subheader("Cantidad de veces elegido como mejor nivel")
conteo = df_mejor_nivel["MEJOR_NIVEL_PLANIFICACION"].value_counts().reset_index()
conteo.columns = ["Nivel", "Cantidad de entidades"]
st.plotly_chart(charts.bar_chart(conteo, x="Nivel", y="Cantidad de entidades"), width="stretch")

st.subheader("Detalle por entidad")
resumen = niveles.resumen_nivel_elegido(df_mejor_nivel, df_modelos, df_dataset)
df_resumen = pd.DataFrame(
    [
        {
            "PRDFAMILY": r.prdfamily,
            "Nivel elegido": r.nivel,
            "Valor(es) del nivel": ", ".join(r.valores) if r.valores else "—",
            "Accuracy del nivel elegido": f"{r.accuracy_avg:.1f}%" if r.accuracy_avg is not None else "—",
            "Error absoluto total": r.error_abs_total,
        }
        for r in resumen
    ]
)
st.dataframe(df_resumen, width="stretch", hide_index=True)
st.caption(
    "\"Accuracy del nivel elegido\" es el promedio de Accuracy_AVG (modelos_forecast_mensual.csv) entre los "
    "valores del nivel a los que pertenece la entidad -- si el nivel elegido es más fino que PRDFAMILY (ej. "
    "PRDID), una misma entidad puede resolver a varios valores y el número es un promedio entre ellos, no un "
    "único accuracy exacto."
)
