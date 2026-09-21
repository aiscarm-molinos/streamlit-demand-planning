# src/experimentos_sagemaker_estado.py
"""
Estado compartido del "entrenamiento activo" entre las 4 páginas de
AWS SageMaker (``pages/9..12``). El usuario elige/descarga un
``model.tar`` una sola vez en "Explorador de Entrenamientos" (``pages/9``);
"Curvas de Backtesting", "Nivel de Planificación" y "Feature Importance"
reusan esa misma elección vía ``st.session_state`` en vez de pedir que se
vuelva a elegir en cada página.

Solo se guarda un **path a un archivo local** (nunca bytes ni un
``tarfile.TarFile`` abierto) en ``session_state`` -- un archivo local ya
puesto en ``sample_data/sagemaker/`` se referencia directo por su path; un
``.tar`` bajado de S3 se vuelca primero a un archivo temporal (ver
``fijar_activo_desde_bytes``) para tener siempre la misma interfaz de
lectura (``model_tar_explorer.abrir_tar`` acepta un path). Guardar solo el
path (no un objeto ``TarFile`` vivo) evita depender de que un handle de
archivo siga abierto entre reruns de Streamlit, que no está garantizado.
"""

import os
import tempfile

import streamlit as st

from src.data import model_tar_explorer as tarexp

CLAVE_ESTADO = "sm_tar_activo"
CLAVE_ENTIDAD = "sm_entidad_seleccionada"


def fijar_activo_desde_path(path: str, nombre: str, origen: str, usuario: str | None = None, entrenamiento: str | None = None) -> None:
    st.session_state[CLAVE_ESTADO] = {
        "path": path,
        "nombre": nombre,
        "origen": origen,
        "usuario": usuario,
        "entrenamiento": entrenamiento,
    }


def fijar_activo_desde_bytes(data: bytes, nombre: str, origen: str, usuario: str | None = None, entrenamiento: str | None = None) -> None:
    sufijo = "".join(os.path.splitext(nombre)) if "." in nombre else ".tar"
    with tempfile.NamedTemporaryFile(suffix=sufijo, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    fijar_activo_desde_path(path, nombre, origen, usuario, entrenamiento)


def tar_activo_info() -> dict | None:
    return st.session_state.get(CLAVE_ESTADO)


def obtener_tar_activo():
    """``(tar, contenido, info)`` del entrenamiento activo, o ``None`` si
    todavía no se eligió ninguno."""
    info = tar_activo_info()
    if info is None:
        return None
    tar = tarexp.abrir_tar(info["path"])
    contenido = tarexp.listar_contenido(tar)
    return tar, contenido, info


def requerir_tar_activo():
    """Para usar al principio de las páginas 10/11/12: si hay un
    entrenamiento activo, devuelve ``(tar, contenido, info)``; si no,
    muestra un aviso con link de vuelta a "Explorador de Entrenamientos" y corta
    la ejecución de la página (``st.stop()``)."""
    activo = obtener_tar_activo()
    if activo is None:
        st.info(
            "Todavía no elegiste ningún entrenamiento. Anda a \"Explorador de Entrenamientos\" y elegí un "
            "`model.tar` (S3 en vivo, si hay permiso de descarga, o un archivo local de ejemplo).",
            icon="👈",
        )
        st.page_link("pages/9_Experimentos_SageMaker.py", label="Ir a Explorador de Entrenamientos", icon="🧪")
        st.stop()
    _, _, info = activo
    st.caption(f"Entrenamiento activo: **{info['nombre']}**" + (f" (usuario `{info['usuario']}`)" if info.get("usuario") else "") + f" -- fuente: {info['origen']}")
    return activo


@st.cache_data(show_spinner="Bajando el dataset procesado de S3...")
def dataset_procesado_s3(usuario: str):
    """``exp/<usuario>/processed/preprocessed_forecast_mensual.csv`` como DataFrame
    (cacheado por usuario). Lanza la excepción de boto3 si falla."""
    from src.data import aws_s3_experimentos as s3exp

    return tarexp.leer_tabla_desde_bytes(s3exp.descargar_dataset_procesado(usuario))


def es_origen_s3(info) -> bool:
    return bool(info) and info.get("origen") == "S3" and bool(info.get("usuario"))


def cargar_dataset(tar, contenido, info):
    """Dataset (``preprocessed_forecast_mensual``) del entrenamiento activo,
    como ``DataFrame``, o ``None`` si no se pudo obtener.

    Con origen S3 (en vivo) siempre viene de ``<usuario>/processed/`` (decisión
    del usuario, 2026-09-21) -- es el dataset más reciente del usuario, no
    necesariamente el de esa corrida; se avisa con un caption. Solo si esa
    descarga falla se cae al del propio tar (si lo trae). Con origen local, del tar."""
    m_dataset = next((m for m in contenido.dataset if m.extension in tarexp.EXTENSIONES_TABLA), None)

    if es_origen_s3(info):
        try:
            df = dataset_procesado_s3(info["usuario"])
        except Exception as e:
            st.warning(f"No se pudo bajar el dataset de `{info['usuario']}/processed/` en S3: `{e}`", icon="⚠️")
        else:
            st.caption(
                f"ℹ️ Dataset tomado de S3 (`{info['usuario']}/processed/preprocessed_forecast_mensual.csv`, "
                "el más reciente del usuario, no necesariamente el de esta corrida)."
            )
            return df

    if m_dataset is not None:
        return tarexp.leer_tabla(tar, m_dataset)
    return None


def fijar_entidad_seleccionada(nivel: str, valor: str) -> None:
    """Guarda ``(nivel, valor)`` para que "Curvas de Backtesting" los
    preseleccione la próxima vez que se abra -- usado desde tablas de
    triage (ej. "Explorador de Entrenamientos", "Nivel de Planificación") para saltar
    directo a la curva de una entidad puntual en vez de tener que volver a
    elegirla a mano."""
    st.session_state[CLAVE_ENTIDAD] = {"nivel": nivel, "valor": str(valor)}


def consumir_entidad_seleccionada() -> dict | None:
    """Devuelve y BORRA la entidad pendiente (si hay) -- se consume una
    sola vez, para no pisar una selección manual posterior del usuario en
    la misma página."""
    return st.session_state.pop(CLAVE_ENTIDAD, None)
