# src/nivel_planificacion.py
"""
Lógica de negocio de "Nivel de Planificación" y "Feature Importance"
(Experimentos SageMaker) -- resuelve, para una entidad (PRDFAMILY) y un
nivel de planificación (PRDID/PRDFAMILY/ZINDFAMILY/ZBRAND/ZBIGBUSINESS), a
qué valor(es) de ese nivel corresponde, para poder:
- buscar su accuracy en ``reports/modelos_forecast_mensual.csv`` (Nivel de
  Planificación), o
- ubicar su(s) archivo(s) ``.pkl`` en ``trained_models/<nivel>/`` (Feature
  Importance).

Ambos casos comparten el mismo problema: ``reports/mejor_nivel_planificacion_
por_entidad.csv`` solo dice PRDFAMILY + nivel elegido, no el/los valores de
ESE nivel para esa entidad -- eso hay que resolverlo contra el dataset
(``preprocessed_forecast_mensual``), que sí tiene las 5 columnas de
jerarquía de producto por fila.

Es 1:1 cuando el nivel elegido ES "PRDFAMILY" (la propia entidad), pero
puede ser 1:muchos en niveles más finos (una familia tiene varios PRDID) o
muchos:1 en niveles más gruesos (varias familias comparten una misma
ZBIGBUSINESS) -- por eso todas las funciones acá devuelven listas, nunca un
valor único.
"""

from dataclasses import dataclass

import pandas as pd

NIVELES_JERARQUIA = ["PRDID", "PRDFAMILY", "ZINDFAMILY", "ZBRAND", "ZBIGBUSINESS"]


def valores_de_nivel(df_dataset: pd.DataFrame, prdfamily: str, nivel: str) -> list[str]:
    """Valores del nivel ``nivel`` a los que pertenece la entidad ``prdfamily``,
    resueltos contra el dataset (preprocessed_forecast_mensual)."""
    if nivel == "PRDFAMILY":
        return [prdfamily]
    if nivel not in df_dataset.columns:
        return []
    sub = df_dataset.loc[df_dataset["PRDFAMILY"] == prdfamily, nivel].dropna()
    return sorted(str(v) for v in sub.unique())


@dataclass
class NivelElegido:
    prdfamily: str
    nivel: str
    error_abs_total: float
    valores: list[str]  # valor(es) resueltos de `nivel` para esta entidad
    accuracy_avg: float | None  # promedio de Accuracy_AVG entre `valores` (None si no se encontró ninguno)


def resumen_nivel_elegido(
    df_mejor_nivel: pd.DataFrame, df_modelos: pd.DataFrame, df_dataset: pd.DataFrame
) -> list[NivelElegido]:
    """Por cada entidad de ``mejor_nivel_planificacion_por_entidad.csv``,
    resuelve sus valores en el nivel elegido y busca su Accuracy_AVG en
    ``modelos_forecast_mensual.csv`` (promedio si hay más de un valor)."""
    resultados = []
    for _, fila in df_mejor_nivel.iterrows():
        prdfamily = fila["PRDFAMILY"]
        nivel = fila["MEJOR_NIVEL_PLANIFICACION"]
        valores = valores_de_nivel(df_dataset, prdfamily, nivel)

        accuracy = None
        if valores:
            match = df_modelos[
                (df_modelos["NIVEL_DE_PLANIFICACION"] == nivel) & (df_modelos["VALOR_NIVEL"].astype(str).isin(valores))
            ]
            if not match.empty and match["Accuracy_AVG"].notna().any():
                accuracy = float(match["Accuracy_AVG"].mean())

        resultados.append(
            NivelElegido(
                prdfamily=prdfamily,
                nivel=nivel,
                error_abs_total=float(fila["ERROR_ABS_TOTAL"]),
                valores=valores,
                accuracy_avg=accuracy,
            )
        )
    return resultados


def nombre_archivo_pkl(nivel: str, valor: str) -> str:
    """Convención de nombre real observada en ``trained_models/<nivel>/`` --
    espacios reemplazados por "_" (ver CLAUDE.md, verificado contra un
    model.tar.gz real: "Cocinero Mezcla" -> "Cocinero_Mezcla",
    "STORK I" -> "STORK_I")."""
    return f"trained_models/{nivel}/forecaster_{nivel}_{valor.replace(' ', '_')}.pkl"
