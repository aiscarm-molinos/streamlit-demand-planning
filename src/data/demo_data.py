# src/data/demo_data.py
"""
Datos de ejemplo (sintéticos) para previsualizar el diseño del tablero
mientras no hay conexión real a SAP IBP/Athena (ver ``src/cache.py::get_or_demo``).

Todas las funciones acá devuelven DataFrames con EXACTAMENTE el mismo
esquema (columnas) que su equivalente real en ``src/cache.py``, para que las
páginas no necesiten ninguna lógica especial según la fuente sea real o de
ejemplo. Semilla fija (``SEED``) para que el demo se vea igual entre
corridas -- no es para simular un caso de negocio real, solo para poder
mirar gráficos/tablas con forma realista.

Grano de cliente: solo ZAREAGC (nunca CUSTID individual) -- igual que las
consultas reales (ver nota en ``extract_odata_sap_ibp.py``).
"""

import numpy as np
import pandas as pd

from src.utils.listas_periodos import periodos_historicos_mes, periodos_futuros_mes, periodid3_a_fecha

SEED = 42
N_PRODUCTOS = 30
N_AREAGC = 10

# Divisiones reales del negocio (ver informe "Reporte – Ranking Forecast
# Accuracy.docx" y capturas del Power BI real: "Segmentación por Gran
# División: Alimentos, Bodegas y Snacks").
GRAN_DIVISIONES = ["Alimentos", "Bodegas", "Snacks"]
GRAN_NEGOCIOS = {
    "Alimentos": ["Harinas", "Pastas"],
    "Bodegas": ["Vinos", "Espumantes"],
    "Snacks": ["Galletitas", "Golosinas"],
}
NEGOCIOS = ["Consumo Masivo", "Foodservice", "Industrial"]  # ZBRAND ("Negocio")
FAMILIAS = ["Familia A", "Familia B", "Familia C", "Familia D", "Familia E"]
# Areas Comerciales reales (según captura de "Ranking por Área Comercial")
AREAS_COMERCIALES = ["Supermercados", "Mayoristas", "Interior", "Distribuidores GBA", "Minoristas GBA", "Otros"]
AREAS_GC = [f"Area GC {i + 1}" for i in range(N_AREAGC)]
AREAGC_A_AREACOMERCIAL = {areagc: AREAS_COMERCIALES[i % len(AREAS_COMERCIALES)] for i, areagc in enumerate(AREAS_GC)}

# Un "arquetipo" de accuracy por SKU, cíclico, para que aparezcan los 6
# segmentos (0, 1, 2.1, 2.2, 3.1, 3.2) en la tabla de segmentación.
ARQUETIPOS = [
    {"segmento": "0", "err_est": 0.03, "err_cons": 0.10},
    {"segmento": "1", "err_est": 0.45, "err_cons": 0.08},
    {"segmento": "2.1", "err_est": 0.55, "err_cons": 0.30},
    {"segmento": "2.2", "err_est": 0.25, "err_cons": 0.35},
    {"segmento": "3.1", "err_est": 0.75, "err_cons": 0.55},
    {"segmento": "3.2", "err_est": 0.45, "err_cons": 0.70},
]


def _dimensiones():
    rng = np.random.default_rng(SEED)

    productos = []
    for i in range(N_PRODUCTOS):
        division = GRAN_DIVISIONES[i % len(GRAN_DIVISIONES)]
        negocio_grande = rng.choice(GRAN_NEGOCIOS[division])
        productos.append({
            "PRDID": f"SKU-{i + 1:04d}",
            "PRDDESCR": f"Producto Demo {i + 1}",
            "ZBIGDIVISION": division,
            "ZBIGBUSINESS": negocio_grande,
            "ZBRAND": NEGOCIOS[i % len(NEGOCIOS)],
            "ZDEMFAMILY": FAMILIAS[i % len(FAMILIAS)],
            "PRDFAMILY": FAMILIAS[i % len(FAMILIAS)],
            "_volumen_base": rng.uniform(200, 2000),
            "_margen_unitario": rng.uniform(0.5, 8.0),
            "_arquetipo": ARQUETIPOS[i % len(ARQUETIPOS)],
        })
    df_productos = pd.DataFrame(productos)
    return df_productos


def _meses_hist_fut(n_hist=24, n_fut=12):
    return periodos_historicos_mes(n_hist) + periodos_futuros_mes(n_fut)


def _con_areagc(fila: dict, rng) -> dict:
    return {**fila, "ZAREAGC": rng.choice(AREAS_GC)}


