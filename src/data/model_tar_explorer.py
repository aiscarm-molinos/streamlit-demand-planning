# src/data/model_tar_explorer.py
"""
Exploración local de un ``model.tar`` de SageMaker (salida de
``exp/<usuario>/models/<entrenamiento>/output/model.tar``).

Modo local: mientras el rol ``MRP_Analistas_IBP_AWS`` no tenga
``s3:GetObject`` (ver ``aws_s3_experimentos.py``), el tablero explora una
copia del ``.tar`` puesta a mano en ``sample_data/sagemaker/`` en vez de
bajarla de S3. La estructura interna esperada (según el usuario, no
verificada todavía contra un .tar real):

- ``reports/``            -- reportes de la prueba (csv/txt/json/imágenes).
- ``trained_models/``     -- modelos serializados (``.pkl``).
- ``preprocessed_forecast_mensual*`` -- dataset usado en el entrenamiento.

Los ``.pkl`` NUNCA se deserializan (``pickle.load``) -- deserializar un pkl
es ejecutar código arbitrario, y estos archivos vienen de un bucket
compartido entre varios data scientists, no de una fuente controlada. Se
listan (nombre/tamaño) y nada más.
"""

import io
import tarfile
from dataclasses import dataclass, field

import pandas as pd

EXTENSIONES_TABLA = {".csv", ".tsv"}
EXTENSIONES_TEXTO = {".txt", ".json", ".log", ".md"}
EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg"}


@dataclass
class MiembroTar:
    nombre: str  # path completo dentro del tar
    size: int
    extension: str = field(init=False)

    def __post_init__(self):
        idx = self.nombre.rfind(".")
        self.extension = self.nombre[idx:].lower() if idx != -1 else ""


@dataclass
class ContenidoModelTar:
    reports: list[MiembroTar]
    trained_models: list[MiembroTar]
    dataset: list[MiembroTar]
    otros: list[MiembroTar]


def abrir_tar(ruta_o_bytes) -> tarfile.TarFile:
    if isinstance(ruta_o_bytes, (bytes, bytearray)):
        return tarfile.open(fileobj=io.BytesIO(ruta_o_bytes))
    return tarfile.open(ruta_o_bytes)


def listar_contenido(tar: tarfile.TarFile) -> ContenidoModelTar:
    reports, trained_models, dataset, otros = [], [], [], []

    for miembro in tar.getmembers():
        if not miembro.isfile():
            continue
        item = MiembroTar(nombre=miembro.name, size=miembro.size)
        nombre_normalizado = miembro.name.lstrip("./")

        if nombre_normalizado.startswith("reports/"):
            reports.append(item)
        elif nombre_normalizado.startswith("trained_models/"):
            trained_models.append(item)
        elif "preprocessed_forecast_mensual" in nombre_normalizado:
            dataset.append(item)
        else:
            otros.append(item)

    clave_orden = lambda item: item.nombre
    return ContenidoModelTar(
        reports=sorted(reports, key=clave_orden),
        trained_models=sorted(trained_models, key=clave_orden),
        dataset=sorted(dataset, key=clave_orden),
        otros=sorted(otros, key=clave_orden),
    )


def leer_tabla(tar: tarfile.TarFile, miembro: MiembroTar) -> pd.DataFrame:
    """``sep=None, engine="python"`` autodetecta el delimitador -- los reports
    reales de este .tar vienen con ";" (no "," como es más común), no asumir
    coma acá. ``decimal=","`` porque las columnas numéricas vienen en formato
    ar/es ("1334,18") -- sin esto quedan como texto en vez de número."""
    with tar.extractfile(miembro.nombre) as f:
        return pd.read_csv(f, sep=None, engine="python", decimal=",")


def leer_texto(tar: tarfile.TarFile, miembro: MiembroTar) -> str:
    with tar.extractfile(miembro.nombre) as f:
        return f.read().decode("utf-8", errors="replace")


def leer_bytes(tar: tarfile.TarFile, miembro: MiembroTar) -> bytes:
    with tar.extractfile(miembro.nombre) as f:
        return f.read()
