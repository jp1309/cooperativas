# Contexto Persistente - Cooperativas Ecuador

Este archivo es la fuente de verdad para recuperar contexto cuando el asistente pierda memoria.
Si estas leyendo esto, **DEBES actualizar este archivo** con cualquier cambio relevante antes de terminar la tarea.

## Instrucciones para el asistente
- Siempre leer `cooperativas/docs/CONTEXTO.md` al inicio de una nueva sesion.
- Actualizar este archivo al finalizar cambios.
- Todo el trabajo debe quedar dentro de `cooperativas/`.
- No modificar el proyecto de bancos (raiz del repo).

## Objetivo del proyecto
Replicar el dashboard de bancos para cooperativas ecuatorianas, con Streamlit, usando los datos en `cooperativas/`.

## Estado actual (PRODUCCION - Desplegado en Streamlit Cloud)

### Estructura de archivos
```
cooperativas/
├── Inicio.py                           # Página principal Streamlit
├── pages/
│   ├── 1_Panorama.py                   # Visión general del sistema (OPTIMIZADO)
│   ├── 2_Balance_General.py            # Análisis temporal de balances
│   ├── 3_Perdidas_Ganancias.py         # PyG con suma móvil 12 meses
│   └── 4_CAMEL.py                      # Indicadores CAMEL (usa pivot cache)
├── utils/
│   ├── __init__.py
│   ├── data_loader.py                  # Funciones de carga (optimizadas + legacy + PyG + indicadores)
│   └── charts.py                       # Componentes de visualización (obtener_color_cooperativa)
├── config/
│   ├── __init__.py
│   └── indicator_mapping.py            # Mapeo de cuentas, segmentos, COLORES y CAMEL
├── scripts/
│   ├── procesar_balance_cooperativas.py # Pipeline ETL balances (ZIPs/XLSM → balance.parquet)
│   ├── procesar_pyg.py                 # Pipeline PyG (desacumulación + suma móvil 12M)
│   ├── procesar_camel.py               # Pipeline ETL indicadores CAMEL desde pivot cache
│   ├── procesar_indicadores.py         # Pipeline ETL balance/PyG desde XLSM (legacy)
│   ├── generar_agregados.py            # Genera datos pre-agregados desde balance.parquet
│   └── descargar_datos_seps.py         # Scraping y descarga automática del portal SEPS
├── .github/
│   └── workflows/
│       └── actualizar_datos.yml        # GitHub Actions: actualización automática mensual
├── master_data/
│   ├── balance.parquet                 # 82 MB, 23M registros (optimizado: sin ruc/nivel, category dtypes)
│   ├── pyg.parquet                     # 16 MB, PyG con valor_12m
│   ├── indicadores.parquet             # ~3 MB, indicadores CAMEL oficiales
│   ├── indicadores_raw.parquet         # Indicadores crudos extraídos de XLSM (legacy, no usado)
│   ├── agg_metricas_sistema.parquet    # 30 KB - KPIs rápidos
│   ├── agg_ranking_cooperativas.parquet # 1.4 MB - Rankings y treemaps
│   ├── agg_series_temporales.parquet   # 2.2 MB - Series temporales
│   ├── agg_catalogo_cooperativas.parquet # 5 KB - Catálogo (259 cooperativas)
│   ├── metadata.json                   # Metadatos de balance (incluye fecha_max)
│   ├── metadata_agregados.json         # Metadatos de agregados
│   └── metadata_indicadores.json       # Metadatos de indicadores CAMEL
├── balances_cooperativas/              # ZIPs fuente balance (2018-2026, no en repo)
├── indicadores/                        # ZIPs fuente indicadores XLSM (2020-2026, no en repo)
├── docs/
│   └── CONTEXTO.md
├── .streamlit/config.toml              # Tema y configuración de servidor
├── .gitignore                          # Excluye ZIPs fuente, archivos intermedios
├── requirements.txt                    # Dependencias para Streamlit Cloud
└── README.md                           # Documentación del proyecto
```

### Datos procesados

