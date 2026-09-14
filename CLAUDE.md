# CLAUDE.md — streamlit-demanda

Contexto para asistentes de IA que trabajen en este repositorio. Léelo antes de proponer o aplicar cambios.

## Qué es este proyecto

App Streamlit que replica funcionalmente dos tableros de Power BI de SAP IBP (Molinos):
- **Tablero Forecast IBP**: Histórico de ventas, Forecast, Plan Anual, Propuestas FCST.
- **Tablero Forecast Accuracy IBP**: Reporte Accuracy, Segmentación SKU, Ranking Clientes, Glosario.

No es una réplica visual pixel-perfect — es funcional (mismos filtros, mismos números, gráficos con Plotly en vez de Power BI). Corre **local**, conectada **en vivo** a SAP IBP (OData) y AWS Athena (Data Lake). Los dos `.pbix` originales quedan en la raíz del repo como referencia.

**Fuente de verdad de este documento**: las queries M (Power Query) reales de ambos tableros, pasadas por el usuario en `tablas_forecast_ibp.txt` y `tablas_forecast_accuracy_ibp.txt` (raíz del repo) — **no están gitignoreadas a propósito, son documentación**. Antes de asumir un key figure, UOM o filtro por analogía con otro repo Molinos, mirar esos dos archivos primero: son lo que Power BI realmente ejecuta contra SAP, no una inferencia.

**Fuente de verdad del diseño del "Tablero Forecast Accuracy IBP"** (páginas 5/6/7): el informe `Reporte – Ranking Forecast Accuracy.docx` (raíz del repo, no gitignoreado) explica la metodología de negocio (ventana U4M, criterio de segmentación, escenarios de proyección), y las capturas `forecast-accuracy-*.png` (raíz del repo) muestran el layout real del Power BI actual. El docx es el documento de diseño que precedió al tablero ("durante el mes en curso se trabajará en desarrollar un tablero de Power BI...") -- ante cualquier duda entre el docx y las capturas, **las capturas ganan** (son "cómo se ve hoy", el docx puede tener detalle que no se terminó de implementar o cambió).

**Fuente de verdad del diseño del "Tablero Forecast IBP"** (páginas 1-4): las capturas `forecast-ibp-*.png` (raíz del repo) -- `historico.png`, `forecast.png`, `plan-anual.png`, `propuestas.png`. Sin documento de diseño aparte para este tablero, solo las capturas.

### Hallazgos de las capturas `forecast-ibp-*.png` (no obvios, ya corregidos)

- **"Histórico de ventas" tiene DOS series de venta real, no una**: "Histórico" (ADJUSTEDACTUALSQTY, vía `get_historico_y_forecast`) y "Entregado" (ACTUALSQTY sin ajustar, vía `get_historico_ventas_mensual` -- la misma función que ya se usaba para accuracy, reutilizada acá). El bar chart las muestra juntas.
- **"Forecast - Estimado" (página 2) NO muestra el waterfall completo** -- solo 2 series: "Historico Ajustado" (pasado) y "12 - Estimado Consensuado" (futuro). El waterfall completo (7 tipos) es exclusivo de **"Propuestas de Forecast" (página 4)**, que sí tiene el selector de Tipo. Antes tenía las 8 categorías en ambas páginas.
- **Las tarjetas de E+P estaban mal armadas**: la segunda tarjeta de "Forecast"/"Propuestas de Forecast" es "Entregado + Pendiente" = `ZENTREGAPENDIENTEMTH` (de `get_entregado_pendiente`, directo de SAP) -- yo la tenía usando `ZAJUSTECOMERCIALESTIMADO` de `get_estimado_comercial`, que es un concepto distinto ("Ajuste Comercial", no E+P). La tercera tarjeta de "Forecast" (no está en Propuestas) es "Entregado Mes en curso" = `ZENTREGADO`.
- **Área Comercial SÍ va en "Histórico de ventas"** (multi-línea "Histórico por Área Comercial" + pie "Volumen por Área Comercial") -- en algún momento las había sacado de esta página por la falsa alarma de que cualquier dimensión de cliente era lenta (ver sección de ZAREAGC más abajo); ya se puede traer de vuelta vía merge con `get_customer_master()`, igual que en Ranking Clientes.
- **"Planificación Anual vs Avance" (página 3, antes "Plan Anual") es un KPI grande con gap %, no una tabla chica**: "Histórico + FCST" (número grande, rojo si por debajo del objetivo) vs "Objetivo" (Plan Anual), con el % de brecha -- implementado con `st.metric(delta=...)`. El gráfico de Plan Anual vs Histórico+FCST usa `charts.area_superpuesta` (áreas superpuestas, NO apiladas) porque ambas series se solapan en el tiempo -- apilarlas (como hacía `area_chart_por_tipo`) las sumaría mal.
- El sidebar de este tablero está agrupado en 3 secciones "Período" (Año, Mes)/"Clientes" (Area Comercial, Area/GC, Customer Group)/"Productos" (Gran División, Gran Negocio, Negocio, Demand Family, Familia, Categoria, Product ID) -- ver `src/filters.py::render_sidebar_filters` (`FILTROS_IBP_CLIENTES`/`FILTROS_IBP_PRODUCTOS`). Las capturas reales muestran Año/Mes como slicers arriba del contenido en vez de en el sidebar, pero se dejaron en el sidebar bajo "Período" por consistencia con el resto de la app -- Streamlit no tiene un lugar natural para "slicers de página" fuera del sidebar. Sigue siendo un sidebar DISTINTO al de Accuracy (más filtros, "Área Comercial"/"Area/GC" en vez de solo estas 2, "Product ID" incluido) -- la agrupación visual es la misma idea en los dos tableros, el contenido de cada sección no.
- El filtro "Año" real es un **range slider** (ej. 2021-2027), no un multiselect -- `src/filters.py` sigue usando multiselect de años individuales; funciona pero no es igual de fidedigno. No se cambió (bajo prioridad frente a los fixes numéricos).
- Las capturas muestran histórico desde 2021 (~5-6 años); `cache.py::MESES_HISTORICOS=24` (2 años) es deliberadamente más corto por costo de carga -- ver la sección de rendimiento más abajo antes de agrandarlo.

## Cómo correr la app

```
cd streamlit-demanda
.venv\Scripts\python -m streamlit run app.py
```

El venv ya existe en el repo (`.venv/`) con todo instalado (`requirements.txt`). Si hace falta reinstalar: `.venv\Scripts\python -m pip install -r requirements.txt`.

### Después de editar código: reiniciar el servidor, no confiar en el auto-reload

Streamlit re-corre el script en cada interacción, pero eso **no garantiza** que haya recargado un módulo de `src/` que se acaba de editar -- ya pasó en este proyecto (el fix de `master_data_sap_ibp.py` no se reflejaba hasta reiniciar). Y el botón "🔄 Recargar datos" del Inicio tampoco alcanza: solo limpia `st.cache_data` y vuelve a correr el script, no reimporta módulos de Python ya cargados en el proceso.

**Regla:** después de cualquier cambio en `src/**` o en `app.py`, parar el proceso (`Ctrl+C` en la terminal donde corre, o matar el proceso que esté escuchando en el puerto) y volver a correr `streamlit run app.py` desde cero antes de darle el cambio por probado -- no alcanza con guardar el archivo y refrescar el navegador. Esto aplica también a variables en `aws_credentials.env`/`ibp.env`/`aws.env` (se leen una sola vez al importar `settings.py`).

### Credenciales (ninguna se commitea, `.gitignore` cubre `*.env`)

