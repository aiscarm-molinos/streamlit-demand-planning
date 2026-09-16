# CLAUDE.md — streamlit-demanda

Contexto para asistentes de IA que trabajen en este repositorio. Léelo antes de proponer o aplicar cambios.

## Qué es este proyecto

App Streamlit que replica funcionalmente dos tableros de Power BI de SAP IBP (Molinos):
- **Tablero Forecast IBP**: Histórico de ventas, Forecast, Plan Anual, Propuestas FCST.
- **Tablero Forecast Accuracy IBP**: Reporte Accuracy, Segmentación SKU, Ranking Clientes, Glosario.

No es una réplica visual pixel-perfect — es funcional (mismos filtros, mismos números, gráficos con Plotly en vez de Power BI). Corre **local**, conectada **en vivo** a SAP IBP (OData) y AWS Athena (Data Lake).

**Nota sobre las fuentes originales (2026-09-14, a pedido del usuario)**: este proyecto arrancó con archivos fuente en la raíz del repo -- las queries M reales (`tablas_forecast_ibp.txt`/`tablas_forecast_accuracy_ibp.txt`, en `docs/`), el informe de diseño (`Reporte – Ranking Forecast Accuracy.docx`), capturas del Power BI real (`forecast-ibp-*.png`/`forecast-accuracy-*.png`) y los dos `.pbix` originales. Todo eso se **borró del repo** una vez que su contenido quedó completamente destilado acá y en `README.md` -- este documento (y el código, que es la traducción fiel de esas queries M) es ahora la ÚNICA fuente de verdad, no hace falta ir a buscar un archivo que ya no existe. Si en algún momento hace falta re-verificar algo contra la fuente original (un nombre de campo dudoso, un layout exacto), pedirle al usuario que la vuelva a pasar -- no asumir por analogía con otro repo Molinos mientras tanto.

### Hallazgos del Power BI real -- Tablero Forecast IBP (no obvios, ya corregidos)

- **"Histórico de ventas" tiene DOS series de venta real, no una**: "Histórico" (ADJUSTEDACTUALSQTY, vía `get_historico_y_forecast`) y "Entregado" (ACTUALSQTY sin ajustar, vía `get_historico_ventas_mensual` -- la misma función que ya se usaba para accuracy, reutilizada acá). El bar chart las muestra juntas.
- **"Forecast - Estimado" (página 2) NO muestra el waterfall completo** -- solo 2 series: "Historico Ajustado" (pasado) y "12 - Estimado Consensuado" (futuro). El waterfall completo (7 tipos) es exclusivo de **"Propuestas de Forecast" (página 4)**, que sí tiene el selector de Tipo. Antes tenía las 8 categorías en ambas páginas.
- **Las tarjetas de E+P estaban mal armadas**: la segunda tarjeta de "Forecast"/"Propuestas de Forecast" es "Entregado + Pendiente" = `ZENTREGAPENDIENTEMTH` (de `get_entregado_pendiente`, directo de SAP) -- yo la tenía usando `ZAJUSTECOMERCIALESTIMADO` de `get_estimado_comercial`, que es un concepto distinto ("Ajuste Comercial", no E+P). La tercera tarjeta de "Forecast" (no está en Propuestas) es "Entregado Mes en curso" = `ZENTREGADO`.
- **Área Comercial SÍ va en "Histórico de ventas"** (multi-línea "Histórico por Área Comercial" + pie "Volumen por Área Comercial") -- en algún momento las había sacado de esta página por la falsa alarma de que cualquier dimensión de cliente era lenta (ver sección de ZAREAGC más abajo); ya se puede traer de vuelta vía merge con `get_customer_master()`, igual que en Ranking Clientes.
- **"Planificación Anual vs Avance" (página 3, antes "Plan Anual") es un KPI grande con gap %, no una tabla chica**: "Histórico + FCST" (número grande, rojo si por debajo del objetivo) vs "Objetivo" (Plan Anual), con el % de brecha -- implementado con `st.metric(delta=...)`. El gráfico de Plan Anual vs Histórico+FCST usa `charts.area_superpuesta` (áreas superpuestas, NO apiladas) porque ambas series se solapan en el tiempo -- apilarlas (como hacía `area_chart_por_tipo`) las sumaría mal.
- El sidebar de los DOS tableros está agrupado en 3 secciones "Período"/"Clientes"/"Productos" -- ver `src/filters.py::render_sidebar_filters`/`render_sidebar_accuracy`. **Desde el 2026-09-14, "Clientes" y "Productos" son EXACTAMENTE los mismos filtros en los dos tableros** (`FILTROS_IBP_CLIENTES`/`FILTROS_IBP_PRODUCTOS`, a pedido del usuario -- ver sección "Filtros en cascada..." más abajo para el detalle completo). Lo único que sigue siendo distinto entre los dos sidebars es "Período" (Año+Mes vs. multiselect de meses, ver más abajo).
- **El filtro "Año" ya es un range slider** (`st.slider(min_value, max_value, value=(desde,hasta))`), no un multiselect -- `_con_ano_mes`/`apply_filters` no cambiaron (siguen esperando una lista de años en `seleccion["Año"]`, así que el slider arma esa lista con `[a for a in anios if rango[0] <= a <= rango[1]]` antes de guardarla). `anio_default` (usado por Plan Anual) ahora colapsa el rango a un único año en vez de preseleccionar un ítem de multiselect. Si `len(anios) <= 1` no se muestra el slider (nada que filtrar), igual que el resto de los filtros cuando no hay opciones.
- **El banner dinámico ya está** arriba del gráfico principal en Forecast y Propuestas FCST -- desde el 2026-09-14 muestra el nivel de la jerarquía de producto MÁS DESAGREGADO que esté filtrado (`filters.nivel_producto_mas_desagregado(filtros)`: "Gran División: Alimentos" si solo eso está filtrado, "Familia: Arlistán" si el usuario filtró una Familia, etc. -- ver sección de filtros en cascada). Histórico de ventas y Plan Anual no lo tienen (no se confirmó ese banner en sus capturas originales antes de borrarlas).
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

**UOM = `UMG` para todas las series** (histórico, forecast, plan, E+P) **y para master data de cliente** (`customer_sap_ibp`, tabla ZCUSTOMER/IBP-Customer). Solo `CAJ` para:
- Master data de producto (`product_sap_ibp`, tabla ZPRODUCT/IBP-Product).
- Margen Unitario (`margen_unitario_sap_ibp`).

Esto fue un bug real: al principio yo tenía `CAJ` por defecto en todas las series y traía datos mal/vacíos. **No volver a poner CAJ como default de una serie sin confirmarlo contra las queries M.**

**Detalle no obvio ya resuelto**: las queries M reales de master data de cliente NO coincidían entre los dos tableros -- la del Tablero Forecast IBP (`ZCUSTOMER`) pedía `UOMTOID eq 'CAJ'`, la del Tablero Accuracy (`IBP - Customer`) pedía `UOMTOID eq 'UMG'` para la MISMA tabla. `customer_sap_ibp()` (compartida por los dos tableros en esta app) usa `UMG` -- la variante de Accuracy, consistente con la regla general de arriba. Si algún día aparece un caso donde el maestro de clientes trae datos raros/vacíos, este es el primer sospechoso a revisar.

**Margen Unitario NO lleva los filtros de negocio estándar** (`ZVIGENCIA`/`ZAREAFCST`/`ZCLIENTEBOCA`) -- la query M real de `margen_unitario_sap_ibp` es una consulta directa por `UOMTOID`+`PERIODID3`+`CURRTOID` nada más, sin pasar por `_consulta_mensual`/`FILTROS_BASE_*`. No agregarle esos filtros "por consistencia" -- no es como está en el Power BI real.

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

### Simplificación conocida: maestro de producto sin snapshot temporal

