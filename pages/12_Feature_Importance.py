# pages/12_Feature_Importance.py
"""
Feature Importance: qué variables pesaron más en la predicción -- entrenamiento
activo (ver ``experimentos_sagemaker_estado.py``). Dos modos:

- **Por entidad**: modelo(s) elegido(s) como mejores para una Familia puntual
  (vía ``mejor_nivel_planificacion_por_entidad.csv``) -- el original.
- **Agregado por nivel** (2026-09-20, a pedido del usuario): promedio de
  importancia por variable de negocio entre TODOS los modelos entrenados en
  un nivel de la jerarquía elegido (ej. todos los ``trained_models/PRDID/*.pkl``),
  para ver qué pesa en general en ese nivel, no solo en una entidad.

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

Traducción de negocio de las variables (``src/feature_labels.py``): agrupa
rezagos/categorías dummy de una misma variable (ej. todas las ``YEAR_*``,
``MONTH_sin``/``MONTH_cos``) bajo un único nombre de negocio -- el detalle
técnico crudo (feature exacto + rezago) sigue disponible en un expander
para quien lo necesite, no se pierde.
"""

import pandas as pd
import streamlit as st

from src import charts
from src import experimentos_sagemaker_estado as estado
from src import feature_labels as flabels
from src import nivel_planificacion as niveles
from src.data import model_deserializer
from src.data import model_tar_explorer as tarexp

st.title("🧠 Feature Importance")
st.caption("Qué variables pesaron más en la predicción -- por entidad, o agregado en un nivel entero de la jerarquía.")

tar, contenido, info = estado.requerir_tar_activo()

if not model_deserializer.venv310_disponible():
    st.warning(
        "No está creado `.venv310` (Python 3.10 + `requirements_fcst.txt`), necesario para deserializar "
        "modelos. Ver README, sección \"AWS SageMaker\", para crearlo.",
        icon="⚠️",
    )
    st.stop()

st.divider()

modo = st.radio("Modo", ["Por entidad", "Agregado por nivel"], horizontal=True)


def _mostrar_importancias(df_fi_raw: pd.DataFrame, titulo: str, key_prefix: str) -> None:
    """Traduce, agrega por variable de negocio y muestra (gráfico + tabla +
    detalle técnico crudo) -- compartido por los dos modos."""
    df_traducido = flabels.traducir_importancias(df_fi_raw)
    df_agregado = flabels.agregar_por_variable(df_traducido)

    st.plotly_chart(
        charts.bar_chart(
            df_agregado.sort_values("importance").tail(15),
            x="importance", y="Etiqueta", orientation="h", title=titulo,
        ),
        width="stretch",
    )
    st.dataframe(
        df_agregado[["Etiqueta", "Grupo", "importance"]].rename(columns={"importance": "Importancia"}),
        width="stretch", hide_index=True,
    )
    charts.boton_descarga_csv(df_agregado, "feature_importance_por_variable.csv", key=f"{key_prefix}_descarga_agregado")

    with st.expander("Ver detalle técnico (feature crudo, rezago)"):
        st.dataframe(
            df_traducido[["feature", "Etiqueta", "Grupo", "Rezago (meses)", "importance"]]
            .rename(columns={"feature": "Feature crudo", "importance": "Importancia"})
            .sort_values("Importancia", ascending=False),
            width="stretch", hide_index=True,
        )
        charts.boton_descarga_csv(df_traducido, "feature_importance_detalle_crudo.csv", key=f"{key_prefix}_descarga_detalle")


if modo == "Por entidad":
    m_mejor_nivel = tarexp.buscar_miembro("mejor_nivel_planificacion_por_entidad.csv", contenido.reports)
    m_dataset = next((m for m in contenido.dataset if m.extension in tarexp.EXTENSIONES_TABLA), None)

    if m_mejor_nivel is None or m_dataset is None:
        st.warning("Este entrenamiento no tiene `mejor_nivel_planificacion_por_entidad.csv` o el dataset.", icon="⚠️")
        st.stop()

    df_mejor_nivel = tarexp.leer_tabla(tar, m_mejor_nivel)
    df_dataset = tarexp.leer_tabla(tar, m_dataset)

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
                    st.caption(f"Regressor: `{resultado.get('regressor')}` -- skforecast `{resultado.get('skforecast_version')}`")
                    _mostrar_importancias(pd.DataFrame(resultado["importancias"]), f"Importancia por variable -- {valor}", key_prefix=f"entidad_{nombre_esperado}")

