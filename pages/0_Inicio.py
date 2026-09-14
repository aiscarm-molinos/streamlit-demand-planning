# pages/0_Inicio.py
"""
Landing page + gate de carga de datos.

Mientras ``st.session_state["datos_cargados"]`` no sea True, ``app.py`` solo
registra esta página en ``st.navigation`` -- el resto de las páginas ni
siquiera aparecen en el sidebar (no solo están "escondidas", no son
alcanzables). Acá se precargan todas las fuentes de ``src/preload.py`` una
sola vez; como quedan en el cache de Streamlit, cuando el usuario entra
después a cada página no dispara ninguna consulta nueva.
"""

import streamlit as st

from src.config.settings import ibp_configurado, athena_configurado
from src.preload import FUENTES

st.title("Forecast Demanda IBP")
st.caption("Réplica funcional de los tableros Power BI: Forecast IBP y Forecast Accuracy IBP")

if "datos_cargados" not in st.session_state:
    st.session_state["datos_cargados"] = False
    st.session_state["carga_estado"] = {}

if not st.session_state["datos_cargados"]:
    st.info(
        "Cargando datos desde SAP IBP / AWS Athena antes de habilitar la navegación. "
        "La primera carga puede tardar varios minutos (después queda cacheada 30 min).",
        icon="⏳",
    )

    progreso = st.progress(0.0)
    tabla = st.empty()
    estados = {nombre: "⏳ Pendiente" for nombre, _, _ in FUENTES}

    def _refrescar():
        tabla.table({"Fuente": list(estados.keys()), "Estado": list(estados.values())})

    _refrescar()

    from src.cache import get_or_demo  # import local: evita ciclos al cargar la página

    for i, (nombre, get_fn, demo_fn) in enumerate(FUENTES):
        estados[nombre] = "🔄 Consultando..."
        _refrescar()
        _, es_demo, error = get_or_demo(get_fn, demo_fn)
        estados[nombre] = "🧪 Demo (sin conexión real)" if es_demo else "✅ Cargado"
        _refrescar()
        progreso.progress((i + 1) / len(FUENTES))

    st.session_state["datos_cargados"] = True
    st.session_state["carga_estado"] = dict(estados)
    st.rerun()

else:
    st.success("Datos cargados. Navegá a cualquier página desde el sidebar.", icon="✅")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 Tablero Forecast IBP")
        st.write("Histórico de ventas, forecast, plan anual y propuestas FCST.")
        st.page_link("pages/1_Historico_de_ventas.py", label="Histórico de ventas", icon="📈")
        st.page_link("pages/2_Forecast.py", label="Forecast", icon="🔮")
        st.page_link("pages/3_Plan_Anual.py", label="Plan Anual", icon="🗓️")
        st.page_link("pages/4_Propuestas_FCST.py", label="Propuestas FCST", icon="📝")

    with col2:
        st.subheader("🎯 Tablero Forecast Accuracy IBP")
        st.write("Accuracy/bias del forecast, segmentación de SKU y ranking de clientes.")
        st.page_link("pages/5_Reporte_Accuracy.py", label="Reporte Accuracy", icon="✅")
        st.page_link("pages/6_Segmentacion_SKU.py", label="Segmentación SKU", icon="🧩")
        st.page_link("pages/7_Ranking_Clientes.py", label="Ranking Clientes", icon="🏆")
        st.page_link("pages/8_Glosario.py", label="Glosario", icon="📖")

    st.divider()
    with st.expander("📋 Estado de la última carga"):
        for nombre, estado in st.session_state["carga_estado"].items():
            st.write(f"{estado} — {nombre}")

    if st.button("🔄 Recargar datos", help="Vuelve a consultar SAP IBP/Athena desde cero (limpia el cache)."):
        st.cache_data.clear()
        st.session_state["datos_cargados"] = False
        st.rerun()

    st.divider()
    with st.expander("⚙️ Configuración de conexión"):
        st.write(f"SAP IBP (OData): {'✅ configurado' if ibp_configurado() else '❌ falta completar ibp.env'}")
        st.write(f"AWS Athena (Data Lake): {'✅ configurado' if athena_configurado() else '❌ falta completar aws.env'}")
        st.caption("Ver .env.example para los nombres de variables esperados.")
