# src/cache.py
"""
Wrappers ``st.cache_data`` sobre los conectores de ``src/data/``.

Streamlit re-ejecuta todo el script en cada interacción del usuario (cambiar
un filtro, etc.) — sin cache, eso dispararía una consulta nueva a SAP
IBP/Athena por cada click. Acá se hace UNA consulta amplia (ventana de meses
histórica + futura) por sesión/TTL, y las páginas filtran el DataFrame ya en
memoria con pandas (ver ``src/filters.py``).

Grano de cliente: TODAS las consultas de key figures piden como mucho
``ZAREAGC`` (nunca CUSTID individual) -- confirmado tanto por las queries M
reales del Power BI como por pruebas contra el tenant (CUSTID: 150s+ y 500;
ZAREAGC: ~8s). Detalle de cliente más fino no es viable en vivo.
"""

import pandas as pd
import streamlit as st

from src.data.extract_odata_sap_ibp import (
    forecast_waterfall_sap_ibp,
    entregado_pendiente_sap_ibp,
    plananual_sap_ibp,
    margen_unitario_sap_ibp,
    PRD_ATTRS_COMUNES,
    CUST_ATTRS_AREAGC,
)
from src.data.master_data_sap_ibp import product_sap_ibp, customer_sap_ibp
from src.data.aws_categoria import categoria_producto_datalake
from src.data import demo_data
from src.utils.listas_periodos import periodos_historicos_mes, periodos_futuros_mes, periodid3_a_fecha

MESES_HISTORICOS = 24
MESES_FUTUROS = 12

PRD_ATRIBUTOS = [c for c in PRD_ATTRS_COMUNES if c != "UOMTOID"]

TTL_MASTER = 6 * 60 * 60   # master data cambia poco: 6hs
TTL_SERIES = 30 * 60       # series de forecast/histórico: 30min
TTL_ATHENA = 15 * 60       # entregado/pendiente "en vivo" del mes en curso: 15min

# Columna OData -> etiqueta "Tipo" del waterfall de forecast (tabla ZFCST /
# IBP-Forecast del Power BI).
WATERFALL_LABELS = {
    "ZESTADISTICOAJUSTADO": "Estadístico Ajustado",
    "STATISTICALFORECASTQTY": "01 - Forecast Estadístico",
    "ZFORECASTDEMANDA": "03 - Forecast Demanda",
    "SALESMGRFORECASTQTY": "04 - Forecast Comercial",
    "SALESFORECASTQTY": "05 - Forecast Planeamiento Comercial",
    "DEMANDPLANNINGQTY": "07 - Forecast Consensuado",
    "ZFCSTESTIMADO": "12 - Estimado Consensuado",
}

# Medidas "bonus" que viajan en la MISMA consulta que el waterfall (ver
# ``forecast_waterfall_sap_ibp`` -- una sola consulta de 11 medidas en vez de
# 3 separadas). No son parte del waterfall de Tipo, pero se piden juntas
# porque es upside gratis (mismo request).
_MEDIDAS_BONUS = ["ACTUALSQTY", "ADJUSTEDACTUALSQTY", "ZFCSTCOMERCIALESTIMADO", "ZAJUSTECOMERCIALESTIMADO"]


@st.cache_data(ttl=TTL_MASTER, persist="disk", show_spinner="Cargando maestro de productos...")
def get_product_master() -> pd.DataFrame:
    return product_sap_ibp()


@st.cache_data(ttl=TTL_MASTER, persist="disk", show_spinner="Cargando maestro de clientes...")
def get_customer_master() -> pd.DataFrame:
    return customer_sap_ibp()


@st.cache_data(ttl=TTL_MASTER, persist="disk", show_spinner="Cargando categoría de producto (Data Lake)...")
def get_categoria_producto() -> pd.DataFrame:
    """grupo_material_3 por SKU (tabla 'AWS - Categoria' del Power BI, join liviano en Athena)."""
    return categoria_producto_datalake()


