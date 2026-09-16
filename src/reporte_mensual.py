# src/reporte_mensual.py
"""
Cálculo de datos del "Reporte de Resultados - Forecast <Mes>" mensual --
réplica automatizada del documento que el equipo arma a mano cada mes
(ver ``reports/`` -- histórico real Feb-Ago 2026 con el mismo formato,
membrete Molinos, que se usó como referencia).

SOLO cálculo (reusa ``accuracy.py`` al máximo, nunca reinventa una fórmula
acá) -- la redacción de los párrafos narrativos vive en
``reporte_mensual_narrativa.py`` y el armado del .docx en
``generador_reporte_docx.py``, separado a propósito (mismo patrón que
``alertas.py`` separado de ``accuracy.py``): así se puede ajustar redacción
o layout sin tocar números, y viceversa.

Dos heurísticas documentadas acá porque no hay un atributo dedicado en SAP
para ninguna de las dos (confirmado contra el maestro real):
- **Libre de Gluten**: ningún campo lo marca -- se aproxima con dos
  condiciones AND (a pedido del usuario, 2026-09-16, acota la aproximación
  original de solo texto): SKU de uno de los Grandes Negocios de
  ``LDG_GRANDES_NEGOCIOS`` (los únicos que realmente tienen líneas Libre de
  Gluten) Y ``PRDDESCR`` conteniendo "LDG" o "GLUTEN" (cubre variantes como
  "Blancaflor Premezcla Universal LDG 10x1k" y cualquier mención textual de
  "Libre de Gluten"/"Sin Gluten").
- **Grandes Cuentas**: ya NO es heurística -- ``GRANDES_CUENTAS`` es la
  lista curada real de 12 cuentas que usa el reporte, dada por el usuario
  (2026-09-16, reemplaza el top-N por volumen que se usaba antes, que se
  colaba con zonas geográficas/canal como "Centro"/"Litoral"/"Pampeana" al
  no poder distinguirlas de una cuenta real por volumen solo).
"""

import pandas as pd

from src.accuracy import acc_bias_consensuado, acc_estadistico, bias_estadistico

# ZBIGBUSINESS (Gran Negocio) confirmados contra el maestro real como los
# únicos con líneas Libre de Gluten -- ver heurística de "Libre de Gluten"
# en el docstring del módulo.
LDG_GRANDES_NEGOCIOS = {"Refrigerados", "Pasta Seca", "Rebozador", "Premezclas", "Horneables"}

# ZAREAGC real -> abreviatura para "Área Gran Cuenta" del reporte -- lista
# curada dada por el usuario (2026-09-16, ver heurística de "Grandes
# Cuentas" en el docstring del módulo); nombres verificados contra el filtro
# real de Area/GC del tablero.
GRANDES_CUENTAS = {
    "CARREFOUR": "CRF",
    "CENCOSUD": "CENCO",
    "CHANGOMAS": "CHANGO",
    "COTO": "COTO",
    "DIA": "DIA",
    "DIARCO": "DRC",
    "LA ANONIMA": "LA ANM",
    "MAKRO": "MKO",
    "MAXICONSUMO": "MXC",
    "NINI": "NINI",
    "VITAL": "VTL",
    "YAGUAR": "YGR",
}

# ZAREACOMERCIAL a excluir de "Área Comercial" del reporte -- no son canales
# de venta reales (a pedido del usuario, 2026-09-16).
AREA_COMERCIAL_EXCLUIR = {"Otros", "Tienda Molinos"}

# ZAREACOMERCIAL real -> abreviatura para "Área Comercial" del reporte --
# DxGBA queda igual, a pedido del usuario (2026-09-16).
AREA_COMERCIAL_ABREVIATURAS = {
    "Supermercados": "SPM",
    "Mayoristas": "MAY",
    "Minoristas GBA": "MIN GBA",
    "Interior": "INT",
}


def accuracy_bias_gran_division_historico(df_producto: pd.DataFrame, meses_12: list) -> tuple:
    """``(tabla_accuracy, tabla_bias)`` -- index ``(ZBIGDIVISION, Métrica)``,
    una columna por mes de ``meses_12`` (trailing 12 meses, orden
    cronológico) -- mismo shape que "Evolución Mensual" de
    ``pages/5_Reporte_Accuracy.py``, pero con una ventana fija de 12 meses
    en vez de la selección del sidebar."""
    df_meses = df_producto[df_producto["PERIODID3"].isin(meses_12)]
    if df_meses.empty:
        vacio = pd.DataFrame()
        return vacio, vacio

    acc_cons = acc_bias_consensuado(df_meses, ["ZBIGDIVISION", "PERIODID3"])
    acc_est = acc_estadistico(df_meses, ["ZBIGDIVISION", "PERIODID3"])
    bias_est = bias_estadistico(df_meses, ["ZBIGDIVISION", "PERIODID3"])

    largo_acc = pd.concat([
        acc_est[["ZBIGDIVISION", "PERIODID3", "Accuracy"]].assign(Métrica="Fcst Estad.").rename(columns={"Accuracy": "Valor"}),
        acc_cons[["ZBIGDIVISION", "PERIODID3", "Accuracy"]].assign(Métrica="Fcst Cons.").rename(columns={"Accuracy": "Valor"}),
    ], ignore_index=True)
    tabla_accuracy = pd.pivot_table(largo_acc, index=["ZBIGDIVISION", "Métrica"], columns="PERIODID3", values="Valor")
    tabla_accuracy = tabla_accuracy[[m for m in meses_12 if m in tabla_accuracy.columns]]

    largo_bias = pd.concat([
        bias_est[["ZBIGDIVISION", "PERIODID3", "Bias"]].assign(Métrica="Fcst Estad.").rename(columns={"Bias": "Valor"}),
        acc_cons[["ZBIGDIVISION", "PERIODID3", "Bias"]].assign(Métrica="Fcst Cons.").rename(columns={"Bias": "Valor"}),
    ], ignore_index=True)
    tabla_bias = pd.pivot_table(largo_bias, index=["ZBIGDIVISION", "Métrica"], columns="PERIODID3", values="Valor")
    tabla_bias = tabla_bias[[m for m in meses_12 if m in tabla_bias.columns]]

    return tabla_accuracy, tabla_bias


