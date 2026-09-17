# streamlit-demand-planning

Tablero de control del área de Demand Planning (Molinos). App Streamlit que replica funcionalmente dos tableros de Power BI de SAP IBP, conectada **en vivo** a SAP IBP (OData) y AWS Athena (Data Lake), con un modo demo automático como respaldo cuando esas fuentes no están disponibles.

No es una réplica visual pixel-perfect de los `.pbix` originales — es una réplica **funcional**: mismos filtros, mismos números, mismas fórmulas de negocio, con gráficos hechos en Plotly en vez de Power BI.

Además de la réplica funcional, la app agrega una capa propia de **alertas accionables**: semáforo de 3 niveles (🟢🟡🔴, mismos cortes 80%/60% que la Segmentación de SKU real) en las tablas de accuracy, badges de Bias direccional (sobre/subestimación), filas críticas resaltadas, y KPIs derivados (run-rate de Plan Anual, YoY de Histórico, ajuste Consensuado vs. Estadístico) pensados para señalar qué mirar, no solo mostrar números — ver `src/alertas.py` y CLAUDE.md.

> Para el detalle técnico completo (arquitectura de datos, fórmulas exactas, decisiones de diseño y su porqué, bugs ya corregidos) ver [`CLAUDE.md`](./CLAUDE.md) — pensado como referencia para quien vaya a tocar el código, humano o asistente de IA.

## Qué tableros replica

### Tablero Forecast IBP
| Página | Contenido |
|---|---|
| Histórico de ventas | Histórico (ajustado) vs Entregado (mes en curso), mix de productos, histórico/volumen por Área Comercial |
| Forecast | Histórico Ajustado + "12 - Estimado Consensuado", KPIs de Forecast/Estimado Actual y Entregado+Pendiente |
| Plan Anual | Plan Anual vs Histórico+Forecast, con el % de brecha contra el objetivo (desde enero 2025, que es cuando arrancó a conformarse el Plan Anual real) |
| Propuestas FCST | Las 7 versiones del waterfall de forecast completo, con selector de Tipo |

### Tablero Forecast Accuracy IBP
| Página | Contenido |
|---|---|
| Reporte Accuracy | Evolución mensual y ponderada de Accuracy/Bias por Gran División, y segmentación de SKUs (por las 3 Grandes Divisiones) |
| Segmentación SKU | Tabla a nivel SKU con Accuracy Estadístico/Consensuado, Desvío y Segmento |
| Ranking Clientes | Ranking de accuracy por Área Comercial y Área/GC, separado por Gran División |
| Glosario | Definiciones reales de indicadores y segmentos (texto de las medidas DAX originales) |

### AWS SageMaker

Sección aparte, sin relación con los dos tableros de arriba (no depende de SAP IBP/Athena, así que es accesible aunque esos datos no hayan terminado de precargarse). Explora los experimentos de forecast que el equipo de Supply corre en AWS SageMaker, guardados en `exp/<usuario>/{input,models,predictions,processed}` dentro del bucket S3 `ibp-forecast-sagemaker-data-595365649575`. 4 páginas, que comparten el mismo "entrenamiento activo" (se elige una vez en la primera, las otras 3 lo reusan):

| Página | Contenido |
|---|---|
| Explorador de Entrenamientos | Navegación en cascada usuario → carpeta → entrenamiento, tabla de contenido tipo consola S3, explorador de `reports/`/`trained_models/`/dataset de un `model.tar` |
| Curvas de Backtesting | Real vs Predicción a lo largo del tiempo, por entidad (`reports/accuracy_forecast_mensual.csv`) |
| Nivel de Planificación | Cuántas veces cada nivel de la jerarquía de producto fue elegido como mejor, y su accuracy (`reports/mejor_nivel_planificacion_por_entidad.csv` + `modelos_forecast_mensual.csv`) |
| Feature Importance | Qué variables pesaron más en la predicción de los modelos elegidos como mejores (deserializa los `.pkl` de `trained_models/`) |