def mapa_area_comercial(df_master: pd.DataFrame) -> pd.DataFrame:
    """
    Una fila por ZAREAGC (nunca más), con ZAREACOMERCIAL/CUSTGROUP colapsados
    a su valor más frecuente -- lista para mergear ``on="ZAREAGC"`` contra
    cualquier serie de key figures sin duplicar filas.

    **Bug real encontrado y corregido (2026-09-14)**: ``customer_sap_ibp()``
    trae el maestro a grano CUSTID, y ni ZAREACOMERCIAL ni CUSTGROUP son
    funcionalmente dependientes de ZAREAGC en los datos reales -- confirmado
    contra el tenant: 13 de 34 ZAREAGC agrupan clientes de MÁS DE UNA
    ZAREACOMERCIAL, 18 de 34 de MÁS DE UN CUSTGROUP, hasta 31 combinaciones
    distintas bajo un mismo ZAREAGC (ej. "Litoral"). El patrón de merge
    anterior (``df_master[cols].drop_duplicates()`` seguido de
    ``merge(..., on="ZAREAGC")``) generaba una fila del `mapa_area` por CADA
    combinación encontrada, y el merge fanoutaba cada fila de la serie
    original una vez por cada una -- inflando cualquier suma (Entregado,
    Forecast, Accuracy) que no filtrara explícitamente por Cliente, hasta
    ~31x en el peor caso. Esto ya afectaba el merge de ZAREACOMERCIAL previo
    a esta sesión (páginas 1/5/6/7), pasó inadvertido porque los datos demo
    tienen una relación 1:1 limpia; se hizo evidente al agregar CUSTGROUP
    (grano aún más fino, blowup mucho mayor) y una página tardó minutos en
    vez de segundos en renderizar.

    **Fix**: colapsar a la moda (valor más frecuente por cantidad de CUSTID)
    de cada atributo por ZAREAGC -- preserva la integridad de las sumas (1
    fila de por vida por ZAREAGC, nunca fan-out) a costa de una aproximación
    deliberada en el filtro: un ZAREAGC que reparte clientes entre varias
    Area Comercial/Customer Group muestra solo la predominante, así que
    filtrar por una de las otras puede no traer ese ZAREAGC aunque en la
    realidad sí tenga algo de esa combinación. Se prefiere esto a la
    alternativa (fan-out) porque romper sumas es peor que un filtro
    aproximado, y es consistente con la simplificación de grano ya aceptada
    en el resto de la app (ver módulo ``cache.py``, grano de cliente).
    """
    cols = [c for c in ["ZAREACOMERCIAL", "CUSTGROUP"] if c in df_master.columns]
    moda = lambda s: s.mode().iat[0] if not s.mode().empty else pd.NA
    return df_master.groupby("ZAREAGC", as_index=False)[cols].agg(moda)


@st.cache_data(ttl=TTL_SERIES, persist="disk", show_spinner="Consultando SAP IBP (waterfall + histórico + comercial)...")
def get_forecast_waterfall_mensual() -> pd.DataFrame:
    """
    Las 11 medidas de ``forecast_waterfall_sap_ibp`` (waterfall de 7 +
    histórico + comercial) para la ventana histórica+futura, a nivel PRDID x
    ZAREAGC x mes -- UNA SOLA consulta a SAP, fuente única para
    ``get_forecast_consensuado_mensual``, ``get_forecast_estadistico_mensual``,
    ``get_historico_ventas_mensual``, ``get_historico_y_forecast_ancho`` + ``melt_historico_y_forecast`` y
    ``get_estimado_comercial``. Ninguna de esas funciones vuelve a pegarle a
    SAP -- todas recortan de este DataFrame ya cacheado.
    """
    meses = periodos_historicos_mes(MESES_HISTORICOS) + periodos_futuros_mes(MESES_FUTUROS)
    df = forecast_waterfall_sap_ibp(meses, PRD_ATRIBUTOS, CUST_ATTRS_AREAGC)
    if df.empty:
        return df
    for col in [*WATERFALL_LABELS, *_MEDIDAS_BONUS]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def get_forecast_consensuado_mensual() -> pd.DataFrame:
    """Forecast Consensuado (DEMANDPLANNINGQTY), extraído del waterfall cacheado."""
    df = get_forecast_waterfall_mensual()
    if df.empty:
        return df
    otras = [c for c in df.columns if c not in WATERFALL_LABELS and c not in _MEDIDAS_BONUS]
    return df[[*otras, "DEMANDPLANNINGQTY"]].rename(columns={"DEMANDPLANNINGQTY": "ForecastConsensuado"})


