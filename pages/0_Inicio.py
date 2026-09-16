# pages/0_Inicio.py
"""
Landing page + gate de carga de datos.

Mientras ``st.session_state["datos_cargados"]`` no sea True, ``app.py`` solo
registra esta página en ``st.navigation`` -- el resto de las páginas ni
siquiera aparecen en el sidebar (no solo están "escondidas", no son
alcanzables). Acá se precargan todas las fuentes de ``src/preload.py`` una
sola vez; como quedan en el cache de Streamlit, cuando el usuario entra
después a cada página no dispara ninguna consulta nueva.
"""

import pandas as pd
import streamlit as st

from src import alertas, cache, charts, filters
from src import generador_reporte_docx as gendoc
from src import reporte_mensual as rm
from src import reporte_mensual_narrativa as narr
from src.accuracy import acc_bias_consensuado, acc_estadistico
from src.config.settings import ibp_configurado, athena_configurado
from src.data import demo_data
from src.preload import FUENTES
from src.utils.listas_periodos import periodid3_a_fecha, periodos_historicos_mes, periodos_futuros_mes, periodos_terminando_en

st.title("Forecast Demanda IBP")
st.caption("Réplica funcional de los tableros Power BI: Forecast IBP y Forecast Accuracy IBP")

if "datos_cargados" not in st.session_state:
    st.session_state["datos_cargados"] = False
    st.session_state["carga_estado"] = {}

if not st.session_state["datos_cargados"]:
    st.info(
        "Cargando datos desde SAP IBP / AWS Athena antes de habilitar la navegación. "
        "La primera carga puede tardar varios minutos (después queda cacheada 30 min).",
        icon="⏳",
    )

    progreso = st.progress(0.0)
    tabla = st.empty()
    estados = {nombre: "⏳ Pendiente" for nombre, _, _ in FUENTES}

    def _refrescar():
        tabla.table({"Fuente": list(estados.keys()), "Estado": list(estados.values())})

    _refrescar()

    from src.cache import get_or_demo  # import local: evita ciclos al cargar la página

    for i, (nombre, get_fn, demo_fn) in enumerate(FUENTES):
        estados[nombre] = "🔄 Consultando..."
        _refrescar()
        _, es_demo, error = get_or_demo(get_fn, demo_fn)
        estados[nombre] = "🧪 Demo (sin conexión real)" if es_demo else "✅ Cargado"
        _refrescar()
        progreso.progress((i + 1) / len(FUENTES))

    st.session_state["datos_cargados"] = True
    st.session_state["carga_estado"] = dict(estados)
    st.rerun()