La query M real de "IBP - Product" (Tablero Accuracy) filtra el maestro de producto por `PERIODID3` = el mes anterior cerrado (con una regla de corte: si hoy es después del día 5 del mes, usa el mes pasado; si no, el anteanterior) -- es decir, el Power BI real toma una FOTO de la jerarquía de producto a una fecha de corte específica, no "la jerarquía tal como está hoy". `product_sap_ibp()` en esta app **no replica ese snapshot** -- trae la jerarquía sin filtrar por período (igual que la query M del Tablero Forecast IBP, que tampoco lo tiene). En la práctica esto rara vez importa (Gran División/Familia de un SKU no suelen cambiar mes a mes), pero si algún reporte de accuracy da un número raro para un producto que cambió de división/familia recientemente, este es un sospechoso a revisar.

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
- **Plan Anual arranca en enero 2025** (`3_Plan_Anual.py::PLAN_ANUAL_DESDE`): el usuario aclaró que el Plan Anual recién se empezó a conformar desde esa fecha, así que traer períodos anteriores no aporta -- se filtra `df_plan`/`df_ancho` a `Date >= 2025-01-01` ANTES de armar el sidebar (así "Año"/"Mes" tampoco ofrecen años previos como opción). Esto coincide con la query M real de "ZBP" (Plan Anual), que hardcodea `años = {2025, 2026}` -- corrobora que el usuario tiene razón, el Plan Anual del Power BI real tampoco tiene datos antes de 2025. De paso se sacó la sección "Detalle por Año" (tabla al pie), no la pidió el usuario. **El filtro "Año" viene preseleccionado en el año en curso** (`anio_default=[pd.Timestamp.today().year]`, nuevo parámetro opcional de `render_sidebar_filters` -- las otras 3 páginas del Tablero IBP no lo pasan, siguen sin preselección).
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

## Filtros en cascada, filtros unificados y banner dinámico (2026-09-14, a pedido del usuario)

Tres pedidos relacionados, todos en `src/filters.py`:

### Clientes/Productos unificados entre los dos tableros

Antes, `render_sidebar_accuracy` usaba `FILTROS_ACCURACY_CLIENTES`/`FILTROS_ACCURACY_PRODUCTOS` -- un subconjunto más chico (sin Customer Group/Negocio/Demand Family/Product ID) calcado de lo que mostraban las capturas reales del Tablero Accuracy. El usuario pidió que sean los MISMOS filtros que el Tablero Forecast IBP en TODAS las páginas -- se borraron esas dos listas y `render_sidebar_accuracy` reutiliza directo `FILTROS_IBP_CLIENTES`/`FILTROS_IBP_PRODUCTOS`. La única diferencia real entre los dos sidebars sigue siendo "Período" (Año+Mes vs. multiselect de meses).

**Esto reveló que faltaba el merge de maestro de clientes en varias páginas del Tablero Forecast IBP**: página 1 (Histórico de ventas) ya mergeaba `ZAREACOMERCIAL` contra `get_customer_master()`, pero páginas 2, 3 y 4 (Forecast, Plan Anual, Propuestas FCST) no mergeaban nada -- ahí "Clientes" solo mostraba "Area/GC" (la única columna de cliente que ya viene en el grano de las key figures, ver "Grano de cliente" más abajo) y ni "Area Comercial" ni "Customer Group" aparecían como filtro, aunque la config de filtros ya los incluyera. Se agregó el mismo merge a las 4 páginas del Tablero Forecast IBP (más las 3 de Accuracy, que también sumaron `CUSTGROUP` a su merge existente de `ZAREACOMERCIAL`) -- ver ``cache.mapa_area_comercial`` más abajo, que es la función que arma ese merge de forma segura.

### Bug real encontrado en el camino: fan-out de filas al mergear el maestro de clientes por ZAREAGC

El patrón de merge que ya existía antes de esta sesión (`df_master[["ZAREAGC","ZAREACOMERCIAL"]].drop_duplicates()` + `merge(..., on="ZAREAGC")`) asume que ZAREAGC determina unívocamente a ZAREACOMERCIAL -- **falso en los datos reales**: confirmado contra el tenant, 13 de 34 valores de ZAREAGC agrupan clientes de MÁS DE UNA ZAREACOMERCIAL (`customer_sap_ibp()` trae el maestro a grano CUSTID, y ZAREACOMERCIAL/CUSTGROUP son atributos de CADA CLIENTE, no de su ZAREAGC). Agregar `CUSTGROUP` al mismo patrón (18 de 34 ZAREAGC con más de un CUSTGROUP) lo empeoró mucho: hasta **31 combinaciones distintas bajo un mismo ZAREAGC** (ej. "Litoral"). `drop_duplicates()` sobre esas columnas deja esas 31 filas, y el `merge(on="ZAREAGC")` posterior duplica cada fila de la serie original una vez por cada una -- inflando cualquier suma (Entregado, Forecast, Accuracy) que no filtre explícitamente por Cliente, y de paso volviendo carísimas las operaciones downstream (`melt`/`groupby` sobre un DataFrame ~30x más grande de lo esperado -- así fue como se lo detectó: la página "Forecast" pasó de tardar ~20s a colgarse varios minutos en cuanto se agregó el merge con CUSTGROUP).

**Fix**: `cache.mapa_area_comercial(df_master)` colapsa el maestro a **una fila por ZAREAGC**, tomando la moda (valor más frecuente por cantidad de CUSTID) de `ZAREACOMERCIAL`/`CUSTGROUP` -- nunca hace fan-out, porque el merge resultante es siempre 1:1 o N:1 (nunca N:M). Es una aproximación deliberada (un ZAREAGC que reparte clientes entre varias Area Comercial/Customer Group solo muestra la predominante en el filtro), pero preserva la integridad de las sumas, que importa más -- consistente con la simplificación de grano ya aceptada en el resto de la app (`CUST_ATTRS_AREAGC`, "grano de cliente: SOLO ZAREAGC"). **Las 7 páginas usan esta función ahora -- no volver al patrón `drop_duplicates()` + merge directo sobre el maestro completo, es el mismo bug.**

### Filtros en cascada dentro de "Clientes"/"Productos"

`_multiselects()` ahora recorta el DataFrame después de cada selección, así que el multiselect SIGUIENTE de la misma sección solo ofrece las opciones que efectivamente coexisten con lo ya elegido (ej.: elegir "Mayoristas" en Area Comercial deja en Area/GC solo sus ~6 cuentas -- DIARCO, MAKRO, MAXICONSUMO, NINI, VITAL, YAGUAR -- verificado en vivo). El orden de `FILTROS_IBP_CLIENTES`/`FILTROS_IBP_PRODUCTOS` importa: tiene que ir de más agregado a más desagregado (Area Comercial > Area/GC > Customer Group; Gran Negocio > Negocio > Demand Family > Familia > Product ID, con Categoria intercalada aunque no sea parte de la jerarquía SAP real). "Gran División" sigue siendo un selectbox aparte (`_selectbox_gran_division`, ver sección de reglas de negocio) que también recorta el DataFrame ANTES de la cascada de "Productos".

### Banner dinámico según el nivel más desagregado filtrado

Antes el banner de Forecast/Propuestas FCST era fijo: `f"Gran División: {division_actual}"`. Ahora `filters.nivel_producto_mas_desagregado(filtros)` recorre `JERARQUIA_PRODUCTO` (Gran División > Gran Negocio > Negocio > Demand Family > Familia > Product ID -- sin Categoria, que no es parte de esta jerarquía) de más desagregado a más agregado y devuelve `"Etiqueta: valores"` del primer nivel con selección explícita -- si el usuario filtró una Familia, el banner pasa a mostrar "Familia: X" en vez de "Gran División: Alimentos" (verificado en vivo). Como "Gran División" es un selectbox siempre-seleccionado, la función siempre devuelve algo (nunca `None`) salvo DataFrame vacío/sin la columna.

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
11. **Merge del maestro de clientes por ZAREAGC generaba fan-out de filas (hasta 31x)** — el patrón `df_master[cols].drop_duplicates()` + `merge(on="ZAREAGC")` asumía que ZAREAGC determina a ZAREACOMERCIAL/CUSTGROUP, pero esos son atributos de CUSTID en el maestro real (13/34 ZAREAGC con más de una ZAREACOMERCIAL, 18/34 con más de un CUSTGROUP). Se hizo evidente al agregar CUSTGROUP al merge (página "Forecast" pasó de ~20s a colgarse minutos). Fix: `cache.mapa_area_comercial()` colapsa a 1 fila por ZAREAGC (moda de cada atributo) antes de mergear. Ver sección "Filtros en cascada..." más abajo.

