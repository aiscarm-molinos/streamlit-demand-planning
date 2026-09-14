# src/filters.py
"""
Filtros compartidos en el sidebar (equivalentes a los slicers de Power BI).

Dos sidebars distintos, cada uno agrupado en secciones "Período"/"Clientes"/
"Productos" (mismo criterio visual en los dos tableros, según las capturas
`forecast-ibp-*.png` y `forecast-accuracy-*.png`), pero con distinto set de
filtros por sección -- son sidebars reales distintos en el Power BI, no una
inconsistencia:

- ``render_sidebar_filters``: Tablero Forecast IBP (páginas 1-4) -- Período
  (Año, Mes), Clientes, Productos.
- ``render_sidebar_accuracy``: Tablero Forecast Accuracy IBP (páginas 5-7) --
  Período (multiselect de meses, no Año/Mes -- ver más abajo), Clientes,
  Productos.

**"Clientes" y "Productos" son EXACTAMENTE los mismos filtros en los dos
tableros** (``FILTROS_IBP_CLIENTES``/``FILTROS_IBP_PRODUCTOS``, reutilizados
por las dos funciones -- 2026-09-14, a pedido del usuario: antes Accuracy
tenía un subconjunto más chico -- sin Customer Group/Negocio/Demand
Family/Product ID -- calcado de lo que mostraban sus capturas reales, pero
el usuario prefirió consistencia entre tableros por sobre fidelidad pixel a
pixel acá). Lo único que sigue siendo distinto entre los dos sidebars es la
sección "Período" (Año+Mes vs. multiselect de meses -- ver
``render_sidebar_accuracy``), que es una diferencia funcional real (U4M
dinámico) y no un límite de filtros de dimensión.

En los dos, "Gran División" NO es un multiselect más -- es un selectbox
obligatorio (siempre hay una división elegida, nunca "Todas"), restringido a
``GRANDES_DIVISIONES_VALIDAS`` (Alimentos/Bodegas/Snacks, default
"Alimentos") -- ver `_selectbox_gran_division`. Ranking Clientes es la única
página que lo desactiva (``incluir_gran_division=False``) porque necesita
ver las 3 divisiones a la vez.

**Filtros en cascada (2026-09-14, a pedido del usuario)**: dentro de cada
sección ("Clientes", "Productos"), cada filtro solo ofrece las opciones que
efectivamente aparecen en el DataFrame ya recortado por los filtros
ANTERIORES de esa misma sección, en el orden en que están listados en
``FILTROS_IBP_CLIENTES``/``FILTROS_IBP_PRODUCTOS``/etc. (que sigue el orden
real de la jerarquía -- Gran División > Gran Negocio > Negocio > Demand
Family > Familia > Product ID; Area Comercial > Area/GC > Customer Group).
Ej.: elegir "Mayoristas" en Area Comercial deja en Area/GC SOLO las Área/GC
ligadas a Mayoristas -- antes cada multiselect calculaba sus opciones sobre
el DataFrame completo, sin mirar qué habían elegido los filtros de arriba.
Ver ``_multiselects``. "Categoria" (grupo_material_3, de Athena) queda en la
cascada de Productos en su posición de siempre (entre Familia y Product ID)
aunque no sea parte de la jerarquía SAP -- no hay problema en que la
cascada pase por ahí también.

Cada página llama a la función que corresponda con su propio DataFrame ya
cargado (los filtros ofrecidos son los que tengan sentido para las columnas
presentes en ese df) y después ``apply_filters(df, filtros)`` para
recortarlo. Todo corre en memoria sobre datos ya cacheados (ver
``src/cache.py``) -- no dispara consultas nuevas a SAP IBP/Athena.
"""

import pandas as pd
import streamlit as st

from src.accuracy import MESES_ANALISIS_DEFAULT
from src.utils.listas_periodos import periodid3_a_fecha, periodos_terminando_en, periodos_futuros_mes