def _tabla_accuracy_nivel(df_producto: pd.DataFrame, group_col: str, mes: str, meses_u6m: list, filtro_prdid: set = None, incluir_bias: bool = False) -> pd.DataFrame:
    """Consensuado/Estadístico del mes + "Cons vs Est" (pp., aporte del
    proceso de planificación) + "Cons vs Est U6M" (mismo delta, promedio de
    los últimos 6 meses -- da contexto de si el aporte del mes es
    consistente o puntual). Usada por Gran Negocio y Libre de Gluten, que
    comparten esta estructura -- solo cambia el nivel de agrupación.
    ``incluir_bias``: agrega "Bias Consensuado"/"Bias Estadistico" -- Gran
    Negocio no las pide (no cambiar su tabla sin que se pida), Libre de
    Gluten sí las usa para el indicador global (ver
    ``accuracy_libre_de_gluten``)."""
    df_mes = df_producto[df_producto["PERIODID3"] == mes]
    df_u6m = df_producto[df_producto["PERIODID3"].isin(meses_u6m)]
    if filtro_prdid is not None:
        df_mes = df_mes[df_mes["PRDID"].astype(str).isin(filtro_prdid)]
        df_u6m = df_u6m[df_u6m["PRDID"].astype(str).isin(filtro_prdid)]

    columnas = [group_col, "Consensuado", "Estadistico"]
    if incluir_bias:
        columnas += ["Bias Consensuado", "Bias Estadistico"]
    columnas += ["Cons vs Est", "Cons vs Est U6M"]
    if df_mes.empty:
        return pd.DataFrame(columns=columnas)

    acc_cons = acc_bias_consensuado(df_mes, [group_col]).rename(columns={"Accuracy": "Consensuado", "Bias": "Bias Consensuado"})
    acc_est = acc_estadistico(df_mes, [group_col])[[group_col, "Accuracy"]].rename(columns={"Accuracy": "Estadistico"})
    tabla = acc_cons.merge(acc_est, on=group_col, how="outer")
    if incluir_bias:
        bias_est = bias_estadistico(df_mes, [group_col]).rename(columns={"Bias": "Bias Estadistico"})
        tabla = tabla.merge(bias_est, on=group_col, how="left")
    else:
        tabla = tabla.drop(columns=["Bias Consensuado"])
    tabla["Cons vs Est"] = (tabla["Consensuado"] - tabla["Estadistico"]) * 100

    if not df_u6m.empty:
        acc_cons_u6m = acc_bias_consensuado(df_u6m, [group_col, "PERIODID3"])[[group_col, "PERIODID3", "Accuracy"]].rename(columns={"Accuracy": "Consensuado"})
        acc_est_u6m = acc_estadistico(df_u6m, [group_col, "PERIODID3"])[[group_col, "PERIODID3", "Accuracy"]].rename(columns={"Accuracy": "Estadistico"})
        u6m = acc_cons_u6m.merge(acc_est_u6m, on=[group_col, "PERIODID3"], how="outer")
        u6m["Delta"] = (u6m["Consensuado"] - u6m["Estadistico"]) * 100
        u6m_prom = u6m.groupby(group_col, as_index=False)["Delta"].mean().rename(columns={"Delta": "Cons vs Est U6M"})
        tabla = tabla.merge(u6m_prom, on=group_col, how="left")
    else:
        tabla["Cons vs Est U6M"] = float("nan")

    return tabla.sort_values("Consensuado", ascending=False, na_position="last")


def _solo_con_accuracy(tabla: pd.DataFrame) -> pd.DataFrame:
    """Descarta filas sin ningún accuracy calculable en el mes (sin
    Actual/Forecast en ese período -- típicamente de baja o sin ventas) --
    a pedido del usuario, "que aparezcan los que tienen accuracy nomás"
    (Gran Negocio, 2026-09-17; Libre de Gluten, 2026-09-16)."""
    return tabla[tabla["Consensuado"].notna() | tabla["Estadistico"].notna()]


