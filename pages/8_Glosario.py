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
