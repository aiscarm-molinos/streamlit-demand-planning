# pages/9_Experimentos_SageMaker.py
"""
Visualizador de experimentos de SageMaker (equipo Supply, forecast).

Independiente del gate de carga de ``0_Inicio.py`` -- no depende de datos
de SAP IBP/Athena, así que se registra en ``app.py`` siempre, sin esperar
esa precarga. Dos fuentes de datos, elegidas con un radio:

- **S3 (en vivo)**: navega ``exp/<usuario>/{input,models,predictions,
  processed}`` en el bucket de ``s3_sagemaker.env`` vía
  ``aws_s3_experimentos.py`` (solo listado -- el rol ``MRP_Analistas_IBP_AWS``
  hoy no tiene ``s3:GetObject``, así que el botón "Descargar y explorar
  model.tar" va a fallar con un mensaje claro hasta que se sumen permisos).
- **Archivo local de ejemplo**: explora un ``model.tar`` puesto a mano en
  ``sample_data/sagemaker/`` (gitignored) vía ``model_tar_explorer.py`` --
  el modo pensado para desarrollar la parte visual mientras tanto.

Cada vez que acá se abre un ``.tar`` (descarga de S3 exitosa, o elección en
modo local), queda guardado como "entrenamiento activo"
(``experimentos_sagemaker_estado.py``) -- las páginas "Curvas de
Backtesting", "Nivel de Planificación" y "Feature Importance" reusan esa
misma elección en vez de pedir que se vuelva a elegir en cada una.
"""

import glob
import os

import pandas as pd
import streamlit as st
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

from src.config.dynamics_config import root_path
from src.config.settings import s3_sagemaker_bucket, s3_sagemaker_configurado, s3_sagemaker_prefix
from src.data import aws_s3_experimentos as s3exp
from src.data import model_tar_explorer as tarexp
from src import experimentos_sagemaker_estado as estado

st.title("🧪 Experimentos SageMaker")
st.caption("Explorador de las pruebas de forecast del equipo de Supply en AWS SageMaker (exp/<usuario>/...).")

col_link1, col_link2, col_link3 = st.columns(3)
with col_link1:
    st.page_link("pages/10_Curvas_Backtesting.py", label="Curvas de Backtesting", icon="📉")
with col_link2:
    st.page_link("pages/11_Nivel_Planificacion.py", label="Nivel de Planificación", icon="🧭")
with col_link3:
    st.page_link("pages/12_Feature_Importance.py", label="Feature Importance", icon="🧠")

SAMPLE_DIR = os.path.join(root_path, "sample_data", "sagemaker")
ORDEN_CARPETAS_USUARIO = ["input", "models", "predictions", "processed"]


def _formato_tamano(num_bytes: int) -> str:
    tamano = float(num_bytes)
    for unidad in ["B", "KB", "MB", "GB"]:
        if tamano < 1024:
            return f"{tamano:.1f} {unidad}"
        tamano /= 1024
    return f"{tamano:.1f} TB"


def _tabla_objetos(archivos: list[s3exp.ObjetoS3]) -> None:
    if not archivos:
        st.caption("(carpeta vacía)")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Nombre": o.nombre,
                    "Tamaño": _formato_tamano(o.size),
                    "Última modificación": o.last_modified,
                    "Storage class": o.storage_class,
                }
                for o in archivos
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def _explorar_model_tar(tar) -> None:
    contenido = tarexp.listar_contenido(tar)

    tab_reports, tab_modelos, tab_dataset = st.tabs(
        [
            f"📄 Reports ({len(contenido.reports)})",
            f"🧠 Modelos entrenados ({len(contenido.trained_models)})",
            f"📦 Dataset ({len(contenido.dataset)})",
        ]
    )

    with tab_reports:
        if not contenido.reports:
            st.caption("No hay archivos en reports/.")
        for miembro in contenido.reports:
            with st.expander(f"{miembro.nombre} ({_formato_tamano(miembro.size)})"):
                if miembro.extension in tarexp.EXTENSIONES_TABLA:
                    st.dataframe(tarexp.leer_tabla(tar, miembro), width="stretch")
                elif miembro.extension in tarexp.EXTENSIONES_TEXTO:
                    st.code(tarexp.leer_texto(tar, miembro))
                elif miembro.extension in tarexp.EXTENSIONES_IMAGEN:
                    st.image(tarexp.leer_bytes(tar, miembro))
                else:
                    st.caption("Formato sin previsualización -- solo metadata.")

    with tab_modelos:
        if not contenido.trained_models:
            st.caption("No hay archivos en trained_models/.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [{"Archivo": m.nombre, "Tamaño": _formato_tamano(m.size)} for m in contenido.trained_models]
                ),
                width="stretch",
                hide_index=True,
            )
            st.caption("Los .pkl no se deserializan (riesgo de ejecución de código arbitrario) -- solo se listan.")

    with tab_dataset:
        if not contenido.dataset:
            st.caption("No se encontró el dataset (preprocessed_forecast_mensual) en este .tar.")
        for miembro in contenido.dataset:
            st.write(f"**{miembro.nombre}** ({_formato_tamano(miembro.size)})")
            if miembro.extension in tarexp.EXTENSIONES_TABLA:
                df = tarexp.leer_tabla(tar, miembro)
                st.dataframe(df.head(200), width="stretch")
                st.caption(f"{len(df)} filas x {len(df.columns)} columnas")
            else:
                st.caption("Formato sin previsualización -- solo metadata.")


