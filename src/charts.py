# src/charts.py
"""
Helpers de gráficos (Plotly) reutilizados entre páginas.

Paleta: paleta categórica validada del skill de dataviz (8 tonos, orden fijo
-- nunca reasignar colores por ranking, siempre por identidad de la serie).
Un solo eje siempre (nunca doble eje): dos magnitudes de escala distinta van
en gráficos separados o indexadas a una base común, no combinadas.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]
POSITIVO = "#2a78d6"   # slot 1 (blue) del par divergente
NEGATIVO = "#e34948"   # slot 8 (red) del par divergente
NEUTRO = "#898781"      # tinta muted


def _base_layout(fig: go.Figure, title: str = None) -> go.Figure:
    """``title=None`` NO debe pasarse a ``update_layout(title=...)`` --
    Plotly no lo trata como "sin título" sino que renderiza literalmente el
    texto "undefined" (visto por primera vez en pages/10_Curvas_Backtesting.py,
    la primera página que llama a un chart sin título; el resto de las
    páginas siempre pasaba un título explícito, por eso no había aparecido
    antes)."""
    fig.update_layout(
        colorway=CATEGORICAL,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        hovermode="x unified",
    )
    if title:
        fig.update_layout(title=title)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(137,135,129,0.25)", zeroline=False)
    return fig


def kpi_card(label: str, value, delta=None, help: str = None):
    st.metric(label, value, delta=delta, help=help)


def area_chart_por_tipo(df: pd.DataFrame, x: str, y: str, color: str, title: str = None) -> go.Figure:
    """Area chart apilado por categoría (ej. Tipo: Histórico/Forecast)."""
    fig = px.area(df, x=x, y=y, color=color)
    return _base_layout(fig, title)


def _hex_a_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def area_superpuesta(df: pd.DataFrame, x: str, y: str, color: str, title: str = None) -> go.Figure:
    """
    Áreas SUPERPUESTAS (no apiladas) -- para series que se solapan en el
    tiempo y hay que comparar una contra otra directamente (ej. "Plan Anual"
    vs "Histórico + Forecast", o varias series de "Área Comercial" en
    simultáneo). ``area_chart_por_tipo`` apila, que está bien para categorías
    mutuamente excluyentes (Tipo Histórico/Forecast) pero sumaría mal acá.
    """
    fig = go.Figure()
    for i, categoria in enumerate(df[color].unique()):
        sub = df[df[color] == categoria].sort_values(x)
        c = CATEGORICAL[i % len(CATEGORICAL)]
        fig.add_trace(go.Scatter(
            x=sub[x], y=sub[y], name=str(categoria), mode="lines",
            line=dict(color=c, width=2),
            fill="tozeroy", fillcolor=_hex_a_rgba(c, 0.25),
        ))
    return _base_layout(fig, title)


def line_chart(df: pd.DataFrame, x: str, y: str, color: str = None, title: str = None) -> go.Figure:
    fig = px.line(df, x=x, y=y, color=color, markers=True)
    fig.update_traces(line=dict(width=2))
    return _base_layout(fig, title)


def bar_chart(df: pd.DataFrame, x: str, y: str, color: str = None, title: str = None, orientation: str = "v") -> go.Figure:
    fig = px.bar(df, x=x, y=y, color=color, orientation=orientation)
    fig.update_traces(marker_line_width=0)
    return _base_layout(fig, title)


def pie_chart(df: pd.DataFrame, names: str, values: str, title: str = None) -> go.Figure:
    fig = px.pie(df, names=names, values=values, hole=0.45)
    fig.update_traces(textinfo="label+percent", textposition="outside")
    fig.update_layout(colorway=CATEGORICAL, paper_bgcolor="rgba(0,0,0,0)", showlegend=True, title=title, margin=dict(l=10, r=10, t=40 if title else 10, b=10))
    return fig


def bias_bar_chart(df: pd.DataFrame, x: str, y: str, title: str = None) -> go.Figure:
    """Bar chart divergente (bias +/-): azul para positivo, rojo para negativo."""
    colors = [POSITIVO if v >= 0 else NEGATIVO for v in df[y]]
    fig = go.Figure(go.Bar(x=df[x], y=df[y], marker_color=colors))
    fig.add_hline(y=0, line_color=NEUTRO, line_width=1)
    return _base_layout(fig, title)


def ranking_semaforo(df: pd.DataFrame, y: str, x: str, title: str = None) -> go.Figure:
    """
    Bar chart horizontal ordenado descendente, coloreado en escala continua
    rojo-amarillo-verde según el valor -- réplica del "Accuracy por Cuentas"
    real (semáforo de accuracy, no identidad categórica: acá el color SÍ
    codifica magnitud/status a propósito, como en el Power BI original).

    Escala de color Y de eje X fijas en ``[0, 1]`` (no dinámicas según el
    máximo de ``df``) -- la Accuracy siempre vive en ese rango (ver
    ``src/accuracy.py::_accuracy_ponderada``), y una escala fija es lo que
    permite comparar el semáforo de una división de negocio contra el de
    otra a simple vista (con rango dinámico, un 60% podía pintarse verde en
    un panel y amarillo en el de al lado solo porque el máximo local era
    distinto). El texto va DENTRO de la barra (no afuera) para que no se
    corte contra el borde del panel en valores altos, y las filas sin datos
    (``NaN`` -- Actual=0) muestran "—" en vez de "nan%".

    **Ojo con el dtype de la columna de color**: ``_accuracy_ponderada`` usa
    ``Serie.replace(0, pd.NA)`` para evitar división por cero, y una columna
    float con algún ``pd.NA`` mezclado (a diferencia de ``np.nan``) pasa a
    dtype ``object`` en pandas -- Plotly Express, al ver dtype ``object``,
    trata la columna como CATEGÓRICA aunque ``color_continuous_scale`` esté
    seteado, y en vez de una barra de color continua dibuja una entrada de
    leyenda por cada valor único (con muchas filas, una leyenda gigantesca
    de números sueltos en vez de semáforo). `pd.to_numeric` fuerza de vuelta
    a float64/NaN antes de graficar -- sin este paso el bug aparece con
    cualquier fila sin datos (Actual=0), no hace falta que sean muchas.
    """
    df = df.sort_values(x, ascending=True).copy()  # ascendente para que barh quede de mayor a menor de arriba a abajo
    df[x] = pd.to_numeric(df[x], errors="coerce").clip(lower=0, upper=1)
    etiquetas = df[x].map(lambda v: f"{v:.1%}" if pd.notna(v) else "—")
    fig = px.bar(
        df, x=x, y=y, orientation="h",
        color=x, color_continuous_scale="RdYlGn", range_color=[0, 1],
        text=etiquetas,
    )
    fig.update_traces(textposition="inside", insidetextanchor="end", marker_line_width=0)
    fig.update_coloraxes(showscale=False)
    altura = max(220, 34 * len(df) + 60)
    fig = _base_layout(fig, title)
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=40 if title else 10, b=10))
    fig.update_xaxes(tickformat=".0%", range=[0, 1])
    return fig


def pivot_table(df: pd.DataFrame, index, columns, values, aggfunc="sum") -> pd.DataFrame:
    """Wrapper fino sobre pandas.pivot_table para las tablas tipo matrix de Power BI."""
    if df.empty:
        return pd.DataFrame()
    return pd.pivot_table(df, index=index, columns=columns, values=values, aggfunc=aggfunc, fill_value=0)
