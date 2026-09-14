# streamlit-demand-planning

Tablero de control del área de Demand Planning (Molinos). App Streamlit que replica funcionalmente dos tableros de Power BI de SAP IBP, conectada **en vivo** a SAP IBP (OData) y AWS Athena (Data Lake), con un modo demo automático como respaldo cuando esas fuentes no están disponibles.

No es una réplica visual pixel-perfect de los `.pbix` originales — es una réplica **funcional**: mismos filtros, mismos números, mismas fórmulas de negocio, con gráficos hechos en Plotly en vez de Power BI.

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

## Cómo correr la app

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example ibp.env
copy .env.example aws.env
# completar ibp.env / aws.env con credenciales reales (ver "Configuración" abajo)
.venv\Scripts\python -m streamlit run app.py
```

Sin credenciales configuradas (o si SAP/Athena no responden), la app cae automáticamente a **modo demo** con datos sintéticos de forma/esquema realista — sirve para explorar el diseño sin conexión real.

### Configuración (variables de entorno)

Ninguna credencial se commitea (`.gitignore` cubre `*.env`). Ver `.env.example` para la plantilla completa.

- **`ibp.env`** — SAP IBP OData: `IBP_USERNAME`, `IBP_PASSWORD`, `IBP_BASE_URL`, `IBP_PA_DEMANDA`.
- **`aws.env`** — AWS Athena: `AWS_PROFILE`, `AWS_REGION`, `AWS_DATABASE`, `AWS_S3_STAGING`.
- **`aws_credentials.env`** (opcional) — credenciales AWS explícitas (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`) cuando no hay un perfil SSO configurado localmente; tienen prioridad sobre `AWS_PROFILE`. Son temporales (SSO) y expiran cada tantas horas — al vencer, la app cae sola a modo demo para Athena.

**Después de cambiar cualquier `*.env` o cualquier archivo de `src/`, hay que reiniciar el proceso de Streamlit** (`Ctrl+C` y volver a correr `streamlit run app.py`) — el botón "🔄 Recargar datos" del Inicio no alcanza, solo limpia el cache de datos, no reimporta módulos de Python.

## Arquitectura

```
app.py                  → entrypoint/router (st.navigation), landing con precarga de datos
pages/                  → 1 archivo por página del multipage (numeradas para fijar el orden)
src/
  config/               → carga de settings.py / dynamics_config.py desde los *.env
  data/                 → clientes de SAP IBP OData y AWS Athena, master data, datos demo
  cache.py              → wrappers st.cache_data + fallback a demo (capa que consumen las páginas)
  accuracy.py           → fórmulas de accuracy/bias/segmentación (réplica de las medidas DAX reales)
  filters.py            → sidebars compartidos (Período/Clientes/Productos) de los dos tableros
  charts.py             → helpers de gráficos Plotly (paleta y layout consistentes)
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

Ver [`CLAUDE.md`](./CLAUDE.md) para el detalle completo de cada uno de estos puntos, decisiones de diseño, y el historial de bugs ya corregidos (para no repetirlos).