## Estructura del repo

```
app.py                  → landing, page_links a las páginas
pages/                  → 1 archivo por página del Streamlit multipage (numeradas para fijar el orden en el sidebar)
src/
  config/
    dynamics_config.py  → root_path
    settings.py         → carga ibp.env / aws.env / aws_credentials.env / s3_sagemaker.env
  data/
    consulta_odata.py           → cliente HTTP a SAP IBP OData (con el fix de SSL acotado)
    extract_odata_sap_ibp.py    → todas las funciones de key figures + filtros estándar
    master_data_sap_ibp.py      → jerarquías de producto/cliente (sin PERIODID3, rápido)
    aws_ejecutar_query.py       → cliente Athena (boto3, sin el fix de SSL global)
    aws_categoria.py            → join liviano Athena para grupo_material_3
    aws_s3_experimentos.py      → listado S3 de exp/<usuario>/... (Experimentos SageMaker, credenciales propias)
    model_tar_explorer.py       → explora un model.tar (local o descargado) sin deserializar .pkl
    demo_data.py                → datos sintéticos, mismo esquema que cache.py
  cache.py              → wrappers st.cache_data + get_or_demo (capa que las páginas consumen)
  accuracy.py           → fórmulas DAX reales (accuracy/bias/segmentación)
  filters.py            → sidebar de filtros compartidos
  charts.py             → helpers Plotly (paleta del skill de dataviz)
sample_data/sagemaker/  → (gitignorada) .tar de ejemplo para "Experimentos SageMaker" en modo local
tablas_forecast_ibp.txt              → queries M reales, Tablero Forecast IBP (documentación, no gitignoreado)
tablas_forecast_accuracy_ibp.txt     → queries M reales, Tablero Forecast Accuracy IBP (ídem)
*.pbix                  → los dos Power BI originales, de referencia
```

## Experimentos SageMaker (2026-09-15) -- no viene de ningún Power BI, feature nueva a pedido del usuario

Tablero nuevo (`pages/9_Experimentos_SageMaker.py`), sin relación con los dos tableros de demanda de arriba -- visualiza las pruebas de forecast que el equipo de Supply corre en AWS SageMaker, guardadas en el bucket S3 `ibp-forecast-sagemaker-data-595365649575`, prefijo `ibp-forecast-mensual/exp/<usuario>/{input,models,predictions,processed}`. Dentro de `models/`, cada corrida (`ibp-training-<usuario>-molinos-<timestamp>/`) tiene una carpeta `output/` con un `model.tar` (`reports/`, `trained_models/*.pkl`, dataset `preprocessed_forecast_mensual`).

Decisiones de diseño, con su porqué:

- **Independiente del gate de `datos_cargados`** (`app.py`): a diferencia del resto de páginas, que no se registran en `st.navigation` hasta que termina la precarga de SAP IBP/Athena (`0_Inicio.py`), esta página no usa esos datos -- se registra siempre, en su propia sección de sidebar. Si se agrega otra página que tampoco dependa de la precarga de demanda, mismo patrón (agregarla al `st.Page(...)` que se arma fuera del `if st.session_state.get("datos_cargados")`).
- **Credenciales AWS propias, en `s3_sagemaker.env`** (no reutiliza `aws.env`/`aws_credentials.env` de Athena): la cuenta (`AI_Platform_DEV`) y el rol (`MRP_Analistas_IBP_AWS`) son distintos de los que usa Athena. `src/config/settings.py` carga este tercer `.env` con sus propias variables (`AWS_PROFILE_SAGEMAKER`/`AWS_REGION_SAGEMAKER`/credenciales explícitas `*_SAGEMAKER`, `AWS_S3_SAGEMAKER_BUCKET`, `AWS_S3_SAGEMAKER_PREFIX`) y `aws_s3_experimentos.py` arma su propia `boto3.Session` (`_crear_sesion_aws_sagemaker`), en vez de reusar `_crear_sesion_aws` de `aws_ejecutar_query.py`.
- **`AWS_S3_SAGEMAKER_PREFIX` NO incluye `/exp`** -- `aws_s3_experimentos.py::_prefijo_exp()` lo agrega (`f"{prefix}/exp/"`). Si se cambia esa función, ojo con no duplicar el segmento `exp` en el prefijo resultante.
- **Rol `MRP_Analistas_IBP_AWS` sin `s3:GetObject` todavía** (solo `s3:ListBucket`, confirmado por el usuario) -- por eso la navegación S3 (`listar_usuarios`/`listar_carpetas_usuario`/`listar_entrenamientos`/`listar_contenido`, todas con `list_objects_v2`) funciona en vivo, pero `descargar_objeto` (`get_object`) va a fallar con `ClientError` (AccessDenied) hasta que se sumen permisos -- la página lo captura y muestra un mensaje explícito en vez de dejar romper la excepción, ofreciendo el modo local como alternativa.
- **Modo local (`sample_data/sagemaker/`, carpeta gitignorada)**: mientras no haya `s3:GetObject`, el desarrollo/prueba de la parte visual (parseo de `model.tar`, previsualización de reports/dataset) se hace contra una copia puesta a mano ahí -- la página escanea `*.tar` en esa carpeta y ofrece un selector. `model_tar_explorer.py` funciona igual sobre bytes descargados de S3 o sobre un archivo local (`abrir_tar` acepta ambos), así que el día que el permiso llegue, el botón "Descargar y explorar" de la página reusa el mismo código de exploración sin cambios.
- **Los `.pkl` de `trained_models/` NUNCA se deserializan** (`pickle.load`/`joblib.load`) -- deserializar un pickle ejecuta código arbitrario, y estos archivos vienen de un bucket compartido entre varios data scientists, no de una fuente controlada. `model_tar_explorer.py` solo lista nombre/tamaño de esos archivos. Si en algún momento hace falta inspeccionar un modelo de verdad, ese es un problema aparte (sandboxing) -- no agregar un `pickle.load` directo acá.
- **Estructura interna del `model.tar` confirmada (2026-09-15) contra un `model.tar.gz` real** puesto en `sample_data/sagemaker/`: `reports/*.csv` (4 archivos: `accuracy_forecast_mensual`, `modelos_forecast_mensual`, `resumen_niveles_planificacion`, `mejor_nivel_planificacion_por_entidad`), `trained_models/<GRANO>/forecaster_<GRANO>_<valor>.pkl` (subcarpetas por grano de planificación -- `PRDID`/`PRDFAMILY`/`ZBIGBUSINESS`/`ZINDFAMILY`/`ZBRAND`, no una lista plana) y `preprocessed_forecast_mensual.csv` en la raíz del tar. La categorización de `model_tar_explorer.py::listar_contenido` (por prefijo/substring) ya cubre esto sin cambios -- funciona igual con los `.pkl` anidados en subcarpetas porque matchea por `startswith("trained_models/")`, no por profundidad.
- **Los `.csv` de este `.tar` vienen delimitados por `;`, no por `,`** -- `model_tar_explorer.py::leer_tabla` usa `pd.read_csv(sep=None, engine="python")` (autodetección) por esto, no asumir coma si se toca esa función.
- **El archivo de SageMaker es `.tar.gz` (comprimido), no `.tar` plano** -- `tarfile.open(...)` en modo `"r"` (el que usa `abrir_tar`) detecta la compresión sola, así que no hace falta lógica aparte; lo que sí hubo que ajustar es el glob de la página (`pages/9_Experimentos_SageMaker.py`), que busca `*.tar`, `*.tar.gz` y `*.tgz` en `sample_data/sagemaker/`, no solo `*.tar`.
- **En S3 el archivo se llama `model.tar.gz`, no `model.tar`** (confirmado contra un `output/` real vía listado en vivo) -- el botón "Descargar y explorar" (`pages/9_Experimentos_SageMaker.py`) matchea por `nombre.startswith("model.tar")`, no por nombre exacto, para no repetir el bug de buscar `"model.tar"` a secas.

### Curvas de Backtesting / Nivel de Planificación / Feature Importance (2026-09-15) -- 3 páginas más, mismo patrón que arriba: pedido puntual del usuario, no viene de ningún Power BI

