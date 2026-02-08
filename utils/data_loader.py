# -*- coding: utf-8 -*-
"""
Carga centralizada de datos con validación y limpieza para cooperativas.
Usa archivos pre-agregados para consultas rápidas.
"""

import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional
import json

# Ruta base de datos
MASTER_DATA_DIR = Path(__file__).parent.parent / "master_data"


# =============================================================================
# CARGA DE DATOS PRE-AGREGADOS (RÁPIDO)
# =============================================================================

@st.cache_data(ttl=3600)
def cargar_metricas_sistema() -> pd.DataFrame:
    """
    Carga métricas pre-agregadas por fecha/segmento/código.
    Archivo pequeño (~30KB) para KPIs rápidos.
    """
    filepath = MASTER_DATA_DIR / "agg_metricas_sistema.parquet"
    if not filepath.exists():
        return pd.DataFrame()
    return pd.read_parquet(filepath)


@st.cache_data(ttl=3600)
def cargar_ranking_cooperativas() -> pd.DataFrame:
    """
    Carga ranking pre-agregado de cooperativas.
    Archivo mediano (~1.4MB) para rankings y treemaps.
    """
    filepath = MASTER_DATA_DIR / "agg_ranking_cooperativas.parquet"
    if not filepath.exists():
        return pd.DataFrame()
    return pd.read_parquet(filepath)


@st.cache_data(ttl=3600)
def cargar_series_temporales() -> pd.DataFrame:
    """
    Carga series temporales pre-agregadas.
    Archivo mediano (~2MB) para gráficos de evolución.
    """
    filepath = MASTER_DATA_DIR / "agg_series_temporales.parquet"
    if not filepath.exists():
        return pd.DataFrame()
    return pd.read_parquet(filepath)


@st.cache_data(ttl=3600)
def cargar_catalogo_cooperativas() -> pd.DataFrame:
    """
    Carga catálogo de cooperativas con ranking por activos.
    Archivo muy pequeño (~5KB).
    """
    filepath = MASTER_DATA_DIR / "agg_catalogo_cooperativas.parquet"
    if not filepath.exists():
        return pd.DataFrame()
    return pd.read_parquet(filepath)


# =============================================================================
# FUNCIONES DE CONSULTA OPTIMIZADAS
# =============================================================================

@st.cache_data(ttl=3600)
def obtener_metricas_kpi(fecha, segmento: str = "Todos") -> dict:
    """
    Obtiene métricas del sistema para KPIs de forma optimizada.
    Usa datos pre-agregados en lugar de filtrar 22M registros.
    """
    df = cargar_metricas_sistema()
    if df.empty:
        return {}

    # Filtrar por fecha
    df_fecha = df[df['fecha'] == fecha]

    # Filtrar por segmento
    if segmento != "Todos":
        df_fecha = df_fecha[df_fecha['segmento'] == segmento]

    metricas = {}

    # Mapeo de códigos a nombres
    codigos = {
        'total_activos': '1',
        'fondos_disponibles': '11',
        'total_cartera': '14',
        'total_depositos': '21',
        'total_patrimonio': '3',
    }

    for nombre, codigo in codigos.items():
        valor = df_fecha[df_fecha['codigo'] == codigo]['valor_total'].sum()
        metricas[nombre] = valor / 1_000_000  # Convertir a millones

    # Número de cooperativas (del código 1 = activos)
    df_activos = df_fecha[df_fecha['codigo'] == '1']
    metricas['num_cooperativas'] = df_activos['num_cooperativas'].sum()

    return metricas


@st.cache_data(ttl=3600)
def obtener_ranking_rapido(fecha, codigo: str = '1', top_n: int = 20, segmento: str = "Todos") -> pd.DataFrame:
    """
    Obtiene ranking de cooperativas de forma optimizada.
    """
    df = cargar_ranking_cooperativas()
    if df.empty:
        return pd.DataFrame()

    # Filtrar
    mask = (df['fecha'] == fecha) & (df['codigo'] == codigo)
    if segmento != "Todos":
        mask &= (df['segmento'] == segmento)

    df_filtrado = df[mask].copy()

    if df_filtrado.empty:
        return pd.DataFrame()

    # Ordenar y tomar top N (0 = todas)
    df_filtrado = df_filtrado.sort_values('valor', ascending=False)
    if top_n > 0:
        df_filtrado = df_filtrado.head(top_n)
    df_filtrado['valor_millones'] = df_filtrado['valor'] / 1_000_000

    return df_filtrado[['cooperativa', 'segmento', 'valor', 'valor_millones']]


