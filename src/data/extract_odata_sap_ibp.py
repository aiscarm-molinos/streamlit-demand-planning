# src/data/extract_odata_sap_ibp.py
"""
Funciones de extracción de key figures desde SAP IBP vía OData.

Reconstruido a partir de las queries M (Power Query) reales de los dos
tableros Power BI (pasadas por el usuario), no por analogía con otros
repos -- son la fuente de verdad de qué key figures, UOM y filtros usa cada
tabla.

Filtros de negocio estándar (aplicados SIEMPRE, en ambos tableros):
    ZVIGENCIA eq '1'        -> solo productos vigentes
    ZAREAFCST ne 'Comex'    -> excluye exportaciones
    ZCLIENTEBOCA eq 'Cliente'
El tablero Accuracy agrega además (ver ``filtros_extra_accuracy`` más abajo):
    ZAREAFCST ne 'Tienda Molinos'
    LOCID eq 'AR01'

UOM: 'UMG' para todas las series (histórico/forecast/plan/E+P) -- 'CAJ' solo
para las consultas de master data de producto y para Margen Unitario.

Key figures
-----------
forecast_consensuado_sap_ibp       -> DEMANDPLANNINGQTY     (Forecast Consensuado)
forecast_estadistico_sap_ibp       -> STATISTICALFORECASTQTY (Forecast Estadístico)
forecast_waterfall_sap_ibp         -> las 7 versiones de forecast de la tabla ZFCST/IBP-Forecast
estimado_consensuado_sap_ibp       -> ZFCSTESTIMADO          (Estimado Consensuado, ala 12 del waterfall)
estimado_comercial_sap_ibp         -> ZFCSTCOMERCIALESTIMADO, ZAJUSTECOMERCIALESTIMADO
entregado_mensual_sap_ibp          -> ZACTUALSQTY            (Histórico de Ventas)
entregado_mensual_ajustado_sap_ibp -> ADJUSTEDACTUALSQTY     (Histórico Ajustado)
plananual_sap_ibp                  -> ZPLANANUAL, filtrado por AÑO (PERIODID1), no por mes
entregado_pendiente_sap_ibp        -> ZENTREGADO, ZPENDIENTESMTH, ZENTREGAPENDIENTEMTH (E+P, directo de IBP)
margen_unitario_sap_ibp            -> ZMARGENUNITARIOUSD
"""
from typing import Union, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.data.consulta_odata import consulta_odata

PRD_ATTRS_COMUNES = ["PRDID", "PRDFAMILY", "ZDEMFAMILY", "ZBRAND", "ZBIGBUSINESS", "ZBIGDIVISION", "UOMTOID"]
# Fact tables solo agregan por Area/GC (ZAREAGC) -- pedir CUSTID individual (o el
# resto de CUST_ATTRS_BASE) en una consulta de key figures tarda 150s+ y termina
# en 500 Internal Server Error (confirmado contra el tenant real). Master data
# de cliente (customer_sap_ibp) sí puede pedir el detalle completo.
CUST_ATTRS_AREAGC = ["ZAREAGC"]
CUST_ATTRS_BASE = ["CUSTID", "ZAREACOMERCIAL", "ZAREAFCST", "ZCANAL", "CUSTCHANNEL", "ZCLIENTEBOCA", "CUSTDESCR", "CUSTGROUP", "ZAREAGC", "UOMTOID"]

FILTROS_BASE_EQ = {"ZVIGENCIA": "1", "ZCLIENTEBOCA": "Cliente"}
FILTROS_BASE_NEQ = {"ZAREAFCST": "Comex"}
# Filtros adicionales que usa específicamente el Tablero Forecast Accuracy IBP
# (IBP - Historico Entrega / IBP - Forecast): una planta puntual y una
# exclusión de área extra.
FILTROS_EXTRA_ACCURACY_EQ = {"LOCID": "AR01"}
FILTROS_EXTRA_ACCURACY_NEQ = {"ZAREAFCST": ["Comex", "Tienda Molinos"]}


def _build_columnas_finales(columnas_base, prd_atributos, cust_atributos, prd_disp, cust_disp):
    columnas_finales = list(columnas_base)
    if prd_atributos:
        columnas_finales.extend([c for c in prd_atributos if c in prd_disp])
    elif "PRDID" in prd_disp and "PRDID" not in columnas_finales:
        columnas_finales.append("PRDID")
    if cust_atributos:
        columnas_finales.extend([c for c in cust_atributos if c in cust_disp])
    return columnas_finales


def _merge_filtros(base: dict, extra: Optional[dict]) -> dict:
    merged = dict(base)
    for k, v in (extra or {}).items():
        if k in merged:
            existentes = merged[k] if isinstance(merged[k], list) else [merged[k]]
            nuevos = v if isinstance(v, list) else [v]
            merged[k] = list(dict.fromkeys(existentes + nuevos))
        else:
            merged[k] = v
    return merged