Comparten el "entrenamiento activo" (`src/experimentos_sagemaker_estado.py`, `st.session_state["sm_tar_activo"]`): se elige/descarga un `model.tar` una sola vez en "Experimentos SageMaker" (`pages/9`), y `requerir_tar_activo()` al principio de `pages/10`/`11`/`12` lo reusa -- si no hay ninguno elegido, muestra un aviso + `page_link` de vuelta a `pages/9` y corta con `st.stop()`, en vez de pedir que se vuelva a elegir en cada página. Solo se guarda un **path a archivo local** en session_state (un `.tar` bajado de S3 se vuelca primero a un temporal vía `tempfile.NamedTemporaryFile(delete=False)`) -- nunca bytes ni un `tarfile.TarFile` abierto, para no depender de que un file handle siga vivo entre reruns de Streamlit.

**El join entidad→nivel→valor es el problema central de "Nivel de Planificación" y "Feature Importance"** (`src/nivel_planificacion.py`): `reports/mejor_nivel_planificacion_por_entidad.csv` solo dice PRDFAMILY + nivel elegido (ej. "ZBIGBUSINESS"), no A QUÉ VALOR de ese nivel pertenece la entidad -- eso se resuelve contra el dataset (`preprocessed_forecast_mensual`, que sí tiene las 5 columnas de jerarquía por fila). Es 1:1 cuando el nivel elegido es la propia `PRDFAMILY`, pero puede ser 1:muchos en niveles más finos (una familia tiene varios PRDID) -- `valores_de_nivel()` siempre devuelve una lista, nunca un valor único, y "Feature Importance" itera esa lista mostrando un expander por cada `.pkl` candidato (no promedia/oculta -- transparencia sobre qué se está mirando). "Nivel de Planificación" sí promedia el accuracy cuando hay varios valores (`resumen_nivel_elegido()`), documentado como aproximación en la propia página, no un accuracy exacto.

**Convención de nombre de archivo confirmada contra el `.tar` real**: `trained_models/<NIVEL>/forecaster_<NIVEL>_<valor con espacios reemplazados por "_">.pkl` (`nivel_planificacion.py::nombre_archivo_pkl`) -- ej. la entidad "Cocinero Mezcla" resuelve a "Aceites Tradicionales" en nivel ZBIGBUSINESS, así que el archivo a buscar es `trained_models/ZBIGBUSINESS/forecaster_ZBIGBUSINESS_Aceites_Tradicionales.pkl`, no un archivo con el nombre de la entidad misma. Si el nombre no calza (`miembros_por_nombre.get(...)` da `None`), la página lo dice explícitamente en vez de fallar -- no se armó un fallback de búsqueda difusa a propósito, para no ocultar un desalineamiento real entre el CSV y `trained_models/` si algún día aparece.

#### Feature Importance: deserializar los .pkl reales resultó mucho más frágil de lo esperado -- arquitectura de subproceso con un segundo Python

Decisión tomada junto con el usuario: deserializar (`joblib.load`) es una excepción DELIBERADA a la regla general de "nunca deserializar .pkl de este bucket" (ver más arriba) -- justificada porque estos modelos son de la propia pipeline de SageMaker del equipo, no de un origen público/no confiable. Aun así, hacerlo andar en la práctica requirió resolver, en orden, estos hallazgos (todos verificados contra el `.tar` real de `sample_data/sagemaker/`, no hipotéticos):

1. **No es pickle plano, es `joblib.dump`** -- `pickle.loads()` directo "funciona" sin error pero devuelve basura (un `numpy.ndarray` de 1 elemento envolviendo un string suelto, ej. `"ADJUSTEDACTUALSQTY"`) en vez de lanzar una excepción clara. Esto es EL síntoma más engañoso de todos: parece que cargó bien pero el objeto no tiene nada que ver con el modelo real. `joblib.load()` es el loader correcto (`model_deserializer.py`/`scripts/feature_importance_subproceso.py` lo usan siempre, nunca `pickle.load` directo).
2. **La versión de skforecast/xgboost/numpy importa, y bastante** -- el pickle referencia clases (`skforecast.recursive._forecaster_recursive.ForecasterRecursive`, `xgboost.sklearn.XGBRegressor`) cuyo layout interno cambia entre versiones. Con versiones "parecidas" (última de PyPI, o hasta la build exacta que aparece en un traceback de error) el booster de XGBoost falla con `XGBoostError: Expecting: """, got: ...` al reconstruirse -- un error de formato binario/JSON, no de import, mucho más difícil de diagnosticar. La única combinación que funcionó de punta a punta fue pinear EXACTO contra `requirements_fcst.txt` (el manifiesto real del repo de training, que el usuario pasó): `numpy==2.0.2`, `scikit-learn==1.6.1`, `xgboost==2.1.3`, `skforecast==0.16.0`, `joblib==1.3.2` (más `lightgbm==4.5.0`/`catboost==1.2.8`, ver punto 4).
3. **`numpy==2.0.2` no tiene wheel para Python 3.13** (el venv principal de la app) y falla al compilar desde fuente por falta de compilador C en la máquina -- el training usó Python 3.10.20 (visible en metadata embebida en el pickle). Por eso existe `.venv310/`, un venv SEPARADO con Python 3.10 (instalado vía `winget install --id Python.Python.3.10 --scope user`), solo para esto -- no se intentó forzar compatibilidad en el venv principal (3.13) porque además del numpy, cualquier ajuste futuro de versión de xgboost/skforecast en el training rompería de nuevo el venv principal si estuviera mezclado ahí.
4. **El usuario aclaró que el regressor interno puede ser xgboost, lightgbm O catboost** (no siempre xgboost) -- `requirements_fcst.txt` ya trae los 3 pineados, y `scripts/feature_importance_subproceso.py` no asume el tipo: usa `forecaster.get_feature_importances()` (método propio de skforecast, agnóstico al regressor de adentro) como primera opción, con fallback genérico a `regressor.feature_importances_` si ese método no existe.
5. **`NameError: name 'pkg_resources' is not defined` al cargar** -- versiones recientes de `setuptools` (85+) dejaron de incluir `pkg_resources`, que el código de carga de skforecast 0.14-0.16 asume disponible. Fix: `pip install "setuptools==70.0.0"` en `.venv310` (no en el venv principal, que no lo necesita).
6. **La instalación de paquetes en `.venv310` dio `SSLError: self-signed certificate in certificate chain`** -- el mismo proxy corporativo MITM que documenta `settings.py` para `requests`, pero acá afectando a `pip` (que no usa el fix de `truststore` de la app). Workaround puntual, solo para instalar paquetes: `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org ...`.
7. **Arquitectura resultante**: el venv principal (3.13) NUNCA importa skforecast/xgboost/lightgbm/catboost -- `src/data/model_deserializer.py::extraer_feature_importance(pkl_bytes)` escribe los bytes a un archivo temporal y lanza `scripts/feature_importance_subproceso.py` como **subproceso** con `.venv310/Scripts/python.exe`, capturando un único JSON por stdout (`{"ok": true, "importancias": [...]}` o `{"ok": false, "error": "..."}`). Esto aísla completamente los conflictos de versión: si mañana cambia la versión de skforecast/xgboost del training, solo hay que reinstalar `.venv310` (siguiendo el `requirements_fcst.txt` actualizado), sin tocar el venv ni el código de la app. `model_deserializer.venv310_disponible()` hace que la página muestre un aviso claro en vez de romper si `.venv310/` no existe (setup manual, no se crea solo -- instala una versión de Python distinta en la máquina, no es algo para automatizar sin que el usuario lo pida).

## Semáforo de accuracy, alertas accionables y KPIs nuevos (2026-09-16) -- de una revisión de producto, no del Power BI real

Se armó un artifact con ~38 recomendaciones (KPIs nuevos, alertas con umbral, cambios visuales) revisando toda la app página por página; el usuario marcó 28 para implementar, agrupadas en 7 tandas y ejecutadas en orden. Dos quedaron **explícitamente fuera de alcance**, no son "pendientes olvidados":
- "Delta en todas las tarjetas KPI" (genérico) -- el usuario prefirió KPIs específicos por página en su lugar (ver más abajo, cada página tiene el suyo).
- "Alerta de drift en Feature Importance" -- depende de comparar importancias entre varias corridas, bloqueado por lo mismo que "Comparar accuracy entre corridas" (ver `aws_s3_experimentos.py`, sin `s3:GetObject`) + necesitaría guardar histórico entre corridas, que no existe. Si se retoma, empezar por ahí.

