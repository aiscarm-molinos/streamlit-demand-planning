# src/alertas.py
"""
Semáforo de 3 niveles y badges de Bias -- capa de PRESENTACIÓN sobre las
métricas de ``accuracy.py`` (no recalcula nada de negocio, solo clasifica y
colorea valores que las páginas ya calculan). Separado de ``accuracy.py`` a
propósito: ese módulo es la fuente de verdad de las fórmulas (réplica fiel
de las medidas DAX reales), este es puro criterio de UI.

Cortes ajustados a pedido del usuario (2026-09-16) -- **ya NO coinciden**
con los de ``accuracy.SEGMENTOS_INFO`` (80%/60%), que siguen siendo los
cortes reales de la segmentación de SKU (fórmula DAX real, no se tocan).
Si se ajusta un corte acá, actualizar también el texto de
``pages/8_Glosario.py`` (sección "Semáforo de Accuracy"), que los
documenta como referencia única.
"""

import pandas as pd

from src.charts import BUENO, MEDIO, MALO, NEUTRO, hex_a_rgba

UMBRAL_BUENO = 0.8   # >= 80%
UMBRAL_MEDIO = 0.7   # 70%-80% (antes 60%-80%)
UMBRAL_BIAS = 0.05   # +/-5% (antes +/-10%) -- Bias ya no tiene nivel "medio":
                      # dentro de la banda es "bueno" (verde), fuera es "malo"
                      # (rojo) simétrico en las dos direcciones -- antes
                      # sobreestimación coloreaba rojo y subestimación azul.

_EMOJI_NIVEL = {"bueno": "🟢", "medio": "🟡", "malo": "🔴", "sin_dato": "⚪"}
_COLOR_NIVEL = {"bueno": BUENO, "medio": MEDIO, "malo": MALO, "sin_dato": NEUTRO}


def nivel_accuracy(valor: float) -> str:
    """``"bueno"`` (>=80%) / ``"medio"`` (70-80%) / ``"malo"`` (<70%) / ``"sin_dato"`` (NaN)."""
    if pd.isna(valor):
        return "sin_dato"
    if valor >= UMBRAL_BUENO:
        return "bueno"
    if valor >= UMBRAL_MEDIO:
        return "medio"
    return "malo"


def nivel_brecha(gap_pct: float, umbral_medio: float = -0.05, umbral_malo: float = -0.15) -> str:
    """Semáforo para brechas vs. un objetivo (ej. Plan Anual) -- a diferencia
    de accuracy (siempre positiva, "malo" = valor bajo), acá "malo" es una
    brecha muy NEGATIVA (muy por debajo del objetivo); una brecha positiva o
    apenas negativa es "bueno"/"medio"."""
    if pd.isna(gap_pct):
        return "sin_dato"
    if gap_pct >= umbral_medio:
        return "bueno"
    if gap_pct >= umbral_malo:
        return "medio"
    return "malo"


def badge_nivel(nivel: str) -> tuple[str, str]:
    """(emoji, color hex) para un ``nivel`` de ``nivel_accuracy``/``nivel_brecha``."""
    return _EMOJI_NIVEL.get(nivel, "⚪"), _COLOR_NIVEL.get(nivel, NEUTRO)


def nivel_bias(valor: float, umbral: float = UMBRAL_BIAS) -> str:
    """``"bueno"`` (dentro de +/-``umbral``) / ``"malo"`` (fuera, en cualquiera
    de las dos direcciones) / ``"sin_dato"`` -- a diferencia de
    ``nivel_accuracy``, Bias no tiene nivel "medio": el color solo marca si
    el sesgo está dentro de un rango aceptable o no, la DIRECCIÓN (sobre/
    subestimación) se comunica en el texto de ``etiqueta_bias``, no en el
    color."""
    if pd.isna(valor):
        return "sin_dato"
    return "bueno" if abs(valor) <= umbral else "malo"


def etiqueta_bias(valor: float, umbral: float = UMBRAL_BIAS) -> tuple[str, str]:
    """(texto, color hex) para un badge de Bias -- el texto distingue
    sobreestimación de subestimación (acciones opuestas: riesgo de
    sobrestock vs. quiebre), pero el COLOR es el mismo semáforo simétrico
    de ``nivel_bias`` (verde adentro de la banda, rojo afuera en cualquier
    dirección) -- ya no usa un color distinto por dirección."""
    if pd.isna(valor):
        return "⚪ Sin dato", NEUTRO
    if abs(valor) <= umbral:
        return "🟢 Sin sesgo relevante", BUENO
    if valor > umbral:
        return "🔴 Sobreestimación (riesgo de sobrestock)", MALO
    return "🔴 Subestimación (riesgo de quiebre)", MALO


