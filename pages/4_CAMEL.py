# -*- coding: utf-8 -*-
"""
Módulo 4: Indicadores CAMEL
Análisis de indicadores financieros del sistema cooperativo ecuatoriano.
Carga indicadores pre-calculados extraídos de las tablas dinámicas de la Superintendencia.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from utils.data_loader import (
    cargar_indicadores,
    obtener_cooperativas_por_segmento,
)
from config.indicator_mapping import (
    GRUPOS_INDICADORES,
    ETIQUETAS_INDICADORES,
    ESCALAS_COLORES_HEATMAP,
    RANGOS_HEATMAP,
)
from utils.charts import obtener_color_cooperativa

# =============================================================================
# CONFIGURACION
# =============================================================================

st.set_page_config(
    page_title="CAMEL | Radar Cooperativo",
    page_icon="📈",
    layout="wide",
)

# Diccionario de meses
MESES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}


# =============================================================================
# FUNCIONES DE CONSULTA
# =============================================================================

@st.cache_data
def obtener_ranking_indicador(df, codigo, fecha, segmento="Todos", top_n=20):
    """Ranking de cooperativas para un indicador en una fecha."""
    df_f = df[(df['codigo'] == codigo) & (df['fecha'] == fecha)]
    if segmento != "Todos":
        df_f = df_f[df_f['segmento'] == segmento]
    df_f = df_f.copy()
    df_f['valor_pct'] = df_f['valor'] * 100
    df_f = df_f.sort_values('valor_pct', ascending=False)
    resultado = df_f[['cooperativa', 'segmento', 'valor', 'valor_pct']]
    return resultado if top_n == 0 else resultado.head(top_n)


@st.cache_data
def obtener_evolucion_indicador(df, codigo, cooperativas, segmento="Todos",
                                 fecha_inicio=None, fecha_fin=None):
    """Serie temporal de un indicador para cooperativas seleccionadas."""
    df_f = df[(df['codigo'] == codigo) & (df['cooperativa'].isin(cooperativas))]
    if segmento != "Todos":
        df_f = df_f[df_f['segmento'] == segmento]
    if fecha_inicio is not None:
        df_f = df_f[df_f['fecha'] >= pd.Timestamp(fecha_inicio)]
    if fecha_fin is not None:
        df_f = df_f[df_f['fecha'] <= pd.Timestamp(fecha_fin)]
    df_f = df_f.copy()
    df_f['valor_pct'] = df_f['valor'] * 100
    return df_f[['fecha', 'cooperativa', 'valor_pct']].sort_values(['cooperativa', 'fecha'])


@st.cache_data
def obtener_heatmap_indicador(df, codigo, cooperativas_ordenadas,
                               segmento="Todos", fecha_inicio=None,
                               fecha_fin=None, top_n=15):
    """Datos para heatmap: cooperativas x periodos."""
    df_f = df[df['codigo'] == codigo].copy()
    if segmento != "Todos":
        df_f = df_f[df_f['segmento'] == segmento]
    if fecha_inicio is not None:
        df_f = df_f[df_f['fecha'] >= pd.Timestamp(fecha_inicio)]
    if fecha_fin is not None:
        df_f = df_f[df_f['fecha'] <= pd.Timestamp(fecha_fin)]

    if df_f.empty:
        return pd.DataFrame()

    # Tomar cooperativas ordenadas por activos, agregar las que falten al final
    coops_en_datos = set(df_f['cooperativa'].unique())
    coops_con_orden = [c for c in cooperativas_ordenadas if c in coops_en_datos]
    coops_sin_orden = sorted(coops_en_datos - set(coops_con_orden))
    coops_todas = coops_con_orden + coops_sin_orden
    top_coops = coops_todas if top_n == 0 else coops_todas[:top_n]
    df_f = df_f[df_f['cooperativa'].isin(top_coops)]

    df_f['periodo'] = df_f['fecha'].dt.strftime('%Y-%m')

    heatmap = df_f.pivot_table(
        index='cooperativa', columns='periodo', values='valor', aggfunc='first'
    )

    # Ordenar cooperativas según el orden de activos (invertido: más grande abajo)
    orden = [c for c in top_coops if c in heatmap.index]
    orden.reverse()
    heatmap = heatmap.reindex(orden)

    return heatmap * 100  # ratio -> porcentaje


# =============================================================================
# UTILIDADES
# =============================================================================

def truncar_nombre(n, max_len=30):
    """Trunca nombres largos manteniendo inicio y final para diferenciar."""
    if len(n) <= max_len:
        return n
    return n[:12] + '...' + n[-(max_len - 15):]


# =============================================================================
# PAGINA PRINCIPAL
# =============================================================================

def main():
    st.title("📈 Indicadores CAMEL")
    st.markdown("Indicadores financieros oficiales del sistema cooperativo ecuatoriano.")

    # Cargar datos
    try:
        df_camel, calidad = cargar_indicadores()
    except FileNotFoundError:
        st.error("No se encontró el archivo de indicadores.")
        st.info("Ejecuta: `python cooperativas/scripts/procesar_camel.py`")
        return

    if df_camel.empty:
        st.warning("No hay datos de indicadores disponibles.")
        return

    # Fechas y segmentos disponibles
    fechas = sorted(df_camel['fecha'].unique(), reverse=True)
    segmentos_disponibles = sorted(df_camel['segmento'].unique())

    # Sidebar - Filtros globales
    st.sidebar.markdown("### Filtros")

    segmento_global = st.sidebar.selectbox(
        "Segmento",
        options=["Todos"] + segmentos_disponibles,
        index=0,
        key="segmento_camel"
    )

    fecha_seleccionada = st.sidebar.selectbox(
        "Fecha de análisis",
        options=fechas,
        format_func=lambda x: pd.Timestamp(x).strftime('%B %Y').title(),
        index=0,
        key="fecha_camel"
    )

    # Lista de cooperativas ordenadas por activos
    cooperativas_ordenadas = obtener_cooperativas_por_segmento(segmento_global)
    if not cooperativas_ordenadas:
        # Fallback: usar cooperativas del dataset de indicadores
        cooperativas_ordenadas = sorted(df_camel['cooperativa'].unique())

    cooperativas_default = cooperativas_ordenadas[:4] if len(cooperativas_ordenadas) >= 4 else cooperativas_ordenadas

    # Info en sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Indicadores:** {calidad['indicadores_unicos']}")
    st.sidebar.markdown(f"**Cooperativas:** {calidad['cooperativas']}")
    st.sidebar.markdown(f"**Período:** {calidad['fecha_min'].strftime('%Y-%m')} - {calidad['fecha_max'].strftime('%Y-%m')}")

    # ==========================================================================
    # TABS PRINCIPALES
    # ==========================================================================

    tab1, tab2, tab3 = st.tabs([
        "📊 Ranking por Indicador",
        "📈 Evolución Temporal",
        "🗺️ Heatmap Mensual"
    ])

    # ==========================================================================
    # TAB 1: RANKING POR INDICADOR
    # ==========================================================================

    with tab1:
        col_filtros, col_grafico = st.columns([1, 3])

        with col_filtros:
            categorias = list(GRUPOS_INDICADORES.keys())
            categoria_sel = st.selectbox(
                "Categoría CAMEL",
                categorias,
                index=0,
                key="categoria_rank"
            )

            codigos_cat = GRUPOS_INDICADORES[categoria_sel]
            indicador_opciones = {ETIQUETAS_INDICADORES.get(c, c): c for c in codigos_cat}
            indicador_nombre = st.selectbox(
                "Indicador",
                list(indicador_opciones.keys()),
                key="indicador_rank"
            )
            indicador_codigo = indicador_opciones[indicador_nombre]

            top_n = st.selectbox(
                "Cooperativas a mostrar",
                options=[30, 50, 0],
                index=0,
                format_func=lambda x: "Todas" if x == 0 else f"Top {x}",
                key="top_n_rank"
            )

        with col_grafico:
            df_ranking = obtener_ranking_indicador(
                df_camel, indicador_codigo, fecha_seleccionada,
                segmento_global, top_n
            )

            if not df_ranking.empty:
                df_ranking_plot = df_ranking.sort_values('valor_pct', ascending=True)

                # Colores por cooperativa
                colores = [obtener_color_cooperativa(coop) for coop in df_ranking_plot['cooperativa']]

                fig = go.Figure(go.Bar(
                    x=df_ranking_plot['valor_pct'],
                    y=df_ranking_plot['cooperativa'].apply(truncar_nombre),
                    orientation='h',
                    marker=dict(color=colores),
                    text=df_ranking_plot['valor_pct'].apply(lambda x: f"{x:.1f}%"),
                    textposition='outside',
                    hovertemplate='<b>%{y}</b><br>Valor: %{x:.2f}%<extra></extra>'
                ))

                fig.update_layout(
                    title=f"{indicador_nombre} - {pd.Timestamp(fecha_seleccionada).strftime('%B %Y').title()}",
                    height=max(400, len(df_ranking_plot) * 25),
                    xaxis_title='Valor (%)',
                    yaxis_title='',
                    showlegend=False,
                    margin=dict(l=10, r=10, t=40, b=40)
                )

                st.plotly_chart(fig, width='stretch')

                # Estadísticas
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric("Promedio", f"{df_ranking['valor_pct'].mean():.2f}%")
                with col_s2:
                    st.metric("Máximo", f"{df_ranking['valor_pct'].max():.2f}%")
                with col_s3:
                    st.metric("Mínimo", f"{df_ranking['valor_pct'].min():.2f}%")
            else:
                st.warning("No hay datos disponibles para este indicador.")

    # ==========================================================================
    # TAB 2: EVOLUCION TEMPORAL
    # ==========================================================================

    with tab2:
        col_filtros2, col_grafico2 = st.columns([1, 3])

        with col_filtros2:
            categoria_evol = st.selectbox(
                "Categoría CAMEL",
                list(GRUPOS_INDICADORES.keys()),
                index=0,
                key="categoria_evol"
            )

            codigos_evol = GRUPOS_INDICADORES[categoria_evol]
            indicador_opciones_evol = {ETIQUETAS_INDICADORES.get(c, c): c for c in codigos_evol}
            indicador_nombre_evol = st.selectbox(
                "Indicador",
                list(indicador_opciones_evol.keys()),
                key="indicador_evol"
            )
            indicador_codigo_evol = indicador_opciones_evol[indicador_nombre_evol]

            cooperativas_evol = st.multiselect(
                "Cooperativas a comparar",
                cooperativas_ordenadas,
                default=cooperativas_default,
                max_selections=8,
                key="cooperativas_evol"
            )

            # Rango de años
            st.markdown("---")
            anos_disponibles_evol = sorted(df_camel['fecha'].dt.year.unique())

            col_ae, col_be = st.columns(2)
            with col_ae:
                ano_inicio_evol = st.selectbox(
                    "Año inicio",
                    anos_disponibles_evol,
                    index=0,
                    key="ano_inicio_evol"
                )
            with col_be:
                ano_fin_evol = st.selectbox(
                    "Año fin",
                    anos_disponibles_evol,
                    index=len(anos_disponibles_evol) - 1,
                    key="ano_fin_evol"
                )

        with col_grafico2:
            if not cooperativas_evol:
                st.info("Selecciona al menos una cooperativa para ver la evolución.")
            else:
                fecha_inicio_evol = pd.Timestamp(year=ano_inicio_evol, month=1, day=1)
                fecha_fin_evol = pd.Timestamp(year=ano_fin_evol, month=12, day=31)

                df_serie = obtener_evolucion_indicador(
                    df_camel, indicador_codigo_evol,
                    cooperativas_evol, segmento_global,
                    fecha_inicio_evol, fecha_fin_evol
                )

                if not df_serie.empty:
                    color_map = {coop: obtener_color_cooperativa(coop) for coop in cooperativas_evol}

                    fig_evol = px.line(
                        df_serie,
                        x='fecha',
                        y='valor_pct',
                        color='cooperativa',
                        title=f"Evolución: {indicador_nombre_evol}",
                        labels={'fecha': 'Fecha', 'valor_pct': 'Valor (%)', 'cooperativa': 'Cooperativa'},
                        color_discrete_map=color_map,
                    )

                    fig_evol.update_layout(
                        height=450,
                        legend=dict(orientation='h', yanchor='bottom', y=-0.3, xanchor='center', x=0.5),
                        hovermode='x unified',
                    )

                    st.plotly_chart(fig_evol, width='stretch')
                else:
                    st.warning("No hay datos disponibles para las cooperativas seleccionadas.")

    # ==========================================================================
    # TAB 3: HEATMAP MENSUAL
    # ==========================================================================

    with tab3:
        col_filtros3, col_grafico3 = st.columns([1, 3])

        with col_filtros3:
            categoria_heat = st.selectbox(
                "Categoría CAMEL",
                list(GRUPOS_INDICADORES.keys()),
                index=0,
                key="categoria_heat"
            )

            codigos_heat = GRUPOS_INDICADORES[categoria_heat]
            indicador_opciones_heat = {ETIQUETAS_INDICADORES.get(c, c): c for c in codigos_heat}
            indicador_nombre_heat = st.selectbox(
                "Indicador",
                list(indicador_opciones_heat.keys()),
                key="indicador_heat"
            )
            indicador_codigo_heat = indicador_opciones_heat[indicador_nombre_heat]

            top_n_heat = st.selectbox(
                "Cooperativas a mostrar",
                options=[30, 50, 0],
                index=0,
                format_func=lambda x: "Todas" if x == 0 else f"Top {x}",
                key="top_n_heat"
            )

            # Rango de años
            st.markdown("---")
            anos_disponibles = sorted(df_camel['fecha'].dt.year.unique())

            col_a, col_b = st.columns(2)
            with col_a:
                ano_inicio = st.selectbox(
                    "Año inicio",
                    anos_disponibles,
                    index=max(0, len(anos_disponibles) - 3),
                    key="ano_inicio_heat"
                )
            with col_b:
                ano_fin = st.selectbox(
                    "Año fin",
                    anos_disponibles,
                    index=len(anos_disponibles) - 1,
                    key="ano_fin_heat"
                )

        with col_grafico3:
            fecha_inicio_heat = pd.Timestamp(year=ano_inicio, month=1, day=1)
            fecha_fin_heat = pd.Timestamp(year=ano_fin, month=12, day=31)

            heatmap_data = obtener_heatmap_indicador(
                df_camel, indicador_codigo_heat,
                cooperativas_ordenadas,
                segmento_global,
                fecha_inicio_heat, fecha_fin_heat,
                top_n_heat
            )

            if not heatmap_data.empty:
                # Escala de colores
                colorscale = ESCALAS_COLORES_HEATMAP.get(indicador_codigo_heat, 'RdYlGn')

                # Rangos
                rango = RANGOS_HEATMAP.get(indicador_codigo_heat)
                zmin = rango[0] if rango else None
                zmax = rango[1] if rango else None

                # Truncar nombres largos (mantener final para diferenciar)
                y_labels = [truncar_nombre(n) for n in heatmap_data.index]

                fig_heat = go.Figure(data=go.Heatmap(
                    z=heatmap_data.values,
                    x=heatmap_data.columns,
                    y=y_labels,
                    colorscale=colorscale,
                    zmin=zmin,
                    zmax=zmax,
                    hovertemplate='Cooperativa: %{y}<br>Período: %{x}<br>Valor: %{z:.2f}%<extra></extra>',
                    colorbar=dict(title='Valor (%)')
                ))

                fig_heat.update_layout(
                    title=f"Evolución Mensual: {indicador_nombre_heat}",
                    height=max(400, len(heatmap_data) * 28),
                    xaxis_title='Período',
                    yaxis_title='',
                    xaxis={'tickangle': -45},
                    margin=dict(l=10, r=10, t=40, b=80)
                )

                st.plotly_chart(fig_heat, width='stretch')
            else:
                st.warning("No hay datos suficientes para el heatmap.")


if __name__ == "__main__":
    main()