### `src/alertas.py` -- semáforo de 3 niveles, separado de `accuracy.py` a propósito

Capa de PRESENTACIÓN (clasifica/colorea) sobre las métricas que `accuracy.py` ya calcula -- no duplica fórmulas. Cortes de accuracy (**verde >80%, amarillo 70-80%, rojo <70%**) fueron ajustados a pedido del usuario (2026-09-16) y **ya NO coinciden** con los de `SEGMENTOS_INFO` (80%/60%, fórmula DAX real de segmentación de SKU, no se tocan); si se ajustan de nuevo, actualizar también `pages/8_Glosario.py` ("Semáforo de Accuracy"), que los documenta como referencia única para todas las páginas. Bias usa un umbral separado (**±5%**, antes ±10%) y ya NO tiene color por dirección: dentro de la banda es verde, fuera es rojo simétrico en ambas direcciones (antes sobreestimación coloreaba rojo y subestimación azul; la dirección sigue distinguiéndose en el TEXTO del badge, no en el color).

Funciones clave: `nivel_accuracy`/`nivel_brecha` (clasificación), `nivel_bias` (clasificación simétrica bueno/malo, sin nivel "medio"), `color_accuracy`/`color_bias` (CSS para `Styler.map`), `estilo_pivot_metricas` (para `Styler.apply(axis=1)` en tablas con Accuracy Y Bias mezclados por fila, ej. "Evolución Mensual" de Reporte Accuracy -- distingue por el nombre de la fila, no por columna), `resaltar_fila_critica` (colorea la fila entera, ej. Segmento "3.2" en Segmentación SKU), `etiqueta_bias`/`badge_nivel` (texto+color para badges fuera de tablas, `etiqueta_bias` distingue sobre/subestimación en el texto aunque el color sea el mismo).

`src/charts.py` -- nuevos: `BUENO`/`MEDIO`/`MALO` (reusan slots ya existentes de `CATEGORICAL`/`NEGATIVO`, no suman tonos), `hex_a_rgba` (antes privada `_hex_a_rgba`, ahora pública porque `alertas.py` también la usa), `boton_descarga_csv` (wrapper de `st.download_button`, ninguna tabla tenía forma de salir de la app hasta ahora), `ranking_semaforo` ahora acepta `hover_data` opcional (usado en Ranking Clientes para mostrar Bias al pasar el mouse sobre el semáforo de Área/GC).

### Dos bugs reales encontrados verificando contra datos de producción (no hipotéticos)

1. **`fig.add_vline(x=...)` rompe con un eje de fechas en una figura armada a mano** (`go.Figure()` con traces manuales, como `charts.area_superpuesta` -- no pasa en gráficos hechos con `px`): tanto pasando un `pd.Timestamp` (`TypeError: Addition/subtraction of integers and integer-arrays with Timestamp...`) como un string de fecha (`TypeError: unsupported operand type(s) for +: 'int' and 'str'`) -- bug de Plotly calculando la posición de la shape contra ese tipo de eje. Encontrado en `pages/2_Forecast.py` (línea vertical "Mes en curso"). **Fix**: `fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper", ...)` + `fig.add_annotation(...)` en vez de `add_vline` -- no pasa por ese cálculo. Si se agrega una línea/marca vertical a cualquier otro gráfico de `area_superpuesta`/`bias_bar_chart` (armados con `go.Figure()`, no `px`), usar `add_shape`, no `add_vline`.
2. **`df.groupby([], as_index=False).agg(...)` -- `ValueError: No group keys passed!`** en pandas: para un "total general" (ej. Accuracy/Bias agregando TODAS las divisiones en Reporte Accuracy/Inicio) no se puede pasar `group_cols=[]` a `acc_bias_consensuado`. Workaround usado en varios lados: `df.assign(_Total="Total")` + `acc_bias_consensuado(df, ["_Total"])`, tomar `.iloc[0]`. No se tocó `accuracy.py` para esto -- es un detalle de caller, no de la fórmula.

### Qué se agregó, por página (grounded en el código real, no repetir la fórmula acá -- ver el archivo)

- **Inicio**: "Resumen ejecutivo" (4 KPI: Accuracy/Bias Consensuado general, Ventas vs. Plan Anual año en curso, cantidad SKU Segmento 3.2) + banner 🟢/🔴 si algo cruza umbral crítico. Reusa el cache ya tibio de `FUENTES`, no dispara queries nuevas.
- **Histórico de ventas**: KPI "Promedio % Variación Mensual" (ruidoso) reemplazado por MMAA (Mismo Mes, Año Anterior, antes rotulado "YoY" -- ver retoque 2026-09-18 más abajo) del último mes cerrado; alerta `st.error` si la variación mes a mes cae ≤-15%; Mix Productos de pie a barra horizontal (más legible con 8 categorías).
- **Forecast**: línea "Mes en curso" en el área (ver bug de `add_vline` arriba).
- **Plan Anual**: badge 🟢/🟡/🔴 de brecha (antes solo el delta binario de `st.metric`). (El KPI "Proyección run-rate" que se agregó acá se sacó de nuevo el 2026-09-18 -- ver retoque más abajo, el usuario dijo que no le servía por ahora.)
- **Propuestas FCST**: los 2 KPIs (duplicados de Forecast) reemplazados por uno propio, "Ajuste Consensuado vs. Estadístico" -- ambas columnas (`ZFCSTESTIMADO`, `STATISTICALFORECASTQTY`) ya estaban en `df_ancho_f`, no hizo falta fuente nueva. `df_ep`/`get_entregado_pendiente` se sacó de esta página (quedó sin consumidor).
- **Reporte Accuracy**: semáforo en las 2 tablas pivot (`estilo_pivot_metricas`); cards de resumen general arriba de todo; badge de Bias direccional; tabla nueva "Top 10 SKU peor Accuracy".
- **Segmentación SKU**: filas de Segmento 3.2 resaltadas (`resaltar_fila_critica`); columna+selector "Ordenar por: Entrega/Impacto" (`Impacto = Margen Total SKU × |Desvío Accuracy|`).
- **Ranking Clientes**: semáforo también en la tabla "Área Comercial" (antes solo el gráfico de Área/GC lo tenía); Bias agregado a ambos; columna "Δ pp. vs. período anterior" (ventana previa del mismo largo que "Meses a analizar", vía `periodos_terminando_en`) con texto rojo si cae ≤-10pp.
- **Glosario**: sección "Semáforo de Accuracy" documentando los cortes de `alertas.py`.
- **Experimentos SageMaker** (`pages/9_Experimentos_SageMaker.py`): "Último entrenamiento hace N días" por usuario (solo `s3:ListBucket`, no necesita descarga -- probado contra S3 real: 17 días para `aiscarm-molinos`); "Comparar accuracy entre corridas" (S3 en vivo Y modo local) -- en S3 falla con el mismo mensaje ya conocido de falta de `s3:GetObject`, probado end-to-end.

Todo lo de arriba se probó contra **datos reales de producción** (no solo `demo_data.py`) -- esta sesión tenía `ibp.env`/`aws.env` configurados de verdad.

## Reporte de Resultados mensual automático (2026-09-16) -- botón en Inicio, no viene del Power BI real

Botón "📄 Generar reporte detallado" en `pages/0_Inicio.py` -- replica automáticamente el "Reporte de Resultados - Forecast <Mes>" que el equipo arma a mano cada mes (histórico real en `reports/`, gitignorado -- documentos de negocio reales, no se commitea). Mismo patrón de separación que `alertas.py`/`accuracy.py`: `src/reporte_mensual.py` (solo cálculo, reusa `accuracy.py`), `src/reporte_mensual_narrativa.py` (solo redacción de los párrafos), `src/generador_reporte_docx.py` (solo layout .docx + conversión a PDF vía `docx2pdf`/Word COM).