@st.cache_data(ttl=3600)
def obtener_datos_treemap_rapido(fecha, segmento: str = "Todos", top_n: int = 20) -> pd.DataFrame:
    """
    Prepara datos para treemap de forma optimizada (vectorizado).
    """
    df = cargar_ranking_cooperativas()
    if df.empty:
        return pd.DataFrame()

    # Filtrar por fecha y segmento
    mask = df['fecha'] == fecha
    if segmento != "Todos":
        mask &= df['segmento'] == segmento
    df_fecha = df[mask]

    # NIVEL 1: Top cooperativas por activos (código '1')
    activos = df_fecha[df_fecha['codigo'] == '1'].nlargest(top_n, 'valor')
    activos = activos[activos['valor'].notna() & (activos['valor'] > 0)]

    if activos.empty:
        return pd.DataFrame()

    # Construir nivel 1 vectorizado
    activos_coop_str = activos['cooperativa'].astype(str).values
    df_n1 = pd.DataFrame({
        'labels': activos_coop_str,
        'parents': '',
        'values': activos['valor'].values / 1_000_000,
        'tipo': 'cooperativa',
        'id': activos_coop_str,
    })

    # NIVEL 2: Subcuentas por cooperativa (vectorizado)
    cooperativas_top = activos['cooperativa'].tolist()
    cuentas_nivel2 = {'11': 'Fondos Disponibles', '13': 'Inversiones', '14': 'Cartera de Créditos'}

    df_top = df_fecha[
        df_fecha['cooperativa'].isin(cooperativas_top) &
        df_fecha['codigo'].isin(cuentas_nivel2.keys()) &
        df_fecha['valor'].notna() &
        (df_fecha['valor'] > 0)
    ].copy()

    if not df_top.empty:
        df_top['nombre_cuenta'] = df_top['codigo'].map(cuentas_nivel2)
        coop_str = df_top['cooperativa'].astype(str).values
        df_n2 = pd.DataFrame({
            'labels': df_top['nombre_cuenta'].values,
            'parents': coop_str,
            'values': df_top['valor'].values / 1_000_000,
            'tipo': 'cuenta_nivel2',
            'id': coop_str + '_' + df_top['nombre_cuenta'].values,
        })
        df_tree = pd.concat([df_n1, df_n2], ignore_index=True)
    else:
        df_tree = df_n1

    # Participación
    total_sistema = df_n1['values'].sum()
    df_tree['participacion'] = (df_tree['values'] / total_sistema * 100) if total_sistema > 0 else 0

    return df_tree


@st.cache_data(ttl=3600)
def obtener_datos_treemap_pasivos_rapido(fecha, segmento: str = "Todos", top_n: int = 20) -> pd.DataFrame:
    """
    Prepara datos para treemap de pasivos y patrimonio (vectorizado).
    """
    df = cargar_ranking_cooperativas()
    if df.empty:
        return pd.DataFrame()

    # Filtrar por fecha y segmento
    mask = df['fecha'] == fecha
    if segmento != "Todos":
        mask &= df['segmento'] == segmento
    df_fecha = df[mask]

    # Top cooperativas por activos
    activos = df_fecha[df_fecha['codigo'] == '1'].nlargest(top_n, 'valor')
    cooperativas_top = activos['cooperativa'].tolist()

    # NIVEL 1: Pasivo + Patrimonio por cooperativa (vectorizado)
    df_pas_pat = df_fecha[
        df_fecha['cooperativa'].isin(cooperativas_top) &
        df_fecha['codigo'].isin(['2', '3'])
    ]
    totales = df_pas_pat.groupby('cooperativa', observed=True)['valor'].sum().reset_index()
    totales = totales[totales['valor'] > 0]

    if totales.empty:
        return pd.DataFrame()

    totales_coop_str = totales['cooperativa'].astype(str).values
    df_n1 = pd.DataFrame({
        'labels': totales_coop_str,
        'parents': '',
        'values': totales['valor'].values / 1_000_000,
        'tipo': 'cooperativa',
        'id': totales_coop_str,
    })

    # NIVEL 2: Subcuentas por cooperativa (vectorizado)
    cuentas_nivel2 = {'21': 'Obligaciones con el Público', '26': 'Obligaciones Financieras', '3': 'Patrimonio'}

    df_sub = df_fecha[
        df_fecha['cooperativa'].isin(cooperativas_top) &
        df_fecha['codigo'].isin(cuentas_nivel2.keys()) &
        df_fecha['valor'].notna() &
        (df_fecha['valor'] > 0)
    ].copy()

    if not df_sub.empty:
        df_sub['nombre_cuenta'] = df_sub['codigo'].map(cuentas_nivel2)
        coop_str = df_sub['cooperativa'].astype(str).values
        df_n2 = pd.DataFrame({
            'labels': df_sub['nombre_cuenta'].values,
            'parents': coop_str,
            'values': df_sub['valor'].values / 1_000_000,
            'tipo': 'cuenta_nivel2',
            'id': coop_str + '_' + df_sub['nombre_cuenta'].values,
        })
        df_tree = pd.concat([df_n1, df_n2], ignore_index=True)
    else:
        df_tree = df_n1

    # Participación
    total_sistema = df_n1['values'].sum()
    df_tree['participacion'] = (df_tree['values'] / total_sistema * 100) if total_sistema > 0 else 0

    return df_tree


