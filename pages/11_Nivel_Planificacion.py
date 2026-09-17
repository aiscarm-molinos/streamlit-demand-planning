# pages/11_Nivel_Planificacion.py
"""
Nivel de Planificación: cuántas veces cada nivel de la jerarquía de
producto (PRDID/PRDFAMILY/ZINDFAMILY/ZBRAND/ZBIGBUSINESS) resultó elegido
como el de menor error para una entidad (PRDFAMILY), y el accuracy de ese
nivel elegido -- para el entrenamiento activo (ver
``experimentos_sagemaker_estado.py``).

Fuentes: ``reports/mejor_nivel_planificacion_por_entidad.csv`` (nivel
elegido + error por entidad), ``reports/modelos_forecast_mensual.csv``
(accuracy por nivel/valor), ``reports/resumen_niveles_planificacion_mensual.csv``
(error de TODOS los niveles candidatos evaluados por entidad, no solo el
ganador -- usado en la sección "Comparación de niveles candidatos", ver
más abajo) y el dataset (preprocessed_forecast_mensual, para resolver a
qué valor de cada nivel pertenece cada entidad -- ver
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

m_mejor_nivel = tarexp.buscar_miembro("mejor_nivel_planificacion_por_entidad.csv", contenido.reports)
m_modelos = tarexp.buscar_miembro("modelos_forecast_mensual.csv", contenido.reports)
m_resumen_niveles = tarexp.buscar_miembro("resumen_niveles_planificacion_mensual.csv", contenido.reports)
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
df_resumen_niveles = tarexp.leer_tabla(tar, m_resumen_niveles) if m_resumen_niveles is not None else None

st.divider()

st.subheader("Cantidad de veces elegido como mejor nivel")
conteo = df_mejor_nivel["MEJOR_NIVEL_PLANIFICACION"].value_counts().reset_index()
conteo.columns = ["Nivel", "Cantidad de entidades"]
conteo["Nivel"] = conteo["Nivel"].map(niveles.etiqueta_nivel)
st.plotly_chart(charts.bar_chart(conteo, x="Nivel", y="Cantidad de entidades"), width="stretch")

st.subheader("Detalle por entidad")
resumen = niveles.resumen_nivel_elegido(df_mejor_nivel, df_modelos, df_dataset)
df_resumen = pd.DataFrame(
    [
        {
            "Familia": r.prdfamily,
            "Nivel elegido": niveles.etiqueta_nivel(r.nivel),
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
    "valores del nivel a los que pertenece la entidad -- si el nivel elegido es más fino que Familia (ej. "
    "SKU), una misma entidad puede resolver a varios valores y el número es un promedio entre ellos, no un "
    "único accuracy exacto."
)
charts.boton_descarga_csv(df_resumen, "detalle_nivel_por_entidad.csv", key="descarga_detalle_nivel")

# --------------------------------------------------
# Comparación de niveles candidatos por entidad (2026-09-20, a pedido del
# usuario) -- resumen_niveles_planificacion_mensual.csv trae el error de
# TODOS los niveles evaluados por entidad, no solo el ganador. Antes este
# archivo no se usaba en ningún lado de la app.
# --------------------------------------------------
st.divider()
st.subheader("Comparación de niveles candidatos por entidad")

if df_resumen_niveles is None or df_resumen_niveles.empty:
    st.info("Este entrenamiento no tiene `reports/resumen_niveles_planificacion_mensual.csv` -- no se puede comparar niveles candidatos.")
else:
    entidad_elegida = st.selectbox("Familia", sorted(df_resumen_niveles["PRDFAMILY"].unique()), key="entidad_comparacion_niveles")

    df_niveles_entidad = df_resumen_niveles[df_resumen_niveles["PRDFAMILY"] == entidad_elegida].copy()
    fila_ganador = df_mejor_nivel[df_mejor_nivel["PRDFAMILY"] == entidad_elegida]
    nivel_ganador = fila_ganador["MEJOR_NIVEL_PLANIFICACION"].iloc[0] if not fila_ganador.empty else None

    df_niveles_entidad["Nivel"] = df_niveles_entidad["NIVEL_EVALUADO"].map(niveles.etiqueta_nivel)
    df_niveles_entidad["Resultado"] = df_niveles_entidad["NIVEL_EVALUADO"].apply(
        lambda n: "Elegido (menor error)" if n == nivel_ganador else "Candidato"
    )
    df_niveles_entidad = df_niveles_entidad.sort_values("ERROR_ABS_TOTAL")

    st.plotly_chart(
        charts.bar_chart(df_niveles_entidad, x="Nivel", y="ERROR_ABS_TOTAL", color="Resultado", title=f"Error absoluto por nivel candidato -- {entidad_elegida}"),
        width="stretch",
    )
    st.dataframe(
        df_niveles_entidad[["Nivel", "ERROR_ABS_TOTAL", "Resultado"]],
        width="stretch",
        hide_index=True,
    )
    charts.boton_descarga_csv(df_niveles_entidad, f"niveles_candidatos_{entidad_elegida}.csv", key="descarga_niveles_candidatos")

    if nivel_ganador:
        valores_ganador = niveles.valores_de_nivel(df_dataset, entidad_elegida, nivel_ganador)
        if valores_ganador:
            if st.button(f"📉 Ver curva de backtesting de '{valores_ganador[0]}' ({niveles.etiqueta_nivel(nivel_ganador)})", key="ir_a_curva"):
                estado.fijar_entidad_seleccionada(nivel_ganador, valores_ganador[0])
                st.switch_page("pages/10_Curvas_Backtesting.py")