**Validado contra el reporte real de agosto** (`reports/2026.zip`): los números de Accuracy/Bias por Gran División coinciden casi exactamente (81%/75% Alimentos, 75%/51% Bodegas, 59%/36% Snacks -- diferencias de 0-1pp, redondeo) -- confirma que `reporte_mensual.py` reusa bien las fórmulas de `accuracy.py`.

**Una heurística con rugosidad conocida, a mejorar si el usuario la nota**:
1. **Resumen ejecutivo (Inicio) y el reporte anclan Accuracy/Segmento al último mes CERRADO** (no una ventana de varios meses) -- distinto del sidebar de Accuracy (`MESES_ANALISIS_DEFAULT=4`). Ventas vs. Plan Anual sigue siendo YTD (acumulado del año). Decisión explícita del usuario, no un descuido.
2. **`texto_destacados` (Gran Negocio) puede resaltar un "peor del ranking" con 0% por volumen irrelevante** (ej. "Tienda Molinos" con Accuracy 0%) -- no filtra por volumen mínimo antes de armar el bottom-N. Si molesta, agregar un piso de volumen (`Historico`/`Actual`) antes de `nsmallest` en `reporte_mensual_narrativa.texto_destacados`.

("Grandes Cuentas" por top-N-por-volumen -- que se colaba con zonas geográficas/canal -- ya NO es una heurística, ver más abajo: se reemplazó por la lista curada real `reporte_mensual.GRANDES_CUENTAS`.)

`assets/molinos_logo.png` -- logo real extraído de `word/media/image9.png` del `.docx` histórico, sí se commitea (marca de la empresa, no dato de negocio sensible).

**Libre de Gluten -- filtro acotado + fila de indicadores globales (2026-09-16, a pedido del usuario).** El filtro original (solo `PRDDESCR` conteniendo "LDG") sobre-incluía -- ahora es AND de dos condiciones: SKU de uno de los `reporte_mensual.LDG_GRANDES_NEGOCIOS` (`Refrigerados`, `Pasta Seca`, `Rebozador`, `Premezclas`, `Horneables` -- únicos Gran Negocio con líneas LDG reales, confirmados contra el maestro) Y `PRDDESCR` con "LDG" o "GLUTEN" (cubre variantes tipo "Libre de Gluten"/"Sin Gluten", no solo la sigla). Además excluye SKU sin ningún accuracy calculable en el mes (sin Actual/Forecast, típicamente de baja) -- a pedido del usuario, "que traiga algo de accuracy". Además, `accuracy_libre_de_gluten` ahora devuelve `(tabla_skus, indicadores_globales)`: `indicadores_globales` es un `dict` con Accuracy Y Bias (Consensuado/Estadístico) + Cons vs Est (U6M incluido) de TODOS esos SKU agregados como un solo grupo, separado a propósito de `tabla_skus` -- si se mezclara en la misma tabla que consume `texto_destacados`, el ranking de líderes/rezagados lo tomaría como "otro SKU más". Se renderiza igual como la primera fila (en negrita, con columnas de Bias que Gran Negocio no tiene) de la MISMA tabla en el .docx vía `_tabla_ranking(..., fila_total=...)` -- `incluir_bias` es un flag nuevo de `_tabla_accuracy_nivel`, default `False` para no tocar la tabla de Gran Negocio.

**Área Comercial / Área Gran Cuenta -- abreviaturas, exclusiones y lista curada real (2026-09-16, a pedido del usuario).** Tres constantes nuevas en `reporte_mensual.py`, aplicadas en `pages/0_Inicio.py` antes de armar `datos_reporte` (renombra columnas de las tablas ya pivotadas, `generador_reporte_docx.py` no sabe nada de esto -- solo renderiza los nombres de columna que recibe):
- `AREA_COMERCIAL_EXCLUIR = {"Otros", "Tienda Molinos"}` -- se filtra `df_producto_area` ANTES de llamar `accuracy_bias_area` (no son canales reales).
- `AREA_COMERCIAL_ABREVIATURAS` -- `Supermercados`→SPM, `Mayoristas`→MAY, `Minoristas GBA`→MIN GBA, `Interior`→INT (`DxGBA` queda igual), aplicado con `.rename(columns=...)` sobre las tablas ya calculadas.
- `GRANDES_CUENTAS` -- reemplaza la vieja `top_grandes_cuentas`/`GRANDES_CUENTAS_EXCLUIR` (heurística de top-N por volumen, ELIMINADA): ahora es la lista curada real de 12 cuentas dada por el usuario (nombres verificados contra el filtro real de Area/GC del tablero), que sirve A LA VEZ de `areas_incluir` (filtra a solo esas 12) Y de mapa de abreviatura (CARREFOUR→CRF, CENCOSUD→CENCO, CHANGOMAS→CHANGO, COTO, DIA, DIARCO→DRC, LA ANONIMA→LA ANM, MAKRO→MKO, MAXICONSUMO→MXC, NINI, VITAL→VTL, YAGUAR→YGR).

**Márgenes del .docx angostos (2026-09-16, a pedido del usuario).** `generar_docx` fija 1.5cm arriba/abajo y 1.3cm izquierda/derecha en las secciones del documento (antes usaba el default de Word, ~2.54cm) -- las tablas de "Evolución Mensual"/Área Comercial/Gran Cuenta son anchas (hasta 12+ columnas), el margen angosto ayuda a que entren sin que Word las achique demasiado.

**Cuatro ajustes más (2026-09-17, a pedido del usuario):**
- **Gran Negocio también filtra por `_solo_con_accuracy`** (mismo helper nuevo que ya usaba Libre de Gluten, extraído en `reporte_mensual.py`) -- antes mostraba negocios sin ningún accuracy calculable en el mes (todo "—"), ahora solo los que tienen algo de dato.
- **Bug real corregido: Bias por SKU en Libre de Gluten no aparecía** -- `tabla_skus` en `accuracy_libre_de_gluten` no pasaba `incluir_bias=True` a `_tabla_accuracy_nivel` (solo la fila Total lo tenía), así que cada fila de SKU mostraba "—" en Bias Cons./Bias Estad. aunque el encabezado ya las incluía (por `fila_total`). Fix de una línea.
- **Bias extremo capado a `< -1000%`/`> +1000%`** en Área Comercial y Área Gran Cuenta (`_formato_bias`/`UMBRAL_BIAS_EXTREMO` en `generador_reporte_docx.py`, flag `capar_extremos` de `_tabla_pivot_semaforo`) -- Bodegas/Snacks con Actual casi 0 en alguna área disparan Bias de miles de % (no es un error de cálculo, es la fórmula `Forecast/Actual - 1` con denominador ínfimo); el número exacto ahí no aporta. NO se capa en Gran División (no le pasa esto).
- **Título del .docx incluye el año** -- `reporte_mensual_narrativa.anio_mes(periodid3)` (nueva función, mismo patrón que `nombre_mes`) se pasa como `datos["anio"]` desde `pages/0_Inicio.py`; el nombre del archivo descargado sigue sin año (no se pidió).

**Cinco retoques de formato más (2026-09-17, a pedido del usuario):**
- **Logo en el HEADER del .docx, no en el cuerpo** -- `_agregar_logo` ahora escribe en `doc.sections[0].header` (con `is_linked_to_previous = False`, si no Word puede ignorar el contenido del header de la 1ra sección) en vez de `doc.add_picture` en el cuerpo -- así el título queda más arriba, sin el párrafo de imagen antes.
- **Accuracy Gran División en formato punteo** -- `texto_accuracy_gran_division` (`reporte_mensual_narrativa.py`) ahora devuelve `list` (un bullet por división) en vez de un string único con `"\n"` -- mismo patrón que `texto_destacados`. `generar_docx` usa `_bullets(...)` en vez de `_parrafo(...)` para esa sección. (El equivalente para Bias, `texto_bias_gran_division`, se agregó y se borró el mismo día -- ver retoque siguiente, ya no lleva narrativa.)
- **Ancho de columnas fijo (`_fijar_ancho_columnas`, nuevo helper)** -- por default Word estira una tabla al ancho completo de la página (autofit), lo que con pocas columnas y texto corto deja filas muy "achatadas" (finísimas de punta a punta). Hay que fijar el ancho en CADA celda de la columna, no solo en `table.columns[i].width` (si no, Word ignora el ancho de columna cuando las celdas ya tienen uno explícito distinto -- bug conocido de python-docx). Aplicado en:
  - `_tabla_ranking` (Gran Negocio y Libre de Gluten): sin `col_desc` (Gran Negocio) usa anchos compactos (~13.6cm total, "más cuadrada"); con `col_desc` (Libre de Gluten) la columna Descripción queda en 7cm para que la descripción del SKU no se parta en varios renglones, achicando las demás columnas.
  - `_tabla_pivot_semaforo` con el nuevo flag `compacto` (solo en Área Comercial, NO en Gran División/Gran Cuenta -- no se pidió ahí y Gran Cuenta ya necesita las 12 columnas anchas).

