# src/data/aws_s3_experimentos.py
"""
Navegación de S3 para el tablero "AWS SageMaker".

Bucket ``ibp-forecast-sagemaker-data-595365649575``, prefijo
``ibp-forecast-mensual/exp`` -- ahí SageMaker deja, por usuario, los
experimentos de forecast (``input/``, ``models/``, ``predictions/``,
``processed/``). Usa credenciales propias (``s3_sagemaker.env``, cuenta
"AI_Platform_DEV", rol "MRP_Analistas_IBP_AWS"), distintas de las de Athena
en ``aws_ejecutar_query.py``.

El rol ``MRP_Analistas_IBP_AWS`` hoy solo tiene ``s3:ListBucket`` -- las
funciones de listado (``listar_*``) andan; ``descargar_objeto`` (necesita
``s3:GetObject``) va a fallar con ``AccessDenied`` hasta que se sumen
permisos. Los callers deben capturar ``ClientError`` alrededor de
``descargar_objeto`` y ofrecer el modo local (``model_tar_explorer.py`` +
``sample_data/sagemaker/``) como fallback -- no está resuelto acá adentro
porque el mensaje/fallback que tiene sentido depende de cada página.
"""

from dataclasses import dataclass

import boto3

from src.config.settings import (
    aws_profile_name_sagemaker,
    aws_region_name_sagemaker,
    s3_sagemaker_bucket,
    s3_sagemaker_prefix,
    aws_access_key_id_sagemaker,
    aws_secret_access_key_sagemaker,
    aws_session_token_sagemaker,
)


@dataclass
class ObjetoS3:
    nombre: str  # último segmento de la key (sin el prefijo del listado)
    key: str  # key completa
    size: int
    last_modified: str
    storage_class: str


def _crear_sesion_aws_sagemaker() -> boto3.Session:
    """Credenciales explícitas (s3_sagemaker.env, sufijo _SAGEMAKER) si están
    presentes; si no, perfil de AWS CLI/SSO (AWS_PROFILE_SAGEMAKER)."""
    if aws_access_key_id_sagemaker and aws_secret_access_key_sagemaker:
        return boto3.Session(
            aws_access_key_id=aws_access_key_id_sagemaker,
            aws_secret_access_key=aws_secret_access_key_sagemaker,
            aws_session_token=aws_session_token_sagemaker,
            region_name=aws_region_name_sagemaker,
        )
    return boto3.Session(profile_name=aws_profile_name_sagemaker, region_name=aws_region_name_sagemaker)


def _cliente_s3():
    return _crear_sesion_aws_sagemaker().client("s3")


def _prefijo_exp() -> str:
    return f"{s3_sagemaker_prefix}/exp/"


def _listar_prefijo(prefix: str) -> tuple[list[str], list[ObjetoS3]]:
    """Listado no recursivo de un prefijo ("carpeta") de S3.

    Devuelve ``(subcarpetas, archivos)`` -- subcarpetas como nombre relativo
    (sin "/" final) vía ``CommonPrefixes`` (requiere ``Delimiter="/"``), y
    archivos como ``ObjetoS3`` con metadata para mostrar en tabla (nombre,
    tamaño, última modificación, storage class), tal como se ve en la
    consola de S3.
    """
    s3 = _cliente_s3()
    subcarpetas: list[str] = []
    archivos: list[ObjetoS3] = []

    paginator = s3.get_paginator("list_objects_v2")
    for pagina in paginator.paginate(Bucket=s3_sagemaker_bucket, Prefix=prefix, Delimiter="/"):
        for cp in pagina.get("CommonPrefixes", []):
            subcarpetas.append(cp["Prefix"][len(prefix):].rstrip("/"))
        for obj in pagina.get("Contents", []):
            if obj["Key"] == prefix:  # el propio "directorio" como marcador, si existe
                continue
            archivos.append(
                ObjetoS3(
                    nombre=obj["Key"][len(prefix):],
                    key=obj["Key"],
                    size=obj["Size"],
                    last_modified=obj["LastModified"].isoformat(),
                    storage_class=obj.get("StorageClass", "STANDARD"),
                )
            )

    return sorted(subcarpetas), sorted(archivos, key=lambda o: o.nombre)


def listar_usuarios() -> list[str]:
    """Carpetas de usuario bajo ``exp/`` (cada una, un data scientist)."""
    subcarpetas, _ = _listar_prefijo(_prefijo_exp())
    return subcarpetas


def listar_carpetas_usuario(usuario: str) -> list[str]:
    """Subcarpetas dentro de ``exp/<usuario>/`` -- típicamente input/models/predictions/processed."""
    subcarpetas, _ = _listar_prefijo(f"{_prefijo_exp()}{usuario}/")
    return subcarpetas


def listar_entrenamientos(usuario: str) -> list[str]:
    """Carpetas de corrida (una por entrenamiento) dentro de ``exp/<usuario>/models/``."""
    subcarpetas, _ = _listar_prefijo(f"{_prefijo_exp()}{usuario}/models/")
    return subcarpetas


def listar_contenido(prefix_relativo: str) -> tuple[list[str], list[ObjetoS3]]:
    """Listado genérico de subcarpetas + archivos bajo ``exp/<prefix_relativo>``.

    ``prefix_relativo`` no lleva "/" inicial ni el prefijo del bucket, ej.
    ``"aiscarm/models/ibp-training-.../output"`` o ``"aiscarm/predictions"``.
    """
    prefix = f"{_prefijo_exp()}{prefix_relativo.strip('/')}/"
    return _listar_prefijo(prefix)


def descargar_objeto(key: str) -> bytes:
    """Descarga el contenido de una key de S3. Requiere ``s3:GetObject`` --
    con el rol ``MRP_Analistas_IBP_AWS`` actual, lanza ``ClientError``
    (AccessDenied). Ver el docstring del módulo para el fallback esperado."""
    s3 = _cliente_s3()
    response = s3.get_object(Bucket=s3_sagemaker_bucket, Key=key)
    return response["Body"].read()