def _build_filters_query(periodo_col, periodo_val, uom, filtros_eq=None, filtros_neq=None):
    filters = [f"{periodo_col} eq '{periodo_val}'", f"UOMTOID eq '{uom}'"]

    def _agregar(filtros, operador):
        for k, v in (filtros or {}).items():
            valores = v if isinstance(v, list) else [v]
            for item in valores:
                filters.append(f"{k} {operador} '{item}'" if isinstance(item, str) else f"{k} {operador} {item}")

    _agregar(_merge_filtros(FILTROS_BASE_EQ, filtros_eq), "eq")
    _agregar(_merge_filtros(FILTROS_BASE_NEQ, filtros_neq), "ne")
    return " and ".join(filters)


def _consulta_por_periodo(
    valores_periodo: Union[str, datetime, List[Union[str, datetime]]],
    periodo_col: str,
    columnas_base: List[str],
    prd_atributos: Optional[List[str]],
    cust_atributos: Optional[List[str]],
    columnas_prd_disponibles: List[str],
    columnas_cust_disponibles: List[str],
    filtros_eq: Optional[dict],
    filtros_neq: Optional[dict],
    uom: str,
    formatear_mes: bool = True,
    max_workers: int = 8,
) -> pd.DataFrame:
    """
    SAP IBP OData no permite pedir varios períodos en una sola consulta
    (``PERIODID3 eq 'X' or PERIODID3 eq 'Y'`` no está soportado por este
    servicio) -- hay que hacer un GET por período. Cada uno tarda ~4-10s de
    latencia de red/proxy, así que para ventanas largas (24-37 períodos) se
    disparan en paralelo (I/O-bound, ``requests.Session`` es thread-safe)
    con un tope de ``max_workers`` para no saturar el Gateway.
    """
    if isinstance(valores_periodo, (str, datetime, int)):
        valores_periodo = [valores_periodo]

    if formatear_mes:
        valores_str = [pd.to_datetime(m).strftime("%y-%b") if not isinstance(m, str) else m for m in valores_periodo]
    else:
        valores_str = [str(v) for v in valores_periodo]

    columnas_finales = _build_columnas_finales(
        columnas_base, prd_atributos, cust_atributos, columnas_prd_disponibles, columnas_cust_disponibles
    )

    def _traer(valor: str) -> pd.DataFrame:
        filters_query = _build_filters_query(periodo_col, valor, uom, filtros_eq, filtros_neq)
        df_periodo = consulta_odata(columnas_finales, filters_query)
        if df_periodo.empty:
            return df_periodo
        df_periodo = df_periodo.drop(columns="__metadata", errors="ignore")
        if "PERIODID3" in df_periodo.columns:
            df_periodo["PERIODID3"] = df_periodo["PERIODID3"].astype(str)
        return df_periodo

    with ThreadPoolExecutor(max_workers=min(max_workers, len(valores_str)) or 1) as executor:
        resultados = list(executor.map(_traer, valores_str))

    dfs = [df for df in resultados if not df.empty]
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame(columns=columnas_finales)


def _consulta_mensual(meses, columnas_base, prd_atributos, cust_atributos, prd_disp, cust_disp, filtros_eq, filtros_neq, uom):
    return _consulta_por_periodo(
        meses, "PERIODID3", columnas_base, prd_atributos, cust_atributos, prd_disp, cust_disp, filtros_eq, filtros_neq, uom
    )


