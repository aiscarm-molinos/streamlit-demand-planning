# src/utils/listas_periodos.py
"""
Generación de listas de períodos mensuales en formato 'yy-MMM' (ej. '25-Jan'),
el mismo formato que usa PERIODID3 en SAP IBP.

Copiado de ``ibp-algoritmo-ep/src/utils/listas_periodos.py`` (solo las
funciones mensuales, las diarias no se usan en este proyecto).
"""

from datetime import datetime, timedelta
from pandas import date_range


def periodos_historicos_mes(n_meses: int):
    """Últimos n_meses en formato 'yy-MMM', excluyendo el mes actual."""
    hoy = datetime.today()
    primer_dia_mes_actual = hoy.replace(day=1)
    fechas_mensuales = date_range(
        end=primer_dia_mes_actual - timedelta(days=1), periods=n_meses, freq="MS"
    )
    return [fecha.strftime("%y-%b") for fecha in fechas_mensuales]


def periodos_futuros_mes(n_meses: int):
    """Desde el mes actual hasta n_meses en el futuro, formato 'yy-MMM'."""
    hoy = datetime.today()
    primer_dia_mes_actual = hoy.replace(day=1)
    fechas_mensuales = date_range(start=primer_dia_mes_actual, periods=n_meses, freq="MS")
    return [fecha.strftime("%y-%b") for fecha in fechas_mensuales]


def periodid3_a_fecha(periodid3):
    """Convierte una Serie/valor 'yy-MMM' (ej. '25-Jan') a datetime (día 1 del mes)."""
    import pandas as pd

    return pd.to_datetime(periodid3, format="%y-%b")


def periodos_terminando_en(n_meses: int, mes_referencia: str):
    """
    Últimos ``n_meses`` en formato 'yy-MMM', terminando en (e incluyendo)
    ``mes_referencia`` -- p.ej. ``periodos_terminando_en(4, "26-Aug")`` da
    los 4 meses del "U4M" (últimos 4 meses) que usa el Reporte Accuracy real,
    anclados al mes que el usuario elija en el filtro "Período", no
    necesariamente al mes actual.
    """
    import pandas as pd

    fecha_ref = periodid3_a_fecha(mes_referencia)
    fechas = date_range(end=fecha_ref, periods=n_meses, freq="MS")
    return [f.strftime("%y-%b") for f in fechas]


def periodos_empezando_en(n_meses: int, mes_referencia: str):
    """
    Próximos ``n_meses`` en formato 'yy-MMM', empezando en el mes siguiente a
    ``mes_referencia`` -- ancla del segundo criterio de "Alcance" del informe
    "Reporte – Ranking Forecast Accuracy" ("SKUs... con forecast al menos
    para los próximos 4 meses"), sobre el mismo mes elegido en el filtro
    "Mes" (no necesariamente el mes actual). Ver
    ``src/accuracy.py::forecast_proximos_4m``.
    """
    import pandas as pd

    fecha_ref = periodid3_a_fecha(mes_referencia) + pd.DateOffset(months=1)
    fechas = date_range(start=fecha_ref, periods=n_meses, freq="MS")
    return [f.strftime("%y-%b") for f in fechas]