def get_forecast_estadistico_mensual() -> pd.DataFrame:
    """Forecast Estadístico (STATISTICALFORECASTQTY), extraído del waterfall cacheado."""
    df = get_forecast_waterfall_mensual()
    if df.empty:
        return df
    otras = [c for c in df.columns if c not in WATERFALL_LABELS and c not in _MEDIDAS_BONUS]
    return df[[*otras, "STATISTICALFORECASTQTY"]].rename(columns={"STATISTICALFORECASTQTY": "ForecastEstadistico"})


def get_historico_ventas_mensual() -> pd.DataFrame:
    """Histórico de Ventas (ACTUALSQTY), extraído del fetch combinado cacheado
    (sin pegarle de nuevo a SAP) -- a nivel PRDID x ZAREAGC x mes."""
    df = get_forecast_waterfall_mensual()
    if df.empty:
        return df
    otras = [c for c in df.columns if c not in WATERFALL_LABELS and c not in _MEDIDAS_BONUS]
    df = df[[*otras, "ACTUALSQTY"]].rename(columns={"ACTUALSQTY": "Actual"})
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


@st.cache_data(ttl=TTL_SERIES, persist="disk", show_spinner=False)
def get_historico_y_forecast_ancho() -> pd.DataFrame:
    """
    Formato ANCHO (1 fila por PRDID x ZAREAGC x mes -- Histórico Ajustado +
    las 7 columnas del waterfall SIN "explotar" a Tipo/Valor). Las páginas
    filtran ESTO por sidebar y recién después llaman a
    ``melt_historico_y_forecast()`` para pasar a formato largo.

    Por qué: "explotar" a Tipo/Valor ANTES de filtrar multiplica por 8 la
    cantidad de filas (una por cada Tipo) sobre el universo COMPLETO sin
    filtrar -- con datos reales eso da ~8.5 millones de filas y ~30s de
    cómputo, que además se vuelve a copiar en cada rerun de Streamlit (cada
    cambio de filtro). Filtrando primero sobre el ancho (mismo tamaño que el
    waterfall, liviano) y recién ahí explotando, el costo de "explotar" cae
    sobre el subconjunto YA filtrado -- mucho más chico en la mayoría de los
    casos (además, "Histórico de ventas" y "Plan Anual" ni siquiera
    necesitan explotar: les alcanza con una sola columna del ancho).
    """
    df = get_forecast_waterfall_mensual()
    if df.empty:
        return df
    columnas = [c for c in df.columns if c not in ("ACTUALSQTY", "ZFCSTCOMERCIALESTIMADO", "ZAJUSTECOMERCIALESTIMADO")]
    df = df[columnas].copy()
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


