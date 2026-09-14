# src/data/master_data_sap_ibp.py
"""
Master data de SAP IBP (jerarquías de producto/cliente).

IMPORTANTE: este Gateway (`MOLIBP`/`EXTRACT_ODATA_SRV`) exige que el
``$select`` incluya SIEMPRE una key figure (``ACTUALSQTY``, "ancla") junto
con los atributos de jerarquía -- sin ella tira
``SY/530: The selected attributes must belong to the same master data type.``,
aunque los atributos sean válidos. Es el mismo patrón que el descubierto para
las consultas con ``PERIODID3`` (necesitan una medida en el ``$select`` para
que el Gateway resuelva el contexto correctamente). Confirmado contra las
queries M reales del Power BI, que siempre incluyen ``ACTUALSQTY`` en estas
tablas de master data aunque no lo usen después. **No sacar `ACTUALSQTY` del
`$select` de estas funciones.**
"""

import pandas as pd

from src.data.consulta_odata import consulta_odata


def product_sap_ibp() -> pd.DataFrame:
    """Jerarquía de producto: PRDID, ZBIGDIVISION (Gran División), ZBIGBUSINESS
    (Gran Negocio), ZBRAND (Negocio), ZDEMFAMILY (Demand Family), PRDFAMILY
    (Familia), PRDDESCR (Product Desc), ZESTADO, ZVIGENCIA."""
    select = [
        "PRDID", "ZBIGDIVISION", "ZBIGBUSINESS", "ZBRAND",
        "ZDEMFAMILY", "ZPRDFAMILYID", "PRDFAMILY", "PRDDESCR",
        "ZESTADO", "ZVIGENCIA", "ACTUALSQTY", "UOMTOID",
    ]
    df = consulta_odata(select, "UOMTOID eq 'CAJ'")
    return df.drop(columns=["UOMTOID", "ACTUALSQTY", "__metadata"], errors="ignore")


def customer_sap_ibp() -> pd.DataFrame:
    """Jerarquía de cliente: CUSTID, ZAREACOMERCIAL (Area Comercial),
    ZAREAFCST, ZAREAGC (Area/GC), CUSTCHANNEL, CUSTDESCR, CUSTGROUP
    (Customer Group)."""
    select = [
        "CUSTID", "ZAREACOMERCIAL", "ZAREAFCST",
        "ZAREAGC", "ZCANAL", "CUSTCHANNEL", "ZCLIENTEBOCA",
        "CUSTDESCR", "CUSTGROUP", "ACTUALSQTY", "UOMTOID",
    ]
    df = consulta_odata(select, "UOMTOID eq 'UMG' and ZCLIENTEBOCA eq 'Cliente'")
    return df.drop(columns=["UOMTOID", "ACTUALSQTY", "__metadata"], errors="ignore")