def _fila_producto(prod) -> dict:
    return {
        "PRDID": prod["PRDID"], "PRDFAMILY": prod["PRDFAMILY"], "ZDEMFAMILY": prod["ZDEMFAMILY"],
        "ZBRAND": prod["ZBRAND"], "ZBIGBUSINESS": prod["ZBIGBUSINESS"], "ZBIGDIVISION": prod["ZBIGDIVISION"],
    }


def producto_master_demo() -> pd.DataFrame:
    df_productos = _dimensiones()
    cols = ["PRDID", "PRDDESCR", "ZBIGDIVISION", "ZBIGBUSINESS", "ZBRAND", "ZDEMFAMILY", "PRDFAMILY"]
    return df_productos[cols].copy()


def entregado_actual_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_historico_ventas_mensual`` (ACTUALSQTY /
    "Entregado"): PERIODID3, Date, Actual + jerarquía de producto + ZAREAGC."""
    rng = np.random.default_rng(SEED + 6)
    df_productos = _dimensiones()
    meses = periodos_historicos_mes(24) + periodos_futuros_mes(1)

    filas = []
    for _, prod in df_productos.iterrows():
        areagc = rng.choice(AREAS_GC)
        base = prod["_volumen_base"]
        for mes in meses:
            filas.append({
                **_fila_producto(prod), "ZAREAGC": areagc, "PERIODID3": mes,
                "Actual": max(base * (1 + rng.normal(0, 0.09)), 0),
            })

    df = pd.DataFrame(filas)
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


# Columnas crudas del waterfall (mismos nombres que ``cache.py::WATERFALL_LABELS``,
# duplicado acá para no crear un import circular demo_data<->cache).
_WATERFALL_COLS = [
    "ZESTADISTICOAJUSTADO", "STATISTICALFORECASTQTY", "ZFORECASTDEMANDA",
    "SALESMGRFORECASTQTY", "SALESFORECASTQTY", "DEMANDPLANNINGQTY", "ZFCSTESTIMADO",
]


def historico_y_forecast_ancho_demo() -> pd.DataFrame:
    """
    Mismo esquema que ``cache.get_historico_y_forecast_ancho``: PERIODID3,
    Date, ADJUSTEDACTUALSQTY + las 7 columnas del waterfall (SIN explotar a
    Tipo/Valor -- eso lo hace ``cache.melt_historico_y_forecast`` después de
    filtrar) + jerarquía de producto + ZAREAGC.
    """
    rng = np.random.default_rng(SEED)
    df_productos = _dimensiones()
    meses = periodos_historicos_mes(24) + periodos_futuros_mes(12)

    filas = []
    for _, prod in df_productos.iterrows():
        areagc = rng.choice(AREAS_GC)
        base = prod["_volumen_base"]
        fila_base = {**_fila_producto(prod), "ZAREAGC": areagc}

        for mes in meses:
            fila = {**fila_base, "PERIODID3": mes, "ADJUSTEDACTUALSQTY": max(base * (1 + rng.normal(0, 0.08)), 0)}
            for col in _WATERFALL_COLS:
                fila[col] = max(base * (1 + rng.normal(0, 0.12)), 0)
            filas.append(fila)

    df = pd.DataFrame(filas)
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


def estimado_comercial_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_estimado_comercial``."""
    rng = np.random.default_rng(SEED + 1)
    df_productos = _dimensiones()
    meses = periodos_futuros_mes(12)

    filas = []
    for _, prod in df_productos.iterrows():
        areagc = rng.choice(AREAS_GC)
        base = prod["_volumen_base"]
        for mes in meses:
            estimado = max(base * (1 + rng.normal(0, 0.1)), 0)
            ajuste = max(estimado * (1 + rng.normal(0, 0.05)), 0)
            filas.append({
                **_fila_producto(prod), "ZAREAGC": areagc, "PERIODID3": mes,
                "ZFCSTCOMERCIALESTIMADO": estimado, "ZAJUSTECOMERCIALESTIMADO": ajuste,
            })

    df = pd.DataFrame(filas)
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