@st.cache_data(ttl=3600)
def obtener_crecimiento_anual(fecha_actual, fecha_anterior, codigo: str, segmento: str = "Todos", top_n: int = 20) -> pd.DataFrame:
    """
    Calcula crecimiento anual por cooperativa de forma optimizada.
    """
    df = cargar_ranking_cooperativas()
    if df.empty:
        return pd.DataFrame()

    # Datos actuales
    mask_actual = (df['fecha'] == fecha_actual) & (df['codigo'] == codigo)
    if segmento != "Todos":
        mask_actual &= (df['segmento'] == segmento)
    df_actual = df[mask_actual][['cooperativa', 'segmento', 'valor']].copy()
    df_actual = df_actual.rename(columns={'valor': 'valor_actual'})

    # Datos anteriores
    mask_anterior = (df['fecha'] == fecha_anterior) & (df['codigo'] == codigo)
    df_anterior = df[mask_anterior][['cooperativa', 'valor']].copy()
    df_anterior = df_anterior.rename(columns={'valor': 'valor_anterior'})

    # Merge
    df_crec = df_actual.merge(df_anterior, on='cooperativa', how='inner')

    # Calcular crecimiento
    df_crec['crecimiento'] = (
        (df_crec['valor_actual'] - df_crec['valor_anterior']) /
        df_crec['valor_anterior'] * 100
    )

    # Filtrar y ordenar (top_n=0 = todas)
    df_crec = df_crec[df_crec['valor_anterior'] > 0].dropna(subset=['crecimiento'])
    if top_n > 0:
        df_crec = df_crec.nlargest(top_n, 'valor_actual')
    df_crec = df_crec.sort_values('crecimiento', ascending=True)

    return df_crec


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

@st.cache_data(ttl=3600)
def obtener_fechas_disponibles_rapido() -> list:
    """Obtiene lista de fechas únicas desde datos pre-agregados."""
    df = cargar_metricas_sistema()
    if df.empty:
        return []
    fechas = df['fecha'].unique()
    return sorted(fechas, reverse=True)


@st.cache_data(ttl=3600)
def obtener_segmentos_disponibles_rapido() -> list:
    """Obtiene lista de segmentos únicos desde datos pre-agregados."""
    df = cargar_metricas_sistema()
    if df.empty:
        return []
    return sorted(df['segmento'].unique())


@st.cache_data(ttl=3600)
def obtener_cooperativas_por_segmento(segmento: str = "Todos") -> list:
    """Obtiene lista de cooperativas ordenadas por activos."""
    df = cargar_catalogo_cooperativas()
    if df.empty:
        return []

    if segmento != "Todos":
        df = df[df['segmento'] == segmento]

    return df['cooperativa'].tolist()


# =============================================================================
# CARGA DE DATOS COMPLETOS (SOLO CUANDO ES NECESARIO)
# =============================================================================