def accuracy_gran_negocio(df_producto: pd.DataFrame, mes: str, meses_u6m: list) -> pd.DataFrame:
    tabla = _tabla_accuracy_nivel(df_producto, "ZBIGBUSINESS", mes, meses_u6m)
    return _solo_con_accuracy(tabla)


def accuracy_libre_de_gluten(df_producto: pd.DataFrame, df_master: pd.DataFrame, mes: str, meses_u6m: list) -> tuple:
    """``(tabla_skus, indicadores_globales)`` -- ``tabla_skus`` un renglón
    por SKU candidato a Libre de Gluten (para el ranking/narrativa de
    ``texto_destacados``, igual que antes); ``indicadores_globales`` un
    ``dict`` con Accuracy Y Bias (Consensuado/Estadístico) + Cons vs Est
    (U6M incluido) agregando TODOS esos SKU juntos como un solo grupo --
    separado a propósito de ``tabla_skus`` para que ``texto_destacados`` no
    lo tome como "otro SKU más" al rankear líderes/rezagados. Filtro: ver
    heurística de "Libre de Gluten" en el docstring del módulo
    (``LDG_GRANDES_NEGOCIOS`` Y descripción con "LDG"/"GLUTEN")."""
    en_negocio = df_master["ZBIGBUSINESS"].isin(LDG_GRANDES_NEGOCIOS)
    en_descripcion = df_master["PRDDESCR"].astype(str).str.contains("LDG|GLUTEN", case=False, na=False, regex=True)
    skus_ldg = set(df_master.loc[en_negocio & en_descripcion, "PRDID"].astype(str).unique())

    # incluir_bias=True: el usuario notó que el Bias por SKU no aparecía en
    # la tabla del .docx -- faltaba pasarlo acá (2026-09-17).
    tabla_skus = _tabla_accuracy_nivel(df_producto, "PRDID", mes, meses_u6m, filtro_prdid=skus_ldg, incluir_bias=True)
    tabla_skus = _solo_con_accuracy(tabla_skus)
    tabla_skus = tabla_skus.merge(df_master[["PRDID", "PRDDESCR"]].drop_duplicates(), on="PRDID", how="left")

    tabla_total = _tabla_accuracy_nivel(
        df_producto.assign(_Total="Total SKU Libre de Gluten"), "_Total", mes, meses_u6m,
        filtro_prdid=skus_ldg, incluir_bias=True,
    )
    indicadores_globales = {} if tabla_total.empty else tabla_total.iloc[0].to_dict()

    return tabla_skus, indicadores_globales


def accuracy_bias_area(df_producto: pd.DataFrame, area_col: str, mes: str, areas_incluir: list = None) -> tuple:
    """``(tabla_accuracy, tabla_bias)`` -- index ``(ZBIGDIVISION, Métrica)``,
    una columna por valor de ``area_col`` (``ZAREACOMERCIAL`` o ``ZAREAGC``)
    -- mismo shape que ``accuracy_bias_gran_division_historico`` pero con
    área en las columnas en vez de mes. ``areas_incluir``: para "Área Gran
    Cuenta", restringe a ``GRANDES_CUENTAS.keys()`` (ver docstring del
    módulo); ``None`` = todas las áreas presentes."""
    df_mes = df_producto[df_producto["PERIODID3"] == mes]
    if areas_incluir is not None:
        df_mes = df_mes[df_mes[area_col].isin(areas_incluir)]
    if df_mes.empty:
        vacio = pd.DataFrame()
        return vacio, vacio

    group_cols = ["ZBIGDIVISION", area_col]
    acc_cons = acc_bias_consensuado(df_mes, group_cols)
    acc_est = acc_estadistico(df_mes, group_cols)
    bias_est = bias_estadistico(df_mes, group_cols)

    largo_acc = pd.concat([
        acc_est[[*group_cols, "Accuracy"]].assign(Métrica="Fcst Estad.").rename(columns={"Accuracy": "Valor"}),
        acc_cons[[*group_cols, "Accuracy"]].assign(Métrica="Fcst Cons.").rename(columns={"Accuracy": "Valor"}),
    ], ignore_index=True)
    tabla_accuracy = pd.pivot_table(largo_acc, index=["ZBIGDIVISION", "Métrica"], columns=area_col, values="Valor")
    if areas_incluir is not None:
        tabla_accuracy = tabla_accuracy[[a for a in areas_incluir if a in tabla_accuracy.columns]]

    largo_bias = pd.concat([
        bias_est[[*group_cols, "Bias"]].assign(Métrica="Fcst Estad.").rename(columns={"Bias": "Valor"}),
        acc_cons[[*group_cols, "Bias"]].assign(Métrica="Fcst Cons.").rename(columns={"Bias": "Valor"}),
    ], ignore_index=True)
    tabla_bias = pd.pivot_table(largo_bias, index=["ZBIGDIVISION", "Métrica"], columns=area_col, values="Valor")
    if areas_incluir is not None:
        tabla_bias = tabla_bias[[a for a in areas_incluir if a in tabla_bias.columns]]

    return tabla_accuracy, tabla_bias
