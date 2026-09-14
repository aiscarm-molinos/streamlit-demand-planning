# src/accuracy.py
"""
Cálculo de accuracy, bias y segmentación de SKU -- réplica fiel de las
medidas DAX del .pbix "Tablero Forecast Accuracy IBP" (texto provisto por el
usuario, no un supuesto). Fuente: tabla "Medidas" del modelo.

Conceptos clave (ver ORDEN_SEGMENTO / SEGMENTOS_INFO para el glosario real):

- "Forecast Consensuado" (DEMANDPLANNINGQTY en SAP IBP OData) vs "Histórico
  de Ventas" (ACTUALSQTY): Accuracy/Bias Consensuado.
- "Forecast Estadístico" (STATISTICALFORECASTQTY, output del modelo ML de
  ibp-forecast-mensual / ibp-forecast-entregas-mensual) vs Histórico:
  Accuracy Estadístico.
- Segmento SKU: clasifica cada PRDID según cuánto mejora (o empeora) el
  proceso de planificación (Consensuado) al forecast estadístico crudo.

Nuance importante: la accuracy ponderada NO es un promedio de ratios por
fila, y TAMPOCO es el error de los totales ya agregados -- siempre se
decompone a grano PRDID x mes primero, se toma el error absoluto ahí, y
RECIÉN AHÍ se suma para dividir por el total de Actual del nivel que se
esté mirando (Accuracy Consensuado y Accuracy Estadístico son iguales en
esto). Es decir, sea cual sea el ``group_cols`` pedido (ZBIGDIVISION total,
ZPRDFAMILY x Area/GC, etc.):

    Accuracy = 1 - (Σ_sku,mes |Actual - Forecast|) / Σ Actual

y NUNCA

    Accuracy = 1 - |Σ Actual - Σ Forecast| / Σ Actual   (ESTO ESTÁ MAL:
    subestima el error cuando el sobre-forecast de un SKU compensa el
    sub-forecast de otro dentro del mismo grupo)

El Bias, en cambio, SÍ es un cociente de sumas totales -- no decompone por
SKU, la fórmula ya es lineal: Σ Forecast / Σ Actual - 1. Por eso
``_accuracy_ponderada`` recibe ``grano_extra`` (siempre incluye "PRDID") por
separado de ``group_cols``, mientras que el Bias se calcula aparte, directo
sobre ``group_cols``.
"""

import pandas as pd

from src.utils.listas_periodos import periodid3_a_fecha

# Cantidad de meses preseleccionados por default en el filtro "Meses a
# analizar" del sidebar de Accuracy (`src/filters.py::render_sidebar_accuracy`)
# -- históricamente los "últimos 4 meses cerrados" (U4M) del informe
# "Reporte – Ranking Forecast Accuracy.docx", pero el usuario puede agregar o
# sacar meses libremente: Accuracy/Bias ponderado se recalculan sobre
# EXACTAMENTE los meses elegidos, no sobre una ventana fija de 4.
MESES_ANALISIS_DEFAULT = 4

# Segundo criterio de "Alcance" del informe (el primero es el gate de
# actividad de `historico_ultimos_3m_cerrados`): "SKUs... con forecast al
# menos para los próximos 4 meses". Ver `forecast_proximos_4m` y
# `src/utils/listas_periodos.py::periodos_empezando_en`.
MESES_PROX_FCST = 4

# Orden de severidad de los segmentos (para el "Acc. Consensuado Proyectado (Escenario)")
ORDEN_SEGMENTO = {"0": 0, "1": 1, "2.1": 2, "2.2": 3, "3.1": 4, "3.2": 5}

# Texto real de la página "Glosario - Segmentación" del .pbix
SEGMENTOS_INFO = {
    "0": {
        "segmento": "0 | Estadístico > 80 %",
        "definicion": "Forecast estadístico con precisión superior al 80 %",
        "interpretacion": "El modelo estadístico predice correctamente la demanda sin intervención manual",
    },
    "1": {
        "segmento": "1 | Consensuado > 80 %",
        "definicion": "Forecast consensuado con precisión superior al 80 %",
        "interpretacion": "La intervención del proceso de planificación mejora significativamente el forecast",
    },
    "2.1": {
        "segmento": "2.1 | 60% < Consensuado < 80% (Mejora)",
        "definicion": "Forecast consensuado mejora la precisión respecto al estadístico dentro del rango 60%-80%",
        "interpretacion": "Existe mejora por intervención humana aunque el forecast aún puede optimizarse",
    },
    "2.2": {
        "segmento": "2.2 | 60% < Consensuado < 80% (Empeora)",
        "definicion": "Forecast consensuado empeora la precisión respecto al estadístico dentro del rango 60%-80%",
        "interpretacion": "La intervención manual reduce la calidad del forecast",
    },
    "3.1": {
        "segmento": "3.1 | Consensuado < 60% (Mejora)",
        "definicion": "Forecast consensuado mejora el resultado estadístico pero mantiene baja precisión (<60%)",
        "interpretacion": "Producto difícil de predecir aunque el ajuste del proceso mejora parcialmente",
    },
    "3.2": {
        "segmento": "3.2 | Consensuado < 60% (Empeora)",
        "definicion": "Forecast consensuado empeora el resultado estadístico con precisión inferior al 60%",
        "interpretacion": "Producto crítico que requiere revisión del modelo y/o proceso de planificación",
    },
}