@st.cache_data(ttl=TTL_SERIES, show_spinner=False)
def melt_historico_y_forecast(df_ancho: pd.DataFrame, incluir_historico: bool = True, tipos_forecast: tuple = None) -> pd.DataFrame:
    """
    Pasa el formato ancho (``get_historico_y_forecast_ancho``, YA FILTRADO
    por la página) a la serie larga Tipo/Valor equivalente a "FCST HIST" del
    Power BI: Histórico Ajustado (ADJUSTEDACTUALSQTY) SOLO para meses
    pasados (excluye el mes en curso), y las versiones del waterfall de
    forecast SOLO para el mes en curso + futuro (excluye meses ya cerrados) --
    a pedido del usuario, sin solapar. Antes el forecast se mostraba también
    para meses pasados (para comparar contra lo ya observado); si hace falta
    ese comportamiento de nuevo, es cuestión de sacar el filtro de
    ``df_ancho_forecast`` de acá abajo.

    ``tipos_forecast``: subconjunto de columnas OData del waterfall a
    incluir (ver ``WATERFALL_LABELS.keys()``); ``None`` = las 7. Pasarlo
    cuando la página solo necesita 1 o 2 tipos (ej. "Forecast - Estimado"
    solo usa Historico Ajustado + "12 - Estimado Consensuado") -- cada tipo
    de más multiplica el costo de "explotar" sin necesidad. Tupla (no lista)
    porque ``st.cache_data`` necesita argumentos hasheables.

    Llamar SIEMPRE después de filtrar por sidebar, nunca antes.

    Returns
    -------
    pd.DataFrame: PERIODID3, Date, Tipo, Origen ('Histórico'|'Forecast'),
    Valor, + jerarquía de producto y ZAREAGC.
    """
    if df_ancho.empty and len(df_ancho.columns) == 0:
        # Ni siquiera tiene columnas (no vino de get_historico_y_forecast_ancho) --
        # no hay nada de lo que partir para armar el esquema largo.
        return df_ancho

    meses_hist = periodos_historicos_mes(MESES_HISTORICOS)
    otras = [c for c in df_ancho.columns if c not in WATERFALL_LABELS and c != "ADJUSTEDACTUALSQTY"]

    if incluir_historico:
        df_hist = df_ancho[df_ancho["PERIODID3"].isin(meses_hist)][[*otras, "ADJUSTEDACTUALSQTY"]].copy()
        df_hist = df_hist.rename(columns={"ADJUSTEDACTUALSQTY": "Valor"})
        df_hist["Tipo"] = "Historico Ajustado"
        df_hist["Origen"] = "Histórico"
    else:
        df_hist = pd.DataFrame()

    # Mes en curso + futuro únicamente (complemento de meses_hist).
    df_ancho_forecast = df_ancho[~df_ancho["PERIODID3"].isin(meses_hist)]

    columnas_pedidas = set(tipos_forecast) if tipos_forecast else set(WATERFALL_LABELS.keys())
    dfs_fcst = []
    for col, label in WATERFALL_LABELS.items():
        if col not in df_ancho.columns or col not in columnas_pedidas:
            continue
        parte = df_ancho_forecast[[*otras, col]].rename(columns={col: "Valor"}).copy()
        parte["Tipo"] = label
        parte["Origen"] = "Forecast"
        dfs_fcst.append(parte)
    df_fcst = pd.concat(dfs_fcst, ignore_index=True) if dfs_fcst else pd.DataFrame()

    return pd.concat([df_hist, df_fcst], ignore_index=True)


def get_estimado_comercial() -> pd.DataFrame:
    """Estimado Comercial + Ajuste E+P (ZFCSTCOMERCIALESTIMADO, ZAJUSTECOMERCIALESTIMADO)
    para el mes en curso y los próximos MESES_FUTUROS meses -- extraído del
    fetch combinado cacheado (sin pegarle de nuevo a SAP)."""
    df = get_forecast_waterfall_mensual()
    if df.empty:
        return df
    meses_futuros = periodos_futuros_mes(MESES_FUTUROS)
    df = df[df["PERIODID3"].isin(meses_futuros)]
    otras = [c for c in df.columns if c not in WATERFALL_LABELS and c not in _MEDIDAS_BONUS]
    df = df[[*otras, "ZFCSTCOMERCIALESTIMADO", "ZAJUSTECOMERCIALESTIMADO"]].copy()
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


