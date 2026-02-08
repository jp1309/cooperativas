# -*- coding: utf-8 -*-
"""
Módulo 3: Pérdidas y Ganancias
Análisis de resultados y rentabilidad del sistema cooperativo.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import sys
import calendar

sys.path.append(str(Path(__file__).parent.parent))

from utils.data_loader import (
    cargar_pyg,
    cargar_balance,
    obtener_fechas_disponibles,
    obtener_segmentos_disponibles,
)
from utils.charts import obtener_color_cooperativa

# =============================================================================
# CONFIGURACION
# =============================================================================

st.set_page_config(
    page_title="Pérdidas y Ganancias | Radar Cooperativo",
    page_icon="💰",
    layout="wide",
)

# Mapeo de cuentas principales de PYG (usando códigos contables)
CUENTAS_PYG = {
    '5': 'INGRESOS (Total)',
    '51': 'Intereses y Descuentos Ganados',
    '52': 'Comisiones Ganadas',
    '54': 'Ingresos por Servicios',
    '4': 'GASTOS (Total)',
    '41': 'Intereses Causados',
    '44': 'Provisiones',
    '45': 'Gastos de Operación',
}

# Diccionario de meses
MESES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

# =============================================================================
# FUNCIONES DE DATOS
# =============================================================================

@st.cache_data
def obtener_orden_cooperativas_por_activos(segmento: str = "Todos") -> list:
    """Obtiene lista de cooperativas ordenadas por activos totales (mayor a menor)."""
    try:
        df_balance, _ = cargar_balance()
        fecha_max_bal = df_balance['fecha'].max()
        # Codigo '1' es activo total
        df_activos = df_balance[
            (df_balance['fecha'] == fecha_max_bal) &
            (df_balance['codigo'] == '1')
        ][['cooperativa', 'segmento', 'valor']].copy()

        if segmento != "Todos":
            df_activos = df_activos[df_activos['segmento'] == segmento]

        df_activos = df_activos.sort_values('valor', ascending=False)
        return df_activos['cooperativa'].tolist()
    except Exception:
        return []


@st.cache_data
def construir_jerarquia_pyg(df: pd.DataFrame) -> dict:
    """Construye jerarquía de cuentas PyG desde los datos."""
    jerarquia = {}

    # Obtener cuentas únicas
    cuentas = df[['codigo', 'cuenta']].drop_duplicates()

    # Nivel 1: códigos de 1 dígito (4, 5)
    for _, row in cuentas[cuentas['codigo'].str.len() == 1].iterrows():
        codigo = row['codigo']
        jerarquia[codigo] = {
            'nombre': row['cuenta'],
            'subcuentas': {}
        }

    # Nivel 2: códigos de 2 dígitos
    for _, row in cuentas[cuentas['codigo'].str.len() == 2].iterrows():
        codigo = row['codigo']
        padre = codigo[0]
        if padre in jerarquia:
            jerarquia[padre]['subcuentas'][codigo] = {
                'nombre': row['cuenta'],
                'subcuentas': {}
            }

    return jerarquia


# =============================================================================
# PAGINA PRINCIPAL
# =============================================================================

def main():
    st.title("💰 Pérdidas y Ganancias")
    st.markdown("Análisis de resultados del sistema cooperativo ecuatoriano.")
    st.caption("Valores anualizados (suma móvil 12 meses)")

    # Cargar datos
    try:
        df_pyg, calidad = cargar_pyg()
    except FileNotFoundError as e:
        st.error(f"Error al cargar datos de PYG: {e}")
        st.info("Ejecuta: `python scripts/procesar_pyg.py`")
        return
    except Exception as e:
        st.error(f"Error al cargar datos de PYG: {e}")
        return

    # Verificar que existe valor_12m
    if 'valor_12m' not in df_pyg.columns:
        st.error("Los datos no tienen la columna 'valor_12m'. Ejecuta: `python scripts/procesar_pyg.py`")
        return

    # Filtrar solo registros con valor_12m válido
    df_pyg = df_pyg[df_pyg['valor_12m'].notna()]

    # Fechas disponibles
    fechas = obtener_fechas_disponibles(df_pyg)
    fecha_min = min(fechas)
    fecha_max = max(fechas)

    # Segmentos disponibles
    segmentos = ["Todos"] + obtener_segmentos_disponibles(df_pyg)

    # Sidebar - Filtros globales
    st.sidebar.markdown("### Filtros")

    segmento_global = st.sidebar.selectbox(
        "Segmento",
        options=segmentos,
        index=0,
        key="segmento_pyg"
    )

    # Filtrar por segmento si aplica
    if segmento_global != "Todos":
        df_pyg = df_pyg[df_pyg['segmento'] == segmento_global]

    # Excluir totales de segmento (VT_) de la lista de cooperativas
    df_pyg_coops = df_pyg[~df_pyg['cooperativa'].str.startswith('VT_')]

    # Lista de cooperativas (sin totales VT_)
    cooperativas = sorted(df_pyg_coops['cooperativa'].unique().tolist())

    # Cooperativas por defecto (top 4 por activos)
    cooperativas_ordenadas = obtener_orden_cooperativas_por_activos(segmento_global)
    cooperativas_default = cooperativas_ordenadas[:4] if len(cooperativas_ordenadas) >= 4 else cooperativas[:4]
    cooperativas_default = [c for c in cooperativas_default if c in cooperativas]

    # Construir jerarquía de cuentas
    jerarquia = construir_jerarquia_pyg(df_pyg)

    # ==========================================================================
    # SECCION 1: EVOLUCION COMPARATIVA
    # ==========================================================================

    st.markdown("---")
    st.markdown("### 1. Evolución Comparativa")
    st.caption("Compara la evolución temporal de múltiples cooperativas para una cuenta de P&G")

    # -------------------------------------------------------------------------
    # FILA 1: Selector de Cuenta (jerárquico)
    # -------------------------------------------------------------------------
    st.markdown("**Seleccionar Cuenta:**")

    col_n1, col_n2 = st.columns(2)

    with col_n1:
        opciones_nivel1 = {f"{k} - {v['nombre']}": k for k, v in jerarquia.items()}
        nivel1_label = st.selectbox(
            "Categoría",
            options=list(opciones_nivel1.keys()),
            index=1 if len(opciones_nivel1) > 1 else 0,  # Ingresos por defecto
            key="cuenta_nivel1_pyg"
        )
        codigo_nivel1 = opciones_nivel1[nivel1_label]

    # Nivel 2
    subcuentas_nivel2 = jerarquia[codigo_nivel1]['subcuentas']
    opciones_nivel2 = {"Todas (agregado)": codigo_nivel1}
    for k, v in subcuentas_nivel2.items():
        label = f"{k} - {v['nombre']}"
        opciones_nivel2[label] = k

    with col_n2:
        nivel2_label = st.selectbox(
            "Subcuenta",
            options=list(opciones_nivel2.keys()),
            index=0,
            key="cuenta_nivel2_pyg"
        )
        codigo_cuenta = opciones_nivel2[nivel2_label]

    # Nombre de la cuenta seleccionada
    if codigo_cuenta == codigo_nivel1:
        nombre_cuenta = jerarquia[codigo_nivel1]['nombre']
    else:
        nombre_cuenta = subcuentas_nivel2[codigo_cuenta]['nombre']

    # -------------------------------------------------------------------------
    # FILA 2: Selector de Cooperativas
    # -------------------------------------------------------------------------
    st.markdown("**Cooperativas a Comparar:**")
    cooperativas_seleccionadas = st.multiselect(
        "Selecciona hasta 10 cooperativas",
        options=cooperativas,
        default=cooperativas_default,
        max_selections=10,
        key="cooperativas_evol_pyg",
        label_visibility="collapsed"
    )

    # -------------------------------------------------------------------------
    # FILA 3: Grafico (izquierda) + Filtro de tiempo (derecha)
    # -------------------------------------------------------------------------
    col_chart, col_tiempo = st.columns([4, 1])

    with col_tiempo:
        st.markdown("**Período**")
        mes_inicio = st.selectbox(
            "Mes desde",
            options=list(range(1, 13)),
            format_func=lambda x: MESES[x],
            index=0,
            key="mes_inicio_pyg"
        )
        ano_inicio = st.selectbox(
            "Año desde",
            options=range(fecha_min.year, fecha_max.year + 1),
            index=0,
            key="ano_inicio_pyg"
        )

        mes_fin = st.selectbox(
            "Mes hasta",
            options=list(range(1, 13)),
            format_func=lambda x: MESES[x],
            index=fecha_max.month - 1,
            key="mes_fin_pyg"
        )
        ano_fin = st.selectbox(
            "Año hasta",
            options=range(fecha_min.year, fecha_max.year + 1),
            index=fecha_max.year - fecha_min.year,
            key="ano_fin_pyg"
        )

        # Modo de visualización
        modo = st.radio(
            "Modo",
            options=['Absoluto', 'Indexado', 'Participación'],
            index=0,
            key="modo_pyg"
        )

        # Incluir total del sistema
        incluir_sistema = st.checkbox(
            "Incluir Total Sistema",
            value=False,
            key="incluir_sistema_pyg"
        )

    with col_chart:
        fecha_inicio_sel = pd.Timestamp(year=ano_inicio, month=mes_inicio, day=1)
        last_day_fin = calendar.monthrange(ano_fin, mes_fin)[1]
        fecha_fin_sel = pd.Timestamp(year=ano_fin, month=mes_fin, day=last_day_fin)

        if cooperativas_seleccionadas:
            fig_evol = go.Figure()
            y_label = "Millones USD"

            for i, cooperativa in enumerate(cooperativas_seleccionadas):
                df_coop = df_pyg[
                    (df_pyg['cooperativa'] == cooperativa) &
                    (df_pyg['codigo'] == codigo_cuenta) &
                    (df_pyg['fecha'] >= fecha_inicio_sel) &
                    (df_pyg['fecha'] <= fecha_fin_sel)
                ].copy().sort_values('fecha')

                if not df_coop.empty:
                    df_coop['valor_millones'] = df_coop['valor_12m'] / 1_000_000

                    if modo == 'Indexado':
                        base = df_coop['valor_millones'].iloc[0]
                        y_data = (df_coop['valor_millones'] / base * 100) if base != 0 else df_coop['valor_millones'] * 0
                        y_label = "Índice (Base 100)"
                    elif modo == 'Participación':
                        # Calcular participación sobre total del sistema (excluir VT_)
                        df_total = df_pyg[
                            (df_pyg['codigo'] == codigo_cuenta) &
                            (df_pyg['fecha'] >= fecha_inicio_sel) &
                            (df_pyg['fecha'] <= fecha_fin_sel) &
                            (~df_pyg['cooperativa'].str.startswith('VT_'))
                        ].groupby('fecha')['valor_12m'].sum().reset_index()
                        df_coop = df_coop.merge(df_total, on='fecha', suffixes=('', '_total'))
                        y_data = (df_coop['valor_12m'] / df_coop['valor_12m_total'] * 100)
                        y_label = "Participación (%)"
                    else:  # Absoluto
                        y_data = df_coop['valor_millones']
                        y_label = "Millones USD (12M)"

                    color_coop = obtener_color_cooperativa(cooperativa)
                    fig_evol.add_trace(go.Scatter(
                        x=df_coop['fecha'],
                        y=y_data,
                        name=cooperativa[:25] + '...' if len(cooperativa) > 25 else cooperativa,
                        mode='lines',
                        line=dict(width=2, color=color_coop),
                        hovertemplate='<b>%{fullData.name}</b><br>Fecha: %{x|%b %Y}<br>Valor: %{y:,.1f}<extra></extra>'
                    ))

            # Agregar total del sistema si se solicita (excluir VT_)
            if incluir_sistema and modo == 'Absoluto':
                df_sistema = df_pyg[
                    (df_pyg['codigo'] == codigo_cuenta) &
                    (df_pyg['fecha'] >= fecha_inicio_sel) &
                    (df_pyg['fecha'] <= fecha_fin_sel) &
                    (~df_pyg['cooperativa'].str.startswith('VT_'))
                ].groupby('fecha')['valor_12m'].sum().reset_index()
                df_sistema['valor_millones'] = df_sistema['valor_12m'] / 1_000_000

                fig_evol.add_trace(go.Scatter(
                    x=df_sistema['fecha'],
                    y=df_sistema['valor_millones'],
                    name='TOTAL SISTEMA',
                    mode='lines',
                    line=dict(width=3, dash='dash', color='black'),
                    hovertemplate='<b>%{fullData.name}</b><br>Fecha: %{x|%b %Y}<br>Valor: %{y:,.1f}M<extra></extra>'
                ))

            fig_evol.update_layout(
                title=f"Evolución: {nombre_cuenta}",
                height=450,
                xaxis_title="Fecha",
                yaxis_title=y_label,
                hovermode="x unified",
                legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
                margin=dict(l=10, r=10, t=40, b=80)
            )

            st.plotly_chart(fig_evol, use_container_width=True)
        else:
            st.info("Selecciona al menos una cooperativa para visualizar.")

    st.markdown("---")

    # ==========================================================================
    # SECCION 2: RANKING POR COOPERATIVA
    # ==========================================================================

    st.markdown("### 2. Ranking de Cooperativas por Cuenta")
    st.caption("Comparación de valores de todas las cooperativas para una cuenta y mes específicos")

    # Filtros
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        # Selector de cuenta jerárquico
        opciones_nivel1_r = {f"{k} - {v['nombre']}": k for k, v in jerarquia.items()}
        nivel1_label_r = st.selectbox(
            "Categoría",
            options=list(opciones_nivel1_r.keys()),
            index=1 if len(opciones_nivel1_r) > 1 else 0,
            key="cuenta_nivel1_rank"
        )
        codigo_nivel1_r = opciones_nivel1_r[nivel1_label_r]

        subcuentas_nivel2_r = jerarquia[codigo_nivel1_r]['subcuentas']
        opciones_nivel2_r = {"Todas (agregado)": codigo_nivel1_r}
        for k, v in subcuentas_nivel2_r.items():
            label = f"{k} - {v['nombre']}"
            opciones_nivel2_r[label] = k

        nivel2_label_r = st.selectbox(
            "Subcuenta",
            options=list(opciones_nivel2_r.keys()),
            index=0,
            key="cuenta_nivel2_rank"
        )
        codigo_rank = opciones_nivel2_r[nivel2_label_r]

    with col_f2:
        mes_rank = st.selectbox(
            "Mes",
            options=list(MESES.keys()),
            format_func=lambda x: MESES[x],
            index=fecha_max.month - 1,
            key="mes_rank_pyg"
        )

    with col_f3:
        ano_rank = st.selectbox(
            "Año",
            options=range(fecha_min.year, fecha_max.year + 1),
            index=fecha_max.year - fecha_min.year,
            key="ano_rank_pyg"
        )

    # Top N selector
    top_n_rank = st.selectbox(
        "Cooperativas a mostrar",
        options=[10, 20, 30, 50],
        index=1,
        format_func=lambda x: f"Top {x}",
        key="top_n_rank_pyg"
    )

    # Construir fecha seleccionada
    last_day_rank = calendar.monthrange(ano_rank, mes_rank)[1]
    fecha_rank = pd.Timestamp(year=ano_rank, month=mes_rank, day=last_day_rank)

    # Obtener nombre de la cuenta para el ranking
    if codigo_rank == codigo_nivel1_r:
        nombre_cuenta_rank = jerarquia[codigo_nivel1_r]['nombre']
    else:
        nombre_cuenta_rank = subcuentas_nivel2_r[codigo_rank]['nombre']

    # Obtener datos de ranking (excluir totales VT_)
    df_rank = df_pyg[
        (df_pyg['fecha'] == fecha_rank) &
        (df_pyg['codigo'] == codigo_rank) &
        (~df_pyg['cooperativa'].str.startswith('VT_'))
    ].copy()

    if not df_rank.empty:
        df_rank['valor_millones'] = df_rank['valor_12m'] / 1_000_000
        df_rank = df_rank.nlargest(top_n_rank, 'valor_millones')
        df_rank = df_rank.sort_values('valor_millones', ascending=True)

        # Asignar colores consistentes por cooperativa
        colores_rank = [obtener_color_cooperativa(coop) for coop in df_rank['cooperativa']]

        # Crear gráfico de barras horizontales
        fig_rank = go.Figure(go.Bar(
            x=df_rank['valor_millones'],
            y=df_rank['cooperativa'].apply(lambda x: x[:30] + '...' if len(x) > 30 else x),
            orientation='h',
            marker=dict(
                color=colores_rank
            ),
            text=df_rank['valor_millones'].apply(lambda x: f"${x:,.0f}M"),
            textposition='outside',
            hovertemplate='<b>%{y}</b><br>Valor: $%{x:,.0f}M<extra></extra>'
        ))

        fig_rank.update_layout(
            title=f"{nombre_cuenta_rank} - {MESES[mes_rank]} {ano_rank}",
            height=max(400, len(df_rank) * 25),
            xaxis_title="Millones USD (12M)",
            yaxis_title="",
            showlegend=False,
            margin=dict(l=10, r=10, t=40, b=40)
        )

        st.plotly_chart(fig_rank, use_container_width=True)

        # Estadísticas del sistema
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            total_sistema = df_rank['valor_millones'].sum()
            st.metric("Total Sistema", f"${total_sistema:,.0f}M")
        with col_s2:
            participacion_top1 = (df_rank['valor_millones'].max() / total_sistema * 100) if total_sistema > 0 else 0
            st.metric("Participación #1", f"{participacion_top1:.1f}%")
        with col_s3:
            df_top5 = df_rank.nlargest(5, 'valor_millones')
            participacion_top5 = (df_top5['valor_millones'].sum() / total_sistema * 100) if total_sistema > 0 and len(df_rank) >= 5 else 0
            st.metric("Concentración Top 5", f"{participacion_top5:.1f}%")
    else:
        st.warning("No hay datos disponibles para el periodo seleccionado.")


if __name__ == "__main__":
    main()