def forecast_consensuado_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """Forecast Consensuado (DEMANDPLANNINGQTY)."""
    return _consulta_mensual(
        meses, ["PERIODID3", "DEMANDPLANNINGQTY"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def forecast_estadistico_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """Forecast Estadístico (STATISTICALFORECASTQTY) -- output del modelo ML,
    escrito de vuelta a SAP IBP bajo este key figure."""
    return _consulta_mensual(
        meses, ["PERIODID3", "STATISTICALFORECASTQTY"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def forecast_waterfall_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """
    Las 7 versiones de forecast de la tabla ZFCST / IBP-Forecast del Power BI
    (el "waterfall" completo de planificación) + Histórico (ACTUALSQTY,
    ADJUSTEDACTUALSQTY) + Estimado Comercial (ZFCSTCOMERCIALESTIMADO,
    ZAJUSTECOMERCIALESTIMADO), TODO en una sola consulta por mes.

    Se combinan acá (en vez de 3 consultas mensuales separadas) porque SAP
    IBP OData no permite pedir varios períodos en un solo request -- cada
    medida extra agregada al mismo ``$select`` es upside gratis (mismo
    request), mientras que cada consulta mensual SEPARADA cuesta un recorrido
    completo de N períodos. Pasar de 3 recorridos (waterfall 36 + histórico
    25 + comercial 12 = 73 requests) a 1 solo (36 requests) es la optimización
    de performance más grande posible acá. Ver ``cache.py`` para cómo cada
    ``get_*`` deriva su recorte de este único fetch sin pegarle de nuevo a SAP.

        ACTUALSQTY              -> Histórico de Ventas
        ADJUSTEDACTUALSQTY      -> Histórico Ajustado
        ZESTADISTICOAJUSTADO    -> Estadístico Ajustado
        STATISTICALFORECASTQTY  -> 01 - Forecast Estadístico
        ZFORECASTDEMANDA        -> 03 - Forecast Demanda
        SALESMGRFORECASTQTY     -> 04 - Forecast Comercial
        SALESFORECASTQTY        -> 05 - Forecast Planeamiento Comercial
        DEMANDPLANNINGQTY       -> 07 - Forecast Consensuado
        ZFCSTESTIMADO           -> 12 - Estimado Consensuado
        ZFCSTCOMERCIALESTIMADO  -> Estimado Comercial
        ZAJUSTECOMERCIALESTIMADO -> Ajuste Comercial
    """
    columnas_base = [
        "PERIODID3", "ACTUALSQTY", "ADJUSTEDACTUALSQTY",
        "ZESTADISTICOAJUSTADO", "STATISTICALFORECASTQTY", "ZFORECASTDEMANDA",
        "SALESMGRFORECASTQTY", "SALESFORECASTQTY", "DEMANDPLANNINGQTY", "ZFCSTESTIMADO",
        "ZFCSTCOMERCIALESTIMADO", "ZAJUSTECOMERCIALESTIMADO",
    ]
    return _consulta_mensual(
        meses, columnas_base, prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def estimado_consensuado_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """Estimado Consensuado (ZFCSTESTIMADO)."""
    return _consulta_mensual(
        meses, ["PERIODID3", "ZFCSTESTIMADO"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def estimado_comercial_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """Estimado Comercial (ZFCSTCOMERCIALESTIMADO) y su ajuste E+P (ZAJUSTECOMERCIALESTIMADO)."""
    return _consulta_mensual(
        meses, ["PERIODID3", "ZFCSTCOMERCIALESTIMADO", "ZAJUSTECOMERCIALESTIMADO"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def entregado_mensual_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """Histórico de Ventas (ZACTUALSQTY)."""
    return _consulta_mensual(
        meses, ["PERIODID3", "ACTUALSQTY"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def entregado_mensual_ajustado_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """Histórico Ajustado (ADJUSTEDACTUALSQTY)."""
    return _consulta_mensual(
        meses, ["PERIODID3", "ADJUSTEDACTUALSQTY"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def entregado_pendiente_sap_ibp(meses, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """
    Entregado + Pendiente del mes en curso, directo de SAP IBP (tabla ZE&P
    del Power BI) -- ZENTREGADO, ZPENDIENTESMTH, ZENTREGAPENDIENTEMTH.
    """
    return _consulta_mensual(
        meses, ["PERIODID3", "ZENTREGADO", "ZPENDIENTESMTH", "ZENTREGAPENDIENTEMTH"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom,
    )


def plananual_sap_ibp(anios, prd_atributos=None, cust_atributos=None, filtros_eq=None, filtros_neq=None, uom="UMG") -> pd.DataFrame:
    """
    Plan Anual (ZPLANANUAL), filtrado por AÑO vía PERIODID1 (no por mes) --
    igual que la tabla ZBP del Power BI. ``anios``: lista de años (int/str).
    """
    return _consulta_por_periodo(
        anios, "PERIODID1", ["PERIODID3", "ZPLANANUAL"], prd_atributos, cust_atributos,
        PRD_ATTRS_COMUNES, CUST_ATTRS_AREAGC, filtros_eq, filtros_neq, uom, formatear_mes=False,
    )


def margen_unitario_sap_ibp(periodo: str, curr: str = "USD", uom: str = "CAJ") -> pd.DataFrame:
    """
    Margen Unitario (ZMARGENUNITARIOUSD) para un único período 'yy-MMM' --
    tabla IBP - Margen del Power BI. UOM/moneda por defecto CAJ/USD (igual
    que el Power BI). Devuelve columnas: PRDID, ZMARGENUNITARIOUSD.
    """
    columnas = ["PRDID", "ZMARGENUNITARIOUSD"]
    filtro = f"UOMTOID eq '{uom}' and PERIODID3 eq '{periodo}' and CURRTOID eq '{curr}'"
    # Margen no lleva los filtros de negocio estándar en el Power BI original
    # (ZVIGENCIA/ZAREAFCST/ZCLIENTEBOCA) -- consulta directa, sin _consulta_mensual.
    df = consulta_odata(columnas, filtro)
    return df.drop(columns="__metadata", errors="ignore")