else:  # Agregado por nivel
    st.caption(
        "Promedia la importancia de cada variable de negocio entre TODOS los modelos entrenados en el nivel "
        "elegido -- deserializa un .pkl por modelo (subproceso), puede tardar con niveles grandes (ej. PRDID)."
    )

    niveles_con_modelos = sorted({m.nombre.split("/")[1] for m in contenido.trained_models if "/" in m.nombre})
    if not niveles_con_modelos:
        st.info("Este entrenamiento no tiene modelos en `trained_models/`.")
        st.stop()

    nivel_agregado = st.selectbox("Nivel de planificación", niveles_con_modelos, format_func=niveles.etiqueta_nivel)
    miembros_nivel = [m for m in contenido.trained_models if m.nombre.startswith(f"trained_models/{nivel_agregado}/")]
    st.write(f"**{len(miembros_nivel)}** modelo(s) en este nivel.")

    if st.button(f"📊 Calcular Feature Importance agregado ({len(miembros_nivel)} modelo(s))", key="calcular_agregado_nivel"):
        progreso = st.progress(0.0, text="Deserializando modelos...")
        filas_agregadas = []
        errores = []
        top5_por_modelo = []

        for i, miembro in enumerate(miembros_nivel):
            pkl_bytes = tarexp.leer_bytes(tar, miembro)
            resultado = model_deserializer.extraer_feature_importance(pkl_bytes)
            progreso.progress((i + 1) / len(miembros_nivel), text=f"Deserializando modelos... ({i + 1}/{len(miembros_nivel)})")

            if not resultado.get("ok"):
                errores.append({"Archivo": miembro.nombre, "Error": resultado.get("error", "desconocido")})
                continue

            df_modelo = pd.DataFrame(resultado["importancias"])
            if df_modelo.empty or df_modelo["importance"].sum() == 0:
                continue
            df_modelo["importance"] = df_modelo["importance"] / df_modelo["importance"].sum()  # normalizar por si el regressor no suma 1

            df_trad = flabels.traducir_importancias(df_modelo)
            df_agg_modelo = flabels.agregar_por_variable(df_trad)
            df_agg_modelo["Archivo"] = miembro.nombre
            filas_agregadas.append(df_agg_modelo)

            top5 = set(df_agg_modelo.sort_values("importance", ascending=False).head(5)["Etiqueta"])
            top5_por_modelo.append(top5)

        progreso.empty()

        if errores:
            with st.expander(f"⚠️ {len(errores)} modelo(s) no se pudieron deserializar"):
                st.dataframe(pd.DataFrame(errores), width="stretch", hide_index=True)

        if not filas_agregadas:
            st.warning("Ningún modelo de este nivel se pudo deserializar con éxito.", icon="⚠️")
            st.stop()

        df_todos = pd.concat(filas_agregadas, ignore_index=True)
        n_modelos_ok = df_todos["Archivo"].nunique()

        df_promedio = (
            df_todos.groupby(["Etiqueta", "Grupo"], as_index=False)["importance"]
            .mean()
            .sort_values("importance", ascending=False)
        )
        df_promedio["En cuántos modelos aparece"] = df_todos.groupby("Etiqueta")["Archivo"].nunique().reindex(df_promedio["Etiqueta"]).values
        conteo_top5 = pd.Series([et for top5 in top5_por_modelo for et in top5]).value_counts()
        df_promedio["Veces en Top 5 del modelo"] = df_promedio["Etiqueta"].map(conteo_top5).fillna(0).astype(int)

        st.subheader(f"Importancia promedio -- {niveles.etiqueta_nivel(nivel_agregado)} ({n_modelos_ok} modelo(s))")
        st.plotly_chart(
            charts.bar_chart(df_promedio.sort_values("importance").tail(15), x="importance", y="Etiqueta", orientation="h"),
            width="stretch",
        )
        st.dataframe(
            df_promedio.rename(columns={"importance": "Importancia promedio"}),
            width="stretch", hide_index=True,
        )
        st.caption(
            "\"Veces en Top 5 del modelo\" -- en cuántos de los modelos deserializados esta variable estuvo entre "
            "las 5 más importantes (no solo el promedio general, que un único modelo con importancia muy alta "
            "puede inflar)."
        )
        charts.boton_descarga_csv(df_promedio, f"feature_importance_agregado_{nivel_agregado}.csv", key="descarga_agregado_nivel")
