# src/experimentos_sagemaker_estado.py
"""
Estado compartido del "entrenamiento activo" entre las 4 páginas de
Experimentos SageMaker (``pages/9..12``). El usuario elige/descarga un
``model.tar`` una sola vez en "Experimentos SageMaker" (``pages/9``);
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
    muestra un aviso con link de vuelta a "Experimentos SageMaker" y corta
    la ejecución de la página (``st.stop()``)."""
    activo = obtener_tar_activo()
    if activo is None:
        st.info(
            "Todavía no elegiste ningún entrenamiento. Anda a \"Experimentos SageMaker\" y elegí un "
            "`model.tar` (S3 en vivo, si hay permiso de descarga, o un archivo local de ejemplo).",
            icon="👈",
        )
        st.page_link("pages/9_Experimentos_SageMaker.py", label="Ir a Experimentos SageMaker", icon="🧪")
        st.stop()
    _, _, info = activo
    st.caption(f"Entrenamiento activo: **{info['nombre']}**" + (f" (usuario `{info['usuario']}`)" if info.get("usuario") else "") + f" -- fuente: {info['origen']}")
    return activo