def color_accuracy(valor: float, alpha: float = 0.22) -> str:
    """CSS ``background-color`` para un valor de accuracy en [0,1] (o NaN) --
    pensado para ``Styler.map(color_accuracy, subset=[...])``."""
    color = _COLOR_NIVEL[nivel_accuracy(valor)]
    return f"background-color: {hex_a_rgba(color, alpha)}" if color != NEUTRO else ""


def color_bias(valor: float, umbral: float = UMBRAL_BIAS, alpha: float = 0.22) -> str:
    """CSS ``background-color`` para un valor de Bias -- semáforo simétrico
    de ``nivel_bias`` (verde adentro de +/-``umbral``, rojo afuera),
    pensado para ``Styler.map``."""
    nivel = nivel_bias(valor, umbral)
    if nivel == "sin_dato":
        return ""
    color = BUENO if nivel == "bueno" else MALO
    return f"background-color: {hex_a_rgba(color, alpha)}"


def color_bias_direccion(valor: float, alpha: float = 0.22) -> str:
    """CSS ``background-color`` para Bias coloreado por DIRECCIÓN -- verde
    si es positivo (sobreestimación), rojo si es negativo (subestimación),
    sin importar la magnitud. Distinto a propósito de ``color_bias``
    (semáforo SIMÉTRICO por magnitud, ±``UMBRAL_BIAS``, usado en el Reporte
    de Resultados mensual): acá es a pedido puntual del usuario para la
    tabla "Ranking por Área Comercial" de Ranking Clientes (2026-09-19),
    donde lo que importa es de qué lado del cero cae, no si está "dentro de
    rango"."""
    if pd.isna(valor):
        return ""
    color = BUENO if valor > 0 else (MALO if valor < 0 else NEUTRO)
    return f"background-color: {hex_a_rgba(color, alpha)}" if color != NEUTRO else ""


def aplicar_semaforo_accuracy(styler: "pd.io.formats.style.Styler", columnas: list) -> "pd.io.formats.style.Styler":
    """``df.style.format(...).pipe(alertas.aplicar_semaforo_accuracy, columnas=[...])``
    -- para tablas donde TODAS las columnas dadas son valores de accuracy en
    [0,1] (ej. los rankings de Ranking Clientes). Para tablas con Accuracy Y
    Bias mezclados por fila, ver ``estilo_pivot_metricas``."""
    return styler.map(color_accuracy, subset=columnas)


def estilo_pivot_metricas(row: pd.Series, nivel_metrica: int = 1) -> list:
    """Para ``Styler.apply(alertas.estilo_pivot_metricas, axis=1)`` sobre un
    pivot con filas ``MultiIndex`` que incluyen una Métrica (ej. "Accuracy
    Consensuado"/"Bias Consensuado"/"Accuracy Estadístico") -- colorea cada
    fila con el semáforo que corresponda según si el nombre de fila contiene
    "Bias" o no. Pensado para las tablas "Evolución Mensual"/"Accuracy &
    Bias Ponderado" de ``pages/5_Reporte_Accuracy.py``, donde una misma
    tabla mezcla ambos tipos de métrica por fila."""
    metrica = row.name[nivel_metrica] if isinstance(row.name, tuple) else row.name
    if "Bias" in str(metrica):
        return [color_bias(v) for v in row]
    return [color_accuracy(v) for v in row]


def resaltar_fila_critica(row: pd.Series, columna: str, valores_criticos: list, alpha: float = 0.15) -> list:
    """Para ``Styler.apply(lambda r: alertas.resaltar_fila_critica(r, ...), axis=1)``
    -- colorea la fila entera si ``row[columna]`` está en ``valores_criticos``
    (ej. Segmento SKU "3.2 | ..." en ``pages/6_Segmentacion_SKU.py``)."""
    if row.get(columna) in valores_criticos:
        return [f"background-color: {hex_a_rgba(MALO, alpha)}"] * len(row)
    return [""] * len(row)
