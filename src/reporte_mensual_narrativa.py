# src/reporte_mensual_narrativa.py
"""
Redacción de los párrafos narrativos del "Reporte de Resultados" mensual --
separado de ``reporte_mensual.py`` (que solo calcula números) a propósito,
para poder ajustar tono/redacción sin tocar las fórmulas.

El tono y la estructura de frases se calcaron del "Reporte de Resultados -
Forecast Agosto" real (``reports/2026.zip``) -- no es una réplica palabra
por palabra (la redacción humana varía frase a frase), pero sigue el mismo
patrón: nivel + comparación vs. mes anterior para División/Negocio,
callouts de "líder"/"mayor aporte"/"impacto negativo" para rankings.
"""

import pandas as pd

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def nombre_mes(periodid3: str) -> str:
    """'26-Aug' -> 'agosto'."""
    from src.utils.listas_periodos import periodid3_a_fecha
    fecha = periodid3_a_fecha(periodid3)
    return MESES_ES[fecha.month]


def _comparacion(valor_actual: float, valor_anterior: float, mes_anterior_nombre: str) -> str:
    if pd.isna(valor_anterior):
        return ""
    if abs(valor_actual - valor_anterior) < 0.005:
        return f", sin cambios respecto a {mes_anterior_nombre}"
    direccion = "por encima" if valor_actual > valor_anterior else "por debajo"
    return f", {direccion} del {valor_anterior:.0%} registrado en {mes_anterior_nombre}"


def texto_accuracy_gran_division(tabla_accuracy: pd.DataFrame, mes: str, mes_anterior: str) -> str:
    """Un párrafo por división -- accuracy consensuado y estadístico del
    mes, comparado contra el mes anterior si está disponible en la tabla."""
    if tabla_accuracy.empty or mes not in tabla_accuracy.columns:
        return "No hay datos de accuracy para el mes seleccionado."

    mes_nombre = nombre_mes(mes)
    mes_ant_nombre = nombre_mes(mes_anterior) if mes_anterior in tabla_accuracy.columns else None
    frases = []
    for division in tabla_accuracy.index.get_level_values(0).unique():
        cons = tabla_accuracy.loc[(division, "Fcst Cons."), mes] if (division, "Fcst Cons.") in tabla_accuracy.index else float("nan")
        est = tabla_accuracy.loc[(division, "Fcst Estad."), mes] if (division, "Fcst Estad.") in tabla_accuracy.index else float("nan")
        cons_ant = tabla_accuracy.loc[(division, "Fcst Cons."), mes_anterior] if mes_ant_nombre and (division, "Fcst Cons.") in tabla_accuracy.index else float("nan")
        est_ant = tabla_accuracy.loc[(division, "Fcst Estad."), mes_anterior] if mes_ant_nombre and (division, "Fcst Estad.") in tabla_accuracy.index else float("nan")

        comp_cons = _comparacion(cons, cons_ant, mes_ant_nombre) if mes_ant_nombre else ""
        comp_est = _comparacion(est, est_ant, mes_ant_nombre) if mes_ant_nombre else ""

        frases.append(
            f"En {division}, el forecast consensuado se ubicó en {cons:.0%}{comp_cons}. "
            f"El estadístico se ubicó en {est:.0%}{comp_est}."
            if pd.notna(cons) and pd.notna(est) else f"En {division} no hay datos suficientes para {mes_nombre}."
        )

    return f"En {mes_nombre}, " + frases[0][3:] + "\n" + "\n".join(frases[1:])


def texto_bias_gran_division(tabla_bias: pd.DataFrame, mes: str) -> str:
    """Un párrafo por división con el Bias estadístico/consensuado del mes,
    con la interpretación de dirección (sobre/subestimación)."""
    if tabla_bias.empty or mes not in tabla_bias.columns:
        return "No hay datos de Bias para el mes seleccionado."

    frases = []
    for division in tabla_bias.index.get_level_values(0).unique():
        est = tabla_bias.loc[(division, "Fcst Estad."), mes] if (division, "Fcst Estad.") in tabla_bias.index else float("nan")
        cons = tabla_bias.loc[(division, "Fcst Cons."), mes] if (division, "Fcst Cons.") in tabla_bias.index else float("nan")
        if pd.isna(est) or pd.isna(cons):
            frases.append(f"{division}: sin datos suficientes de Bias.")
            continue
        dir_est = "sobreestimación" if est > 0 else "subestimación"
        dir_cons = "sobreestimación" if cons > 0 else "subestimación"
        if dir_est == dir_cons and abs(cons) < abs(est):
            cierre = f"El consensuado redujo la {dir_est} del estadístico."
        elif dir_est == dir_cons:
            cierre = f"El consensuado amplió la {dir_est} del estadístico."
        else:
            cierre = "El consensuado invirtió la dirección del sesgo del estadístico."
        frases.append(
            f"{division} presentó un Bias estadístico de {est:+.1%} y consensuado de {cons:+.1%}. {cierre}"
        )

    return "\n".join(frases)


def texto_destacados(
    tabla: pd.DataFrame, col_nombre: str, col_consensuado: str = "Consensuado",
    col_aporte: str = "Cons vs Est", top_n: int = 3, bottom_n: int = 2,
    nombre_seccion: str = "los casos",
) -> list:
    """Bullets de "líderes"/"mayor aporte"/"impacto negativo"/"parte baja
    del ranking" -- generaliza el patrón real observado en Gran Negocio y
    Libre de Gluten (misma estructura de callouts, distinto nivel de
    agrupación). Devuelve una lista de strings (una por bullet), no un solo
    párrafo -- el renderer arma la lista con viñetas."""
    tabla = tabla.dropna(subset=[col_consensuado])
    if tabla.empty:
        return [f"No hay datos suficientes para destacar {nombre_seccion}."]

    bullets = []
    lideres = tabla.nlargest(top_n, col_consensuado)
    for i, (_, fila) in enumerate(lideres.iterrows()):
        puesto = ["Lideraron el ranking", "Se ubicó en el segundo puesto", "Alcanzó el tercer puesto"][min(i, 2)]
        bullets.append(f"{fila[col_nombre]}: {puesto} con un accuracy consensuado del {fila[col_consensuado]:.0%}.")

    if col_aporte in tabla.columns and tabla[col_aporte].notna().any():
        mejor_aporte = tabla.loc[tabla[col_aporte].idxmax()]
        if mejor_aporte[col_aporte] > 0:
            bullets.append(
                f"{mejor_aporte[col_nombre]}: Registró el mayor aporte del proceso, +{mejor_aporte[col_aporte]:.0f}pp, "
                f"elevando el consensuado al {mejor_aporte[col_consensuado]:.0%} desde un estadístico del {mejor_aporte['Estadistico']:.0%}."
            )
        peor_aporte = tabla.loc[tabla[col_aporte].idxmin()]
        if peor_aporte[col_aporte] < 0:
            bullets.append(
                f"{peor_aporte[col_nombre]}: Mostró el impacto negativo más significativo del proceso, {peor_aporte[col_aporte]:.0f}pp, "
                f"señalando una oportunidad de mejora en la planificación."
            )

    rezagados = tabla.nsmallest(bottom_n, col_consensuado)
    if not rezagados.empty:
        nombres = ", ".join(f"{f[col_nombre]} ({f[col_consensuado]:.0%})" for _, f in rezagados.iterrows())
        bullets.append(f"En la parte baja del ranking: {nombres}.")

    return bullets