#### balance.parquet (82 MB disco → ~500 MB RAM)
- 23,003,634 registros (incluye enero 2026)
- 259 cooperativas únicas
- Columnas: fecha, segmento, cooperativa, codigo, cuenta, valor (todas category excepto fecha/valor)
- Segmentos: SEGMENTO 1, SEGMENTO 2, SEGMENTO 3, SEGMENTO 1 MUTUALISTA
- Período: Enero 2018 - Enero 2026 (97 meses)
- **Sin columnas ruc ni nivel** (eliminadas para reducir memoria, no usadas por UI)
- Nombres de mutualistas unificados retroactivamente a `Mutualista X` en toda la historia

#### pyg.parquet (17 MB disco → 79 MB RAM)
- 2,126,296 registros
- 242 cooperativas únicas (normalizado LTDA)
- Columnas: fecha, segmento, cooperativa, codigo, cuenta, valor_acumulado, valor_mes, valor_12m (todas category excepto fecha/valores)
- Período: 2020-2025 (72 meses)
- 75% de registros con valor_12m válido (primeros 11 meses de cada serie no tienen)
- **Sin columna ruc** (eliminada para reducir memoria, no usada por UI)

#### indicadores.parquet
- ~550K registros
- 231 cooperativas únicas
- **37 indicadores CAMEL oficiales en 7 categorías**
- Período: Enero 2020 - Diciembre 2025
- Segmentos: SEGMENTO 1, SEGMENTO 2, SEGMENTO 3, SEGMENTO 1 MUTUALISTA
- **Valores como ratios (0-1)**, multiplicar por 100 para porcentaje
- Schema: cooperativa, segmento, fecha, codigo, indicador, valor, categoria
- Segmento unificado: cada cooperativa usa el segmento de su último dato disponible

#### Lógica de desacumulación PyG
Los datos de PyG son **acumulados** mes a mes dentro de cada año:
1. **valor_acumulado**: Valor original del archivo (acumulado YTD)
2. **valor_mes**: Valor desacumulado del mes = valor_acumulado - valor_mes_anterior (excepto enero)
3. **valor_12m**: Suma móvil de 12 meses para comparabilidad interanual

### Módulos funcionales

#### 1. Inicio.py
Página de bienvenida con descripción del sistema y los 4 módulos disponibles.

#### 2. 1_Panorama.py (OPTIMIZADO)
- KPIs del sistema (Activos, Cartera, Depósitos, Patrimonio, Número de cooperativas)
- Treemap de activos con drill-down (Cooperativa → Componentes)
- Treemap de pasivos y patrimonio
- Rankings por activos y pasivos
- Crecimiento YoY por cooperativa (Cartera y Depósitos)
- Usa datos pre-agregados para carga rápida

#### 3. 2_Balance_General.py
Tres secciones con **selector de cuentas jerárquico uniforme** (4 niveles):
1. **Evolución Comparativa**: Series temporales de múltiples cooperativas
2. **Heatmap de Variación YoY**: Matriz cooperativa × mes
3. **Ranking por Cuenta**: Comparación de valores para cuenta/mes específicos

#### 4. 3_Perdidas_Ganancias.py
- **Valores anualizados** usando suma móvil 12 meses (valor_12m)
- Selector de cuentas jerárquico (Nivel 1: 4-Gastos/5-Ingresos, Nivel 2: subcuentas)
- Sección 1: Evolución Comparativa con modos Absoluto/Indexado/Participación
- Sección 2: Ranking de cooperativas por cuenta y mes
- Excluye totales de segmento (VT_*) de visualizaciones
- Filtro por segmento en sidebar

#### 5. 4_CAMEL.py
Indicadores financieros **oficiales de la Superintendencia**, extraídos directamente del pivot cache
de los archivos XLSM (hoja "5. INDICADORES FINANCIEROS"). Ya no calcula desde códigos contables.