**Formato final del .docx acordado con el usuario (2026-09-17) -- pasó un `reporte_final.docx` editado a mano como referencia** (gitignoreado, documento de negocio real, no se commitea -- mismo criterio que `reports/`/`sample_data/`). Comparado ese archivo contra lo que generaba la app (`doc.element.body` recorrido a mano, ya que `doc.paragraphs` no intercala las tablas) para encontrar las diferencias exactas y replicarlas en `generar_docx`:
- **Bias Gran División, Libre de Gluten y Área Gran Cuenta van SIN texto narrativo/explicativo antes de la tabla** -- Accuracy Gran División y Gran Negocio SÍ mantienen sus bullets. `pages/0_Inicio.py` ya no calcula `texto_bias_division` ni `texto_ldg` (ambos se sacaron de `datos_reporte`); `texto_bias_gran_division` se borró de `reporte_mensual_narrativa.py` por quedar sin ningún caller.
- **`texto_destacados` tiene un nuevo flag `incluir_rezagados` (default `True`)** -- Gran Negocio lo llama con `incluir_rezagados=False`: el bullet "En la parte baja del ranking: ..." solía resaltar entidades de volumen irrelevante (ej. "Tienda Molinos" 0%, la rugosidad ya documentada más arriba) y el usuario lo sacó en su edición.
- **Párrafo de cierre ampliado**: "...en el tablero de Forecast Accuracy en la sección de Abastecimiento del CIC" (antes terminaba en "...en el tablero.").
- **Nombre de archivo**: `"Reporte Accuracy & Bias - {Mes} {Año}"` (antes `"Reporte de resultados {Mes}"`, sin año) -- pedido aparte, no viene de `reporte_final.docx` (los nombres de archivo no viajan dentro del .docx).

## Ajustes de Inicio y de la sección IBP Forecast (2026-09-18, a pedido del usuario)

**Bug real corregido: "SKU en Segmento crítico (3.2)" del Resumen ejecutivo siempre daba 0.** `pages/0_Inicio.py::_resumen_division` llamaba `cache.calcular_tabla_segmentacion(df_mes_div)` sin el segundo argumento `df_forecast_prox4m` -- el propio docstring de `tabla_segmentacion_sku` (`src/accuracy.py`) ya advertía que `None` equivale a "sin forecast futuro para ningún SKU", así que NINGÚN SKU queda elegible para Segmento. `pages/5_Reporte_Accuracy.py`/`pages/6_Segmentacion_SKU.py` ya lo hacían bien (siempre pasan `forecast_proximos_4m(...)`); Inicio no. Fix: mismo patrón que esas páginas -- `meses_prox4m = periodos_empezando_en(MESES_PROX_FCST, mes_ultimo_cerrado)` + `forecast_proximos_4m(df_full_div, meses_prox4m)` con `df_full_div` (TODOS los períodos de la división, no solo `mes_ultimo_cerrado` -- el forecast a futuro está fuera de ese mes).

**"Ventas vs. Plan Anual YTD" reemplazada por Bias Estadístico/Consensuado en la tabla del Resumen ejecutivo** -- ya no se carga `df_ancho`/`df_plan` ahí (quedaron sin otro uso en el archivo, se sacaron junto con `periodos_historicos_mes`/`MESES_HISTORICOS`). Bias Consensuado sale gratis de `acc_bias_consensuado` (ya devuelve Accuracy Y Bias); Bias Estadístico usa `bias_estadistico` (antes solo importado en `reporte_mensual.py`). Alerta crítica de "Ventas YTD por debajo de -15%" reemplazada por "Bias Consensuado fuera de ±5%" (`alertas.nivel_bias`), incluido `alertas.color_bias` en el estilo de la tabla.

**Sección de sidebar renombrada**: `"Tablero Forecast IBP"` → `"IBP Forecast"` en `app.py` (clave del dict de `st.navigation`) y en el subheader/card equivalente de `pages/0_Inicio.py` (`st.subheader("📊 ...")`). `"Tablero Forecast Accuracy IBP"` NO se tocó (no se pidió). El nombre real del tablero Power BI (usado en docstrings/comentarios como referencia histórica) tampoco se tocó -- es documentación, no UI.

**Retoques puntuales de UI en las 4 páginas de IBP Forecast:**
- **Histórico de ventas**: KPI "YoY (Mon YYYY)" → "MMAA (Mes Año)" -- MMAA = "Mismo Mes, Año Anterior" (lo que el KPI mide), de paso corrige que `%b` daba el mes en inglés ("Aug") en vez de español; `MESES_ABREV_ES` (lista local al archivo) da la abreviatura correcta.
- **Forecast**: sacado el título "Valor por Tipo" de `charts.area_superpuesta(...)` -- se superponía con la leyenda horizontal (ver bug de layout más abajo).
- **Plan Anual**: el título "Plan Anual vs Histórico + FCST" se mantiene (a diferencia de Forecast, acá SÍ se pidió conservarlo) pero se corrigió el layout compartido (ver abajo) para que no se superponga con la leyenda.
- **Propuestas FCST**: sacado el título "Suma de Valor" de `charts.line_chart(...)` -- mismo criterio que Forecast, título genérico que no aportaba.
- **Bug de layout compartido (`charts._base_layout`)**: con título Y leyenda horizontal juntos, el título (posicionado por Plotly cerca del borde superior del ÁREA del gráfico) caía en la misma franja que la leyenda (`y=1.02`, también relativo al área del gráfico) -- se superponían. Fix: `title.y=0.98` con `yanchor="top"` en referencia "container" (relativo a TODA la figura, no al área del gráfico) + margen superior `t=60` (antes `40`) para darle aire a ambos. Afecta a los 6 charts que pasan por `_base_layout` con título (`area_chart_por_tipo`, `area_superpuesta`, `line_chart`, `bar_chart`, `bias_bar_chart`, `ranking_semaforo`) -- revisado que no rompe los que NO tienen este problema (ej. los `ranking_semaforo` de Ranking Clientes, que no pasan `title=` y quedan con un `st.subheader` afuera).

**KPI "Proyección run-rate {año}" de Plan Anual ELIMINADO (mismo día, 2026-09-18)** -- el usuario pidió sacarlo ("no me sirve por ahora") apenas después de que se le explicara qué significaba (ritmo mensual de los meses YA CERRADOS del año, solo Histórico Ajustado real sin Forecast Consensuado, × 12, vs. Plan Anual -- una segunda mirada independiente del forecast oficial). `pages/3_Plan_Anual.py` volvió a un solo `st.metric` ("Histórico + FCST" + brecha), sin el `st.columns(2)`. Si se vuelve a pedir en el futuro, la lógica de cálculo era simple (promedio de `ADJUSTEDACTUALSQTY` de los meses cerrados del año × 12) -- no hace falta ir a buscarla al historial de git, alcanza con recrearla.

## Ajustes de la sección IBP Accuracy & Bias (2026-09-19, a pedido del usuario)

**Sección de sidebar renombrada**: `"Tablero Forecast Accuracy IBP"` → `"IBP Accuracy & Bias"` en `app.py` (clave del dict de `st.navigation`) y en el subheader/card equivalente de `pages/0_Inicio.py` -- mismo patrón que el retoque de `"Tablero Forecast IBP"` → `"IBP Forecast"` del 2026-09-18.