- **S3 (en vivo)** — navega usuarios → carpetas → entrenamientos (`models/`) vía listado (`s3:ListBucket`, ver `s3_sagemaker.env`). El rol `MRP_Analistas_IBP_AWS` hoy **no** tiene `s3:GetObject`, así que no se puede descargar/explorar el contenido de un `model.tar` desde acá todavía — el botón lo indica con un mensaje claro.
- **Archivo local de ejemplo** — mientras no haya permiso de descarga, explora un `model.tar`/`model.tar.gz` puesto a mano en `sample_data/sagemaker/` (carpeta gitignored, no se commitea): pestañas para `reports/` (previsualiza csv/txt/imágenes), `trained_models/` (solo lista los `.pkl` para navegación general — sí se deserializan puntualmente en "Feature Importance", ver abajo) y el dataset (`preprocessed_forecast_mensual`).

#### Feature Importance: `.venv310` (Python 3.10 aparte)

Los `.pkl` de `trained_models/` son `joblib.dump` de objetos `skforecast.ForecasterRecursive` (regressor XGBoost/LightGBM/CatBoost adentro) entrenados con un Python/librerías específicos (`requirements_fcst.txt`, en la raíz del repo — pineado del lado del training, no de esta app). El venv principal de la app es Python 3.13, y `numpy==2.0.2` (la versión de entrenamiento) no tiene wheel para 3.13 — hace falta un **segundo venv, con Python 3.10**, solo para esto. La página "Feature Importance" invoca ese venv como **subproceso aislado** (`src/data/model_deserializer.py` + `scripts/feature_importance_subproceso.py`) — el venv principal nunca importa skforecast/xgboost/lightgbm/catboost directamente.

Setup (una sola vez, no se automatiza porque instala una versión de Python distinta en la máquina):
```
winget install --id Python.Python.3.10 --scope user
py -3.10 -m venv .venv310
.venv310\Scripts\python -m pip install -r requirements_fcst.txt
```
Si la red corporativa da `SSLError: self-signed certificate in certificate chain` al instalar (mismo proxy/CA interna que documenta `settings.py`), agregar `--trusted-host pypi.org --trusted-host files.pythonhosted.org` al `pip install`. Si además aparece `NameError: name 'pkg_resources' is not defined` al cargar un modelo, es porque `setuptools` reciente ya no lo incluye — `pip install "setuptools==70.0.0"` en ese mismo venv lo resuelve.

`.venv310/` es gitignorado (igual que `.venv/`) — sin este setup, la página "Feature Importance" muestra un aviso explicando qué falta en vez de romper; el resto de la app (incluidas las otras 3 páginas de AWS SageMaker) funciona igual sin él.

## Cómo correr la app

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example ibp.env
copy .env.example aws.env
copy .env.example s3_sagemaker.env
# completar ibp.env / aws.env / s3_sagemaker.env con credenciales reales (ver "Configuración" abajo)
.venv\Scripts\python -m streamlit run app.py
```

Sin credenciales configuradas (o si SAP/Athena no responden), la app cae automáticamente a **modo demo** con datos sintéticos de forma/esquema realista — sirve para explorar el diseño sin conexión real.

### Configuración (variables de entorno)

Ninguna credencial se commitea (`.gitignore` cubre `*.env`). Ver `.env.example` para la plantilla completa.

- **`ibp.env`** — SAP IBP OData: `IBP_USERNAME`, `IBP_PASSWORD`, `IBP_BASE_URL`, `IBP_PA_DEMANDA`.
- **`aws.env`** — AWS Athena: `AWS_PROFILE`, `AWS_REGION`, `AWS_DATABASE`, `AWS_S3_STAGING`.
- **`aws_credentials.env`** (opcional) — credenciales AWS explícitas (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`) cuando no hay un perfil SSO configurado localmente; tienen prioridad sobre `AWS_PROFILE`. Son temporales (SSO) y expiran cada tantas horas — al vencer, la app cae sola a modo demo para Athena.
- **`s3_sagemaker.env`** — AWS S3 para "AWS SageMaker": `AWS_PROFILE_SAGEMAKER`/`AWS_REGION_SAGEMAKER` (o credenciales explícitas `*_SAGEMAKER`), `AWS_S3_SAGEMAKER_BUCKET`, `AWS_S3_SAGEMAKER_PREFIX`. Cuenta y rol **distintos** de los de Athena (cuenta `AI_Platform_DEV`, rol `MRP_Analistas_IBP_AWS`) — no reutiliza `AWS_PROFILE`/`aws_credentials.env` de arriba.