**37 indicadores en 7 categorías:**
- **C - Capital** (5): Cart. Improd. Descubierta/Patrimonio, Cartera Improductiva/Patrimonio, FK, FI, Capitalización Neto
- **A - Calidad de Activos** (3): Activos Improductivos/Activos, Activos Productivos/Activos, AP/PC
- **A - Morosidad por Cartera** (7): Total, Consumo, Inmobiliaria, Microcrédito, Productivo, Vivienda IP, Educativo
- **A - Cobertura por Cartera** (7): Total, Consumo, Inmobiliaria, Microcrédito, Productivo, Vivienda IP, Educativo
- **M - Management y Eficiencia** (3): Gastos Op/Activo, Gastos Op/Margen, Gastos Personal/Activo
- **E - Earnings (Rentabilidad)** (11): ROE, ROA, Intermediación, Margen/Patrimonio, Margen/Activo, 6 Rendimientos de Cartera
- **L - Liquidez** (1): Fondos Disponibles / Depósitos CP

Tres pestañas: Ranking, Evolución Temporal, Heatmap Mensual.
Filtros: Segmento y Fecha en sidebar. Selectores: Top 30, Top 50, Todas.

**Heatmap:**
- Cooperativas ordenadas por activos totales (más grande abajo, más pequeño arriba)
- Rangos de colores alineados con el módulo de bancos para consistencia financiera
- Nombres largos truncados con `truncar_nombre()`: mantiene inicio y final (ej: "ASOCIACION M...IENDA PICHINCHA")

### Normalización de nombres de cooperativas (IMPORTANTE)
Los nombres de cooperativas se normalizan para evitar duplicados:
- **LIMITADA → LTDA** (todas las ocurrencias)
- **LTDA. → LTDA** (elimina punto final)
- Espacios múltiples eliminados
- **Mutualistas**: Se unifican a nombres canónicos `Mutualista Ambato`, `Mutualista Azuay`, `Mutualista Imbabura`, `Mutualista Pichincha` (ver detalle abajo)
- **Correcciones manuales** en `procesar_camel.py`: 8 cooperativas con nombres distintos entre indicadores y balance (dict CORRECCIONES_NOMBRE)

Esta normalización se aplica en:
- `procesar_balance_cooperativas.py`: Función `normalizar_nombre()` + dict `MUTUALISTAS_NOMBRES`
- `procesar_camel.py`: Función `normalizar_nombre()` + CORRECCIONES_NOMBRE + expansión de mutualistas
- `procesar_pyg.py`: Función `normalizar_nombre_cooperativa()`
- `indicator_mapping.py`: COLORES_COOPERATIVAS usa nombres con LTDA

**Resultado**: Balance: 259 cooperativas únicas. Indicadores: 231 cooperativas (3 sin match en balance, cerradas/absorbidas 2020-2021).

#### Nombres canónicos de mutualistas
Las 4 mutualistas tienen nombres históricos distintos según el año de los datos:
- 2018-2025 (CSV/TXT): Nombre largo (ej: `ASOCIACION MUTUALISTA DE AHORRO Y CREDITO PARA LA VIVIENDA AMBATO`)
- 2026+ (XLSM): Nombre corto (ej: `AMBATO`)

El dict `MUTUALISTAS_NOMBRES` en `procesar_balance_cooperativas.py` mapea ambas formas al nombre canónico:
```python
MUTUALISTAS_NOMBRES = {
    'ASOCIACION MUTUALISTA DE AHORRO Y CREDITO PARA LA VIVIENDA AMBATO': 'Mutualista Ambato',
    'ASOCIACION MUTUALISTA DE AHORRO Y CREDITO PARA LA VIVIENDA AZUAY':  'Mutualista Azuay',
    'ASOCIACION MUTUALISTA DE AHORRO Y CREDITO PARA LA VIVIENDA IMBABURA': 'Mutualista Imbabura',
    'ASOCIACION MUTUALISTA DE AHORRO Y CREDITO PARA LA VIVIENDA PICHINCHA': 'Mutualista Pichincha',
    'AMBATO':    'Mutualista Ambato',
    'AZUAY':     'Mutualista Azuay',
    'IMBABURA':  'Mutualista Imbabura',
    'PICHINCHA': 'Mutualista Pichincha',
}
```
**Sin riesgo de colisión**: Existe `AMBATO LTDA` (cooperativa Segmento 1) que es diferente a `AMBATO` (mutualista Segmento 1 Mutualista). La función `normalizar_nombre()` verifica `MUTUALISTAS_NOMBRES` antes de aplicar otras transformaciones, por lo que `AMBATO LTDA` no se ve afectada.