@st.cache_data(ttl=3600)
def cargar_balance() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Carga balance.parquet completo.
    NOTA: Solo usar cuando se necesiten datos detallados (nivel 4-6 dígitos).
    Para la mayoría de consultas, usar las funciones optimizadas.
    """
    filepath = MASTER_DATA_DIR / "balance.parquet"

    if not filepath.exists():
        raise FileNotFoundError(f"No se encontró {filepath}")

    df = pd.read_parquet(filepath)

    # Convertir fecha si es necesario
    if not pd.api.types.is_datetime64_any_dtype(df['fecha']):
        df['fecha'] = pd.to_datetime(df['fecha'])

    calidad = {
        'registros': len(df),
        'cooperativas': df['cooperativa'].nunique(),
        'segmentos': df['segmento'].nunique(),
        'fecha_min': df['fecha'].min(),
        'fecha_max': df['fecha'].max(),
    }

    return df, calidad


@st.cache_data(ttl=3600)
def cargar_metadata() -> Dict[str, Any]:
    """Carga metadata.json."""
    filepath = MASTER_DATA_DIR / "metadata.json"
    if not filepath.exists():
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


@st.cache_data(ttl=3600)
def cargar_indicadores() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Carga indicadores.parquet (Indicadores CAMEL extraídos del pivot cache).

    Columnas: cooperativa, segmento, fecha, codigo, indicador, valor, categoria
    Valores almacenados como ratios (0-1), no porcentajes.
    """
    filepath = MASTER_DATA_DIR / "indicadores.parquet"

    if not filepath.exists():
        raise FileNotFoundError(f"No se encontró {filepath}")

    df_original = pd.read_parquet(filepath)
    registros_originales = len(df_original)

    df = df_original.copy()

    # Filtrar indicadores vacíos
    mask_indicador_valido = df['indicador'].fillna('').str.strip() != ''
    df = df[mask_indicador_valido]

    # Filtrar valores nulos en columnas clave
    df = df.dropna(subset=['cooperativa', 'fecha'])

    # Convertir fecha a datetime si no lo es
    if not pd.api.types.is_datetime64_any_dtype(df['fecha']):
        df['fecha'] = pd.to_datetime(df['fecha'])

    calidad = {
        'registros_originales': registros_originales,
        'registros_limpios': len(df),
        'registros_eliminados': registros_originales - len(df),
        'cooperativas': df['cooperativa'].nunique(),
        'fechas': df['fecha'].nunique(),
        'fecha_min': df['fecha'].min(),
        'fecha_max': df['fecha'].max(),
        'indicadores_unicos': df['codigo'].nunique(),
        'categorias': df['categoria'].unique().tolist(),
    }

    return df, calidad


@st.cache_data(ttl=3600)
def cargar_pyg() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Carga pyg.parquet (Estado de Pérdidas y Ganancias).
    Contiene cuentas 4 (Gastos) y 5 (Ingresos).
    """
    filepath = MASTER_DATA_DIR / "pyg.parquet"

    if not filepath.exists():
        raise FileNotFoundError(f"No se encontró {filepath}")

    df = pd.read_parquet(filepath)

    # Convertir fecha si es necesario
    if not pd.api.types.is_datetime64_any_dtype(df['fecha']):
        df['fecha'] = pd.to_datetime(df['fecha'])

    calidad = {
        'registros': len(df),
        'cooperativas': df['cooperativa'].nunique(),
        'segmentos': df['segmento'].nunique(),
        'fecha_min': df['fecha'].min(),
        'fecha_max': df['fecha'].max(),
    }

    return df, calidad


# =============================================================================
# FUNCIONES LEGACY (compatibilidad con código existente)
# =============================================================================

def obtener_fechas_disponibles(df: pd.DataFrame) -> list:
    """Obtiene lista de fechas únicas ordenadas (más reciente primero)."""
    fechas = df['fecha'].dropna().unique()
    return sorted(fechas, reverse=True)


def obtener_segmentos_disponibles(df: pd.DataFrame) -> list:
    """Obtiene lista de segmentos únicos."""
    return sorted(df['segmento'].unique())


def filtrar_por_segmento(df: pd.DataFrame, segmento: str) -> pd.DataFrame:
    """Filtra DataFrame por segmento."""
    if segmento == "Todos":
        return df.copy()
    return df[df['segmento'] == segmento].copy()


def obtener_top_cooperativas(
    df: pd.DataFrame,
    fecha,
    codigo: str = '1',
    top_n: int = 20,
    segmento: Optional[str] = None
) -> List[str]:
    """Obtiene top N cooperativas por valor."""
    df_filtrado = df[(df['fecha'] == fecha) & (df['codigo'] == codigo)]
    if segmento and segmento != "Todos":
        df_filtrado = df_filtrado[df_filtrado['segmento'] == segmento]
    return df_filtrado.nlargest(top_n, 'valor')['cooperativa'].tolist()