**Después de cambiar cualquier `*.env` o cualquier archivo de `src/`, hay que reiniciar el proceso de Streamlit** (`Ctrl+C` y volver a correr `streamlit run app.py`) — el botón "🔄 Recargar datos" del Inicio no alcanza, solo limpia el cache de datos, no reimporta módulos de Python.

## Arquitectura

```
app.py                  → entrypoint/router (st.navigation), landing con precarga de datos
pages/                  → 1 archivo por página del multipage (numeradas para fijar el orden)
src/
  config/               → carga de settings.py / dynamics_config.py desde los *.env
  data/                 → clientes de SAP IBP OData, AWS Athena y AWS S3 (SageMaker), master data, datos demo
                           model_deserializer.py invoca .venv310 como subproceso (ver Feature Importance)
  cache.py              → wrappers st.cache_data + fallback a demo (capa que consumen las páginas)
  accuracy.py           → fórmulas de accuracy/bias/segmentación (réplica de las medidas DAX reales)
  nivel_planificacion.py → join entidad→nivel→valor para "Nivel de Planificación"/"Feature Importance"
  experimentos_sagemaker_estado.py → "entrenamiento activo" compartido entre las 4 páginas de SageMaker
  filters.py            → sidebars compartidos (Período/Clientes/Productos) de los dos tableros
  charts.py             → helpers de gráficos Plotly (paleta y layout consistentes)
scripts/feature_importance_subproceso.py → corre con .venv310 (Python 3.10), no con el venv principal
sample_data/sagemaker/  → (gitignored) .tar de ejemplo para probar "AWS SageMaker" en local
requirements_fcst.txt   → pins EXACTOS del training de SageMaker (para .venv310, no para el venv principal)
```

**Fuente de datos**: conexión en vivo a SAP IBP vía OData (Gateway `EXTRACT_ODATA_SRV`/`MOLIBP`) para históricos/forecast/plan, y a AWS Athena (Data Lake) para la categoría de producto (`grupo_material_3`). Todo se cachea con `st.cache_data` (persistido a disco, sobrevive a un reinicio del proceso) para no repetir consultas caras entre reruns de Streamlit.

**Modo demo**: cada fuente de datos tiene una función `demo_data.*` con el MISMO esquema de columnas que la fuente real — si SAP/Athena fallan o no hay credenciales, la página cae sola a datos sintéticos y muestra un cartel "🧪 Mostrando datos de EJEMPLO".

## Reglas de negocio clave

- **Grandes Divisiones válidas: Alimentos, Bodegas y Snacks únicamente** — cualquier otra división de la jerarquía de producto (ej. "MP, Semi y Subproductos") queda excluida de toda la app. El filtro "Gran División" es un selector obligatorio de una sola opción (default "Alimentos") en casi todas las páginas; la única excepción es "Ranking Clientes", que muestra las 3 divisiones simultáneamente.
- **Accuracy = 1 − (Σ error absoluto) / (Σ Entrega)**, siempre acotada a `[0, 1]` — nunca negativa, nunca mayor a 100 %. Se calcula decomponiendo siempre a nivel SKU x mes antes de sumar, sin importar el nivel de agregación que se esté mirando (ZBIGDIVISION total, Área Comercial, Área/GC, etc.) — nunca sobre los totales ya agregados de ese grupo. El **Bias**, en cambio, sí es un cociente de sumas totales (Σ Forecast / Σ Entrega − 1), lineal, sin decomponer por SKU.
- **Ventana de análisis dinámica ("Meses a analizar")**: las 3 páginas del Tablero Accuracy dejan elegir directamente qué meses entran en el cálculo de Accuracy/Bias ponderado (multiselect, no una ventana fija) — por default vienen preseleccionados los últimos 4 meses **cerrados** (nunca el mes en curso, que puede tener venta parcial).
- **Segmentación de SKU** (0 / 1 / 2.1 / 2.2 / 3.1 / 3.2, según el accuracy estadístico y consensuado de cada SKU) y el **Accuracy Consensuado Proyectado** (simulación incremental de qué pasaría si se corrigieran los SKU de cada segmento a un objetivo teórico: 100 % para el segmento 1, 80 % para el 2.x, 60 % para el 3.x) replican fielmente las medidas DAX y la metodología del informe de diseño original. Un SKU solo es elegible para tener Segmento si tuvo venta en los últimos 3 meses cerrados Y tiene forecast consensuado para los próximos 4 meses.
- **Grano de cliente**: las consultas de series (histórico/forecast/plan) solo piden granularidad hasta `ZAREAGC` (Área/GC) — pedir `CUSTID` individual multiplica el tiempo de respuesta de SAP ~30x y termina en error 500. "Área Comercial" se resuelve haciendo merge contra el maestro de clientes (que sí puede pedir ese detalle, al no llevar filtro de período).

