# src/generador_reporte_docx.py
"""
Arma el .docx del "Reporte de Resultados" mensual -- mismo layout que el
real (``reports/`` -- logo Molinos, títulos azules, tablas con semáforo de
color, párrafos narrativos entre tablas), pero con **tablas nativas de
Word** en vez de imágenes pegadas desde Excel (así son las del archivo
real, confirmado extrayendo ``word/media/*.png`` del .docx -- ver
CLAUDE.md). Convierte a PDF con ``docx2pdf`` (usa Word instalado
localmente vía COM) -- si no hay Word, ``convertir_a_pdf`` devuelve
``None`` con el motivo, nunca rompe.

Separado de ``reporte_mensual.py``/``reporte_mensual_narrativa.py`` a
propósito -- este módulo es SOLO layout/presentación, no calcula ni
redacta nada.
"""

import io
import os
import tempfile

import pandas as pd
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from src import alertas
from src.charts import BUENO, MEDIO, MALO
from src.config.dynamics_config import root_path

LOGO_PATH = os.path.join(root_path, "assets", "molinos_logo.png")
AZUL_TITULO = RGBColor(0x18, 0x4E, 0x8C)
FUENTE = "Calibri"

_HEX_NIVEL = {"bueno": BUENO.lstrip("#"), "medio": MEDIO.lstrip("#"), "malo": MALO.lstrip("#"), "sin_dato": "FFFFFF"}


def _fuente(run, negrita: bool = None, tamano: Pt = None, color: RGBColor = None) -> None:
    """Fuerza Calibri en el run -- ``run.font.name`` solo no alcanza para
    que Word lo respete siempre (referencia también ``w:eastAsia`` en el
    XML), por eso el ``rFonts`` explícito."""
    run.font.name = FUENTE
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), FUENTE)
    if negrita is not None:
        run.bold = negrita
    if tamano is not None:
        run.font.size = tamano
    if color is not None:
        run.font.color.rgb = color