else:
    st.success("Datos cargados. Navegá a cualquier página desde el sidebar.", icon="✅")

    st.divider()
    st.subheader("Resumen ejecutivo")

    # Todo esto reusa el cache ya tibio de FUENTES de arriba -- no dispara
    # ninguna consulta nueva a SAP/Athena, solo agrega sobre lo ya cargado.
    df_producto, _, _ = cache.get_or_demo(cache.get_forecast_vs_actual_producto, demo_data.forecast_vs_actual_producto_demo)
    df_ancho, _, _ = cache.get_or_demo(cache.get_historico_y_forecast_ancho, demo_data.historico_y_forecast_ancho_demo)
    df_plan, _, _ = cache.get_or_demo(cache.get_plan_anual, demo_data.plan_anual_demo)

    anio_actual = pd.Timestamp.today().year

    # Último mes CERRADO (con venta real, excluye el mes en curso) -- a
    # pedido del usuario, Accuracy/Segmento del resumen ejecutivo van a un
    # único mes puntual (no una ventana de varios meses como el default de
    # "Meses a analizar" del sidebar de Accuracy), igual que el "Reporte de
    # Resultados" mensual real ("En agosto, Alimentos terminó con..." -- un
    # solo mes, no un rolling window).
    mes_actual = periodos_futuros_mes(1)[0]
    mes_ultimo_cerrado = None
    if not df_producto.empty and "Actual" in df_producto.columns:
        meses_con_venta = sorted(df_producto.loc[df_producto["Actual"] > 0, "PERIODID3"].dropna().unique(), key=periodid3_a_fecha)
        meses_cerrados = [m for m in meses_con_venta if m != mes_actual]
        if meses_cerrados:
            mes_ultimo_cerrado = meses_cerrados[-1]
        elif meses_con_venta:
            mes_ultimo_cerrado = meses_con_venta[-1]

    st.caption(
        f"Accuracy y SKU en Segmento crítico: **{mes_ultimo_cerrado or '—'}** (último mes cerrado) · "
        f"Ventas vs. Plan Anual: acumulado **{anio_actual}** (YTD)"
    )

    meses_hist = periodos_historicos_mes(cache.MESES_HISTORICOS)

    def _resumen_division(division: str) -> dict:
        fila = {"Gran División": division, "Accuracy Estadístico": float("nan"), "Accuracy Consensuado": float("nan"),
                "Ventas vs. Plan Anual YTD": float("nan"), "SKU en Segmento crítico (3.2)": 0}

        if not df_producto.empty and "ZBIGDIVISION" in df_producto.columns and mes_ultimo_cerrado:
            df_mes_div = df_producto[(df_producto["ZBIGDIVISION"] == division) & (df_producto["PERIODID3"] == mes_ultimo_cerrado)]
            if not df_mes_div.empty:
                df_mes_div_total = df_mes_div.assign(_Total="Total")
                r_cons = acc_bias_consensuado(df_mes_div_total, ["_Total"])
                if not r_cons.empty:
                    fila["Accuracy Consensuado"] = float(r_cons.iloc[0]["Accuracy"])
                r_est = acc_estadistico(df_mes_div_total, ["_Total"])
                if not r_est.empty:
                    fila["Accuracy Estadístico"] = float(r_est.iloc[0]["Accuracy"])
                tabla_seg_div = cache.calcular_tabla_segmentacion(df_mes_div)
                fila["SKU en Segmento crítico (3.2)"] = int((tabla_seg_div["Segmento"] == "3.2").sum())

        if not df_ancho.empty and not df_plan.empty and "ZBIGDIVISION" in df_ancho.columns:
            df_ancho_div = df_ancho[df_ancho["ZBIGDIVISION"] == division]
            es_pasado = df_ancho_div["PERIODID3"].isin(meses_hist)
            df_hf_anio = pd.concat([
                df_ancho_div.loc[es_pasado & (df_ancho_div["Date"].dt.year == anio_actual), ["ADJUSTEDACTUALSQTY"]].rename(columns={"ADJUSTEDACTUALSQTY": "Valor"}),
                df_ancho_div.loc[~es_pasado & (df_ancho_div["Date"].dt.year == anio_actual), ["DEMANDPLANNINGQTY"]].rename(columns={"DEMANDPLANNINGQTY": "Valor"}),
            ], ignore_index=True)
            total_hf_anio = df_hf_anio["Valor"].sum()
            df_plan_div = df_plan[df_plan["ZBIGDIVISION"] == division]
            total_plan_anio = df_plan_div.loc[df_plan_div["Date"].dt.year == anio_actual, "PLANANUAL"].sum()
            fila["Ventas vs. Plan Anual YTD"] = (total_hf_anio / total_plan_anio - 1) if total_plan_anio else float("nan")

        return fila

    tabla_resumen = pd.DataFrame([_resumen_division(d) for d in filters.GRANDES_DIVISIONES_VALIDAS])

    st.dataframe(
        tabla_resumen.style.format(
            {
                "Accuracy Estadístico": "{:.1%}", "Accuracy Consensuado": "{:.1%}",
                "Ventas vs. Plan Anual YTD": "{:+.1%}",
            },
            na_rep="—",
        )
        .pipe(alertas.aplicar_semaforo_accuracy, columnas=["Accuracy Estadístico", "Accuracy Consensuado"])
        .map(lambda v: f"background-color: {charts.hex_a_rgba(charts.MALO, 0.22)}" if pd.notna(v) and v > 0 else "", subset=["SKU en Segmento crítico (3.2)"]),
        width="stretch",
        hide_index=True,
    )

    alertas_criticas = []
    for _, fila in tabla_resumen.iterrows():
        if alertas.nivel_accuracy(fila["Accuracy Consensuado"]) == "malo":
            alertas_criticas.append(f"{fila['Gran División']}: Accuracy Consensuado por debajo del 70%")
        if alertas.nivel_brecha(fila["Ventas vs. Plan Anual YTD"]) == "malo":
            alertas_criticas.append(f"{fila['Gran División']}: Ventas YTD por debajo del -15% vs. Plan Anual")
        if fila["SKU en Segmento crítico (3.2)"] > 0:
            alertas_criticas.append(f"{fila['Gran División']}: {fila['SKU en Segmento crítico (3.2)']} SKU en Segmento 3.2 (crítico)")

    if alertas_criticas:
        st.warning("🔴 " + " · ".join(alertas_criticas), icon="⚠️")
    else:
        st.success("🟢 Ningún indicador clave por debajo de umbral crítico.", icon="✅")

    st.divider()
    st.subheader("📄 Reporte de Resultados")
    st.caption(
        "Genera automáticamente el mismo documento mensual que se arma a mano (Accuracy/Bias por Gran "
        "División -- 12 meses de historial --, Gran Negocio, Libre de Gluten, Área Comercial y Gran "
        "Cuenta), anclado al último mes cerrado."
    )

    if st.button("📄 Generar reporte detallado", disabled=mes_ultimo_cerrado is None):
        with st.spinner(f"Armando el reporte de {mes_ultimo_cerrado}..."):
            df_master, _, _ = cache.get_or_demo(cache.get_product_master, demo_data.producto_master_demo)

            # "Área Comercial" no es nativo de df_producto (viene a grano
            # ZAREAGC) -- mismo merge que usa el resto de las páginas
            # (cache.mapa_area_comercial), nunca el maestro de clientes
            # completo sin colapsar (fan-out, ver docstring de esa función).
            df_customer_master, _, _ = cache.get_or_demo(cache.get_customer_master, demo_data.customer_master_demo)
            df_producto_area = df_producto
            if "ZAREACOMERCIAL" in df_customer_master.columns:
                mapa_area = cache.mapa_area_comercial(df_customer_master)
                df_producto_area = df_producto.merge(mapa_area, on="ZAREAGC", how="left")

            mes_anterior = periodos_terminando_en(2, mes_ultimo_cerrado)[0]
            meses_12 = periodos_terminando_en(12, mes_ultimo_cerrado)
            meses_u6m = periodos_terminando_en(6, mes_ultimo_cerrado)

            tabla_acc_division, tabla_bias_division = rm.accuracy_bias_gran_division_historico(df_producto, meses_12)
            tabla_negocio = rm.accuracy_gran_negocio(df_producto, mes_ultimo_cerrado, meses_u6m)
            tabla_ldg, indicadores_globales_ldg = rm.accuracy_libre_de_gluten(df_producto, df_master, mes_ultimo_cerrado, meses_u6m)
            df_producto_area_comercial = df_producto_area[~df_producto_area["ZAREACOMERCIAL"].isin(rm.AREA_COMERCIAL_EXCLUIR)]
            tabla_acc_area_comercial, tabla_bias_area_comercial = rm.accuracy_bias_area(df_producto_area_comercial, "ZAREACOMERCIAL", mes_ultimo_cerrado)
            tabla_acc_area_comercial = tabla_acc_area_comercial.rename(columns=rm.AREA_COMERCIAL_ABREVIATURAS)
            tabla_bias_area_comercial = tabla_bias_area_comercial.rename(columns=rm.AREA_COMERCIAL_ABREVIATURAS)

            tabla_acc_area_cuenta, tabla_bias_area_cuenta = rm.accuracy_bias_area(df_producto, "ZAREAGC", mes_ultimo_cerrado, areas_incluir=list(rm.GRANDES_CUENTAS.keys()))
            tabla_acc_area_cuenta = tabla_acc_area_cuenta.rename(columns=rm.GRANDES_CUENTAS)
            tabla_bias_area_cuenta = tabla_bias_area_cuenta.rename(columns=rm.GRANDES_CUENTAS)

            datos_reporte = {
                "mes": mes_ultimo_cerrado,
                "mes_nombre": narr.nombre_mes(mes_ultimo_cerrado),
                "anio": narr.anio_mes(mes_ultimo_cerrado),
                "mes_anterior": mes_anterior,
                "tabla_acc_division": tabla_acc_division,
                "tabla_bias_division": tabla_bias_division,
                "texto_acc_division": narr.texto_accuracy_gran_division(tabla_acc_division, mes_ultimo_cerrado, mes_anterior),
                "tabla_negocio": tabla_negocio,
                "texto_negocio": narr.texto_destacados(tabla_negocio, "ZBIGBUSINESS", nombre_seccion="los Grandes Negocios", incluir_rezagados=False),
                "tabla_ldg": tabla_ldg,
                "indicadores_globales_ldg": indicadores_globales_ldg,
                "tabla_acc_area_comercial": tabla_acc_area_comercial,
                "tabla_bias_area_comercial": tabla_bias_area_comercial,
                "tabla_acc_area_cuenta": tabla_acc_area_cuenta,
                "tabla_bias_area_cuenta": tabla_bias_area_cuenta,
            }

            docx_bytes = gendoc.generar_docx(datos_reporte)
            pdf_bytes, error_pdf = gendoc.convertir_a_pdf(docx_bytes)

        nombre_archivo = f"Reporte Accuracy & Bias - {datos_reporte['mes_nombre'].capitalize()} {datos_reporte['anio']}"
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button("⬇️ Descargar .docx", data=docx_bytes, file_name=f"{nombre_archivo}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with col_dl2:
            if pdf_bytes:
                st.download_button("⬇️ Descargar .pdf", data=pdf_bytes, file_name=f"{nombre_archivo}.pdf", mime="application/pdf")
            else:
                st.caption(f"⚠️ PDF no disponible: {error_pdf}")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 Tablero Forecast IBP")
        st.write("Histórico de ventas, forecast, plan anual y propuestas FCST.")
        st.page_link("pages/1_Historico_de_ventas.py", label="Histórico de ventas", icon="📈")
        st.page_link("pages/2_Forecast.py", label="Forecast", icon="🔮")
        st.page_link("pages/3_Plan_Anual.py", label="Plan Anual", icon="🗓️")
        st.page_link("pages/4_Propuestas_FCST.py", label="Propuestas FCST", icon="📝")

    with col2:
        st.subheader("🎯 Tablero Forecast Accuracy IBP")
        st.write("Accuracy/bias del forecast, segmentación de SKU y ranking de clientes.")
        st.page_link("pages/5_Reporte_Accuracy.py", label="Reporte Accuracy", icon="✅")
        st.page_link("pages/6_Segmentacion_SKU.py", label="Segmentación SKU", icon="🧩")
        st.page_link("pages/7_Ranking_Clientes.py", label="Ranking Clientes", icon="🏆")
        st.page_link("pages/8_Glosario.py", label="Glosario", icon="📖")

    st.divider()
    with st.expander("📋 Estado de la última carga"):
        for nombre, estado in st.session_state["carga_estado"].items():
            st.write(f"{estado} — {nombre}")

    if st.button("🔄 Recargar datos", help="Vuelve a consultar SAP IBP/Athena desde cero (limpia el cache)."):
        st.cache_data.clear()
        st.session_state["datos_cargados"] = False
        st.rerun()

    st.divider()
    with st.expander("⚙️ Configuración de conexión"):
        st.write(f"SAP IBP (OData): {'✅ configurado' if ibp_configurado() else '❌ falta completar ibp.env'}")
        st.write(f"AWS Athena (Data Lake): {'✅ configurado' if athena_configurado() else '❌ falta completar aws.env'}")
        st.caption("Ver .env.example para los nombres de variables esperados.")
