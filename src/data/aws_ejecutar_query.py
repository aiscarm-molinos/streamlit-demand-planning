# src/data/aws_ejecutar_query.py
"""
Ejecución de queries en AWS Athena con polling y paginación.

Adaptado de ``ibp-algoritmo-ep/src/data/aws_ejecutar_query.py``.
``ejecutar_query(query)`` envía una query SQL a Athena, espera su
finalización mediante polling cada 2 segundos y descarga los resultados
paginados, devolviendo un ``pd.DataFrame`` (todas las columnas vienen como
string — Athena las devuelve así, castear según haga falta en el caller).
"""

import time
import boto3
import pandas as pd

from src.config.settings import (
    aws_profile_name,
    aws_region_name,
    aws_database,
    aws_output_location,
    aws_access_key_id,
    aws_secret_access_key,
    aws_session_token,
)


def _crear_sesion_aws() -> boto3.Session:
    """Credenciales explícitas (aws_credentials.env) si están presentes;
    si no, perfil de AWS CLI/SSO (AWS_PROFILE en aws.env)."""
    if aws_access_key_id and aws_secret_access_key:
        return boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=aws_region_name,
        )
    return boto3.Session(profile_name=aws_profile_name, region_name=aws_region_name)


def ejecutar_query(query: str) -> pd.DataFrame:
    if not aws_database or not aws_output_location:
        raise EnvironmentError(
            "AWS Athena no configurado: AWS_DATABASE y AWS_S3_STAGING deben "
            "estar definidos en aws.env (ver .env.example)."
        )

    session = _crear_sesion_aws()
    athena = session.client("athena")

    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": aws_database},
        ResultConfiguration={"OutputLocation": aws_output_location},
    )
    query_execution_id = response["QueryExecutionId"]

    while True:
        status = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            break
        time.sleep(2)

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "No reason provided")
        raise Exception(f"Query failed: {state}. Reason: {reason}")

    results = []
    next_token = None
    while True:
        if next_token:
            response = athena.get_query_results(QueryExecutionId=query_execution_id, NextToken=next_token)
        else:
            response = athena.get_query_results(QueryExecutionId=query_execution_id)
        results.extend(response["ResultSet"]["Rows"])
        next_token = response.get("NextToken")
        if not next_token:
            break

    columns = [col["Label"] for col in response["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
    rows = [[v.get("VarCharValue", None) for v in row["Data"]] for row in results[1:]]  # skip header

    return pd.DataFrame(rows, columns=columns)