# Únicas 3 Grandes Divisiones de negocio válidas -- a pedido del usuario, la
# app nunca debe traer/mostrar ninguna otra (ej. "MP, Semi y Subproductos",
# que aparece en la jerarquía real de SAP pero no es una división de negocio
# operativa a efectos de este análisis). "Gran División" por eso NO es un
# multiselect más de `FILTROS_IBP_PRODUCTOS`/`FILTROS_ACCURACY_PRODUCTOS` --
# es un selectbox de una sola opción, siempre con un valor elegido (default
# "Alimentos"), manejado aparte por `_selectbox_gran_division`.
GRANDES_DIVISIONES_VALIDAS = ["Alimentos", "Bodegas", "Snacks"]
GRAN_DIVISION_DEFAULT = "Alimentos"

FILTROS_IBP_CLIENTES = [
    ("Area Comercial", "ZAREACOMERCIAL"),
    ("Area/GC", "ZAREAGC"),
    ("Customer Group", "CUSTGROUP"),
]
FILTROS_IBP_PRODUCTOS = [
    ("Gran Negocio", "ZBIGBUSINESS"),
    ("Negocio", "ZBRAND"),
    ("Demand Family", "ZDEMFAMILY"),
    ("Familia", "PRDFAMILY"),
    ("Categoria", "Categoria"),
    ("Product ID", "PRDID"),
]

# Jerarquía real de producto, de más agregado a más desagregado -- usada por
# ``nivel_producto_mas_desagregado`` para el banner "Gran División: X" /
# "Familia: X" de las páginas del Tablero Forecast IBP (Categoria queda
# afuera a propósito: no es un nivel de la jerarquía SAP, es una
# clasificación aparte de Athena, cruzada con la jerarquía, no anidada en
# ella -- no tiene un lugar único en este orden agregado→desagregado).
JERARQUIA_PRODUCTO = [
    ("Gran División", "ZBIGDIVISION"),
    ("Gran Negocio", "ZBIGBUSINESS"),
    ("Negocio", "ZBRAND"),
    ("Demand Family", "ZDEMFAMILY"),
    ("Familia", "PRDFAMILY"),
    ("Product ID", "PRDID"),
]


def nivel_producto_mas_desagregado(filtros: dict) -> str | None:
    """
    "Gran División: Alimentos" o "Familia: X, Y" -- recorre
    ``JERARQUIA_PRODUCTO`` de más desagregado a más agregado y devuelve
    "Etiqueta: valores" del primer nivel con una selección explícita en
    ``filtros`` (el usuario eligió algo puntual ahí, no "todas"). "Gran
    División" es la única que SIEMPRE tiene un valor (selectbox
    obligatorio), así que esta función siempre devuelve algo si `filtros`
    viene de `render_sidebar_filters`/`render_sidebar_accuracy` -- ``None``
    solo si ni siquiera eso está (df sin la columna, ej. df vacío).
    """
    for label, col in reversed(JERARQUIA_PRODUCTO):
        valores = filtros.get(col)
        if valores:
            return f"{label}: {', '.join(str(v) for v in valores)}"
    return None


def _selectbox_gran_division(df: pd.DataFrame, key_prefix: str, seleccion: dict) -> str | None:
    """
    "Gran División" SIEMPRE con un valor elegido (nunca "Todas") y una sola
    selección a la vez -- default "Alimentos". Restringido a
    ``GRANDES_DIVISIONES_VALIDAS``: si el DataFrame trae alguna otra división
    (ej. "MP, Semi y Subproductos"), ni siquiera aparece como opción, así que
    ``apply_filters`` la excluye de por sí en cuanto este filtro se aplica
    (que es siempre, al ser obligatorio).

    Devuelve la división elegida (o ``None`` si no hay columna/opciones) --
    el caller la usa para recortar el DataFrame ANTES de armar el resto de
    los filtros de "Productos" (cascada, ver docstring del módulo).
    """
    if "ZBIGDIVISION" not in df.columns:
        return None
    opciones = [d for d in GRANDES_DIVISIONES_VALIDAS if d in df["ZBIGDIVISION"].dropna().unique()]
    if not opciones:
        return None
    index_default = opciones.index(GRAN_DIVISION_DEFAULT) if GRAN_DIVISION_DEFAULT in opciones else 0
    elegida = st.selectbox("Gran División", opciones, index=index_default, key=f"{key_prefix}_ZBIGDIVISION")
    seleccion["ZBIGDIVISION"] = [elegida]
    return elegida