@st.cache_data(ttl=TTL_SERIES, persist="disk", show_spinner="Consultando Plan Anual en SAP IBP...")
def get_plan_anual() -> pd.DataFrame:
    """Plan Anual (ZPLANANUAL), filtrado por AÑO (PERIODID1) -- igual que la
    tabla ZBP del Power BI, no por PERIODID3."""
    # Rango mínimo de años que cubre con margen periodos_historicos_mes(24) +
    # periodos_futuros_mes(12) en cualquier mes del año (antes tenía +/-1 año
    # de padding de más, pidiendo 6 años en vez de 4 -- un 33% de requests
    # innecesarios a SAP para esta consulta).
    hoy = pd.Timestamp.today()
    anio_desde = hoy.year - (-(-MESES_HISTORICOS // 12))  # ceil(MESES_HISTORICOS/12)
    anio_hasta = hoy.year + (-(-MESES_FUTUROS // 12))     # ceil(MESES_FUTUROS/12)
    anios = list(range(anio_desde, anio_hasta + 1))

    df = plananual_sap_ibp(anios, PRD_ATRIBUTOS, CUST_ATTRS_AREAGC)
    if df.empty:
        return df
    df["ZPLANANUAL"] = pd.to_numeric(df["ZPLANANUAL"], errors="coerce").fillna(0.0)
    df = df.rename(columns={"ZPLANANUAL": "PLANANUAL"})
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


@st.cache_data(ttl=TTL_ATHENA, persist="disk", show_spinner="Consultando Entregado/Pendiente en SAP IBP...")
def get_entregado_pendiente() -> pd.DataFrame:
    """Entregado + Pendiente del mes en curso (ZENTREGADO, ZPENDIENTESMTH,
    ZENTREGAPENDIENTEMTH), directo de SAP IBP -- tabla ZE&P del Power BI."""
    mes_actual = periodos_futuros_mes(1)
    df = entregado_pendiente_sap_ibp(mes_actual, PRD_ATRIBUTOS, CUST_ATTRS_AREAGC)
    if df.empty:
        return df
    for col in ["ZENTREGADO", "ZPENDIENTESMTH", "ZENTREGAPENDIENTEMTH"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=TTL_SERIES, persist="disk", show_spinner="Consultando Margen Unitario en SAP IBP...")
def get_margen_unitario() -> pd.DataFrame:
    """
    Margen Unitario (ZMARGENUNITARIOUSD) del mes en curso; si viene vacío,
    cae al mes anterior -- mismo criterio que la tabla IBP - Margen del
    Power BI. Devuelve PRDID, Margen Unitario (USD) (agregado por MAX ante
    posibles duplicados, igual que el Power BI).
    """
    mes_actual = periodos_futuros_mes(1)[0]
    df = margen_unitario_sap_ibp(mes_actual)
    if df.empty:
        mes_previo = periodos_historicos_mes(1)[0]
        df = margen_unitario_sap_ibp(mes_previo)
    if df.empty:
        return df
    df["ZMARGENUNITARIOUSD"] = pd.to_numeric(df["ZMARGENUNITARIOUSD"], errors="coerce")
    return (
        df.groupby("PRDID", as_index=False)["ZMARGENUNITARIOUSD"].max()
        .rename(columns={"ZMARGENUNITARIOUSD": "MargenUnitarioUSD"})
    )


@st.cache_data(ttl=TTL_SERIES, persist="disk", show_spinner="Cruzando Forecast Consensuado vs Histórico de Ventas...")
def get_forecast_vs_actual() -> pd.DataFrame:
    """
    Forecast Consensuado vs Histórico de Ventas, a nivel PERIODID3-PRDID-ZAREAGC
    (+ jerarquías de producto). Insumo de "Reporte Accuracy" (por Gran
    División) y "Ranking Clientes" (por Area/GC) -- ver
    ``src/accuracy.py::acc_bias_consensuado``.
    """
    df_fcst = get_forecast_consensuado_mensual()
    df_act = get_historico_ventas_mensual()
    if df_fcst.empty or df_act.empty:
        return pd.DataFrame()

    claves = [c for c in ["PERIODID3", "PRDID", "ZAREAGC"] if c in df_fcst.columns and c in df_act.columns]
    df = df_fcst.merge(df_act[[*claves, "Actual"]], on=claves, how="outer")
    df["ForecastConsensuado"] = pd.to_numeric(df["ForecastConsensuado"], errors="coerce").fillna(0.0)
    df["Actual"] = pd.to_numeric(df["Actual"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=TTL_SERIES, persist="disk", show_spinner="Cruzando Forecast Consensuado/Estadístico vs Histórico...")
def get_forecast_vs_actual_producto() -> pd.DataFrame:
    """
    Igual que ``get_forecast_vs_actual`` pero con Forecast Estadístico
    agregado -- insumo de "Acc. FCST Estadístico" y de toda la Segmentación
    SKU. Mantiene el grano PRDID x ZAREAGC x mes (NO colapsa Area/GC acá)
    para que "Reporte Accuracy" y "Segmentación SKU" puedan filtrar por Area
    Comercial/Area GC en el sidebar antes de agregar -- ver
    ``src/filters.py::render_sidebar_accuracy``. Esto no cambia ningún
    resultado para quien no filtre por cliente: ``acc_bias_consensuado``,
    ``acc_estadistico`` y ``tabla_segmentacion_sku`` agregan por ``PRDID``
    (sumando) puertas adentro, así que reciben esto o la versión ya
    colapsada por PRDID x mes y dan el mismo número -- colapsar ahí en vez de
    acá es lo que habilita filtrar por cliente antes de esa suma.
    """
    df = get_forecast_vs_actual()
    if df.empty:
        return pd.DataFrame()

    df_est = get_forecast_estadistico_mensual()
    if not df_est.empty:
        claves = [c for c in ["PERIODID3", "PRDID", "ZAREAGC"] if c in df.columns and c in df_est.columns]
        df = df.merge(df_est[[*claves, "ForecastEstadistico"]], on=claves, how="left")
        df["ForecastEstadistico"] = df["ForecastEstadistico"].fillna(0.0)
    else:
        df["ForecastEstadistico"] = 0.0

    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


@st.cache_data(ttl=TTL_SERIES, show_spinner=False)
def calcular_tabla_segmentacion(df_producto: pd.DataFrame, df_forecast_prox4m: pd.DataFrame = None) -> pd.DataFrame:
    """
    Wrapper cacheado de ``accuracy.tabla_segmentacion_sku`` -- el fetch a SAP
    ya está resuelto en este punto (viene de ``get_forecast_vs_actual_producto``,
    cacheado), pero el cálculo en sí (varios groupby + merge sobre el
    DataFrame filtrado a la ventana U4M) se repetía en cada rerun de Streamlit
    (cambiar cualquier filtro de la página, no solo el "Mes") aunque el
    resultado fuera exactamente el mismo. Cachearlo por el contenido de
    ``df_producto`` (+ ``df_forecast_prox4m``, segundo criterio de
    elegibilidad "forecast próximos 4 meses") evita ese recálculo -- notorio
    en "Reporte Accuracy" y "Segmentación SKU", las páginas con más lag al
    abrir.
    """
    from src.accuracy import tabla_segmentacion_sku

    return tabla_segmentacion_sku(df_producto, df_forecast_prox4m)


def get_or_demo(get_fn, demo_fn):
    """
    Intenta la fuente real (SAP IBP/Athena, vía ``safe_call``); si falla o
    viene vacía, cae a datos de ejemplo sintéticos (``src/data/demo_data.py``)
    para poder previsualizar el diseño del tablero sin conexión/autorización
    real. Devuelve ``(df, es_demo, error)`` -- las páginas muestran un cartel
    cuando ``es_demo`` es True.
    """
    df, error = safe_call(get_fn)
    if error or df.empty:
        return demo_fn(), True, error
    return df, False, None


def safe_call(fn, *args, **kwargs):
    """
    Ejecuta ``fn`` (una de las funciones cacheadas de este módulo) y devuelve
    ``(df, error)``. Uso en cada página:

        df, error = safe_call(get_historico_y_forecast_ancho)
        if error:
            st.error(f"No se pudo conectar: {error}")
            st.stop()

    Evita repetir el mismo try/except de conexión (credenciales faltantes,
    timeouts, Athena caído) en cada una de las páginas.
    """
    try:
        return fn(*args, **kwargs), None
    except Exception as e:
        return pd.DataFrame(), str(e)
