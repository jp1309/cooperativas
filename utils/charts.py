# -*- coding: utf-8 -*-
"""
Componentes gráficos reutilizables para el dashboard de cooperativas.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import List, Optional, Dict, Any
from pathlib import Path
import sys

# Agregar path para imports
sys.path.append(str(Path(__file__).parent.parent))
from config.indicator_mapping import COLORES_COOPERATIVAS, COLORES_SEGMENTO, obtener_color_cooperativa, obtener_color_segmento


# =============================================================================
# COLORES Y ESTILOS
# =============================================================================

COLORES = {
    'primario': '#1a365d',
    'secundario': '#2c5282',
    'acento': '#3182ce',
    'exito': '#38a169',
    'advertencia': '#dd6b20',
    'error': '#e53e3e',
    'neutro': '#718096',
    'fondo': '#f7fafc',
}

PALETA_COOPERATIVAS = px.colors.qualitative.Set2 + px.colors.qualitative.Pastel1

LAYOUT_BASE = {
    'font': {'family': 'Inter, sans-serif'},
    'paper_bgcolor': 'white',
    'plot_bgcolor': 'white',
    'margin': {'l': 10, 'r': 10, 't': 40, 'b': 10},
}


# =============================================================================
# FUNCIONES DE COLORES
# =============================================================================

def obtener_colores_para_cooperativas(cooperativas: List[str]) -> Dict[str, str]:
    """Obtiene un diccionario de colores para una lista de cooperativas."""
    return {coop: obtener_color_cooperativa(coop) for coop in cooperativas}


# =============================================================================
# TARJETAS KPI
# =============================================================================

def render_kpi_card(
    valor: str,
    label: str,
    delta: Optional[float] = None,
    delta_label: str = "",
    color: str = COLORES['acento']
):
    """Renderiza una tarjeta KPI con estilos personalizados."""
    delta_html = ""
    if delta is not None:
        signo = "+" if delta >= 0 else ""
        delta_color = COLORES['exito'] if delta >= 0 else COLORES['error']
        delta_html = f'<div style="color: {delta_color}; font-size: 0.85rem; margin-top: 4px;">{signo}{delta:.1f}% {delta_label}</div>'

    st.markdown(f"""
        <div style="
            background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
            border-radius: 12px;
            padding: 1.2rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            border-left: 4px solid {color};
            margin-bottom: 1rem;
        ">
            <div style="font-size: 1.8rem; font-weight: 700; color: #1a365d;">{valor}</div>
            <div style="font-size: 0.8rem; color: #718096; text-transform: uppercase; letter-spacing: 0.5px;">{label}</div>
            {delta_html}
        </div>
    """, unsafe_allow_html=True)


# =============================================================================
# GRAFICOS DE RANKING
# =============================================================================

def crear_ranking_barras(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    titulo: str = "",
    formato_valor: str = "${:,.0f}M",
    altura: int = 400,
    usar_colores_cooperativas: bool = True
) -> go.Figure:
    """Crea gráfico de barras horizontales para ranking."""
    df_sorted = df.sort_values(x_col, ascending=True)

    # Determinar colores
    if usar_colores_cooperativas and y_col == 'cooperativa':
        colors = [obtener_color_cooperativa(coop) for coop in df_sorted[y_col]]
        marker_dict = dict(color=colors)
    else:
        colors = df_sorted[x_col]
        marker_dict = dict(color=colors, colorscale='Blues')

    fig = go.Figure(go.Bar(
        y=df_sorted[y_col],
        x=df_sorted[x_col],
        orientation='h',
        marker=marker_dict,
        text=[formato_valor.format(v) for v in df_sorted[x_col]],
        textposition='outside',
        hovertemplate="<b>%{y}</b><br>Valor: %{x:,.2f}<extra></extra>"
    ))

    fig.update_layout(
        **LAYOUT_BASE,
        title=titulo,
        height=altura,
        xaxis_title="",
        yaxis_title="",
        yaxis=dict(categoryorder='total ascending'),
        showlegend=False
    )

    return fig


# =============================================================================
# TREEMAP
# =============================================================================

def crear_treemap(
    df: pd.DataFrame,
    path_col: str = None,
    values_col: str = None,
    titulo: str = "",
    altura: int = 450,
    jerarquico: bool = False
) -> go.Figure:
    """Crea un treemap para visualizar composición."""
    df_clean = df.copy()

    if jerarquico:
        required_cols = ['labels', 'parents', 'values']
        if not all(col in df_clean.columns for col in required_cols):
            fig = go.Figure()
            fig.add_annotation(
                text="Estructura de datos incorrecta",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(height=altura, title=titulo)
            return fig

        df_clean = df_clean.dropna(subset=['values'])
        df_clean = df_clean[df_clean['values'] > 0]

        if df_clean.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="No hay datos disponibles",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(height=altura, title=titulo)
            return fig

        labels = df_clean['labels'].tolist()
        parents = df_clean['parents'].tolist()
        values = df_clean['values'].tolist()

        if 'id' in df_clean.columns:
            ids = df_clean['id'].tolist()
        else:
            ids = None

        if 'participacion' in df_clean.columns:
            colors = df_clean['participacion'].tolist()
        else:
            colors = values

        texttemplate = "%{label}<br>$%{value:,.0f}M"

        if 'participacion' in df_clean.columns:
            customdata = df_clean[['participacion']].values.tolist()
            hovertemplate = "<b>%{label}</b><br>Valor: $%{value:,.0f}M<br>Participación: %{customdata[0]:.1f}%<extra></extra>"
        else:
            customdata = None
            hovertemplate = "<b>%{label}</b><br>Valor: $%{value:,.0f}M<extra></extra>"

        fig = go.Figure(go.Treemap(
            labels=labels,
            ids=ids,
            parents=parents,
            values=values,
            marker=dict(
                colors=colors,
                colorscale='Blues',
                showscale=False,
                line=dict(width=2, color='white')
            ),
            texttemplate=texttemplate,
            customdata=customdata,
            hovertemplate=hovertemplate,
            branchvalues="total"
        ))

    else:
        df_clean = df_clean.dropna(subset=[values_col, path_col])
        df_clean = df_clean[df_clean[values_col] > 0]

        if df_clean.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="No hay datos disponibles",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(height=altura, title=titulo)
            return fig

        labels = df_clean[path_col].tolist()
        parents = [''] * len(labels)
        values = df_clean[values_col].tolist()
        colors = values

        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            marker=dict(
                colors=colors,
                colorscale='Blues',
                showscale=True
            ),
            hovertemplate="<b>%{label}</b><br>Valor: $%{value:,.0f}M<extra></extra>"
        ))

    fig.update_layout(
        **LAYOUT_BASE,
        title=titulo,
        height=altura,
    )

    return fig


# =============================================================================
# GRAFICO DE LINEAS (SERIES TEMPORALES)
# =============================================================================

def crear_linea_temporal(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    color_col: Optional[str] = None,
    titulo: str = "",
    y_label: str = "Valor",
    altura: int = 400,
    mostrar_area: bool = False,
    usar_colores_cooperativas: bool = True
) -> go.Figure:
    """Crea gráfico de líneas para series temporales."""
    if color_col:
        if usar_colores_cooperativas and color_col == 'cooperativa':
            cooperativas = df[color_col].unique().tolist()
            color_map = obtener_colores_para_cooperativas(cooperativas)

            fig = px.line(
                df,
                x=x_col,
                y=y_col,
                color=color_col,
                markers=True,
                line_shape='spline',
                color_discrete_map=color_map,
            )
        else:
            fig = px.line(
                df,
                x=x_col,
                y=y_col,
                color=color_col,
                markers=True,
                line_shape='spline',
                color_discrete_sequence=PALETA_COOPERATIVAS,
            )
    else:
        fig = px.line(
            df,
            x=x_col,
            y=y_col,
            markers=True,
            line_shape='spline',
        )
        if mostrar_area:
            fig.update_traces(fill='tozeroy', line_color=COLORES['acento'])

    fig.update_layout(
        **LAYOUT_BASE,
        title=titulo,
        height=altura,
        xaxis_title="",
        yaxis_title=y_label,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    fig.update_xaxes(showgrid=True, gridcolor='#f0f0f0')
    fig.update_yaxes(showgrid=True, gridcolor='#f0f0f0')

    return fig


# =============================================================================
# HEATMAP
# =============================================================================

def crear_heatmap(
    df: pd.DataFrame,
    titulo: str = "",
    color_scale: str = 'RdYlGn',
    altura: int = 400,
    mostrar_valores: bool = True
) -> go.Figure:
    """Crea heatmap a partir de un DataFrame pivotado."""
    fig = px.imshow(
        df,
        color_continuous_scale=color_scale,
        aspect='auto',
    )

    if mostrar_valores:
        fig.update_traces(
            text=df.values,
            texttemplate="%{text:.1f}",
            textfont={"size": 10},
        )

    fig.update_layout(
        **LAYOUT_BASE,
        title=titulo,
        height=altura,
    )

    return fig