def _con_ano_mes(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns and not df.empty:
        df = df.copy()
        df["Año"] = df["Date"].dt.year
        df["Mes"] = df["Date"].dt.month
    return df


def _multiselects(df: pd.DataFrame, config: list, key_prefix: str, seleccion: dict) -> None:
    """
    En cascada: cada filtro de ``config`` recorta ``df`` antes de calcular
    las opciones del SIGUIENTE de la lista -- elegir "Mayoristas" en Area
    Comercial dejaría en Area/GC solo las Área/GC que en el DataFrame
    filtrado a Mayoristas tengan al menos una fila (ver docstring del
    módulo). El orden de ``config`` importa: tiene que ir de más agregado a
    más desagregado.
    """
    for label, col in config:
        if col not in df.columns:
            continue
        opciones = sorted(df[col].dropna().unique().tolist())
        if not opciones:
            continue
        elegido = st.multiselect(label, opciones, default=[], key=f"{key_prefix}_{col}")
        if elegido:
            seleccion[col] = elegido
            df = df[df[col].isin(elegido)]


def render_sidebar_filters(df: pd.DataFrame, key_prefix: str = "", anio_default: list = None) -> dict:
    """
    Sidebar del Tablero Forecast IBP -- 3 secciones "Período" (Año, Mes),
    "Clientes" y "Productos" (ver capturas `forecast-ibp-*.png`: el Power BI
    real pone Año/Mes como slicers arriba del contenido en vez de en el
    sidebar, pero acá quedan en el sidebar bajo "Período" por consistencia
    con el resto de la app -- Streamlit no tiene un lugar natural para
    "slicers de página" fuera del sidebar).

    ``anio_default``: año preseleccionado en el slider "Año" -- una lista de
    un elemento por compatibilidad con el llamador (`[año]`), colapsa el
    rango a ese único año (default ``None`` = rango completo, como en la
    mayoría de las páginas). Usado por "Plan Anual" (año en curso) -- las
    páginas que no lo necesitan no tienen que pasarlo.
    """
    if df.empty:
        return {}

    df = _con_ano_mes(df)
    seleccion: dict = {}

    with st.sidebar:
        if "Año" in df.columns or "Mes" in df.columns:
            st.subheader("Período")
        if "Año" in df.columns:
            anios = sorted(df["Año"].dropna().unique().tolist())
            if len(anios) > 1:
                anio_min, anio_max = anios[0], anios[-1]
                default_range = (
                    (anio_default[0], anio_default[0])
                    if anio_default and anio_default[0] in anios
                    else (anio_min, anio_max)
                )
                rango = st.slider("Año", min_value=anio_min, max_value=anio_max, value=default_range, key=f"{key_prefix}_Año")
                elegido = [a for a in anios if rango[0] <= a <= rango[1]]
                if len(elegido) < len(anios):
                    seleccion["Año"] = elegido
        if "Mes" in df.columns:
            meses = sorted(df["Mes"].dropna().unique().tolist())
            elegido = st.multiselect("Mes", meses, default=[], key=f"{key_prefix}_Mes")
            if elegido:
                seleccion["Mes"] = elegido

        st.subheader("Clientes")
        _multiselects(df, FILTROS_IBP_CLIENTES, key_prefix, seleccion)

        st.subheader("Productos")
        division = _selectbox_gran_division(df, key_prefix, seleccion)
        df_productos = df[df["ZBIGDIVISION"] == division] if division else df
        _multiselects(df_productos, FILTROS_IBP_PRODUCTOS, key_prefix, seleccion)

    return seleccion


def render_sidebar_accuracy(df: pd.DataFrame, key_prefix: str, incluir_gran_division: bool = True) -> tuple[dict, list]:
    """
    Sidebar agrupado del Tablero Forecast Accuracy IBP -- devuelve
    ``(filtros, meses_analisis)``: ``filtros`` para pasar a ``apply_filters``
    (igual que ``render_sidebar_filters``) y ``meses_analisis`` (lista de
    PERIODID3 elegidos en "Período", ORDENADA cronológicamente -- lista
    vacía si no hay ningún mes con ``Actual > 0`` o el usuario no eligió
    ninguno).

    A diferencia de una ventana fija "últimos N meses cerrados", acá el
    usuario elige DIRECTAMENTE qué meses entran en el análisis (multiselect,
    no un único mes ancla) -- Accuracy/Bias ponderado en las 3 páginas se
    recalculan sobre exactamente esos meses, sean cuantos sean. Por default
    vienen preseleccionados los últimos ``MESES_ANALISIS_DEFAULT`` meses
    CERRADOS (el mes en curso NUNCA viene preseleccionado, aunque ya tenga
    algo de ``Actual`` parcial acumulado y por eso aparezca en
    ``meses_disponibles`` -- el usuario puede agregarlo a mano si quiere,
    pero por default el análisis arranca del último mes ya cerrado), pero
    agregar o sacar meses del multiselect cambia el cálculo al toque.

    ``meses_analisis`` se calcula sobre TODO ``df`` (no sobre el resultado de
    aplicar ``filtros``) para poder dibujar la sección "Período" primero, en
    el mismo orden que la captura real -- a diferencia de la versión anterior
    de estas páginas, que calculaba la lista de meses disponibles DESPUÉS de
    aplicar Cliente/Producto (el sidebar genérico se declara completo antes
    de poder filtrar, así que no hay forma de mantener ese orden de cálculo Y
    mostrar "Período" arriba a la vez). Si los meses elegidos no tienen datos
    para el resto de los filtros, las páginas ya manejan ese caso
    (``df_meses.empty`` -> warning).

    ``incluir_gran_division``: ``False`` en "Ranking Clientes" -- esa página
    ya muestra las 3 Grandes Divisiones válidas simultáneamente (una columna
    por división), así que un selectbox de una sola división no tendría
    sentido ahí (ver `7_Ranking_Clientes.py`, que arma su propio recorte a
    ``GRANDES_DIVISIONES_VALIDAS`` en vez de depender de este filtro).
    """
    if df.empty:
        return {}, []

    seleccion: dict = {}
    meses_analisis: list = []

    with st.sidebar:
        st.subheader("Período")
        if "Actual" in df.columns:
            meses_disponibles = sorted(df.loc[df["Actual"] > 0, "PERIODID3"].dropna().unique(), key=periodid3_a_fecha)
            if meses_disponibles:
                mes_actual = periodos_futuros_mes(1)[0]
                meses_cerrados = [m for m in meses_disponibles if m != mes_actual]
                ancla = meses_cerrados[-1] if meses_cerrados else meses_disponibles[-1]
                default_ = [m for m in periodos_terminando_en(MESES_ANALISIS_DEFAULT, ancla) if m in meses_disponibles]
                elegidos = st.multiselect(
                    "Meses a analizar", meses_disponibles, default=default_,
                    key=f"{key_prefix}_MesesAnalisis",
                    help="Accuracy y Bias ponderado se calculan sobre estos meses -- agregá o sacá meses libremente.",
                )
                meses_analisis = sorted(elegidos, key=periodid3_a_fecha)

        st.subheader("Clientes")
        _multiselects(df, FILTROS_IBP_CLIENTES, key_prefix, seleccion)

        st.subheader("Productos")
        division = _selectbox_gran_division(df, key_prefix, seleccion) if incluir_gran_division else None
        df_productos = df[df["ZBIGDIVISION"] == division] if division else df
        _multiselects(df_productos, FILTROS_IBP_PRODUCTOS, key_prefix, seleccion)

    return seleccion, meses_analisis


def apply_filters(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    if df.empty or not filtros:
        return df

    df = _con_ano_mes(df)
    mask = pd.Series(True, index=df.index)
    for col, valores in filtros.items():
        if col in df.columns:
            mask &= df[col].isin(valores)
    return df[mask]