## Key figures (SAP IBP OData → concepto de negocio)

| Concepto | Campo OData | Notas |
|---|---|---|
| Histórico de Ventas | `ACTUALSQTY` | |
| Histórico Ajustado | `ADJUSTEDACTUALSQTY` | |
| Forecast Consensuado | `DEMANDPLANNINGQTY` | ala "07" del waterfall |
| Forecast Estadístico | `STATISTICALFORECASTQTY` | output del modelo ML, escrito de vuelta a IBP |
| Estimado Consensuado | `ZFCSTESTIMADO` | ala "12" del waterfall |
| Plan Anual | `ZPLANANUAL` | filtrado por año (`PERIODID1`), no por mes |
| Entregado / Pendiente / E+P | `ZENTREGADO` / `ZPENDIENTESMTH` / `ZENTREGAPENDIENTEMTH` | directo de SAP IBP, ya calculados |
| Margen Unitario | `ZMARGENUNITARIOUSD` | USD, UOM CAJ, mes actual con fallback al anterior |
| Gran División / Gran Negocio / Negocio / Demand Family / Familia | `ZBIGDIVISION` / `ZBIGBUSINESS` / `ZBRAND` / `ZDEMFAMILY` / `PRDFAMILY` | jerarquía de producto |
| Categoria | `grupo_material_3` (AWS Athena) | join liviano contra el maestro de materiales |

UOM = `UMG` para todas las series y para el maestro de clientes; `CAJ` solo para el maestro de producto y Margen Unitario. Filtros de negocio que aplican siempre: `ZVIGENCIA eq '1'`, `ZAREAFCST ne 'Comex'`, `ZCLIENTEBOCA eq 'Cliente'` (el Tablero Accuracy agrega `LOCID eq 'AR01'` y excluye además `'Tienda Molinos'`).

## Limitaciones conocidas

- No es pixel-perfect contra los `.pbix` originales (algunos sliders son multiselect en vez de range slider, falta algún banner de texto decorativo).
- El histórico visible es de 24 meses hacia atrás / 12 hacia adelante (configurable en `cache.py::MESES_HISTORICOS`/`MESES_FUTUROS`) por costo de carga contra SAP — el Power BI real muestra más años de histórico.
- Detalle de cliente limitado a Área/GC en las consultas de series (ver "Reglas de negocio clave" arriba) — es una limitación real del Gateway de SAP, no de esta app.
- "AWS SageMaker" no puede descargar/explorar un `model.tar` desde S3 todavía — el rol `MRP_Analistas_IBP_AWS` solo tiene permiso de listado (`s3:ListBucket`), no de descarga (`s3:GetObject`). Mientras se gestiona el permiso, la exploración de contenido funciona en modo local con un `.tar` de ejemplo en `sample_data/sagemaker/`.

Ver [`CLAUDE.md`](./CLAUDE.md) para el detalle completo de cada uno de estos puntos, decisiones de diseño, y el historial de bugs ya corregidos (para no repetirlos).