### Unificación de segmentos
Cooperativas que cambiaron de segmento a lo largo del tiempo (51 cooperativas) toman el segmento de su **último dato disponible**. Esto se aplica en `procesar_camel.py` como post-procesamiento después de consolidar todos los años, asegurando que cada cooperativa tenga un único segmento en todo el período.

### Sistema de colores (indicator_mapping.py)
- **Top 10 cooperativas**: Colores brillantes y muy saturados
- **Top 11-30**: Colores medios (saturación media-alta)
- **Top 31-60**: Colores secundarios
- **Top 61-100**: Colores terciarios
- **Top 101-200+**: Colores quinarios (ciclo de paleta suave)
- Función `obtener_color_cooperativa(nombre)` retorna el color asignado
- **IMPORTANTE**: Los nombres en COLORES_COOPERATIVAS usan LTDA (no LIMITADA)

### Exclusión de totales VT_
Los datos de indicadores incluyen filas con nombres tipo `VT_TOTAL SEGMENTO X` que son totales pre-calculados.
Estos **deben excluirse** de:
- Listas de cooperativas en selectores
- Cálculos de ranking
- Cálculos de participación
- Total del sistema

Patrón para excluir: `~df['cooperativa'].str.startswith('VT_')`

### Unidades monetarias (IMPORTANTE)
- Los valores en parquet están en USD completos
- La división para mostrar es `/ 1_000_000` (millones)
- Las etiquetas usan sufijo "M" (Millones USD)
- PyG usa etiqueta "Millones USD (12M)" para indicar suma móvil

### Funciones de data_loader.py

**Funciones optimizadas (para Panorama - usan pre-agregados):**
- `obtener_fechas_disponibles_rapido()` → lista de fechas
- `obtener_segmentos_disponibles_rapido()` → lista de segmentos
- `obtener_metricas_kpi(fecha, segmento)` → dict de KPIs
- `obtener_ranking_rapido(fecha, codigo, top_n, segmento)` → DataFrame
- `obtener_datos_treemap_rapido(fecha, segmento, top_n)` → DataFrame
- `obtener_datos_treemap_pasivos_rapido(fecha, segmento, top_n)` → DataFrame
- `obtener_crecimiento_anual(fecha_actual, fecha_anterior, codigo, segmento, top_n)` → DataFrame
- `obtener_cooperativas_por_segmento(segmento)` → lista de cooperativas ordenadas por activos

**Funciones de carga completa:**
- `cargar_balance()` → (DataFrame, dict_calidad) - Para Balance General
- `cargar_pyg()` → (DataFrame, dict_calidad) - Para Pérdidas y Ganancias
- `cargar_indicadores()` → (DataFrame, dict_calidad) - Para CAMEL (valores como ratios 0-1)

**Funciones legacy (compatibilidad):**
- `obtener_fechas_disponibles(df)` → lista
- `obtener_segmentos_disponibles(df)` → lista
- `obtener_top_cooperativas(df, fecha, codigo, top_n, segmento)` → lista

### Ejecución
```bash
cd cooperativas

# 1. Procesar balances desde ZIPs (genera balance.parquet)
python scripts/procesar_balance_cooperativas.py

# 2. Generar datos pre-agregados (ejecutar cuando cambie balance.parquet)
python scripts/generar_agregados.py

# 3. Procesar PyG (desacumular y calcular suma móvil 12M)
python scripts/procesar_pyg.py

# 4. Procesar indicadores CAMEL desde pivot cache XLSM (genera indicadores.parquet)
python scripts/procesar_camel.py

# 5. Iniciar aplicación
streamlit run Inicio.py --server.port 8502
```

### Despliegue en producción