# Texto real de la página "Glosario - Accuracy" del .pbix
GLOSARIO_ACCURACY = [
    {"Indicador": "Accuracy Estadístico", "Definición": "Precisión del forecast generado por el modelo estadístico", "Fórmula": "1 - ABS(Entrega - Forecast Estadístico) / Entrega", "Interpretación": "Permite evaluar el modelo estadístico"},
    {"Indicador": "Accuracy Consensuado", "Definición": "Precisión del forecast consensuado", "Fórmula": "1 - ABS(Entrega - Forecast Consensuado) / Entrega", "Interpretación": "Representa la precisión del forecast consensuado en el proceso de planificación"},
    {"Indicador": "Accuracy Ponderado", "Definición": "Precisión del forecast consensuado ponderado por los meses de análisis", "Fórmula": "Accuracy promedio ponderado por Entrega", "Interpretación": "Representa la precisión del forecast consensuado en el período de análisis"},
    {"Indicador": "Accuracy Proyectado", "Definición": "Estimación futura de precisión basada en historial", "Fórmula": "Cálculo ponderado secuencial", "Interpretación": "Permite dimensionar el impacto del accuracy consensuado en caso de seguir secuencialmente los planes de acción por segmento"},
    {"Indicador": "Bias", "Definición": "Mide tendencia a sobreestimar o subestimar la demanda", "Fórmula": "(Forecast / Entrega) - 1", "Interpretación": "Bias positivo indica sobreestimación y uno negativo indica subestimación"},
    {"Indicador": "% Volumen", "Definición": "Participación del SKU en el volumen total", "Fórmula": "Volumen SKU / Volumen Total", "Interpretación": "Identifica productos de mayor impacto"},
    {"Indicador": "Margen Unitario", "Definición": "Contribución marginal a nivel total MRP", "Fórmula": "SAP IBP", "Interpretación": "Mide el margen que deja el SKU por UMG"},
    {"Indicador": "% Margen Neto Total", "Definición": "Porcentaje del margen total", "Fórmula": "Margen Total SKU / Margen Total Filtrado", "Interpretación": "Permite visualizar el peso del SKU en el margen total"},
    {"Indicador": "Desvío Accuracy (pp.)", "Definición": "Diferencia entre accuracy estadístico y consensuado", "Fórmula": "Acc. FCST Consensuado - Acc. FCST Estadístico", "Interpretación": "Mide cuanto mejora/empeora el accuracy con el proceso de planificación"},
]


def _accuracy_ponderada(
    df: pd.DataFrame,
    group_cols: list,
    grano_extra: list,
    col_forecast: str,
    col_actual: str,
) -> pd.DataFrame:
    """
    Agrega a nivel ``group_cols + grano_extra`` y recién ahí calcula el error
    absoluto por celda -- antes de sumar y dividir por el total de Actual en
    ``group_cols``. Esto es lo que hace "ponderado por volumen": un promedio
    de ratios por fila daría un número distinto (y sesgado hacia SKUs/meses
    chicos) que este cociente de sumas.

    La Accuracy es un indicador de 0 a 1 -- da exactamente 1 únicamente
    cuando la sumatoria del error absoluto es 0 (Forecast = Actual en cada
    celda del grano), y `_abs_error` al ser una suma de valores `.abs()`
    nunca es negativa -- así que con un ``Actual`` (denominador) POSITIVO,
    ``1 - _abs_error/Actual`` matemáticamente nunca puede superar 1 (el
    ``clip(upper=1)`` de abajo es un cinturón de seguridad, no debería
    recortar nada en ese caso). El único modo de que la cuenta cruda dé
    >100% es que el ``Actual`` total del grupo sea NEGATIVO (devoluciones/
    notas de crédito que hacen neto negativo a nivel Area/GC, por ej.) --
    ahí ``_abs_error / Actual`` se vuelve negativo y ``1 - (negativo)`` > 1,
    y el clip lo tapaba mostrando un falso 100% en vez de señalar que el
    dato no tiene una lectura de accuracy válida. Por eso el denominador
    exige ``Actual > 0`` estricto (no solo `!= 0`) -- Actual cero O negativo
    da ``NaN``, nunca un accuracy inflado.
    """
    grano_cols = list(dict.fromkeys([*group_cols, *grano_extra]))
    grano = df.groupby(grano_cols, as_index=False).agg(
        Forecast=(col_forecast, "sum"), Actual=(col_actual, "sum")
    )
    grano["_abs_error"] = (grano["Forecast"] - grano["Actual"]).abs()

    g = grano.groupby(group_cols, as_index=False).agg(
        Forecast=("Forecast", "sum"), Actual=("Actual", "sum"), _abs_error=("_abs_error", "sum")
    )
    denominador = g["Actual"].where(g["Actual"] > 0)
    g["Accuracy"] = (1 - g["_abs_error"] / denominador).clip(lower=0, upper=1)
    return g.drop(columns=["_abs_error"])