def _sombrear_celda(cell, hex_color: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


def _texto_celda(cell, texto: str, negrita: bool = False, centrado: bool = True, color_blanco: bool = False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    if centrado:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(texto)
    _fuente(run, negrita=negrita, tamano=Pt(9), color=RGBColor(0xFF, 0xFF, 0xFF) if color_blanco else None)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def _agregar_logo(doc: Document) -> None:
    """Logo en el ENCABEZADO del documento (no en el cuerpo) -- a pedido
    del usuario (2026-09-17), para que el título quede más arriba en vez
    de correrse por un párrafo de imagen en el cuerpo."""
    if not os.path.exists(LOGO_PATH):
        return
    header = doc.sections[0].header
    header.is_linked_to_previous = False  # sin esto Word puede no aplicar el contenido del header de la 1ra sección
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.add_run().add_picture(LOGO_PATH, width=Inches(1.2))


def _titulo_seccion(doc: Document, texto: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(texto)
    _fuente(run, negrita=True, tamano=Pt(13), color=AZUL_TITULO)


def _subtitulo(doc: Document, texto: str) -> None:
    """Subtítulo chico para distinguir dos tablas dentro de una misma
    sección (ej. "Accuracy" / "Bias" en Área Comercial/Gran Cuenta) --
    sin esto las dos tablas quedaban pegadas una contra la otra."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(texto)
    _fuente(run, negrita=True, tamano=Pt(10))


def _parrafo(doc: Document, texto: str) -> None:
    p = doc.add_paragraph(texto)
    p.paragraph_format.space_after = Pt(6)
    for run in p.runs:
        _fuente(run, tamano=Pt(10))


def _bullets(doc: Document, items: list) -> None:
    for item in items:
        p = doc.add_paragraph(item, style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        for run in p.runs:
            _fuente(run, tamano=Pt(10))
    if items:
        doc.paragraphs[-1].paragraph_format.space_after = Pt(8)


def _fijar_ancho_columnas(tabla, anchos: list) -> None:
    """Ancho fijo por columna (``Cm``), en vez del autofit de Word que
    estira la tabla al ancho completo de la página -- en tablas con pocas
    columnas y texto corto eso las deja muy "achatadas" (filas finísimas
    de punta a punta), a pedido del usuario (2026-09-17). Hay que fijar el
    ancho en CADA celda, no solo en ``table.columns[i].width``: Word
    ignora el segundo si las celdas ya tienen un ancho explícito distinto
    (comportamiento conocido de python-docx)."""
    tabla.autofit = False
    for row in tabla.rows:
        for i, ancho in enumerate(anchos):
            if i < len(row.cells):
                row.cells[i].width = ancho
    for i, ancho in enumerate(anchos):
        if i < len(tabla.columns):
            tabla.columns[i].width = ancho


def _espaciador(doc: Document) -> None:
    """Separa un cuadro del siguiente -- sin esto, dos tablas seguidas
    quedan pegadas (visualmente parecen una sola) y el título de la
    siguiente sección queda pegado contra el borde de la tabla anterior."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(10)


UMBRAL_BIAS_EXTREMO = 10.0  # +/-1000% -- por encima/debajo, "<-1000%"/">+1000%" en vez del número (ver _formato_bias)


def _formato_bias(valor: float, capar_extremos: bool) -> str:
    """``+X%`` normal -- si ``capar_extremos`` y el valor supera
    +/-1000% (típico de un Área/Gran Cuenta con Actual casi 0 en el
    denominador del Bias, no un error de cálculo), muestra "< -1000%"/
    "> +1000%" en vez del número real -- a pedido del usuario (2026-09-17),
    los valores exactos ahí no aportan y distraen de las columnas con
    datos representativos."""
    if capar_extremos and valor < -UMBRAL_BIAS_EXTREMO:
        return "< -1000%"
    if capar_extremos and valor > UMBRAL_BIAS_EXTREMO:
        return "> +1000%"
    return f"{valor:+.0%}"


def _tabla_pivot_semaforo(doc: Document, tabla: pd.DataFrame, es_bias: bool = False, capar_extremos: bool = False, compacto: bool = False) -> None:
    """``tabla``: index ``(Gran División, Métrica)``, columnas = meses o
    áreas -- misma forma que ``reporte_mensual.accuracy_bias_gran_division_historico``/
    ``accuracy_bias_area``. Una fila de Word por cada fila de ``tabla``, con
    la primera columna (Gran División) fusionada verticalmente cada 2 filas.

    El texto de la división se escribe SOLO en la primera fila de cada par
    (la segunda queda vacía) -- escribirlo en las dos y recién después
    fusionar duplica el texto ("Alimentos" aparece dos veces apiladas
    dentro de la misma celda, ``cell.merge()`` concatena los párrafos de
    ambas celdas de origen en vez de reemplazarlos). ``capar_extremos``:
    ver ``_formato_bias`` -- usado en Área Comercial/Gran Cuenta (Bodegas y
    Snacks tienen Actual casi 0 en algunas áreas, dispara Bias de miles de
    %), NO en Gran División (ahí no pasa, los totales no se acercan a 0).
    ``compacto``: ancho fijo por columna en vez de autofit (ver
    ``_fijar_ancho_columnas``) -- usado en Área Comercial (2026-09-17, "más
    cuadrada, no tan achatada"), NO en Gran División/Gran Cuenta (no se
    pidió ahí -- Gran Cuenta ya necesita las 12 columnas anchas)."""
    if tabla.empty:
        _parrafo(doc, "Sin datos suficientes para esta tabla.")
        return

    columnas = list(tabla.columns)
    n_cols = 2 + len(columnas)
    t = doc.add_table(rows=1, cols=n_cols)
    t.style = "Table Grid"

    encabezado = t.rows[0].cells
    _texto_celda(encabezado[0], "Gran división", negrita=True)
    _texto_celda(encabezado[1], "Bias" if es_bias else "Accuracy", negrita=True)
    for i, col in enumerate(columnas):
        _texto_celda(encabezado[2 + i], str(col), negrita=True)
    for cell in encabezado:
        _sombrear_celda(cell, "2A78D6")
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    fila_division_anterior = None
    for (division, metrica), valores in tabla.iterrows():
        fila = t.add_row().cells
        if division != fila_division_anterior:
            _texto_celda(fila[0], str(division), negrita=True)
        # si es la 2da fila del par, fila[0] queda vacía a propósito -- se fusiona con la de arriba más abajo
        _texto_celda(fila[1], metrica)
        for i, col in enumerate(columnas):
            valor = valores[col]
            celda = fila[2 + i]
            if pd.isna(valor):
                _texto_celda(celda, "—")
            elif es_bias:
                _texto_celda(celda, _formato_bias(valor, capar_extremos))
                _sombrear_celda(celda, _HEX_NIVEL[alertas.nivel_bias(valor)])
            else:
                _texto_celda(celda, f"{valor:.0%}")
                _sombrear_celda(celda, _HEX_NIVEL[alertas.nivel_accuracy(valor)])
        fila_division_anterior = division

    if compacto:
        _fijar_ancho_columnas(t, [Cm(2.6), Cm(2.3)] + [Cm(2.2)] * len(columnas))

    # Fusiona la columna "Gran división" cada 2 filas (Fcst Estad./Fcst Cons.)
    filas_datos = t.rows[1:]
    i = 0
    while i < len(filas_datos):
        if i + 1 < len(filas_datos):
            filas_datos[i].cells[0].merge(filas_datos[i + 1].cells[0])
        i += 2

    _espaciador(doc)


def _tabla_ranking(doc: Document, tabla: pd.DataFrame, col_nombre: str, etiqueta_nombre: str, col_desc: str = None, fila_total: dict = None) -> None:
    """Tabla plana (no pivot) para Gran Negocio / Libre de Gluten:
    nombre [+ descripción] | Consenso | Estadístico [| Bias Cons. | Bias
    Estad.] | Cons vs Est | Cons vs Est U6M. ``fila_total``: indicadores
    GLOBALES opcionales (ver ``reporte_mensual.accuracy_libre_de_gluten``)
    -- se renderiza como primera fila, en negrita y con las columnas de
    Bias (Gran Negocio no las pasa, así que no aparecen ahí).

    Ancho fijo por columna (2026-09-17, a pedido del usuario): sin
    ``col_desc`` (Gran Negocio) la tabla queda compacta/"más cuadrada" en
    vez de estirada al ancho completo de la página; con ``col_desc``
    (Libre de Gluten) la columna de Descripción queda bien ancha para que
    la descripción del SKU no se parta en varios renglones."""
    if tabla.empty and not fila_total:
        _parrafo(doc, "Sin datos suficientes para esta tabla.")
        return

    mostrar_bias = bool(fila_total) and "Bias Consensuado" in fila_total
    columnas_extra = ([col_desc] if col_desc and col_desc in tabla.columns else [])
    encabezados = [etiqueta_nombre, *[c for c in ["Descripción"] if columnas_extra], "Consenso", "Estadístico"]
    if mostrar_bias:
        encabezados += ["Bias Cons.", "Bias Estad."]
    encabezados += ["Cons vs Est", "Cons vs Est U6M"]
    t = doc.add_table(rows=1, cols=len(encabezados))
    t.style = "Table Grid"
    for i, texto in enumerate(encabezados):
        _texto_celda(t.rows[0].cells[i], texto, negrita=True)
        _sombrear_celda(t.rows[0].cells[i], "2A78D6")
        t.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    def _fila(datos_fila: dict, es_total: bool = False) -> None:
        celdas = t.add_row().cells
        idx = 0
        _texto_celda(celdas[idx], str(datos_fila.get(col_nombre, "Total")), negrita=es_total); idx += 1
        if columnas_extra:
            _texto_celda(celdas[idx], str(datos_fila.get(col_desc, "")), centrado=False, negrita=es_total); idx += 1
        for col in ["Consensuado", "Estadistico"]:
            valor = datos_fila.get(col)
            if pd.isna(valor):
                _texto_celda(celdas[idx], "—", negrita=es_total)
            else:
                _texto_celda(celdas[idx], f"{valor:.0%}", negrita=es_total)
                _sombrear_celda(celdas[idx], _HEX_NIVEL[alertas.nivel_accuracy(valor)])
            idx += 1
        if mostrar_bias:
            for col in ["Bias Consensuado", "Bias Estadistico"]:
                valor = datos_fila.get(col)
                if pd.isna(valor):
                    _texto_celda(celdas[idx], "—", negrita=es_total)
                else:
                    _texto_celda(celdas[idx], f"{valor:+.1%}", negrita=es_total)
                    _sombrear_celda(celdas[idx], _HEX_NIVEL[alertas.nivel_bias(valor)])
                idx += 1
        for col in ["Cons vs Est", "Cons vs Est U6M"]:
            valor = datos_fila.get(col)
            _texto_celda(celdas[idx], f"{valor:+.0f}pp" if pd.notna(valor) else "—", negrita=es_total)
            idx += 1

    if fila_total:
        _fila(fila_total, es_total=True)
    for _, fila in tabla.iterrows():
        _fila(fila.to_dict())

    n_numericas = 2 + (2 if mostrar_bias else 0) + 2  # Consenso/Estadístico [+Bias Cons./Estad.] + Cons vs Est/U6M
    if columnas_extra:
        _fijar_ancho_columnas(t, [Cm(1.4), Cm(7.0)] + [Cm(1.75)] * n_numericas)
    else:
        _fijar_ancho_columnas(t, [Cm(4.0)] + [Cm(2.4)] * n_numericas)

    _espaciador(doc)


def generar_docx(datos: dict) -> bytes:
    """``datos`` -- dict armado por la página (ver ``pages/0_Inicio.py``):
    mes_nombre, mes, anio, mes_anterior, tabla_acc_division, tabla_bias_division,
    texto_acc_division, tabla_negocio, texto_negocio, tabla_ldg,
    indicadores_globales_ldg, tabla_acc_area_comercial, tabla_bias_area_comercial,
    tabla_acc_area_cuenta, tabla_bias_area_cuenta. Devuelve los bytes del
    .docx -- no escribe nada a disco.

    Formato final acordado con el usuario (2026-09-17, ver ``reporte_final.docx``
    que pasó como referencia): Bias Gran División, Libre de Gluten y Área
    Gran Cuenta van SIN texto narrativo/explicativo antes de la tabla (a
    diferencia de Accuracy Gran División y Gran Negocio, que sí llevan
    bullets) -- por eso ``texto_bias_division``/``texto_ldg`` ya no están
    en este dict ni se usan acá."""
    doc = Document()
    doc.styles["Normal"].font.name = FUENTE  # base de todo el documento -- lo que no se toca explícitamente hereda esto

    for seccion in doc.sections:  # márgenes angostos (a pedido del usuario, 2026-09-16) -- las tablas de meses/áreas son anchas
        seccion.top_margin = Cm(1.5)
        seccion.bottom_margin = Cm(1.5)
        seccion.left_margin = Cm(1.3)
        seccion.right_margin = Cm(1.3)

    _agregar_logo(doc)

    titulo = doc.add_heading(f"Reporte de Resultados - Forecast {datos['mes_nombre'].capitalize()} {datos['anio']}", level=1)
    for run in titulo.runs:
        _fuente(run, color=AZUL_TITULO)

    _parrafo(
        doc,
        "A continuación, les compartimos los KPIs del Forecast Estadístico y Consensuado. El Forecast "
        "Estadístico es el pronóstico que generamos con los algoritmos y modelos matemáticos, y el "
        "Consensuado tiene el aporte de los equipos de Marketing, Comercial, Planeamiento, y Supply. "
        "Generado automáticamente desde el Tablero Forecast Demanda IBP.",
    )

    _titulo_seccion(doc, "Accuracy Gran División - Total Molinos")
    _bullets(doc, datos["texto_acc_division"])
    _tabla_pivot_semaforo(doc, datos["tabla_acc_division"])

    _titulo_seccion(doc, "Bias Gran División – Total Molinos")
    _parrafo(
        doc,
        "El Bias mide el desvío del forecast respecto a las entregas reales. Un Bias positivo indica una "
        "sobreestimación, mientras que un Bias negativo refleja una subestimación.",
    )
    _tabla_pivot_semaforo(doc, datos["tabla_bias_division"], es_bias=True)

    _titulo_seccion(doc, "Accuracy Gran Negocio – Total Molinos")
    _bullets(doc, datos["texto_negocio"])
    _tabla_ranking(doc, datos["tabla_negocio"], "ZBIGBUSINESS", "Gran negocio")

    _titulo_seccion(doc, "Accuracy Libre de Gluten – Total Molinos")
    _tabla_ranking(doc, datos["tabla_ldg"], "PRDID", "SKU", col_desc="PRDDESCR", fila_total=datos.get("indicadores_globales_ldg"))

    _titulo_seccion(doc, "Accuracy y Bias Gran División – Área Comercial")
    _subtitulo(doc, "Accuracy")
    _tabla_pivot_semaforo(doc, datos["tabla_acc_area_comercial"], compacto=True)
    _subtitulo(doc, "Bias")
    _tabla_pivot_semaforo(doc, datos["tabla_bias_area_comercial"], es_bias=True, capar_extremos=True, compacto=True)

    _titulo_seccion(doc, "Accuracy y Bias Gran División – Área Gran Cuenta")
    _subtitulo(doc, "Accuracy")
    _tabla_pivot_semaforo(doc, datos["tabla_acc_area_cuenta"])
    _subtitulo(doc, "Bias")
    _tabla_pivot_semaforo(doc, datos["tabla_bias_area_cuenta"], es_bias=True, capar_extremos=True)

    _parrafo(
        doc,
        "Toda la información presentada en este reporte puede consultarse a nivel de cliente, SKU o familia de "
        "productos en el tablero de Forecast Accuracy en la sección de Abastecimiento del CIC",
    )

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def convertir_a_pdf(docx_bytes: bytes) -> tuple:
    """``(pdf_bytes, error)`` -- usa ``docx2pdf`` (Word instalado local vía
    COM). Si falla (sin Word, u otro SO), devuelve ``(None, mensaje)`` en
    vez de romper -- el caller ofrece igual el .docx.

    ``pythoncom.CoInitialize()``/``CoUninitialize()`` explícitos alrededor
    de la conversión -- Streamlit reusa el mismo worker thread entre
    reruns, y ese thread puede quedar con el apartment COM en un estado
    inconsistente después de la primera conversión (visto en vivo:
    ``(-2147221008, 'No se ha llamado a CoInitialize.', ...)`` en el
    SEGUNDO click al botón, no en el primero). Inicializar/desinicializar
    en cada llamada, en vez de confiar en que ``docx2pdf`` ya lo maneja
    internamente, es lo que lo hace repetible."""
    try:
        import pythoncom
        from docx2pdf import convert
    except ImportError as e:
        return None, f"docx2pdf/pywin32 no está instalado: {e}"

    pythoncom.CoInitialize()
    tmp_dir = tempfile.mkdtemp()
    ruta_docx = os.path.join(tmp_dir, "reporte.docx")
    ruta_pdf = os.path.join(tmp_dir, "reporte.pdf")
    try:
        with open(ruta_docx, "wb") as f:
            f.write(docx_bytes)
        convert(ruta_docx, ruta_pdf)
        with open(ruta_pdf, "rb") as f:
            return f.read(), None
    except Exception as e:
        return None, f"No se pudo convertir a PDF (¿Word instalado?): {e}"
    finally:
        for ruta in (ruta_docx, ruta_pdf):
            if os.path.exists(ruta):
                os.unlink(ruta)
        os.rmdir(tmp_dir)
        pythoncom.CoUninitialize()
