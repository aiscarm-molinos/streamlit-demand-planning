# src/feature_labels.py
"""
Traducción de negocio de las variables exógenas de los modelos de AWS
SageMaker (``ForecasterRecursive`` de skforecast, pipeline
``ibp-forecast-mensual``) -- para mostrar "Feature Importance" en términos
de negocio en vez de nombres técnicos del ``ColumnTransformer`` de
entrenamiento.

El patrón de nombre crudo (confirmado contra ``get_feature_importances()``
real de 2 ``.pkl`` de muestra en ``sample_data/sagemaker/model.tar`` -- uno
PRDFAMILY, uno PRDID, no es una suposición):

- Exógenas: ``<transformer>__<VARIABLE>[_lag_<N>]``, ej.
  ``scaler_price__PUNITARIO``, ``scaler_volume__SOM_lag_1``,
  ``onehot__SEASON_Verano``, ``remainder__MONTH_cos``. Los prefijos
  ``scaler_price``/``scaler_volume``/``onehot``/``remainder`` son nombres
  internos del pipeline de entrenamiento (ruido de preprocesamiento) -- se
  descartan al traducir, no aportan nada de negocio.
- Autoregresivo del propio target (``ADJUSTEDACTUALSQTY``): ``lag_<N>``,
  sin prefijo (ej. ``lag_1``, ``lag_3`` -- según ``lags_grid`` elegido en
  el entrenamiento).

Definiciones de negocio: ``ZSELLOUTCLIENTE``/``PUNITARIO``/``PINDEX``/
``SOM``/``SOV`` de la tabla de key figures real de
``ibp-forecast-mensual/README.md``; ``PLANANUAL``/``PENDIENTE_CAJ`` de
``forecast_mensual_dataset.py`` del mismo repo; ``ADJUSTEDACTUALSQTY`` de
la tabla de key figures de este mismo ``CLAUDE.md`` ("Histórico
Ajustado"). ``MONTH``/``SEASON``/``YEAR`` son lectura del código de
preprocesamiento (``CyclicalFeatures``/``OneHotEncoder``), no de un
README -- confirmado con el usuario 2026-09-20.
"""

import re

import pandas as pd

ETIQUETAS_VARIABLE = {
    "ZSELLOUTCLIENTE": "Venta al consumidor (Sell-out Scentia, CAJ)",
    "PUNITARIO": "Precio unitario (ARS/CAJ)",
    "PINDEX": "Índice de precio vs. mercado",
    "SOM": "Share of Market (participación en volumen)",
    "SOV": "Share of Value (participación en valor)",
    "PLANANUAL": "Plan Anual (SAP IBP)",
    "PENDIENTE_CAJ": "Pedido pendiente de entrega (CAJ)",
    "MONTH": "Estacionalidad del mes",
    "SEASON": "Estación del año",
    "YEAR": "Año calendario",
    "TARGET": "Venta propia (Histórico Ajustado), mes(es) anterior(es)",
}

# Agrupamiento de negocio -- para una vista agregada (ej. Feature Importance
# por nivel), colapsar variables relacionadas bajo un mismo concepto.
GRUPO_VARIABLE = {
    "ZSELLOUTCLIENTE": "Ventas / participación de mercado",
    "SOM": "Ventas / participación de mercado",
    "SOV": "Ventas / participación de mercado",
    "PUNITARIO": "Precio",
    "PINDEX": "Precio",
    "PLANANUAL": "Plan comercial",
    "PENDIENTE_CAJ": "Pedidos pendientes",
    "MONTH": "Estacionalidad",
    "SEASON": "Estacionalidad",
    "YEAR": "Estacionalidad",
    "TARGET": "Historia propia (autoregresivo)",
}

_RE_TRANSFORMER_PREFIX = re.compile(r"^(scaler_price|scaler_volume|remainder|onehot)__(.+)$")
_RE_LAG_SUFFIX = re.compile(r"_lag_(\d+)$")


def variable_base(feature_cruda: str) -> tuple[str, int | None]:
    """
    Descompone un nombre de feature crudo en ``(variable_base, rezago_meses)``.

    Ej. ``"scaler_volume__SOM_lag_1"`` -> ``("SOM", 1)``,
    ``"onehot__SEASON_Verano"`` -> ``("SEASON", None)``,
    ``"remainder__MONTH_cos"`` -> ``("MONTH", None)``,
    ``"lag_3"`` -> ``("TARGET", 3)``.
    """
    nombre = feature_cruda

    m = _RE_TRANSFORMER_PREFIX.match(nombre)
    if m:
        nombre = m.group(2)

    if re.fullmatch(r"lag_\d+", nombre):
        return "TARGET", int(nombre.split("_")[1])

    for base in ("SEASON", "YEAR"):
        if nombre.startswith(f"{base}_"):
            return base, None

    if nombre in ("MONTH_cos", "MONTH_sin"):
        return "MONTH", None

    m = _RE_LAG_SUFFIX.search(nombre)
    if m:
        return nombre[: m.start()], int(m.group(1))

    return nombre, None


def etiqueta_variable(variable: str) -> str:
    """Nombre de negocio de una variable base -- la variable cruda tal cual
    si no está en ``ETIQUETAS_VARIABLE``, nunca rompe con un valor inesperado
    (mismo criterio que ``nivel_planificacion.etiqueta_nivel``)."""
    return ETIQUETAS_VARIABLE.get(variable, variable)


def grupo_variable(variable: str) -> str:
    return GRUPO_VARIABLE.get(variable, "Otras")


def traducir_importancias(df_importancias: pd.DataFrame, col_feature: str = "feature") -> pd.DataFrame:
    """
    Agrega columnas de negocio a un DataFrame de importancias crudo
    (salida de ``model_deserializer.extraer_feature_importance``, columnas
    ``feature``/``importance``): ``Variable``, ``Rezago (meses)``,
    ``Etiqueta``, ``Grupo``. Una fila por feature cruda -- no agrupa, eso lo
    hace ``agregar_por_variable`` a propósito separado.
    """
    out = df_importancias.copy()
    base_rezago = out[col_feature].apply(variable_base)
    out["Variable"] = base_rezago.apply(lambda t: t[0])
    out["Rezago (meses)"] = base_rezago.apply(lambda t: t[1])
    out["Etiqueta"] = out["Variable"].map(etiqueta_variable)
    out["Grupo"] = out["Variable"].map(grupo_variable)
    return out


def agregar_por_variable(df_traducido: pd.DataFrame, col_importance: str = "importance") -> pd.DataFrame:
    """Suma ``importance`` por Variable/Etiqueta/Grupo -- colapsa
    ``YEAR_2020..2026``, ``SEASON_*``, rezagos, etc. en una sola fila por
    variable de negocio. Requiere ``traducir_importancias`` corrido antes."""
    return (
        df_traducido.groupby(["Variable", "Etiqueta", "Grupo"], as_index=False)[col_importance]
        .sum()
        .sort_values(col_importance, ascending=False)
        .reset_index(drop=True)
    )
