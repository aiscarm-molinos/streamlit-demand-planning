# pages/12_Feature_Importance.py
"""
Feature Importance: qué variables pesaron más en la predicción, para el(los)
modelo(s) .pkl del nivel elegido como mejor para una entidad -- entrenamiento
activo (ver ``experimentos_sagemaker_estado.py``).

Deserializa el .pkl real (``joblib.load`` de un
``skforecast.ForecasterRecursive``, luego ``.get_feature_importances()``) en
un **subproceso con Python 3.10 + requirements_fcst.txt pineado exacto**
(``.venv310/``, ver README) -- el venv principal de la app (Python 3.13) no
puede: ``numpy==2.0.2`` (versión de entrenamiento) no tiene wheel para 3.13,
y aun con versiones cercanas aparecen incompatibilidades binarias más
adentro (booster de XGBoost). Ver ``src/data/model_deserializer.py`` y
CLAUDE.md para el detalle completo de cómo se llegó a esta arquitectura.

Deserializar estos .pkl es una excepción deliberada a la regla general de
no deserializar pickles de este bucket (ver ``model_tar_explorer.py``) --
decidida junto con el usuario porque son modelos entrenados por su propio
equipo en su pipeline de SageMaker, no de un origen público/no confiable.
"""

import pandas as pd
import streamlit as st

from src import charts
from src import experimentos_sagemaker_estado as estado
from src import nivel_planificacion as niveles
from src.data import model_deserializer
from src.data import model_tar_explorer as tarexp

st.title("🧠 Feature Importance")
st.caption("Qué variables pesaron más en la predicción del/de los modelo(s) elegido(s) como mejores.")

tar, contenido, info = estado.requerir_tar_activo()

if not model_deserializer.venv310_disponible():
    st.warning(
        "No está creado `.venv310` (Python 3.10 + `requirements_fcst.txt`), necesario para deserializar "
        "modelos. Ver README, sección \"Experimentos SageMaker\", para crearlo.",
        icon="⚠️",
    )
    st.stop()


def _buscar(nombre_sufijo: str, lista):
    return next((m for m in lista if m.nombre.endswith(nombre_sufijo)), None)


m_mejor_nivel = _buscar("mejor_nivel_planificacion_por_entidad.csv", contenido.reports)
m_dataset = next((m for m in contenido.dataset if m.extension in tarexp.EXTENSIONES_TABLA), None)

if m_mejor_nivel is None or m_dataset is None:
    st.warning("Este entrenamiento no tiene `mejor_nivel_planificacion_por_entidad.csv` o el dataset.", icon="⚠️")
    st.stop()

df_mejor_nivel = tarexp.leer_tabla(tar, m_mejor_nivel)
df_dataset = tarexp.leer_tabla(tar, m_dataset)

st.divider()

entidad = st.selectbox("Entidad (Familia)", sorted(df_mejor_nivel["PRDFAMILY"].unique()))
fila = df_mejor_nivel[df_mejor_nivel["PRDFAMILY"] == entidad].iloc[0]
nivel = fila["MEJOR_NIVEL_PLANIFICACION"]
valores = niveles.valores_de_nivel(df_dataset, entidad, nivel)

st.write(f"Nivel elegido para **{entidad}**: **{niveles.etiqueta_nivel(nivel)}**" + (f" ({len(valores)} valor(es))" if len(valores) != 1 else ""))

if not valores:
    st.info("No se pudo resolver ningún valor de este nivel para la entidad en el dataset.")
    st.stop()

miembros_por_nombre = {m.nombre: m for m in contenido.trained_models}

for valor in valores:
    nombre_esperado = niveles.nombre_archivo_pkl(nivel, valor)
    miembro = miembros_por_nombre.get(nombre_esperado)

    with st.expander(f"{valor} -- `{nombre_esperado}`", expanded=(len(valores) == 1)):
        if miembro is None:
            st.caption("No se encontró este archivo en `trained_models/`.")
            continue

        if st.button("🔎 Analizar", key=f"analizar_{nombre_esperado}"):
            with st.spinner("Deserializando modelo (subproceso .venv310)..."):
                pkl_bytes = tarexp.leer_bytes(tar, miembro)
                resultado = model_deserializer.extraer_feature_importance(pkl_bytes)

            if not resultado.get("ok"):
                st.error(resultado.get("error", "Error desconocido."))
            else:
                df_fi = pd.DataFrame(resultado["importancias"]).sort_values("importance", ascending=True)
                st.caption(f"Regressor: `{resultado.get('regressor')}` -- skforecast `{resultado.get('skforecast_version')}`")
                st.plotly_chart(
                    charts.bar_chart(df_fi.tail(15), x="importance", y="feature", orientation="h"),
                    width="stretch",
                )
                st.dataframe(
                    df_fi.sort_values("importance", ascending=False), width="stretch", hide_index=True
                )
