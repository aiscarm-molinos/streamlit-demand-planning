# src/data/consulta_odata.py
"""
Cliente HTTP básico para el servicio OData de SAP IBP.

Adaptado de ``ibp-forecast-mensual/src/data/consulta_odata.py``. Expone
``consulta_odata``, usada internamente por ``extract_odata_sap_ibp.py`` y
``master_data_sap_ibp.py`` para hacer GET al endpoint OData configurado en
``ibp.env`` (ver ``src/config/settings.py``).

Red corporativa: el proxy/firewall re-firma el HTTPS con una CA interna que
Windows ya conoce pero ``certifi`` (el almacén que usa ``requests`` por
default) no. ``_sesion_con_certs_windows()`` arma una ``requests.Session``
que usa el almacén de certificados del SO (vía ``truststore``) SOLO para
estas llamadas -- a propósito no se aplica de forma global
(``truststore.inject_into_ssl()``), porque eso rompe a boto3/botocore
(usado para Athena) con un ``RecursionError`` al construir su propio
contexto SSL.
"""

import ssl
import warnings

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.exceptions import InsecureRequestWarning
import truststore
import pandas as pd

from src.config.settings import ibp_username, ibp_password, ibp_base_url, ibp_resource

# urllib3 no reconoce del todo un ssl.SSLContext ajeno (el de truststore) y
# por eso emite este warning -- verificado a mano que la validación de
# certificado SIGUE activa (una conexión a un host con certificado
# genuinamente inválido falla como corresponde). Es un falso positivo
# conocido de la combinación truststore + urllib3, no una verificación
# deshabilitada.
warnings.filterwarnings("ignore", category=InsecureRequestWarning)


# Tamaño del pool de conexiones HTTP -- por default `requests`/urllib3 usa 10,
# que se queda corto en cuanto el ThreadPoolExecutor de
# ``extract_odata_sap_ibp.py`` dispara varios GET concurrentes al mismo host:
# sin esto, los workers de más quedan haciendo cola por una conexión libre en
# vez de viajar en paralelo de verdad.
POOL_SIZE = 20


class _TruststoreAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        # ``ssl_context`` es un kwarg reconocido por PoolManager/urllib3.
        # pool_connections/pool_maxsize NO van acá -- van en el __init__ del
        # adapter (ver más abajo), que es quien le pasa `connections`/
        # `maxsize` posicionales a este método.
        kwargs["ssl_context"] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return super().init_poolmanager(*args, **kwargs)


def _sesion_con_certs_windows() -> requests.Session:
    session = requests.Session()
    session.mount("https://", _TruststoreAdapter(pool_connections=POOL_SIZE, pool_maxsize=POOL_SIZE))
    return session


_session = _sesion_con_certs_windows()


def consulta_odata(select: list, filters: str = None) -> pd.DataFrame:
    """Descarga datos de SAP IBP usando OData con credenciales fijas."""
    if not ibp_base_url or not ibp_resource:
        raise EnvironmentError(
            "SAP IBP no configurado: IBP_URL e IBP_PA_DEMANDA deben estar "
            "definidos en ibp.env (ver .env.example)."
        )

    params = {
        "$format": "json",
        "$select": ",".join(select),
    }
    if filters:
        params["$filter"] = filters

    response = _session.get(
        f"{ibp_base_url}/{ibp_resource}",
        params=params,
        auth=HTTPBasicAuth(ibp_username, ibp_password),
        headers={"Accept": "application/json"},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json().get("d", {}).get("results", [])
    return pd.DataFrame(data) if data else pd.DataFrame()