st.divider()

fuentes_disponibles = []
if s3_sagemaker_configurado():
    fuentes_disponibles.append("S3 (en vivo)")
archivos_sample = sorted(
    set(
        glob.glob(os.path.join(SAMPLE_DIR, "*.tar"))
        + glob.glob(os.path.join(SAMPLE_DIR, "*.tar.gz"))
        + glob.glob(os.path.join(SAMPLE_DIR, "*.tgz"))
    )
)
if archivos_sample:
    fuentes_disponibles.append("Archivo local de ejemplo")

if not fuentes_disponibles:
    st.warning(
        "No hay conexión a S3 configurada (ver `s3_sagemaker.env` en `.env.example`) ni archivos de ejemplo en "
        "`sample_data/sagemaker/`. Agregá un `.tar` ahí para poder probar el tablero en local.",
        icon="⚠️",
    )
    st.stop()

fuente = st.radio("Fuente de datos", fuentes_disponibles, horizontal=True)

if fuente == "S3 (en vivo)":
    st.caption(f"Bucket `{s3_sagemaker_bucket}` · prefijo `{s3_sagemaker_prefix}/exp/`")

    try:
        usuarios = s3exp.listar_usuarios()
    except (ClientError, NoCredentialsError, ProfileNotFound) as e:
        st.error(f"No se pudo listar `exp/` en S3 -- revisá `s3_sagemaker.env`. Detalle: {e}")
        st.stop()

    if not usuarios:
        st.info("No hay carpetas de usuario bajo `exp/` todavía.")
        st.stop()

    usuario = st.selectbox("Usuario", usuarios)
    carpetas = s3exp.listar_carpetas_usuario(usuario)
    if not carpetas:
        st.info(f"`{usuario}/` no tiene subcarpetas.")
        st.stop()

    carpetas_ordenadas = [c for c in ORDEN_CARPETAS_USUARIO if c in carpetas] + [
        c for c in carpetas if c not in ORDEN_CARPETAS_USUARIO
    ]
    carpeta = st.selectbox("Carpeta", carpetas_ordenadas)

    if carpeta == "models":
        entrenamientos = s3exp.listar_entrenamientos(usuario)
        if not entrenamientos:
            st.info(f"`{usuario}/models/` no tiene entrenamientos todavía.")
            st.stop()
        entrenamiento = st.selectbox("Entrenamiento", entrenamientos)
        _, archivos_output = s3exp.listar_contenido(f"{usuario}/models/{entrenamiento}/output")
        st.subheader(f"`{usuario}/models/{entrenamiento}/output/`")
        _tabla_objetos(archivos_output)

        objeto_tar = next((o for o in archivos_output if o.nombre.startswith("model.tar")), None)
        if objeto_tar and st.button(f"⬇️ Descargar y explorar {objeto_tar.nombre}"):
            try:
                contenido_bytes = s3exp.descargar_objeto(objeto_tar.key)
            except ClientError as e:
                st.error(
                    "No se pudo descargar `model.tar` -- el rol `MRP_Analistas_IBP_AWS` no tiene permiso de "
                    f"descarga (`s3:GetObject`) todavía. Mientras tanto, usá el modo \"Archivo local de ejemplo\".\n\n`{e}`"
                )
            else:
                estado.fijar_activo_desde_bytes(
                    contenido_bytes, objeto_tar.nombre, origen="S3", usuario=usuario, entrenamiento=entrenamiento
                )
                _explorar_model_tar(tarexp.abrir_tar(contenido_bytes))
    else:
        _, archivos = s3exp.listar_contenido(f"{usuario}/{carpeta}")
        st.subheader(f"`{usuario}/{carpeta}/`")
        _tabla_objetos(archivos)

else:  # Archivo local de ejemplo
    nombres = [os.path.basename(p) for p in archivos_sample]
    elegido = st.selectbox("Archivo (sample_data/sagemaker/)", nombres)
    ruta = os.path.join(SAMPLE_DIR, elegido)
    estado.fijar_activo_desde_path(ruta, elegido, origen="local")
    _explorar_model_tar(tarexp.abrir_tar(ruta))