**Ranking Clientes -- 4 retoques en "Ranking por Área Comercial" / "Ranking por Área/GC":**
- **Bias coloreado por DIRECCIÓN en la tabla de Área Comercial**: nueva función `alertas.color_bias_direccion` (verde positivo/rojo negativo, sin importar magnitud) -- a propósito DISTINTA de `alertas.color_bias` (semáforo simétrico por magnitud ±`UMBRAL_BIAS`, usado en el Reporte de Resultados mensual). No unificar las dos sin que el usuario lo pida: son criterios de UI distintos para lugares distintos.
- **Columna `ZAREACOMERCIAL` renombrada a "Área Comercial"** en la tabla (`.rename(columns=...)` justo antes de `st.dataframe`, después de todo el cálculo/merge que sí necesita el nombre real de columna).
- **`ranking_semaforo` del gráfico "Área/GC" excluye ahora las filas con Accuracy NaN** (`dropna(subset=["Accuracy"])` antes de graficar) -- antes esas áreas (ej. "Sub-Productos", a veces "Otros") aparecían como una etiqueta sin ninguna barra, ocupando espacio. Importante: esto NO saca filas con Accuracy exactamente 0% -- `accuracy._accuracy_ponderada` solo da NaN cuando el Actual del grupo es ≤0 (sin dato real para evaluar), un 0% real (Actual>0 pero error≥Actual, cuenta activa con accuracy pésima) es información real y se mantiene a propósito, aunque visualmente también se vea "sin barra".
- **Eje "ZAREAGC" → "Área/GC"** en el mismo gráfico -- se renombra la columna (`.rename(columns={"ZAREAGC": "Área/GC"})`) antes de pasarla a `charts.ranking_semaforo`, que usa el nombre de columna directo como título de eje (Plotly Express).

**Auditoría completa de la app buscando IDs de atributo SAP expuestos en UI (2026-09-19, a pedido del usuario) -- 7 atributos puntuales: `ZBIGBUSINESS`, `ZBIGDIVISION`, `ZAREACOMERCIAL`, `ZAREAGC`, `PRDFAMILY`, `PRDID`, `ZBRAND`.** El patrón de bug es siempre el mismo: pasarle a Plotly Express (`px.bar`/`px.line`/`px.pie`, dentro de `bar_chart`/`line_chart`/`pie_chart`/`ranking_semaforo` de `charts.py`) o a `st.dataframe`/`pd.pivot_table` una columna SIN renombrar antes -- Plotly Express usa el nombre de columna tal cual como título de eje/leyenda, y `st.dataframe` muestra el nombre de columna (o el nombre de nivel de un `MultiIndex`) tal cual como header. Encontrados y corregidos:
- `pages/1_Historico_de_ventas.py`: eje Y de "Mix Productos" mostraba `ZBIGBUSINESS` → renombrado a "Gran Negocio" antes de `charts.bar_chart`.
- `pages/5_Reporte_Accuracy.py`: las dos tablas pivot ("Evolución Mensual"/"Accuracy & Bias Ponderado") mostraban `ZBIGDIVISION` como header del índice → renombrado a "Gran División" apenas se calcula `acc_cons_mes`/`acc_est_mes`/`acc_cons_tot`/`acc_est_tot` (antes de armar `largo`/`ponderado`/el pivot). La tabla "Top 10 SKU con peor Accuracy" mostraba `PRDID` → renombrado a "SKU" (ya se renombraba `PRDDESCR`→"Descripción" ahí, faltaba el `PRDID`).
- `pages/11_Nivel_Planificacion.py`: columna `PRDFAMILY` en la tabla "Detalle por entidad" → renombrada a "Familia" (mismo término que `FILTROS_IBP_PRODUCTOS`/`JERARQUIA_PRODUCTO` en `filters.py`).
- `pages/12_Feature_Importance.py`: `st.selectbox("Entidad (PRDFAMILY)", ...)` → `"Entidad (Familia)"`.
- **Verificado que NO hace falta tocar** (comprobado en vivo, no solo por código): `charts.pie_chart`/`charts.area_superpuesta` con una columna ID como `names`/`color` -- a diferencia de `px.bar`/`px.line`, no les vimos agregar un título de leyenda visible con el nombre de columna (`pie_chart` no fija `legend_title`, y `area_superpuesta` arma el `go.Figure` a mano con `name=` por trace, nunca expone el nombre de columna). El .docx del Reporte de Resultados mensual (`generador_reporte_docx.py`) también está limpio -- los `col_nombre`/`group_col` que recibe son solo claves internas de lookup (`dict.get(...)`), el header real sale de un `etiqueta_nombre`/texto fijo aparte, nunca del nombre de columna.
- **Resuelto el mismo día**: `pages/10_Curvas_Backtesting.py`/`pages/11_Nivel_Planificacion.py`/`pages/12_Feature_Importance.py` mostraban como VALORES (no como header) los códigos crudos de `nivel_planificacion.NIVELES_JERARQUIA` (`PRDID`/`PRDFAMILY`/`ZINDFAMILY`/`ZBRAND`/`ZBIGBUSINESS`) en un selectbox, un gráfico de barras y un mensaje de texto. El usuario confirmó el término de negocio que faltaba: `ZINDFAMILY` = "Familia Industrial". Fix: `nivel_planificacion.NIVEL_LABELS`/`etiqueta_nivel()` (dict + helper nuevos) -- el código crudo se sigue usando tal cual para matchear contra `NIVEL_DE_PLANIFICACION`/`VALOR_NIVEL` y armar rutas de `.pkl` (`nombre_archivo_pkl`, nunca se toca), `etiqueta_nivel()` es solo la capa de presentación. Aplicado vía `st.selectbox(..., format_func=niveles.etiqueta_nivel)` en Curvas de Backtesting (mantiene el valor crudo devuelto, solo cambia lo que se ve) y `.map(niveles.etiqueta_nivel)`/llamada directa en Nivel de Planificación y Feature Importance. Las rutas de archivo (`trained_models/PRDID/...`, en fuente monoespaciada) quedan sin traducir a propósito -- son referencias técnicas reales, no un rótulo de negocio.

## Backlog -- mejoras pendientes (no implementadas, no son bugs)

- **Margen Unitario de Segmentación SKU podría venir del Data Lake en vez de SAP IBP (idea del usuario, 2026-09-19)**: hoy `cache.get_margen_unitario` (que llama a `margen_unitario_sap_ibp`, ver `ZMARGENUNITARIOUSD`) trae un único valor por PRDID -- el mes en curso, con fallback al mes anterior si viene vacío, agregado por MAX ante duplicados (réplica fiel de la medida DAX real, ver docstring de la función y la fila "Margen Unitario" en la tabla de key figures de `CLAUDE.md`). El usuario señaló que el Data Lake (Athena, mismo origen que `get_categoria_producto`) tiene el margen a grano MES x SKU x CLIENTE -- mucho más rico que el valor puntual actual (permitiría ver evolución mensual del margen, o desagregarlo por cliente, no solo un snapshot). Quedaría para usarse en `pages/6_Segmentacion_SKU.py` (columnas "Margen Unitario (USD)"/"Margen Total SKU (USD)"/"% Mix Margen (SKU)"/"Impacto"). Antes de tocar nada: pedirle al usuario el nombre real de la tabla/columnas de Athena (mismo criterio que el resto del repo -- nunca asumir un nombre de key figure por analogía).

## Checklist antes de proponer un cambio en la capa de datos

- [ ] ¿Estoy por asumir un nombre de key figure o un UOM? → revisar `tablas_forecast_ibp.txt`/`tablas_forecast_accuracy_ibp.txt` primero, no adivinar por analogía con otro repo.
- [ ] ¿Estoy por pedir un atributo de cliente en una consulta de key figures? → solo `ZAREAGC`, nunca CUSTID/otros. Si hace falta más detalle, probar tiempo de respuesta antes de construir sobre esa base.
- [ ] ¿Toco `consulta_odata.py` o `settings.py`? → no aplicar `truststore` de forma global, solo vía el adapter acotado.
- [ ] ¿Cambié una columna en `cache.py`? → actualizar la función demo correspondiente en `demo_data.py` con el mismo esquema.
- [ ] ¿Toco `accuracy.py`? → verificar contra el texto DAX real (pedirle al usuario que lo vuelva a pasar si no está a mano), no reinventar la fórmula.
