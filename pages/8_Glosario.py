# pages/8_Glosario.py
"""
Réplica de la página "Glosario" del Tablero Forecast Accuracy IBP.

Texto real, pasado por el usuario desde las tablas "Glosario - Accuracy" y
"Glosario - Segmentación" del .pbix (ver src/accuracy.py: GLOSARIO_ACCURACY,
SEGMENTOS_INFO).
"""

import pandas as pd
import streamlit as st

from src.accuracy import GLOSARIO_ACCURACY, SEGMENTOS_INFO

st.title("📖 Glosario")

st.subheader("Indicadores de Accuracy")
st.dataframe(pd.DataFrame(GLOSARIO_ACCURACY), width="stretch", hide_index=True)

st.subheader("Segmentación de SKU")
df_segmentos = pd.DataFrame(
    [
        {"Orden": ORDEN, "Segmento": info["segmento"], "Definición": info["definicion"], "Interpretación": info["interpretacion"]}
        for ORDEN, (_, info) in enumerate(SEGMENTOS_INFO.items(), start=1)
    ]
)
st.dataframe(df_segmentos, width="stretch", hide_index=True)

st.subheader("Semáforo de Accuracy")
st.caption(
    "Cortes de color usados en las tablas y KPIs de Reporte Accuracy, Segmentación SKU, Ranking Clientes, "
    "Plan Anual e Inicio (ver `src/alertas.py`) -- **no coinciden** con los de la Segmentación de SKU de arriba "
    "(80%/60%), que son la fórmula DAX real y no se tocan."
)
df_semaforo = pd.DataFrame(
    [
        {"Color": "🟢 Bueno", "Rango": "Accuracy > 80%", "Lectura": "El forecast predice correctamente la demanda"},
        {"Color": "🟡 Medio", "Rango": "70% ≤ Accuracy ≤ 80%", "Lectura": "Precisión aceptable, con margen de mejora"},
        {"Color": "🔴 Malo", "Rango": "Accuracy < 70%", "Lectura": "Precisión baja, requiere revisión"},
    ]
)
st.dataframe(df_semaforo, width="stretch", hide_index=True)

st.caption(
    "Bias (umbral ±5%, semáforo simétrico -- el color solo marca si el sesgo está dentro de rango, no la "
    "dirección): "
    "🟢 Sin sesgo relevante (entre -5% y +5%) · "
    "🔴 Sobreestimación (Bias > +5%, riesgo de sobrestock) · "
    "🔴 Subestimación (Bias < -5%, riesgo de quiebre)."
)