**Repositorio**: [jp1309/cooperativas](https://github.com/jp1309/cooperativas) (rama `main`)
**Plataforma**: Streamlit Cloud (free tier, ~1 GB RAM)
**Archivo principal**: `Inicio.py`

Archivos de despliegue:
- `requirements.txt`: streamlit, pandas, numpy, pyarrow, plotly, kaleido, requests, beautifulsoup4
- `.streamlit/config.toml`: Tema azul (#2c5282), servidor headless
- `.gitignore`: Excluye ZIPs fuente, archivos intermedios, __pycache__

### Optimización de memoria (CRÍTICO para Streamlit Cloud)

Los parquets se optimizaron para caber en el límite de ~1 GB RAM de Streamlit Cloud:

| Métrica | Sin optimizar | Optimizado | Reducción |
|---------|---------------|------------|-----------|
| Balance RAM | 4,736 MB | 500 MB | -89% |
| PyG RAM | 723 MB | 79 MB | -89% |
| **Total** | **5,459 MB** | **579 MB** | **-89%** |

Optimizaciones aplicadas:
1. **Columnas eliminadas**: `ruc` (1.4 GB, no usada) y `nivel` (no usada) del balance; `ruc` del PyG
2. **Category dtypes**: `codigo`, `cuenta`, `segmento`, `cooperativa` almacenados como category (no object)
3. **Carga selectiva**: `pd.read_parquet(columns=[...])` en `data_loader.py` carga solo columnas necesarias
4. **Dtypes en parquet**: Los scripts de procesamiento ya generan category dtypes, la conversión en carga es un safety net

**IMPORTANTE**: Si se regeneran los parquets, asegurar que los scripts de procesamiento mantengan la exclusión de `ruc`/`nivel` y el uso de category dtypes.

## Próximo paso sugerido
- Agregar exportación de datos a Excel
- Agregar comparativo entre segmentos
- Agregar promedios del sistema como referencia en gráficos CAMEL

## Notas técnicas importantes

### Formatos de archivos fuente por año
| Año | Formato | Delimitador | Notas |
|-----|---------|-------------|-------|
| 2018-2021 | CSV/TXT | `;` | Encoding `utf-8-sig` |
| 2022-2025 | CSV/TXT | `\t` (tab) | Coma decimal en valores, columnas diferentes |
| 2026+ | XLSM | N/A | ZIP con un XLSM por segmento, formato ancho (cooperativas como columnas) |

**Lectura de XLSM (2026+)**: Función `leer_xlsm_balance()` en `procesar_balance_cooperativas.py`:
- Un archivo XLSM por segmento (Segmento 1, Segmento 2, Segmento 3, Mutualistas)
- Ignora CONAFIPS y FINANCOOP (no son cooperativas de ahorro y crédito)
- Busca la hoja con "ESTADO" y "FINANCIERO" en el nombre
- Localiza fila header con "COD CONTABLE"
- Extrae fecha de celda datetime antes del header (fallback: parsea nombre de archivo `_ene_2026`)
- Aplica `melt()` para convertir formato ancho (cooperativas=columnas) a largo (una fila por cooperativa+cuenta)
- Requiere `openpyxl` instalado

### Extracción de indicadores CAMEL desde pivot cache
- Los archivos XLSM son ZIPs con XML interno
- La hoja "5. INDICADORES FINANCIEROS" usa un pivot table respaldado por un pivotCache
- El número del pivot cache **varía entre años**: cache3 en 2021/2023, cache4 en 2020/2022/2024/2025
- `procesar_camel.py` detecta el cache correcto buscando campos marcadores (`I28_ROE`, `I29_ROA`, `I1_suficiencia_patrimonial`)
- Los valores se almacenan como **ratios (0-1)**, no porcentajes. Ej: ROA=0.009 → 0.9%
- La UI multiplica por 100 para mostrar porcentajes
- Las funciones `extraer_lookup_tables()` y `parsear_cache_records()` parsean el XML de pivot cache
- Los campos de indicadores usan prefijo `I{número}_` (ej: `I28_ROE`, `I5_Moros_carte`)
- Las filas `VT_TOTAL` del cache son totales del sistema y se excluyen

### Constantes CAMEL en indicator_mapping.py
- `GRUPOS_INDICADORES`: 7 categorías CAMEL con 37 códigos para selectores de UI
- `ETIQUETAS_INDICADORES`: Nombres amigables por código
- `ESCALAS_COLORES_HEATMAP`: RdYlGn (mayor=mejor), RdYlGn_r (menor=mejor), Blues (neutral)
- `RANGOS_HEATMAP`: Rangos de valores en porcentaje, alineados con módulo de bancos

### Truncamiento de nombres largos
Función `truncar_nombre(n, max_len=30)` en `4_CAMEL.py` mantiene inicio y final del nombre para diferenciar cooperativas con prefijos similares (especialmente mutualistas). Se aplica en ranking y heatmap.

## Errores previos a evitar
- Trabajar fuera de `cooperativas/`.
- Modificar archivos del proyecto de bancos.
- No manejar el BOM (Byte Order Mark) en archivos UTF-8
- No convertir comas decimales a puntos en archivos 2022+
- **Dividir por 1000 en lugar de 1_000_000** - causa valores 1000x más grandes
- **No normalizar nombres** - causa cooperativas duplicadas (LIMITADA vs LTDA)
- **No excluir VT_** - incluye totales pre-calculados en rankings
- **Truncar nombres a longitud fija** - hace indistinguibles cooperativas con prefijo largo similar (mutualistas)
- **No optimizar dtypes para Streamlit Cloud** - balance.parquet con object dtypes usa 4.7 GB RAM, excede el límite de 1 GB. Siempre usar category dtypes y excluir columnas no usadas (ruc, nivel)

### Errores cometidos en sesión 2026-02-22 (aprendizajes)

#### 1. Normalización de nombres incompleta al renombrar mutualistas
**Error**: Al renombrar mutualistas a `Mutualista X` en `procesar_balance_cooperativas.py`, no se actualizaron simultáneamente los otros 3 lugares que también usaban los nombres antiguos:
- `config/indicator_mapping.py` → claves en `COLORES_COOPERATIVAS`
- `scripts/procesar_camel.py` → expansión a nombre largo
- `scripts/procesar_pyg.py` → sin ninguna normalización de mutualistas

**Consecuencia**: Los colores de las 4 mutualistas se volvieron negros (el dict no encontraba match), y los parquets de indicadores y PyG tenían nombres distintos al de balance, rompiendo la consistencia entre módulos.

**Regla**: Cuando se cambia el nombre canónico de una entidad, buscar con grep en TODO el proyecto antes de commitear: `grep -rn "MUTUALISTA\|nombre_anterior" .`

#### 2. Llamada a `generar_agregados.py` sin controlar el tamaño de salida
**Error**: Al llamar `generar_agregados.py` localmente (sin supervisión) durante la corrección de colores, el script generó `agg_ranking_cooperativas.parquet` de 212 MB (era 1.4 MB). El `groupby` con `observed=False` en category dtypes genera el producto cartesiano de todas las categorías (157M filas en lugar de 157K).

**Consecuencia**: El push fue rechazado por GitHub (límite 100 MB). Se tuvo que hacer `--amend` con los archivos restaurados del commit anterior.

**Regla**:
- Nunca agregar archivos `agg_*.parquet` al staging sin verificar su tamaño (`ls -lh master_data/agg_*.parquet`)
- Si un parquet creció más del doble inesperadamente, NO hacer push — investigar primero
- Al regenerar pre-agregados localmente, asegurarse de que `generar_agregados.py` use `observed=True` en todos los groupby con category dtypes

#### 3. `use_container_width` deprecado en Streamlit 1.54
**Error**: El proyecto usaba `use_container_width=True` (19 ocurrencias en 5 archivos), parámetro eliminado en Streamlit 1.54. Streamlit Cloud instaló 1.54 y generó warnings masivos en los logs.

**Solución**: Reemplazar `use_container_width=True` → `width='stretch'` y `use_container_width=False` → `width='content'`.

**Regla**: Al crear nuevos gráficos con `st.plotly_chart()` o `st.page_link()`, usar `width='stretch'` directamente.

#### 4. `observed=False` deprecado en pandas con category dtypes
**Error**: `groupby()` y `pivot_table()` en `2_Balance_General.py` sin `observed=True` generaban FutureWarning en producción porque las columnas son category dtype.

**Regla**: Siempre agregar `observed=True` en cualquier `groupby()` o `pivot_table()` que opere sobre columnas con category dtype. En este proyecto: `cooperativa`, `segmento`, `codigo`, `cuenta`.

## Historial de cambios

### 2026-02-22 - Automatización mensual y datos enero 2026

#### Automatización con GitHub Actions
- **Creado** `.github/workflows/actualizar_datos.yml`: workflow que corre automáticamente los días 15, 18, 20 y 22 de cada mes a las 6 AM UTC (reintentos en caso de que la SEPS no publique el día 15)
- **Creado** `scripts/descargar_datos_seps.py`: scraping del portal SEPS para encontrar el `download_id` del ZIP del año corriente, descarga con streaming (no hace falta conocer el ID de antemano)
- **Actualizado** `requirements.txt`: agregados `requests>=2.31.0` y `beautifulsoup4>=4.12.0`
- El workflow usa `GITHUB_TOKEN` con `permissions: contents: write` para hacer commit+push automático de los parquets actualizados
- Streamlit Cloud detecta el push y se redespliega automáticamente

#### Soporte para formato XLSM 2026
- La SEPS cambió el formato del ZIP de balance: 2026 contiene 4 archivos XLSM (uno por segmento) en formato ancho (cooperativas como columnas), en lugar del CSV/TXT de años anteriores
- **Agregada** función `leer_xlsm_balance()` en `procesar_balance_cooperativas.py`
- `leer_archivo_desde_zip()` ahora auto-detecta si el ZIP contiene XLSM y delega a la función correcta
- `procesar_dataframe()` maneja ambos formatos (CSV con columna `FECHA_DE_CORTE`, y XLSM ya normalizado)
- Requiere `openpyxl` (agregado al pip install del workflow)

#### Modo incremental en ETL de balance
- `generar_balance_parquet()` ahora carga el `balance.parquet` existente como base histórica
- Solo procesa ZIPs del año de `fecha_max` en adelante
- Filtra registros nuevos (fecha > fecha_max existente) y concatena
- Esto permite que GitHub Actions procese solo el ZIP nuevo sin necesitar los 8 años de histórico

#### Datos enero 2026
- **234,116 nuevos registros** procesados desde 4 archivos XLSM
- **Total: 23,003,634 registros** (era 22,769,518)
- **Período: Enero 2018 - Enero 2026** (97 meses, era 96)
- `balance.parquet`: 82 MB (era 78 MB)

#### Normalización de nombres de mutualistas
- Detectado cambio en nomenclatura: en 2026 las mutualistas usan nombre corto (`AMBATO`, `AZUAY`, etc.) en lugar del nombre largo de años anteriores
- Verificado que no hay colisión con cooperativas: `AMBATO LTDA` (cooperativa Seg. 1) ≠ `AMBATO` (mutualista Seg. 1 Mutualista)
- **Agregado** dict `MUTUALISTAS_NOMBRES` en `procesar_balance_cooperativas.py` que mapea ambas formas al nombre canónico `Mutualista X`
- Nombres aplicados retroactivamente a los 490,208 registros de mutualistas en toda la historia del parquet

### 2026-02-08 - Despliegue en producción
- **Desplegado en Streamlit Cloud** desde GitHub repo jp1309/cooperativas
- **Optimización de memoria**: RAM reducida de 5.5 GB a 579 MB (-89%)
  - Eliminadas columnas `ruc` y `nivel` de balance.parquet (no usadas por UI)
  - Eliminada columna `ruc` de pyg.parquet (no usada por UI)
  - Columnas string convertidas a category dtype en scripts de procesamiento y data_loader
  - Carga selectiva con `pd.read_parquet(columns=[...])`
- **Archivos de despliegue creados**: requirements.txt, .streamlit/config.toml, .gitignore, README.md
- **CAMEL Evolución Temporal**: Agregados selectores Año inicio/Año fin (igual que Heatmap)
- **Rangos de heatmap ajustados**: ROE [-5, 15], ROA [-1, 3] (proporción ~5x leverage)

### 2026-02-06 - Refinamientos finales
- **Indicadores reducidos a 37**: Eliminados CART_REF, CART_REEST, CART_VENCER de A-Calidad de Activos
- **Rangos de heatmap alineados con bancos**: MOR [0,10], COB [0,300], ACT_IMPR [0,40], AP_PC [80,120], GO_ACT [0,10], GP_ACT [0,5]
- **Truncamiento inteligente de nombres**: `truncar_nombre()` mantiene inicio+final para diferenciar mutualistas y cooperativas similares
- **Corregido conteo**: 37 indicadores en 7 categorías (era 40 antes de eliminar 3 de cartera)

### 2026-02-06 - Ajustes post Fase 4
- **Normalización de nombres unificada**: LIMITADA→LTDA en `procesar_balance_cooperativas.py` y `procesar_camel.py`
- **Nombres de mutualistas expandidos** en `procesar_camel.py`: "AMBATO"→"ASOCIACION MUTUALISTA DE AHORRO Y CREDITO PARA LA VIVIENDA AMBATO"
- **Correcciones de nombre** en `procesar_camel.py` (CORRECCIONES_NOMBRE dict): 8 cooperativas con nombres distintos entre indicadores y balance
- **Catálogo mejorado** en `generar_agregados.py`: usa última fecha por cooperativa (no solo última global)
- `agg_catalogo_cooperativas.parquet`: 259 cooperativas (antes 203)
- `indicadores.parquet`: 231 cooperativas (antes 261, después de normalizar)
- Solo 3 cooperativas sin match en balance (cerradas/absorbidas 2020-2021)
- **Reorganización CAMEL**: Vulnerabilidad (VULN_PAT, FK, FI, CAP_NETO, CART_IMPR_PAT) movida a C-Capital, eliminada SUF_PAT
- **Selectores**: Top 30, Top 50, Todas (ranking y heatmap)
- **Heatmap**: siempre ordena por activos totales (más grande abajo, más pequeño arriba)
- **Segmento unificado**: cada cooperativa toma el segmento de su último dato disponible (51 cooperativas cambiaron de segmento histórico)

### 2026-02-06 - Fase 4 completada (Indicadores CAMEL desde pivot cache)
- Reescrito módulo 4_CAMEL.py: ya no calcula indicadores, los lee pre-extraídos
- Creado script `procesar_camel.py`: extrae indicadores del pivot cache de XLSM
- Generado `indicadores.parquet`: ~550K registros, 231 cooperativas, 2020-2025
- Agregadas constantes CAMEL a `indicator_mapping.py`: GRUPOS_INDICADORES, ETIQUETAS, ESCALAS, RANGOS
- Agregada función `cargar_indicadores()` a `data_loader.py`

### 2026-02-06 - Fase 3 completada
- Agregado módulo 3_Perdidas_Ganancias.py con suma móvil 12 meses
- Creado script procesar_pyg.py (desacumulación + suma móvil)
- Creado script procesar_indicadores.py (extrae datos de XLSM - legacy)
- Agregado pyg.parquet con columnas valor_acumulado, valor_mes, valor_12m
- Normalización de nombres: LIMITADA → LTDA
- Exclusión de totales VT_ en visualizaciones de PyG
- Agregada función cargar_pyg() en data_loader.py

### 2026-02-05 - Fase 2 completada
- Agregado sistema de colores para 200+ cooperativas (Top 10 brillantes, resto gradual)
- Optimización de rendimiento con datos pre-agregados (~3.6 MB vs 73 MB)
- Agregada sección de Pasivos y Patrimonio en Panorama
- Corregida inconsistencia de unidades (1000 → 1_000_000 para millones)
- Unificados selectores de cuentas jerárquicos en los 3 módulos de Balance General
- Agregado script `generar_agregados.py`

### 2026-02-04 - Fase 1 completada
- Implementación completa de ETL de balances
- Módulos Streamlit: Panorama y Balance General
