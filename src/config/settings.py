# src/config/settings.py
"""
Carga y exposición de credenciales y configuración de conexión.

Lee variables de entorno desde dos archivos .env ubicados en la raíz del
proyecto (ver .env.example):

- ``ibp.env``: credenciales y URL de SAP IBP OData (IBP_USERNAME,
  IBP_PASSWORD, IBP_URL, IBP_PA_DEMANDA).
- ``aws.env``: configuración de AWS Athena (AWS_PROFILE, AWS_REGION,
  AWS_DATABASE, AWS_S3_STAGING).
- ``aws_credentials.env`` (opcional): credenciales explícitas de AWS
  (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN) para cuando
  no hay un perfil SSO configurado localmente (``aws configure sso``). Si
  están presentes, ``aws_ejecutar_query.py`` las usa en vez de
  ``AWS_PROFILE``.
- ``s3_sagemaker.env``: configuración de AWS S3 para "Experimentos
  SageMaker" (AWS_PROFILE_SAGEMAKER/AWS_REGION_SAGEMAKER o credenciales
  explícitas *_SAGEMAKER, AWS_S3_SAGEMAKER_BUCKET, AWS_S3_SAGEMAKER_PREFIX).
  Cuenta y rol DISTINTOS de los de Athena (cuenta "AI_Platform_DEV", rol
  "MRP_Analistas_IBP_AWS") -- por eso no reutiliza aws_profile_name.

Mismo patrón que ``ibp-forecast-mensual/src/config/settings.py``. Ninguno
de los dos .env se commitea (ver .gitignore).

Red corporativa: el tráfico HTTPS pasa por un proxy/firewall que reemplaza
el certificado del servidor por uno firmado con una CA interna (típico de
Molinos). Windows ya confía en esa CA (viene instalada por política de
dominio), pero el almacén de certificados de Python (``certifi``) no la
conoce -- sin esto, cualquier ``requests.get`` a un host externo falla con
``SSLCertVerificationError: self-signed certificate in certificate chain``.
El fix (``truststore``, para que ``requests`` use el almacén nativo del SO)
vive en ``src/data/consulta_odata.py``, acotado a esa sesión de requests --
NO se aplica acá de forma global (``truststore.inject_into_ssl()`` rompe a
botocore/boto3 con un ``RecursionError`` al construir su propio contexto
SSL: es una incompatibilidad conocida entre truststore y cómo botocore arma
el ``ssl_context`` de urllib3).
"""

import os

from dotenv import load_dotenv

from src.config.dynamics_config import root_path

# -------------------------------
# SAP IBP SETTINGS
# -------------------------------
ibp_env_path = os.path.join(root_path, "ibp.env")
load_dotenv(dotenv_path=ibp_env_path)

ibp_username = os.getenv("IBP_USERNAME")
ibp_password = os.getenv("IBP_PASSWORD")
ibp_base_url = os.getenv("IBP_BASE_URL")
ibp_resource = os.getenv("IBP_PA_DEMANDA")

# -------------------------------
# AWS ATHENA SETTINGS
# -------------------------------
aws_env_path = os.path.join(root_path, "aws.env")
load_dotenv(dotenv_path=aws_env_path)

aws_profile_name = os.getenv("AWS_PROFILE")
aws_region_name = os.getenv("AWS_REGION")
aws_database = os.getenv("AWS_DATABASE")
aws_s3_staging_dir = os.getenv("AWS_S3_STAGING")
aws_query_results = "query-results/"
aws_output_location = (
    os.path.join(aws_s3_staging_dir, aws_query_results) if aws_s3_staging_dir else None
)

# Credenciales explícitas (alternativa a AWS_PROFILE cuando no hay SSO local configurado)
aws_credentials_env_path = os.path.join(root_path, "aws_credentials.env")
load_dotenv(dotenv_path=aws_credentials_env_path)

aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_session_token = os.getenv("AWS_SESSION_TOKEN")

# -------------------------------
# AWS S3 SETTINGS (Experimentos SageMaker)
# -------------------------------
# Cuenta/rol distintos a los de Athena arriba (cuenta "AI_Platform_DEV", rol
# "MRP_Analistas_IBP_AWS") -- por eso viven en su propio .env con su propio
# perfil/credenciales, en vez de reutilizar aws_profile_name.
s3_sagemaker_env_path = os.path.join(root_path, "s3_sagemaker.env")
load_dotenv(dotenv_path=s3_sagemaker_env_path)

aws_profile_name_sagemaker = os.getenv("AWS_PROFILE_SAGEMAKER")
aws_region_name_sagemaker = os.getenv("AWS_REGION_SAGEMAKER")
s3_sagemaker_bucket = os.getenv("AWS_S3_SAGEMAKER_BUCKET")
s3_sagemaker_prefix = (os.getenv("AWS_S3_SAGEMAKER_PREFIX") or "").strip("/")

aws_access_key_id_sagemaker = os.getenv("AWS_ACCESS_KEY_ID_SAGEMAKER")
aws_secret_access_key_sagemaker = os.getenv("AWS_SECRET_ACCESS_KEY_SAGEMAKER")
aws_session_token_sagemaker = os.getenv("AWS_SESSION_TOKEN_SAGEMAKER")


def ibp_configurado() -> bool:
    return bool(ibp_base_url and ibp_resource and ibp_username and ibp_password)


def athena_configurado() -> bool:
    return bool(aws_database and aws_output_location)


def s3_sagemaker_configurado() -> bool:
    return bool(s3_sagemaker_bucket)