def plan_anual_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_plan_anual``."""
    rng = np.random.default_rng(SEED + 2)
    df_productos = _dimensiones()
    meses = _meses_hist_fut()

    filas = []
    for _, prod in df_productos.iterrows():
        areagc = rng.choice(AREAS_GC)
        base = prod["_volumen_base"]
        for mes in meses:
            filas.append({
                **_fila_producto(prod), "ZAREAGC": areagc, "PERIODID3": mes,
                "PLANANUAL": max(base * (1 + rng.normal(0, 0.06)), 0),
            })

    df = pd.DataFrame(filas)
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df


def entregado_pendiente_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_entregado_pendiente`` (SAP IBP directo, PRDID-ZAREAGC, mes en curso)."""
    rng = np.random.default_rng(SEED + 3)
    df_productos = _dimensiones()
    mes_actual = periodos_futuros_mes(1)[0]

    filas = []
    for _, prod in df_productos.iterrows():
        areagc = rng.choice(AREAS_GC)
        base = prod["_volumen_base"] / 4
        entregado = max(base * (1 + rng.normal(0, 0.15)), 0)
        pendiente = max(base * rng.uniform(0.05, 0.2), 0)
        filas.append({
            "PRDID": prod["PRDID"], "ZAREAGC": areagc, "PERIODID3": mes_actual,
            "ZENTREGADO": entregado, "ZPENDIENTESMTH": pendiente, "ZENTREGAPENDIENTEMTH": entregado + pendiente,
        })
    return pd.DataFrame(filas)


def margen_unitario_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_margen_unitario``: PRDID, MargenUnitarioUSD."""
    df_productos = _dimensiones()
    return df_productos[["PRDID", "_margen_unitario"]].rename(columns={"_margen_unitario": "MargenUnitarioUSD"})


def customer_master_demo() -> pd.DataFrame:
    """Mismo esquema (recortado) que ``cache.get_customer_master``: ZAREAGC, ZAREACOMERCIAL."""
    return pd.DataFrame({
        "ZAREAGC": AREAS_GC,
        "ZAREACOMERCIAL": [AREAGC_A_AREACOMERCIAL[a] for a in AREAS_GC],
    })


def categoria_producto_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_categoria_producto``: sku, familia, grupo_material_3."""
    df_productos = _dimensiones()
    return pd.DataFrame({
        "sku": df_productos["PRDID"],
        "familia": df_productos["PRDFAMILY"],
        "grupo_material_3": df_productos["ZDEMFAMILY"],
    })


def forecast_vs_actual_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_forecast_vs_actual`` (grano PRDID x ZAREAGC x mes)."""
    rng = np.random.default_rng(SEED + 4)
    df_productos = _dimensiones()
    meses = _meses_hist_fut()

    filas = []
    for _, prod in df_productos.iterrows():
        areagc = rng.choice(AREAS_GC)
        base = prod["_volumen_base"]
        err_cons = prod["_arquetipo"]["err_cons"]
        for mes in meses:
            actual = max(base * (1 + rng.normal(0, 0.05)), 1)
            forecast_cons = max(actual * (1 + rng.normal(err_cons, 0.05) * rng.choice([1, -1])), 0)
            filas.append({
                **_fila_producto(prod), "ZAREAGC": areagc, "PERIODID3": mes,
                "ForecastConsensuado": forecast_cons, "Actual": actual,
            })

    return pd.DataFrame(filas)


def forecast_vs_actual_producto_demo() -> pd.DataFrame:
    """Mismo esquema que ``cache.get_forecast_vs_actual_producto`` (grano
    PRDID x ZAREAGC x mes, con Forecast Estadístico) -- insumo de Reporte
    Accuracy y Segmentación SKU."""
    rng = np.random.default_rng(SEED + 5)
    df_productos = _dimensiones()
    meses = _meses_hist_fut()

    filas = []
    for _, prod in df_productos.iterrows():
        areagc = rng.choice(AREAS_GC)
        base = prod["_volumen_base"]
        err_cons = prod["_arquetipo"]["err_cons"]
        err_est = prod["_arquetipo"]["err_est"]
        for mes in meses:
            actual = max(base * (1 + rng.normal(0, 0.05)), 1)
            forecast_cons = max(actual * (1 + rng.normal(err_cons, 0.05) * rng.choice([1, -1])), 0)
            forecast_est = max(actual * (1 + rng.normal(err_est, 0.05) * rng.choice([1, -1])), 0)
            filas.append({
                **_fila_producto(prod), "ZAREAGC": areagc, "PERIODID3": mes,
                "ForecastConsensuado": forecast_cons, "ForecastEstadistico": forecast_est, "Actual": actual,
            })

    df = pd.DataFrame(filas)
    df["Date"] = periodid3_a_fecha(df["PERIODID3"])
    return df