def acc_bias_consensuado(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """
    "Acc. FCST Consensuado (Ponderado por Mes)" + "Bias FCST Consensuado
    (Ponderado por Mes)". ``df`` necesita PERIODID3, PRDID,
    ForecastConsensuado, Actual + las columnas de ``group_cols``.

    La Accuracy SIEMPRE decompone a PRDID x mes antes de tomar el error
    absoluto (igual que ``acc_estadistico`` -- ver nota del módulo), sin
    importar el nivel de agregación pedido en ``group_cols``: la accuracy de
    "ZBIGDIVISION total" o de "Area Comercial x Gran Negocio" se mide a nivel
    SKU y recién se suma, nunca sobre los totales ya agregados de ese grupo
    (bug corregido -- antes decomponía solo a nivel PERIODID3, sin PRDID, lo
    que subestimaba el error cuando un SKU sobre-forecasteaba y otro
    sub-forecasteaba dentro del mismo grupo).

    El Bias, a diferencia de la Accuracy, es un cociente de sumas totales (no
    decompone por SKU ni por mes, la fórmula ya es lineal:
    Σ Forecast / Σ Actual - 1).
    """
    acc = _accuracy_ponderada(df, group_cols, ["PRDID", "PERIODID3"], "ForecastConsensuado", "Actual")
    bias = df.groupby(group_cols, as_index=False).agg(
        Forecast=("ForecastConsensuado", "sum"), Actual=("Actual", "sum")
    )
    bias["Bias"] = bias["Forecast"] / bias["Actual"].replace(0, pd.NA) - 1
    return acc.merge(bias[[*group_cols, "Bias"]], on=group_cols)


def acc_estadistico(df_producto: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """
    "Acc. FCST Estadístico (Ponderado por Mes)": siempre decompone por
    PRDID x Mes antes de agregar a ``group_cols`` (igual que el CROSSJOIN de
    la medida DAX original), acotado a [0, 1]. ``df_producto`` necesita
    ForecastEstadistico, Actual, PRDID, PERIODID3.
    """
    return _accuracy_ponderada(df_producto, group_cols, ["PRDID", "PERIODID3"], "ForecastEstadistico", "Actual")


def historico_ultimos_3m_cerrados(df_producto: pd.DataFrame) -> pd.DataFrame:
    """
    Suma de Actual en los últimos 3 meses presentes en ``df_producto``, por
    PRDID -- gate de actividad de "Historico Últimos 3M Cerrados". Toma los
    3 meses más recientes DEL DATAFRAME RECIBIDO (no de "hoy"): si la página
    ya filtró a la ventana U4M antes de llamar, esto da automáticamente los
    últimos 3 de esos 4 meses, sin necesidad de pasar el mes de referencia
    de nuevo acá.
    """
    if df_producto.empty:
        return pd.DataFrame(columns=["PRDID", "HistoricoUlt3M"])
    meses_presentes = sorted(df_producto["PERIODID3"].unique(), key=lambda m: periodid3_a_fecha(m))
    ultimos_3 = meses_presentes[-3:]
    df = df_producto[df_producto["PERIODID3"].isin(ultimos_3)]
    return df.groupby("PRDID", as_index=False)["Actual"].sum().rename(columns={"Actual": "HistoricoUlt3M"})


def forecast_proximos_4m(df_producto_full: pd.DataFrame, meses_prox4m: list) -> pd.DataFrame:
    """
    Suma de ForecastConsensuado en los próximos ``MESES_PROX_FCST`` meses
    (segundo criterio de "Alcance" del informe), por PRDID. Gate de
    elegibilidad para poder asignar Segmento -- no participa del cálculo de
    accuracy en sí. ``df_producto_full`` necesita venir SIN filtrar a la
    ventana U4M -- esos meses son posteriores al mes de referencia elegido,
    fuera de esa ventana (por eso es un ``merge`` aparte y no un argumento de
    ``tabla_segmentacion_sku`` que ya viniera incluido en ``df_producto``).
    """
    if df_producto_full.empty:
        return pd.DataFrame(columns=["PRDID", "ForecastProx4M"])
    df = df_producto_full[df_producto_full["PERIODID3"].isin(meses_prox4m)]
    return df.groupby("PRDID", as_index=False)["ForecastConsensuado"].sum().rename(columns={"ForecastConsensuado": "ForecastProx4M"})


def _segmentar_fila(row) -> str | None:
    if row["HistoricoUlt3M"] <= 0 or row["ForecastProx4M"] <= 0 or pd.isna(row["AccEstadistico"]) or pd.isna(row["AccConsensuado"]):
        return None
    bk, bl, bm = row["AccEstadistico"], row["AccConsensuado"], row["DesvioAccuracyPP"]
    if bk > 0.8:
        return "0"
    if bl > 0.8:
        return "1"
    if 0.6 <= bl < 0.8:
        return "2.1" if bm > 0 else "2.2"
    if bl < 0.6:
        return "3.1" if bm > 0 else "3.2"
    return None


_ACC_AJUSTADA_POR_SEGMENTO_FIJO = {"1": 1.0, "2.1": 0.8, "2.2": 0.8, "3.1": 0.6, "3.2": 0.6}


def tabla_segmentacion_sku(df_producto: pd.DataFrame, df_forecast_prox4m: pd.DataFrame = None) -> pd.DataFrame:
    """
    Tabla por PRDID con Acc. Consensuado, Acc. Estadístico, Bias, Desvío
    (pp.), Segmento SKU (Base) y Acc Ajustada -- réplica fiel de las medidas
    DAX homónimas. ``df_producto`` necesita PERIODID3, PRDID,
    ForecastConsensuado, ForecastEstadistico, Actual (grano PRDID x mes, sin
    desagregar por cliente).

    ``df_forecast_prox4m``: salida de ``forecast_proximos_4m`` (PRDID,
    ForecastProx4M) -- segundo criterio de "Alcance" del informe ("forecast
    al menos para los próximos 4 meses"). ``None`` equivale a "sin forecast
    futuro para ningún SKU" (ningún SKU queda elegible para Segmento) -- las
    páginas SIEMPRE deberían pasarlo; el default solo evita un `KeyError` si
    algún caller nuevo todavía no lo arma.
    """
    acc_cons = acc_bias_consensuado(df_producto, ["PRDID"]).rename(
        columns={"Accuracy": "AccConsensuado", "Bias": "BiasConsensuado"}
    )[["PRDID", "AccConsensuado", "BiasConsensuado"]]
    acc_est = acc_estadistico(df_producto, ["PRDID"])[["PRDID", "Accuracy"]].rename(
        columns={"Accuracy": "AccEstadistico"}
    )
    hist3m = historico_ultimos_3m_cerrados(df_producto)
    historico_total = df_producto.groupby("PRDID", as_index=False)["Actual"].sum().rename(columns={"Actual": "Historico"})
    if df_forecast_prox4m is None:
        df_forecast_prox4m = pd.DataFrame(columns=["PRDID", "ForecastProx4M"])

    tabla = (
        acc_cons.merge(acc_est, on="PRDID", how="outer")
        .merge(hist3m, on="PRDID", how="left")
        .merge(historico_total, on="PRDID", how="left")
        .merge(df_forecast_prox4m, on="PRDID", how="left")
    )
    tabla["HistoricoUlt3M"] = tabla["HistoricoUlt3M"].fillna(0)
    tabla["ForecastProx4M"] = tabla["ForecastProx4M"].fillna(0)
    tabla["DesvioAccuracyPP"] = (tabla["AccConsensuado"] - tabla["AccEstadistico"]) * 100

    tabla["Segmento"] = tabla.apply(_segmentar_fila, axis=1)
    tabla["OrdenSegmento"] = tabla["Segmento"].map(ORDEN_SEGMENTO)
    tabla["AccAjustada"] = tabla.apply(
        lambda r: r["AccEstadistico"] if r["Segmento"] == "0" else _ACC_AJUSTADA_POR_SEGMENTO_FIJO.get(r["Segmento"]),
        axis=1,
    )
    return tabla


def cantidad_sku_por_segmento(tabla_segmentacion: pd.DataFrame) -> pd.DataFrame:
    """"Cantidad SKU Segmento": cantidad de PRDID distintos por Segmento."""
    return (
        tabla_segmentacion.dropna(subset=["Segmento"])
        .groupby("Segmento", as_index=False)["PRDID"].nunique()
        .rename(columns={"PRDID": "Cantidad SKU"})
    )


def volumen_por_segmento(tabla_segmentacion: pd.DataFrame) -> pd.DataFrame:
    """"% Volumen": participación de cada segmento sobre el volumen total
    "segmentable" (SKUs con histórico en los últimos 3 meses cerrados Y con
    Segmento asignado)."""
    segmentables = tabla_segmentacion.dropna(subset=["Segmento"])
    total = segmentables["Historico"].sum()
    out = segmentables.groupby("Segmento", as_index=False)["Historico"].sum()
    out["% Volumen"] = out["Historico"] / total if total else 0.0
    return out


def acc_consensuado_proyectado(tabla_segmentacion: pd.DataFrame, escenario_orden: int) -> float:
    """
    "Acc. Consensuado Proyectado (Escenario)": si se corrigieran todos los
    SKU con Orden Segmento <= ``escenario_orden`` a su Acc Ajustada, ¿cuál
    sería el accuracy resultante, ponderado por volumen (Historico total)?
    """
    df = tabla_segmentacion[tabla_segmentacion["Historico"] > 0].copy()
    if df.empty:
        return float("nan")
    df["AccFinal"] = df.apply(
        lambda r: r["AccAjustada"]
        if (pd.notna(r["OrdenSegmento"]) and r["OrdenSegmento"] <= escenario_orden)
        else r["AccConsensuado"],
        axis=1,
    )
    df = df.dropna(subset=["AccFinal"])
    if df.empty or df["Historico"].sum() == 0:
        return float("nan")
    # AccFinal ya es un promedio ponderado de valores en [0, 1] (AccAjustada/
    # AccConsensuado, ambos acotados en _accuracy_ponderada), así que el
    # resultado ya cae en ese rango -- el clip es solo un cinturón de
    # seguridad, no debería recortar nada en la práctica.
    return min(max((df["Historico"] * df["AccFinal"]).sum() / df["Historico"].sum(), 0.0), 1.0)


def resumen_segmentos(tabla_segmentacion: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla "Segmento" del Reporte de Proyección Accuracy real: Segmento,
    Cantidad SKU, % Volumen, Accuracy Proyectado -- una fila por segmento (en
    el orden 0, 1, 2.1, 2.2, 3.1, 3.2) más una fila "Total".

    La columna "Accuracy Proyectado" de cada fila es el resultado
    ACUMULATIVO de corregir todos los segmentos hasta ese, inclusive (en el
    orden de la tabla) -- exactamente el mismo número que devuelve
    ``acc_consensuado_proyectado(tabla, ORDEN_SEGMENTO[segmento])``, mostrado
    fila por fila en vez de con un selector aparte. Así se ve en el Power BI
    real: cada fila del segmento siguiente ya "incluye" la corrección de los
    anteriores.
    """
    cantidad = cantidad_sku_por_segmento(tabla_segmentacion).set_index("Segmento")["Cantidad SKU"]
    volumen = volumen_por_segmento(tabla_segmentacion).set_index("Segmento")["% Volumen"]

    filas = []
    for seg in ["0", "1", "2.1", "2.2", "3.1", "3.2"]:
        if seg not in cantidad.index:
            continue
        filas.append({
            "Segmento": SEGMENTOS_INFO[seg]["segmento"],
            "Cantidad SKU": int(cantidad.get(seg, 0)),
            "% Volumen": volumen.get(seg, 0.0),
            "Accuracy Proyectado": acc_consensuado_proyectado(tabla_segmentacion, ORDEN_SEGMENTO[seg]),
        })

    tabla = pd.DataFrame(filas)
    if tabla.empty:
        return tabla

    total = {
        "Segmento": "Total",
        "Cantidad SKU": int(tabla["Cantidad SKU"].sum()),
        "% Volumen": tabla["% Volumen"].sum(),
        "Accuracy Proyectado": float("nan"),
    }
    return pd.concat([tabla, pd.DataFrame([total])], ignore_index=True)