- `ibp.env` — SAP IBP OData: `IBP_USERNAME`, `IBP_PASSWORD`, `IBP_BASE_URL`, `IBP_PA_DEMANDA` (= `MOLIBP`).
- `aws.env` — Athena: `AWS_PROFILE`, `AWS_REGION`, `AWS_DATABASE`, `AWS_S3_STAGING`.
- `aws_credentials.env` (opcional) — credenciales AWS explícitas (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`), tienen prioridad sobre `AWS_PROFILE` si están. El usuario terminó usando este mecanismo (con las credenciales del perfil `296062593156_MRP_Analistas_IBP_AWS`) en vez de `AWS_PROFILE` — ver nota de mayúsculas/minúsculas abajo.

**Las credenciales son temporales (SSO) y EXPIRAN** (`ExpiredTokenException: The security token included in the request is expired`) — esto no es un bug, es esperable cada tantas horas. La app cae sola a modo demo para Athena cuando pasa (ver "Modo demo" más abajo). Para tener datos reales de nuevo, el usuario genera credenciales frescas (login SSO del perfil) y las pasa como `aws_access_key_id`/`aws_secret_access_key`/`aws_session_token` — no hay forma de que la app se re-loguee sola.

**Detalle no obvio**: el usuario suele pegar el bloque tal cual se lo da la consola de AWS SSO -- formato de archivo de credenciales de AWS CLI, con encabezado `[nombre_del_perfil]` y claves en **minúscula** (`aws_access_key_id=...`). Eso funciona igual en `aws_credentials.env` porque en Windows las variables de entorno son case-insensitive (`os.getenv("AWS_ACCESS_KEY_ID")` encuentra `aws_access_key_id` sin problema) y `python-dotenv` ignora la línea `[perfil]` sin fallar. No hay que pedirle que lo reformatee.

**`aws_credentials.env` necesita reiniciar el proceso -- `~/.aws/credentials` no.** `settings.py` lee `aws_credentials.env` una sola vez, al importarse el módulo (arranque del proceso) -- si el usuario pasa credenciales nuevas ahí, hace falta parar (`Ctrl+C`) y volver a correr `streamlit run app.py` para que se tomen; el botón "🔄 Recargar datos" del Inicio NO alcanza (solo limpia `st.cache_data` y re-corre el script, no reimporta módulos). En cambio boto3 relee `~/.aws/credentials` en cada llamada, así que un cambio ahí no necesita reiniciar nada.

Ver `.env.example` para la plantilla completa.

## Arquitectura de datos (todo verificado contra el tenant real)

### UOM y filtros de negocio estándar

**UOM = `UMG` para todas las series** (histórico, forecast, plan, E+P). Solo `CAJ` para:
- Master data de producto (`product_sap_ibp`, tabla ZPRODUCT/IBP-Product).
- Margen Unitario (`margen_unitario_sap_ibp`).

Esto fue un bug real: al principio yo tenía `CAJ` por defecto en todas las series y traía datos mal/vacíos. **No volver a poner CAJ como default de una serie sin confirmarlo contra las queries M.**

Filtros de negocio que van SIEMPRE (hardcodeados en `extract_odata_sap_ibp.py::FILTROS_BASE_EQ`/`FILTROS_BASE_NEQ`, no hace falta pasarlos manualmente):
```
ZVIGENCIA eq '1'
ZAREAFCST ne 'Comex'
ZCLIENTEBOCA eq 'Cliente'
```
El **Tablero Accuracy** agrega además (`FILTROS_EXTRA_ACCURACY_EQ`/`_NEQ`, pasar explícitamente donde aplique):
```
LOCID eq 'AR01'
ZAREAFCST ne 'Tienda Molinos'
```

### Toda consulta necesita una key figure "ancla" en el $select — incluso master data

Este Gateway (`MOLIBP`/`EXTRACT_ODATA_SRV`) no resuelve bien un `$select` que solo tenga atributos de jerarquía sin ninguna key figure/measure acompañándolo. Confirmado en dos variantes distintas del mismo problema:

1. **Con `PERIODID3` en el filtro pero sin measure en el `$select`** → `SY/530: You need authorization to display this object.` (esto en su momento me hizo pensar, incorrectamente, que faltaba un permiso de usuario — no era eso).
2. **Master data (`product_sap_ibp`/`customer_sap_ibp`) sin measure en el `$select`** → `SY/530: The selected attributes must belong to the same master data type.`

En ambos casos la solución es la misma: agregar `ACTUALSQTY` al `$select` (no hace falta usar su valor después, solo que esté presente) — así es como las queries M reales del Power BI SIEMPRE lo hacen, incluso en ZPRODUCT/ZCUSTOMER donde ese valor no se termina usando. **No sacar `ACTUALSQTY` de `product_sap_ibp`/`customer_sap_ibp` en `master_data_sap_ibp.py`, y si se agrega una consulta nueva de master data, agregarlo ahí también.**

### Grano de cliente: SOLO ZAREAGC, nunca CUSTID

Confirmado dos veces independientemente (queries M reales + pruebas contra el tenant): pedir una key figure con `CUSTID` (o cualquier atributo de cliente más granular que ZAREAGC) en el `$select` tarda **150s+ y termina en 500 Internal Server Error**. Con `ZAREAGC` la misma consulta tarda **~4-8s**. Por eso:
- `CUST_ATTRS_AREAGC = ["ZAREAGC"]` es lo único que se pasa como `cust_atributos` en consultas de key figures.
- `CUST_ATTRS_BASE` (con CUSTID, ZAREACOMERCIAL, CUSTGROUP, etc.) es SOLO para `customer_sap_ibp()` (master data, sin PERIODID3, rápida).
- Para tener "Area Comercial" en una página (ej. Ranking Clientes), se hace merge de `ZAREAGC` contra `get_customer_master()` (cacheada, rápida) — nunca pidiéndoselo a una consulta de key figures.

**Si en el futuro hace falta más detalle de cliente que ZAREAGC, no asumir que es posible — probar primero con una consulta chica y medir tiempo antes de construir sobre esa base.**

### Key figures (nombre real de campo OData, confirmado)

| Concepto Power BI | Campo OData real | Notas |
|---|---|---|
| Histórico de Ventas | `ACTUALSQTY` | **No** `ZACTUALSQTY` (así lo tenía yo al principio, probablemente traía columnas vacías en silencio) |
| Histórico Ajustado | `ADJUSTEDACTUALSQTY` | Usado en "FCST HIST" / Tablero Forecast IBP |
| Forecast Consensuado | `DEMANDPLANNINGQTY` | |
| Forecast Estadístico | `STATISTICALFORECASTQTY` | Output del modelo ML (`ibp-forecast-mensual`/`ibp-forecast-entregas-mensual`), escrito de vuelta a IBP |
| Estimado Consensuado | `ZFCSTESTIMADO` | Ala "12" del waterfall |
| Plan Anual | `ZPLANANUAL` | Filtrado por **AÑO** vía `PERIODID1`, NO por mes (`PERIODID3`). Sin fallback a otro key figure — eso me lo había inventado yo, no existe en el Power BI real |
| Entregado (E+P) | `ZENTREGADO` | Directo de SAP IBP, **no** de Athena |
| Pendiente (E+P) | `ZPENDIENTESMTH` | Directo de SAP IBP |
| E+P (Entregado+Pendiente) | `ZENTREGAPENDIENTEMTH` | Directo de SAP IBP, ya calculado del lado de SAP |
| Margen Unitario | `ZMARGENUNITARIOUSD` | Filtro por `CURRTOID eq 'USD'` + `UOMTOID eq 'CAJ'`; mes actual con fallback al mes anterior si viene vacío |
| Negocio (jerarquía producto) | `ZBRAND` | **No** `ZINDFAMILY` (ese campo ni se usa) |
| Gran Negocio | `ZBIGBUSINESS` | |
| Gran División | `ZBIGDIVISION` | |
| Demand Family | `ZDEMFAMILY` | |
| Familia | `PRDFAMILY` | |

**El waterfall completo de forecast** (tabla ZFCST / IBP-Forecast del Power BI, 7 versiones) está en `forecast_waterfall_sap_ibp()` / `cache.get_forecast_waterfall_mensual()` — una sola consulta, de la que `get_forecast_consensuado_mensual()` y `get_forecast_estadistico_mensual()` extraen su columna (sin pegarle de nuevo a SAP):

```
ZESTADISTICOAJUSTADO   -> "Estadístico Ajustado"
STATISTICALFORECASTQTY -> "01 - Forecast Estadístico"
ZFORECASTDEMANDA       -> "03 - Forecast Demanda"
SALESMGRFORECASTQTY    -> "04 - Forecast Comercial"
SALESFORECASTQTY       -> "05 - Forecast Planeamiento Comercial"
DEMANDPLANNINGQTY      -> "07 - Forecast Consensuado"
ZFCSTESTIMADO          -> "12 - Estimado Consensuado"
```

### Entregado/Pendiente (E+P): NO usa Athena

Versión vieja (descartada): había un módulo `entregado_pendiente_datalake.py` que reconstruía Entregado/Pendiente desde Athena (`sap_sd_confpedidos`/`sap_sd_volnegocio`), copiando el patrón del repo `ibp-algoritmo-ep` (Algoritmo E+P). **Eso era para otro propósito** (el Algoritmo E+P necesita reconstruirlo porque ese es su output). Este Power BI simplemente lee `ZENTREGADO`/`ZPENDIENTESMTH`/`ZENTREGAPENDIENTEMTH` **directo de SAP IBP** (probablemente el mismo Lambda del Algoritmo E+P los escribe de vuelta a IBP). Ese módulo se borró — no reintroducirlo sin confirmar que de verdad hace falta.

### grupo_material_3 (categoría de producto)

Viene de Athena, join liviano (no transaccional pesado):
```sql
SELECT m.sku, m.familia, g.grupo_material_3
FROM sap_materiales m LEFT JOIN sap_grupo_materiales g ON m.sku = g.sku
WHERE m.tipo_producto = 'Producto terminado' AND g.grupo_material_3 IS NOT NULL AND g.grupo_material_3 <> ''
```
Ver `src/data/aws_categoria.py::categoria_producto_datalake()`. Rápido (~6s).

## Fórmulas de Accuracy (DAX real, no un supuesto)

El usuario pasó el texto real de las medidas DAX del `.pbix` Accuracy y el Glosario — están traducidas fielmente a Python en `src/accuracy.py`. Puntos clave si hay que tocar esa lógica:

- **La accuracy ponderada NO es un promedio de ratios por fila, y TAMPOCO es el error de los totales ya agregados.** Siempre decompone a grano **PRDID x mes** primero, toma el error absoluto ahí, y RECIÉN AHÍ suma para dividir por el total de Actual del nivel que se esté pidiendo. Ver `_accuracy_ponderada()` — el parámetro `grano_extra` es justamente eso.
- **Bug corregido (2026-09-14, reportado por el usuario): `acc_bias_consensuado` decomponía solo a `PERIODID3`, sin `PRDID`.** Con `group_cols=["ZBIGDIVISION"]` (o cualquier corte por cliente -- Area Comercial, Area/GC), eso calculaba `1 - |ΣActual - ΣForecast| / ΣActual` **sobre los totales ya agregados de esa división/mes**, no sobre el error de cada SKU -- si un SKU sobre-forecasteaba y otro sub-forecasteaba dentro del mismo grupo, los errores se cancelaban entre sí y el accuracy salía artificialmente alto. Confirmado con un caso sintético: SKU A (Actual 100, Forecast 150) + SKU B (Actual 100, Forecast 50) en la misma división daba ~100% de accuracy (mal, los errores de +50 y -50 se cancelan al sumar antes de tomar el absoluto) en vez del 50% correcto (`1 - (|150-100|+|50-100|)/200`). **Fix**: `acc_bias_consensuado` ahora decompone a `["PRDID", "PERIODID3"]` SIEMPRE, exactamente igual que `acc_estadistico` (ver abajo) -- no había ninguna razón real de negocio para que las dos midieran distinto. Esto **NO cambiaba nada** en `tabla_segmentacion_sku` (ahí `group_cols=["PRDID"]` ya forzaba ese grano de por sí) ni en ninguna vista que solo mire una división/mes con un único SKU relevante -- el bug solo se notaba al agregar por encima del SKU (Gran División total, Area Comercial, Area/GC), que es exactamente donde el usuario lo detectó (Reporte Accuracy, Ranking Clientes).
- **Regla general, sea cual sea el nivel de agregación pedido (ZBIGDIVISION total, ZPRDFAMILY x Area/GC, ZBIGBUSINESS x Area Comercial, lo que sea)**: la Accuracy (Consensuado o Estadístico) siempre se mide a nivel SKU x mes y RECIÉN AHÍ se suma/divide -- `Accuracy = 1 - (Σ_sku,mes |Actual - Forecast|) / Σ Actual`. El **Bias**, en cambio, siempre se mide a nivel TOTAL del grupo -- es lineal (`ΣForecast/ΣActual - 1`), no decompone por SKU ni por mes.
- **Acc. FCST Consensuado** y **Acc. FCST Estadístico**: mismo grano = `group_cols + ["PRDID", "PERIODID3"]` SIEMPRE (equivalente al `CROSSJOIN(Meses, Productos)` de la medida DAX original), y las dos se acotan a `[0, 1]` por igual (`clip(lower=0, upper=1)` dentro de `_accuracy_ponderada`, incondicional -- ver sección "Accuracy siempre en [0, 1]" más abajo).
- **Bias**: es lineal, no necesita grano especial — `ΣForecast/ΣActual - 1` directo sobre los totales de `group_cols`.
- **Segmento SKU**: `_segmentar_fila()` replica el `SWITCH(TRUE(), ...)` exacto — ojo que el orden de evaluación importa: primero chequea `AccEstadistico > 0.8` (segmento "0") ANTES que `AccConsensuado > 0.8` (segmento "1"), aunque el SKU tenga buen consensuado. Si se reordena esa lógica, cambian los segmentos.
- **Acc. Consensuado Proyectado (Escenario)**: simulación "si corrigiera todos los SKU hasta el segmento X" — ver `acc_consensuado_proyectado()`.
- El texto real del Glosario (Indicador/Fórmula/Definición/Interpretación, y las definiciones de los 6 segmentos) está en `GLOSARIO_ACCURACY` y `SEGMENTOS_INFO` dentro de `src/accuracy.py` — la página 8 (`Glosario`) los renderiza directo de ahí, no hay texto duplicado en la página.

Si el usuario cambia una medida DAX en el pbix, hay que pedirle que la vuelva a pasar y actualizar `src/accuracy.py` — no volver a adivinar.

### "Meses a analizar" (selección dinámica) — todo el Tablero Accuracy corre sobre esto, no sobre todo el histórico

Confirmado por el informe (`Reporte – Ranking Forecast Accuracy.docx`) y las 3 capturas del Power BI real: el "Reporte de Proyección Accuracy" completo (páginas 5, 6 y 7) calcula accuracy/bias/segmentación **ponderado por volumen**, nunca sobre toda la ventana de 36 meses que trae `cache.py`. El primer bug que corregí acá fue justamente que las fórmulas usaban todo el histórico.

**Cambio de diseño (2026-09-14, a pedido del usuario)**: el diseño original de Power BI ancla una ventana FIJA de "últimos 4 meses cerrados" (U4M) con un único selector "Mes". El usuario pidió que esto sea dinámico: en vez de una ventana fija, un multiselect **"Meses a analizar"** donde elige directamente CUÁLES meses entran en el cálculo -- Accuracy/Bias ponderado se recalculan sobre exactamente esos meses, sean cuantos sean (no necesariamente 4, no necesariamente consecutivos). Por default vienen preseleccionados los últimos `accuracy.MESES_ANALISIS_DEFAULT` (4) meses con `Actual > 0` -- mismo comportamiento inicial que daba la ventana U4M -- pero el usuario puede agregar o sacar meses libremente. `MESES_U4M` ya no existe como tal (renombrada a `MESES_ANALISIS_DEFAULT`, que solo fija el tamaño del default, no una ventana obligatoria).

Mecanismo (ver `src/filters.py::render_sidebar_accuracy` y `src/accuracy.py::MESES_ANALISIS_DEFAULT`):
- Cada una de las 3 páginas tiene, en el sidebar (sección "Período"), un **multiselect "Meses a analizar"** -- no un único mes ancla, y no "Año"+"Mes" como en el Tablero Forecast IBP.
- La función devuelve `meses_analisis` (lista ordenada cronológicamente); las páginas filtran el DataFrame a `PERIODID3.isin(meses_analisis)` (`df_meses`, antes `df_u4m`) **antes** de llamar a `tabla_segmentacion_sku`/`acc_bias_consensuado`/`acc_estadistico` — esas funciones no cambiaron su firma, agregan sobre lo que reciben.
- El segundo criterio de elegibilidad "forecast próximos 4 meses" (`forecast_proximos_4m`) ahora ancla su ventana futura en `meses_analisis[-1]` (el mes MÁS RECIENTE de los elegidos), no en un único "mes de referencia" separado -- `periodos_empezando_en(MESES_PROX_FCST, meses_analisis[-1])`.
- `historico_ultimos_3m_cerrados()` (el gate de actividad de la segmentación) sigue sin calcular "los últimos 3 meses desde hoy" — toma los 3 meses más recientes **presentes en el DataFrame que recibe** (`df_meses`), así que se adapta automáticamente a cuantos meses el usuario haya elegido (si elige menos de 3, usa los que haya). Si algún día se llama a esta función con un DataFrame sin filtrar por `meses_analisis` (36 meses), el gate quedaría mal (usaría los últimos 3 de TODO el histórico) — siempre filtrar antes de llamarla.

### Estructura real de las 3 páginas del Tablero Accuracy (según captura, no el docx)

- **Reporte Accuracy** (`5_Reporte_Accuracy.py`, título real "Reporte de Proyección Accuracy"): multiselect "Meses a analizar" (sidebar, sección "Período") + dos tablas lado a lado (Accuracy Estadístico/Consensuado/Bias por Gran División, una por cada mes elegido -- "Evolución Mensual" -- y la misma terna pero agregada en un solo valor sobre todos los meses elegidos -- "Accuracy & Bias Ponderado (meses seleccionados)"), scopeadas a la única Gran División elegida en el sidebar, + tabla "Segmento" (Cantidad SKU, % Volumen, Accuracy Proyectado) **desglosada por las 3 Grandes Divisiones válidas** (columnas lado a lado, IGNORA el filtro de Gran División del sidebar a propósito -- pedido del usuario, ver "Reglas de negocio agregadas a pedido del usuario" más abajo).
  - La columna **"Accuracy Proyectado" es acumulativa fila por fila**, no un valor único con selector aparte: la fila del segmento "0" muestra el resultado de corregir solo el grupo 0; la fila "1" de corregir 0+1; ... hasta "3.2" que muestra el resultado de corregir TODOS los segmentos. Es literalmente `acc_consensuado_proyectado(tabla, ORDEN_SEGMENTO[segmento])` evaluada una vez por cada segmento en orden -- ver `src/accuracy.py::resumen_segmentos()`. No hay que ofrecer un selector de escenario aparte, ya está expresado en la tabla.
- **Segmentación de SKU** (`6_Segmentacion_SKU.py`): tabla a nivel SKU, con filtros propios "Segmento"/"SKU" arriba de la tabla (además del sidebar). Orden de columnas real: SKU, Descripción SKU, Entrega, Margen Unitario (USD), % Mix Margen (SKU), FCST Estadístico, FCST Consensuado, Acc. FCST Estadístico Ponderado, Acc. FCST Consensuado Ponderado, Desvío Accuracy (pp.), Segmento SKU -- **Estadístico va antes que Consensuado** en las columnas de forecast/accuracy (al revés de como yo las había puesto la primera vez).
- **Ranking Clientes** (`7_Ranking_Clientes.py`): el ranking por Área Comercial (tablas) y por Área/GC (gráficos de barra) van **separados por Gran División, en columnas lado a lado** (una columna por división -- las 3 de `filters.GRANDES_DIVISIONES_VALIDAS`, nunca una 4ta) -- no es un solo ranking global como en la versión anterior de esta página. Única página que llama a `render_sidebar_accuracy(..., incluir_gran_division=False)` (ver "Reglas de negocio..." más abajo). Los gráficos de barra usan una escala continua semáforo rojo-amarillo-verde (`charts.ranking_semaforo`, `color_continuous_scale="RdYlGn"`, rango fijo `[0,1]`) en vez de la paleta categórica -- acá el color SÍ codifica magnitud a propósito, es la única excepción al principio general de "color por identidad, no por ranking" del resto de la app.

### Simplificaciones conocidas (no bloqueantes, pendientes si se pide más fidelidad)

- El filtro "Categoria" (grupo_material_3, vía `cache.get_categoria_producto`) ya está conectado en las **7 páginas de los dos tableros** (antes solo en Accuracy): mergean `sku`→`PRDID`/`grupo_material_3`→`Categoria` contra su/sus DataFrame(s) base antes de armar el sidebar (mismo patrón que el merge de `ZAREACOMERCIAL`). En el Tablero Forecast IBP se mergea en TODOS los DataFrames que ya reciben `apply_filters` con el resto de filtros de producto (ej. en `2_Forecast.py`/`4_Propuestas_FCST.py`: `df_ancho`, `df_comercial` y `df_ep`, no solo el que arma el sidebar) para que el filtro narrowee también las tarjetas KPI, igual que ya hacía Gran División. Igual que el merge de Area Comercial, en modo demo no se conecta (el `if not es_demo_categoria` se salta) -- solo aparece con conexión real a Athena.
- **Sidebar agrupado real ya implementado en los DOS tableros**: `src/filters.py::render_sidebar_accuracy(df, key_prefix)` para las 3 páginas de Accuracy -- 3 secciones "Período" (multiselect "Meses a analizar", ver sección dedicada más arriba -- antes vivía como un único `st.selectbox` en el cuerpo de la página), "Clientes" (Area Comercial, Area/GC) y "Productos" (Gran División, Gran Negocio, Categoria, Familia -- sin Negocio/Demand Family/Product ID/Customer Group/Año, que no están en el diseño real de estas 3 páginas). `render_sidebar_filters` para las 4 páginas del Tablero Forecast IBP -- mismas 3 secciones pero con el set de filtros completo (ver hallazgo más arriba).
  - **Area Comercial/Area GC ya funcionan también en Reporte Accuracy y Segmentación SKU** (no solo en Ranking Clientes): `cache.get_forecast_vs_actual_producto` dejó de colapsar `ZAREAGC` -- ahora mantiene el grano PRDID x ZAREAGC x mes (igual que `get_forecast_vs_actual`) y las 2 páginas mergean `ZAREAGC`→`ZAREACOMERCIAL` contra `get_customer_master()` antes del sidebar, mismo patrón que ya usaba Ranking Clientes. Esto es transparente para quien no filtre por cliente: `acc_bias_consensuado`/`acc_estadistico`/`tabla_segmentacion_sku`/`historico_ultimos_3m_cerrados`/`forecast_proximos_4m` agregan sumando por `PRDID` (o `PRDID x PERIODID3`) puertas adentro, así que colapsar ZAREAGC ahí en vez de en `cache.py` da el mismo número cuando no hay filtro de cliente activo, y permite filtrar por Area/GC cuando sí lo hay -- verificado con datos sintéticos (misma Accuracy ungrouped vs. pre-colapsado, y el filtro por un solo Area/GC da el subtotal esperado).
    - **Ojo si se toca `6_Segmentacion_SKU.py`**: el bloque `avg_por_mes` (FCST Estadístico/Consensuado/Entrega promedio de los meses elegidos) NO puede promediar directo sobre `df_meses` con este grano -- promediaría sobre (mes x ZAREAGC) en vez de sobre mes, sesgado por cuántas Area/GC tenga cada SKU. Por eso ahora es dos pasos: `groupby(["PRDID","PERIODID3"]).sum()` (colapsa ZAREAGC) y RECIÉN AHÍ `groupby("PRDID").mean()` (promedia los meses elegidos). Cualquier cálculo nuevo sobre `df_meses` en estas 2 páginas que use `.mean()` en vez de `.sum()` tiene que pasar por el mismo colapso previo.
- **Elegibilidad "forecast próximos 4 meses" ya implementada**: además del gate de actividad hacia atrás (`historico_ultimos_3m_cerrados`, 3 meses), `src/accuracy.py::forecast_proximos_4m(df_producto_full, meses_prox4m)` exige `ForecastConsensuado` > 0 sumado en los `MESES_PROX_FCST=4` meses siguientes al último mes elegido (`meses_analisis[-1]`, vía `listas_periodos.py::periodos_empezando_en`) para que un SKU reciba Segmento -- ver el gate en `_segmentar_fila`. `df_producto_full` tiene que venir SIN filtrar a `meses_analisis` (esos meses futuros quedan afuera de esa selección) -- las páginas 5 y 6 arman ese DataFrame a partir de `df_f` (post sidebar, pre-selección de meses) y se lo pasan a `cache.calcular_tabla_segmentacion(df_meses, df_forecast_prox4m)` (firma con segundo argumento).

## Reglas de negocio agregadas a pedido del usuario (2026-09-14, no vienen del Power BI real)

Una tanda de pedidos puntuales de negocio, aplicados sobre los dos tableros. A diferencia del resto de este documento (que documenta réplica fiel del Power BI real), estas son decisiones de producto del usuario que van MÁS ALLÁ o AL MARGEN de lo que muestra el Power BI original -- no asumir que están en las capturas.

### Gran División: selectbox obligatorio de una sola opción, restringido a 3 valores

`src/filters.py::GRANDES_DIVISIONES_VALIDAS = ["Alimentos", "Bodegas", "Snacks"]` + `_selectbox_gran_division()`. En los DOS tableros, "Gran División" dejó de ser un multiselect más de la sección "Productos" -- es un `st.selectbox` aparte, SIEMPRE con un valor elegido (nunca "Todas"), default "Alimentos", y sus opciones están restringidas a esas 3 divisiones -- si el DataFrame trae alguna otra (ej. "MP, Semi y Subproductos", que sí existe en la jerarquía real de SAP y aparecía en Ranking Clientes antes de este cambio), ni siquiera se ofrece como opción. Como el filtro es obligatorio, esto excluye esa división de TODA la app automáticamente en cuanto `apply_filters` se aplica -- no hace falta un filtro aparte a nivel de datos.

**Excepción: `7_Ranking_Clientes.py`** llama a `render_sidebar_accuracy(..., incluir_gran_division=False)` -- esa página ya muestra las 3 divisiones válidas simultáneamente (una columna por división), así que un selectbox de una sola no tendría sentido; en cambio arma `divisiones` directo desde `GRANDES_DIVISIONES_VALIDAS`, sin pasar por el selectbox.

**Excepción parcial: `5_Reporte_Accuracy.py`, sección "Segmento"** -- a pedido del usuario, esa sección específica muestra las 3 divisiones desglosadas (una tabla por división, `Cantidad SKU`/`% Volumen`/`Accuracy Proyectado`), aunque el resto de la página ("Evolución Mensual", "Accuracy & Bias Ponderado") sí queda scopeado a la única división elegida en el sidebar. Para lograrlo, esa sección arma su propio `df_todas_divisiones` sacando `"ZBIGDIVISION"` del dict de `filtros` antes de llamar a `apply_filters` (respeta el resto de filtros -- Clientes/Categoria/Familia/meses -- pero no la división elegida), y recién ahí itera por división. Si se toca esta página, tener en cuenta que hay DOS "vistas" de `df` conviviendo: la scopeada a 1 división (`df_meses`, para Evolución/Ponderado) y la de las 3 divisiones (`df_meses_todas_divisiones`, para Segmento).

### Accuracy siempre en `[0, 1]` -- da exactamente 1 SOLO si el error absoluto total es 0

`src/accuracy.py::_accuracy_ponderada` hace `.clip(lower=0, upper=1)` incondicional, pero el clip por sí solo NO alcanza -- el 14/09 el usuario reportó (y tenía razón) que estaba viendo 100% de accuracy por Area/GC en casos donde eso claramente no podía ser cierto. Causa real: `_abs_error` es una suma de `.abs()` (nunca negativa), así que con un `Actual` (denominador) POSITIVO, `1 - _abs_error/Actual` matemáticamente NUNCA puede superar 1 -- el único modo de que la cuenta cruda dé más de 100% es que el `Actual` TOTAL del grupo sea NEGATIVO (ej. devoluciones/notas de crédito que hacen neto negativo a nivel Area/GC): ahí `_abs_error/Actual` se vuelve negativo y `1 - (negativo)` > 1, y el `clip(upper=1)` tapaba ese caso mostrando un falso 100% en vez de señalar que el dato no tiene una lectura de accuracy válida ahí. **Fix**: el denominador exige `Actual > 0` estricto (`g["Actual"].where(g["Actual"] > 0)`, no el `.replace(0, pd.NA)` de antes que solo cubría el cero exacto) -- Actual cero O negativo da `Accuracy = NaN`, nunca un accuracy inflado. Verificado con un caso sintético (Actual=-50, Forecast=100 → antes 100%, ahora NaN). `acc_consensuado_proyectado()` también clippea su resultado por las dudas (aunque matemáticamente ya cae en rango, al ser un promedio ponderado de valores ya acotados). Si se agrega una métrica de accuracy nueva en algún lado, pasar por `_accuracy_ponderada` en vez de calcular el cociente a mano -- si no, hay que acordarse tanto del clip como del guard de denominador positivo. El `Bias` (`bias["Actual"].replace(0, pd.NA)`) tiene la misma fragilidad teórica ante un `Actual` negativo, pero no se tocó -- no fue parte de lo reportado, y a diferencia de Accuracy no tiene un rango "imposible" tan claro contra el cual contrastar.

### Bug de dtype en `charts.ranking_semaforo` -- leyenda gigante en vez de semáforo

Encontrado al mejorar la visual de "Ranking por Área/GC" (pedido del usuario): `_accuracy_ponderada` arma `Actual.replace(0, pd.NA)` para evitar división por cero -- una columna float con algún `pd.NA` mezclado (a diferencia de `np.nan`) pasa a dtype `object` en pandas. Plotly Express, con dtype `object`, trata la columna de `color` como CATEGÓRICA aunque se le pase `color_continuous_scale`, y en vez de una barra de color continua dibuja una entrada de leyenda POR CADA VALOR ÚNICO -- con muchas filas, una leyenda kilométrica de números sueltos tapando el gráfico (esto ya pasaba antes de esta sesión, no es una regresión nueva). **Fix**: `pd.to_numeric(df[x], errors="coerce")` antes de graficar, en cualquier chart que use una columna de accuracy/error como `color` continuo -- si se agrega un gráfico nuevo con ese patrón, aplicar el mismo `to_numeric` primero.

De paso, mientras se tocaba esa función: escala de color Y de eje X fijas en `[0, 1]` (antes `range_color` era dinámico según el máximo de cada subset, lo que pintaba un 60% de verde en un panel y de amarillo en el de al lado solo por el máximo local) y texto adentro de la barra (`textposition="inside"`) en vez de afuera, para que no se corte contra el borde en valores altos.

### "Salto raro al 0" en el área Histórico Ajustado / Forecast (página Forecast)

`charts.area_chart_por_tipo` (usa `px.area` APILADO) no es apto para 2 series que NO se solapan en el tiempo (Historico Ajustado termina justo donde empieza el Forecast, por diseño -- ver "Histórico y Forecast/Estimado ya no se solapan en el tiempo" más abajo): Plotly interpola el área apilada contra el dominio combinado de ambas series y dibuja una caída diagonal a 0 justo en el mes de corte, aunque los datos en sí YA estaban bien separados (esto no era un problema de datos, era 100% de rendering). **Fix**: `2_Forecast.py` pasó de `charts.area_chart_por_tipo` a `charts.area_superpuesta` (mismo helper que ya usa "Plan Anual vs Histórico + FCST") -- traces independientes con `fill="tozeroy"` en vez de apilado, cada una anclada solo a su propio rango real de fechas, sin interpolación cruzada. Si se agrega otra página con 2+ series de Tipo que NO se solapen en el tiempo, usar `area_superpuesta`, no `area_chart_por_tipo` (esta última queda para cuando de verdad haga falta apilar categorías simultáneas -- hoy no la usa ninguna página).

### KPI "Forecast/Estimado Actual" corregido (páginas Forecast y Propuestas FCST)

Usaba `ZFCSTCOMERCIALESTIMADO` (`cache.get_estimado_comercial`, "Ajuste Comercial") en vez de `ZFCSTESTIMADO` (el mismo key figure que ya grafica la serie "12 - Estimado Consensuado") -- por eso el número de la tarjeta nunca coincidía con lo que mostraba el gráfico arriba. Fix en ambas páginas: `df_ancho_f.loc[df_ancho_f["PERIODID3"] == mes_actual, "ZFCSTESTIMADO"].sum()` (`mes_actual = periodos_futuros_mes(1)[0]`). `cache.get_estimado_comercial`/`demo_data.estimado_comercial_demo` quedaron sin ningún consumidor en `pages/` tras este fix (se sacó la carga de `df_comercial` de ambas páginas) -- la función en sí NO se borró de `cache.py`/`demo_data.py`/`extract_odata_sap_ibp.py` por si hace falta para otra cosa más adelante, pero ya no se precarga como parte del flujo de estas 2 páginas.

### Otros ajustes puntuales de esta tanda

- **"Entregado" en "Histórico de ventas" (página 1)**: ahora SOLO se muestra para el mes en curso (antes traía todo el histórico junto con "Histórico") -- filtro `PERIODID3 == periodos_futuros_mes(1)[0]` sobre `df_entregado_f` antes de armar la serie del bar chart.
- **Plan Anual arranca en enero 2025** (`3_Plan_Anual.py::PLAN_ANUAL_DESDE`): el usuario aclaró que el Plan Anual recién se empezó a conformar desde esa fecha, así que traer períodos anteriores no aporta -- se filtra `df_plan`/`df_ancho` a `Date >= 2025-01-01` ANTES de armar el sidebar (así "Año"/"Mes" tampoco ofrecen años previos como opción). De paso se sacó la sección "Detalle por Año" (tabla al pie), no la pidió el usuario. **El filtro "Año" viene preseleccionado en el año en curso** (`anio_default=[pd.Timestamp.today().year]`, nuevo parámetro opcional de `render_sidebar_filters` -- las otras 3 páginas del Tablero IBP no lo pasan, siguen sin preselección).
- **"Propuestas de Forecast" (página 4)**: el multiselect "Tipo" viene preseleccionado en `["Historico Ajustado", "01 - Forecast Estadístico", "12 - Estimado Consensuado"]` (antes las 8 categorías por default, saturando el gráfico) -- `TIPOS_DEFAULT` al tope del archivo.
- **Segmentación SKU (página 6)**: la tabla ahora tiene alto dinámico (`height=min(38 + 35*(filas+1), 1200)`) en vez del alto chico fijo default de `st.dataframe`, para que se vean más filas sin scroll interno.

### "Meses a analizar" (Accuracy) ya NO preselecciona el mes en curso

A pedido del usuario: el mes en curso puede tener `Actual` parcial (el mes todavía no cerró) y por eso aparecía en `meses_disponibles` y quedaba preseleccionado por default junto con los otros 3 -- pero un mes a mitad de cerrar distorsiona la Accuracy/Bias ponderado (compara Forecast del mes completo contra una Entrega todavía incompleta). **Fix en `render_sidebar_accuracy`**: el ancla del default ya no es `meses_disponibles[-1]` a secas, sino el último mes CERRADO -- `mes_actual = periodos_futuros_mes(1)[0]`, se excluye de `meses_cerrados = [m for m in meses_disponibles if m != mes_actual]`, y `periodos_terminando_en(MESES_ANALISIS_DEFAULT, meses_cerrados[-1])` arma el default a partir de ahí. El mes en curso NO desaparece de las opciones del multiselect (sigue siendo `Actual > 0`, el usuario lo puede agregar a mano si quiere incluirlo), solo se saca del default. Afecta a las 3 páginas de Accuracy por igual (comparten `render_sidebar_accuracy`).

## SSL / red corporativa (Molinos)

El tráfico HTTPS pasa por un proxy que reemplaza el certificado del servidor por uno de una CA interna. Windows la conoce (política de dominio), pero el bundle de `certifi` que usa `requests` no.

**Fix aplicado — OJO, es fácil romperlo**: `truststore` (hace que el `ssl` de Python use el almacén de certificados de Windows) está aplicado **solo a la sesión de `requests` de SAP IBP** (`src/data/consulta_odata.py::_TruststoreAdapter` + `_sesion_con_certs_windows()`), vía un adapter montado en una `requests.Session` propia. **Nunca llamar a `truststore.inject_into_ssl()` de forma global** (por ejemplo en `settings.py`) — eso parchea el `ssl.SSLContext` de todo el proceso, y **rompe a boto3/botocore (Athena) con un `RecursionError`** al construir su propio `ssl_context` (incompatibilidad conocida entre truststore y cómo urllib3/botocore arman `context.options`). Si alguna vez Athena empieza a tirar `RecursionError: maximum recursion depth exceeded` en `botocore/httpsession.py`, sospechar primero de esto.

## Rendimiento

### Limitación real de SAP (no un bug): un GET por período

SAP IBP OData no permite pedir varios períodos en una sola consulta (`PERIODID3 eq 'X' or PERIODID3 eq 'Y'` no está soportado por este servicio) — `_consulta_por_periodo()` loopea un `GET` por mes/año, en paralelo (`ThreadPoolExecutor`).

| Consulta | Meses/años | Tiempo real |
|---|---|---|
| Cualquier key figure sola, sin ZAREAGC | 1 mes | ~4s |
| Cualquier key figure con ZAREAGC | 1 mes | ~8-12s |
| Cualquier key figure con CUSTID | 1 mes | 150s+ y termina en 500 (no usar, ver arriba) |
| `get_forecast_waterfall_mensual()` (11 medidas combinadas) | 36 meses, 8 workers | **~75-85s** |
| `get_plan_anual()` | 4 años (ver abajo) | no vuelto a medir tras el fix de años, estimado ~130s (antes 200s con 6 años) |

### Optimizaciones aplicadas (sesión de performance) — con antes/después medido

1. **Fusionar 3 consultas mensuales en 1** (`forecast_waterfall_sap_ibp` ahora trae 11 medidas -- las 7 del waterfall + `ACTUALSQTY`/`ADJUSTEDACTUALSQTY` + `ZFCSTCOMERCIALESTIMADO`/`ZAJUSTECOMERCIALESTIMADO` -- en el mismo `$select`, un solo recorrido de 36 meses). Antes: 3 recorridos separados (36+25+12 = 73 requests), el waterfall solo ya medía **355s**. Después: **~75-85s para TODO junto** (una sola consulta de 36 requests). `get_forecast_consensuado_mensual`, `get_forecast_estadistico_mensual`, `get_historico_ventas_mensual`, `get_historico_y_forecast_ancho` y `get_estimado_comercial` recortan de este único DataFrame cacheado -- ninguna vuelve a pegarle a SAP.
2. **Pool de conexiones HTTP más grande** (`consulta_odata.py::POOL_SIZE = 20`, antes el default de `requests`/urllib3 es 10). Este fue el cambio con más impacto real: con 8 workers concurrentes y un pool de 10, la concurrencia casi no aceleraba nada (12 meses: 58.6s, vs. ~96s secuencial -- apenas ~1.6x); con pool de 20, el mismo tipo de consulta escaló mucho mejor (36 meses/11 medidas en 75-85s, muy por debajo de lo que daría ese ratio de 1.6x). **Ojo con los nombres de parámetro**: `pool_connections`/`pool_maxsize` van en el `__init__` del adapter, NO dentro de `init_poolmanager(**kwargs)` -- pasarlos ahí los manda a `PoolManager` como si fueran parte de la "pool key" de urllib3 y tira `TypeError: PoolKey.__new__() got an unexpected keyword argument 'key_pool_connections'`.
3. **`persist="disk"` en todos los `st.cache_data` de `cache.py`**. Sobrevive a un reinicio del proceso (antes, cada restart del server perdía todo el cache y había que esperar de nuevo la carga completa). **Importante para probarlo**: `persist="disk"` solo se activa con el runtime real de Streamlit (`streamlit run`) -- si se prueba una función cacheada vía `python -c` suelto, Streamlit loguea `"No runtime found, using MemoryCacheStorageManager"` y cae a cache en memoria únicamente, sin persistir a disco (así que un segundo `python -c` en un proceso nuevo NO va a ser rápido -- eso no significa que `persist="disk"` esté roto, significa que el modo de prueba no lo ejercita). Para validarlo de verdad hay que reiniciar el servidor real dos veces y comparar.
4. **`get_plan_anual()` pedía 6 años cuando con 4 alcanza** (tenía un padding de +/-1 año de más en el cálculo del rango). Con `MESES_HISTORICOS=24`/`MESES_FUTUROS=12`, el rango mínimo que cubre todos los casos es `[hoy.year-2, hoy.year+1]` -- se corrigió a `ceil(MESES_HISTORICOS/12)`/`ceil(MESES_FUTUROS/12)` en vez de años fijos, para que siga siendo correcto si esas constantes cambian.
5. **`get_historico_y_forecast()` armaba ~8.5 millones de filas SIN FILTRAR, siempre** (explotaba el waterfall a 8 categorías de "Tipo" -- Historico Ajustado + 7 forecasts -- ANTES de que la página filtrara por sidebar). Eso costaba ~30-40s de cómputo puro (no red) y, peor, `st.cache_data` **devuelve una copia** en cada llamada -- ese dataframe de 8.5M filas se copiaba enteroen CADA rerun de cada página que lo usaba (1, 2, 3 y 4), en cada interacción, no solo la primera vez. Es la causa más probable de "retrasos al abrir páginas" que persistían incluso con todo cacheado en red.
   - **Fix**: se separó en `get_historico_y_forecast_ancho()` (formato ancho, mismo tamaño que el waterfall, sin explotar) + `melt_historico_y_forecast(df_ancho, tipos_forecast=...)` (explota a Tipo/Valor, con un parámetro opcional para pedir solo los tipos que hacen falta). Cada página ahora filtra por sidebar SOBRE EL ANCHO primero, y recién explota el subconjunto ya filtrado -- y de paso, cada página pide solo los tipos que realmente muestra:
     - **Página 1** (Histórico de ventas): no necesita "Tipo" para nada, solo la columna `ADJUSTEDACTUALSQTY` del ancho -- no llama a `melt_historico_y_forecast` en absoluto.
     - **Página 2** (Forecast - Estimado): solo 1 tipo de forecast (`tipos_forecast=("ZFCSTESTIMADO",)`), no las otras 6.
     - **Página 3** (Planificación Anual): arma su única serie "Histórico + FCST" directo desde el ancho (`ADJUSTEDACTUALSQTY` pasado + `DEMANDPLANNINGQTY` futuro), tampoco llama al melt.
     - **Página 4** (Propuestas de Forecast): la única que necesita las 7 versiones completas (selector de Tipo) -- `tipos_forecast=None` (todas).
   - Medido: explotar TODO sin filtrar sigue constando ~40s (dataset real, sin filtrar) -- filtrar por una sola Gran División antes de explotar bajó a ~23s (Alimentos es ~71% del universo de SKUs, así que el filtro por división sola no achica tanto; filtrar por Familia/Product ID/Area-GC específicos sí reduce mucho más). La página 4 (única que sigue necesitando las 7 versiones) va a seguir sintiéndose pesada sin filtrar -- es inherente al volumen de datos, no un bug.
   - `melt_historico_y_forecast` y `calcular_tabla_segmentacion` (ver abajo) están cacheados con `st.cache_data` (sin `persist="disk"`, a propósito -- son resultados por combinación de filtros, no vale la pena persistir docenas de variantes a disco) para que repetir la MISMA combinación de filtros no recalcule.
6. **`tabla_segmentacion_sku` (Reporte Accuracy, Segmentación SKU) se recalculaba en cada rerun** aunque el resultado fuera idéntico -- ahora pasa por `cache.calcular_tabla_segmentacion()` (cacheada).

### Histórico y Forecast/Estimado ya no se solapan en el tiempo

Pedido del usuario: *"todo lo referido a Historico me traiga periodos pasados sin incluir el actual, y todo lo referido a FCST/ESTIMADO quiero que me traiga el mes en curso y periodos futuros"* — antes, `melt_historico_y_forecast` explotaba las 7 columnas de forecast del waterfall para los 36 meses completos (incluyendo los 24 meses "históricos"), así que en las páginas 2 y 4 las series de Forecast/Estimado aparecían superpuestas con el histórico en el pasado, no solo desde el mes en curso.

**Fix en `cache.py::melt_historico_y_forecast(df_ancho, incluir_historico=True, tipos_forecast=None)`**: ahora filtra explícitamente por partición temporal antes de explotar cada bloque:
- **Histórico Ajustado** (`ADJUSTEDACTUALSQTY`) sale SOLO de `df_ancho[df_ancho["PERIODID3"].isin(meses_hist)]` (pasado, `meses_hist = periodos_historicos_mes(MESES_HISTORICOS)`, no incluye el mes en curso).
- **Cada tipo de Forecast/Estimado** (las 7 columnas del waterfall, o el subconjunto pedido en `tipos_forecast`) sale SOLO de `df_ancho[~df_ancho["PERIODID3"].isin(meses_hist)]` (mes en curso + futuro) — antes salía del `df_ancho` completo (36 meses), por eso se solapaba con el histórico.

Resultado sin gap ni overlap: el último mes de Histórico Ajustado es el mes anterior al actual, el primero de cualquier Forecast/Estimado es el mes actual. Verificado con datos demo (`Historico Ajustado` hasta `2026-08-01`, `Forecast` desde `2026-09-01`, mes actual = septiembre 2026).

**De paso se eliminó la columna `TipoSerie`** (`"Histórico"` vs `"Forecast"`) que `melt_historico_y_forecast` calculaba -- había quedado sin ningún consumidor tras el refactor de la página 4 (Propuestas de Forecast) tiempo atrás. Si hace falta distinguir Histórico de Forecast en una página nueva, ya no hace falta esa columna: alcanza con el nombre en `Tipo` (`"Histórico Ajustado"` es siempre pasado, cualquier otro valor de `Tipo` es siempre mes en curso/futuro, por construcción).

**Afecta a**: página 2 (Forecast - Estimado) y página 4 (Propuestas de Forecast), únicas que llaman a `melt_historico_y_forecast`. Página 1 (Histórico de ventas) y página 3 (Planificación Anual) ya armaban su corte pasado/futuro manualmente sobre el ancho (con el mismo criterio `PERIODID3.isin(meses_hist)`) y no necesitaron cambios.

### Qué queda pendiente si hace falta más velocidad

- Reducir `MESES_HISTORICOS`/`MESES_FUTUROS` en `cache.py` (haría todo más rápido pero se aleja de la fidelidad con Power BI, que muestra ~6 años de histórico).
- Pedirle a Basis/SAP un endpoint que acepte rango de fechas en una sola llamada (eliminaría el loop de N requests de raíz).
- Si `POOL_SIZE=20` sigue siendo un cuello de botella, probar valores más altos (no se exploró más allá de 20 por costo de las pruebas contra el tenant real -- cada prueba de 36 meses tarda ~80s).

## Modo demo (`get_or_demo`)

Cada página llama `cache.get_or_demo(get_fn, demo_fn)` en vez de `cache.safe_call` directo. Si la fuente real falla o viene vacía, cae a datos sintéticos (`src/data/demo_data.py`, semilla fija) y la página muestra un cartel "🧪 Mostrando datos de EJEMPLO". Esto es automático — no hace falta tocar nada para que ande cuando SAP/Athena no estén disponibles, y deja de mostrarse solo en cuanto la fuente real responde. Los datos demo tienen el MISMO esquema de columnas que la fuente real correspondiente — si se cambia una columna real, hay que actualizar su función demo en paralelo o las páginas rompen al caer a demo.

## Historial de correcciones (para no repetir el mismo error)

1. **"Necesitás autorización SAP"** — diagnóstico inicial incorrecto. Era un artefacto de una prueba manual (filtrar por `PERIODID3` sin pedir ninguna medida en el `$select` dispara `SY/530` en este Gateway). Las funciones reales de la app siempre piden measure + filtro juntos, así que nunca pegan ese caso.
2. **CUSTID en vez de ZAREAGC** — causó los timeouts/500 que en su momento me llevaron a sacar la página "Ranking Clientes" del todo. Se volvió a agregar al confirmar que ZAREAGC sí es viable.
3. **UOM CAJ por defecto** — mal, correcto es UMG para series (ver arriba).
4. **ZACTUALSQTY / ZINDFAMILY** — nombres de campo que asumí por analogía con otros repos Molinos (`ibp-algoritmo-ep`, `ibp-forecast-mensual`) y que NO son los reales de este modelo Power BI. Las queries M son la fuente de verdad, no otros repos.
5. **Entregado/Pendiente vía Athena** — reconstrucción innecesaria; SAP IBP ya expone esos key figures calculados.
6. **`truststore.inject_into_ssl()` global** — rompía boto3. Ver sección SSL arriba.
7. **Master data sin `ACTUALSQTY` en el `$select`** — mismo mecanismo que el error de autorización del punto 1, pero en `product_sap_ibp`/`customer_sap_ibp`. Ver sección "Toda consulta necesita una key figure ancla" arriba.
8. **`acc_bias_consensuado` sin decomponer por `PRDID`** — calculaba el error absoluto sobre los totales YA agregados del grupo (ej. ZBIGDIVISION-mes) en vez de sumar el error absoluto de cada SKU. Daba un accuracy artificialmente alto cuando el sobre-forecast de un SKU compensaba el sub-forecast de otro dentro del mismo grupo. Reportado por el usuario con un caso concreto (accuracy a nivel ZBIGDIVISION sospechosamente alto); confirmado con un ejemplo sintético de 2 SKUs. Fix: decompone siempre a `["PRDID", "PERIODID3"]`, igual que `acc_estadistico` (que nunca tuvo este bug). Ver sección "Fórmulas de Accuracy" arriba.
9. **`ranking_semaforo` con leyenda gigante en vez de semáforo** — dtype `object` (por `pd.NA` mezclado con floats) hacía que Plotly tratara la columna de color como categórica. Fix: `pd.to_numeric(..., errors="coerce")` antes de graficar. Ver sección "Reglas de negocio agregadas a pedido del usuario" más abajo.
10. **Salto/caída a 0 en el área Histórico Ajustado / Forecast (página 2)** — artefacto de `px.area` apilado (`area_chart_por_tipo`) al combinar 2 series que no se solapan en el tiempo, no un problema de datos. Fix: `area_superpuesta` (traces independientes, no apiladas). Ver sección "Reglas de negocio agregadas a pedido del usuario" más abajo.

## Estructura del repo

```
app.py                  → landing, page_links a las 8 páginas
pages/                  → 1 archivo por página del Streamlit multipage (numeradas para fijar el orden en el sidebar)
src/
  config/
    dynamics_config.py  → root_path
    settings.py         → carga ibp.env / aws.env / aws_credentials.env
  data/
    consulta_odata.py           → cliente HTTP a SAP IBP OData (con el fix de SSL acotado)
    extract_odata_sap_ibp.py    → todas las funciones de key figures + filtros estándar
    master_data_sap_ibp.py      → jerarquías de producto/cliente (sin PERIODID3, rápido)
    aws_ejecutar_query.py       → cliente Athena (boto3, sin el fix de SSL global)
    aws_categoria.py            → join liviano Athena para grupo_material_3
    demo_data.py                → datos sintéticos, mismo esquema que cache.py
  cache.py              → wrappers st.cache_data + get_or_demo (capa que las páginas consumen)
  accuracy.py           → fórmulas DAX reales (accuracy/bias/segmentación)
  filters.py            → sidebar de filtros compartidos
  charts.py             → helpers Plotly (paleta del skill de dataviz)
tablas_forecast_ibp.txt              → queries M reales, Tablero Forecast IBP (documentación, no gitignoreado)
tablas_forecast_accuracy_ibp.txt     → queries M reales, Tablero Forecast Accuracy IBP (ídem)
*.pbix                  → los dos Power BI originales, de referencia
```

## Checklist antes de proponer un cambio en la capa de datos

- [ ] ¿Estoy por asumir un nombre de key figure o un UOM? → revisar `tablas_forecast_ibp.txt`/`tablas_forecast_accuracy_ibp.txt` primero, no adivinar por analogía con otro repo.
- [ ] ¿Estoy por pedir un atributo de cliente en una consulta de key figures? → solo `ZAREAGC`, nunca CUSTID/otros. Si hace falta más detalle, probar tiempo de respuesta antes de construir sobre esa base.
- [ ] ¿Toco `consulta_odata.py` o `settings.py`? → no aplicar `truststore` de forma global, solo vía el adapter acotado.
- [ ] ¿Cambié una columna en `cache.py`? → actualizar la función demo correspondiente en `demo_data.py` con el mismo esquema.
- [ ] ¿Toco `accuracy.py`? → verificar contra el texto DAX real (pedirle al usuario que lo vuelva a pasar si no está a mano), no reinventar la fórmula.
