# app.py
"""
Entrypoint / router de la app -- réplica funcional de los dos tableros de
Power BI IBP, conectada en vivo a SAP IBP (OData) y AWS Athena (Data Lake).

Usa ``st.navigation`` (no el auto-discovery clásico de ``pages/``) a
propósito: mientras los datos no terminaron de precargarse
(``st.session_state["datos_cargados"]``, gestionado en
``pages/0_Inicio.py``), acá solo se registra la página de Inicio -- las
demás páginas ni aparecen en el sidebar ni son alcanzables por URL. Una vez
cargados, se registran todas. Antes de usarla: copiar ``.env.example`` a
``ibp.env`` y ``aws.env`` (raíz del proyecto) y completar credenciales
reales.
"""

import streamlit as st

st.set_page_config(page_title="Forecast Demanda IBP", page_icon="📈", layout="wide")

inicio = st.Page("pages/0_Inicio.py", title="Inicio", icon="🏠", default=True)

if st.session_state.get("datos_cargados", False):
    paginas = {
        "": [inicio],
        "Tablero Forecast IBP": [
            st.Page("pages/1_Historico_de_ventas.py", title="Histórico de ventas", icon="📈"),
            st.Page("pages/2_Forecast.py", title="Forecast", icon="🔮"),
            st.Page("pages/3_Plan_Anual.py", title="Plan Anual", icon="🗓️"),
            st.Page("pages/4_Propuestas_FCST.py", title="Propuestas FCST", icon="📝"),
        ],
        "Tablero Forecast Accuracy IBP": [
            st.Page("pages/5_Reporte_Accuracy.py", title="Reporte Accuracy", icon="✅"),
            st.Page("pages/6_Segmentacion_SKU.py", title="Segmentación SKU", icon="🧩"),
            st.Page("pages/7_Ranking_Clientes.py", title="Ranking Clientes", icon="🏆"),
            st.Page("pages/8_Glosario.py", title="Glosario", icon="📖"),
        ],
    }
else:
    paginas = [inicio]

nav = st.navigation(paginas)
nav.run()
