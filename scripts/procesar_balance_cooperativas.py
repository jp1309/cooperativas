# -*- coding: utf-8 -*-
"""
Pipeline ETL para procesar balances de cooperativas ecuatorianas.
Lee archivos ZIP con datos CSV/TXT y genera balance.parquet consolidado.
"""

import pandas as pd
import zipfile
import json
from pathlib import Path
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

# Rutas
BASE_DIR = Path(__file__).parent.parent
BALANCES_DIR = BASE_DIR / "balances_cooperativas"
OUTPUT_DIR = BASE_DIR / "master_data"


def calcular_nivel(codigo: str) -> int:
    """Calcula el nivel jerárquico según la longitud del código contable."""
    if pd.isna(codigo):
        return 0
    codigo_str = str(codigo).strip()
    longitud = len(codigo_str)
    if longitud == 1:
        return 1
    elif longitud == 2:
        return 2
    elif longitud <= 4:
        return 3
    elif longitud <= 6:
        return 4
    else:
        return 5


def normalizar_nombre(nombre: str) -> str:
    """Normaliza el nombre de la cooperativa."""
    if pd.isna(nombre):
        return ""
    # Convertir a título y limpiar espacios
    nombre = str(nombre).strip()
    # Remover prefijos comunes para nombres más cortos
    prefijos = [
        "COOPERATIVA DE AHORRO Y CREDITO ",
        "COOPERATIVA DE AHORRO Y CRÉDITO ",
        "COOP. DE AHORRO Y CREDITO ",
    ]
    for prefijo in prefijos:
        if nombre.upper().startswith(prefijo):
            nombre = nombre[len(prefijo):]
            break
    nombre = nombre.strip()

    # Unificar LIMITADA a LTDA
    nombre = nombre.replace(' LIMITADA', ' LTDA')

    # Eliminar punto al final de LTDA.
    if nombre.endswith('LTDA.'):
        nombre = nombre[:-1]

    # Eliminar espacios múltiples
    nombre = ' '.join(nombre.split())

    return nombre


def leer_archivo_desde_zip(zip_path: Path) -> pd.DataFrame:
    """Lee el archivo CSV/TXT desde un ZIP."""
    print(f"  Procesando: {zip_path.name}")

    # Determinar año del archivo para decidir el formato
    año_archivo = int(zip_path.name.split('-')[0].split('_')[0])

    with zipfile.ZipFile(zip_path, 'r') as zf:
        # Obtener nombre del archivo interno
        archivos = zf.namelist()
        archivo_datos = [f for f in archivos if f.endswith(('.csv', '.txt'))][0]

        # Leer contenido
        with zf.open(archivo_datos) as f:
            if año_archivo >= 2022:
                # Archivos 2022+ usan tabs y nombres de columnas diferentes
                df = pd.read_csv(
                    f,
                    sep='\t',
                    encoding='utf-8-sig',
                    dtype=str
                )
                # Normalizar nombres de columnas
                df.columns = df.columns.str.strip().str.replace('\ufeff', '')
                df = df.rename(columns={
                    'FECHA DE CORTE': 'FECHA_DE_CORTE',
                    'RAZON SOCIAL': 'RAZON_SOCIAL',
                    'DESCRIPCION CUENTA': 'DESCRIPCION_CUENTA',
                    'SALDO (USD)': 'SALDO_USD',
                })
            else:
                # Archivos 2018-2021 usan punto y coma
                df = pd.read_csv(
                    f,
                    sep=';',
                    encoding='utf-8-sig',
                    dtype={
                        'CUENTA': str,
                        'RUC': str,
                    }
                )

    # Limpiar nombres de columnas (remover BOM si existe)
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')

    return df


def procesar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Procesa y normaliza el DataFrame."""

    # Renombrar columnas
    df = df.rename(columns={
        'FECHA_DE_CORTE': 'fecha',
        'SEGMENTO': 'segmento',
        'RUC': 'ruc',
        'RAZON_SOCIAL': 'cooperativa',
        'CUENTA': 'codigo',
        'DESCRIPCION_CUENTA': 'cuenta',
        'SALDO_USD': 'valor',
    })

    # Parsear fecha
    df['fecha'] = pd.to_datetime(df['fecha'], format='mixed')

    # Normalizar nombres
    df['cooperativa'] = df['cooperativa'].apply(normalizar_nombre)

    # Calcular nivel jerárquico
    df['nivel'] = df['codigo'].apply(calcular_nivel)

    # Limpiar valores - manejar formato con coma decimal
    if df['valor'].dtype == object:
        # Reemplazar coma por punto para convertir a número
        df['valor'] = df['valor'].str.replace(',', '.', regex=False)
    df['valor'] = pd.to_numeric(df['valor'], errors='coerce').fillna(0)

    # Asegurar que código sea string
    df['codigo'] = df['codigo'].astype(str).str.strip()

    return df


def generar_balance_parquet():
    """Genera el archivo balance.parquet consolidado."""

    print("=" * 60)
    print("PIPELINE ETL - BALANCES DE COOPERATIVAS")
    print("=" * 60)

    # Crear directorio de salida si no existe
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Buscar todos los ZIPs
    zips = sorted(BALANCES_DIR.glob("*.zip"))
    print(f"\nArchivos ZIP encontrados: {len(zips)}")

    # Procesar cada ZIP
    dataframes = []
    for zip_path in zips:
        try:
            df = leer_archivo_desde_zip(zip_path)
            df = procesar_dataframe(df)
            dataframes.append(df)
            print(f"    -> {len(df):,} registros")
        except Exception as e:
            print(f"    ERROR: {e}")

    # Concatenar todos los DataFrames
    print("\nConsolidando datos...")
    df_final = pd.concat(dataframes, ignore_index=True)

    # Unificar segmento: cada cooperativa toma el segmento de su último dato
    print("Unificando segmentos...")
    ultimo_segmento = (
        df_final.sort_values('fecha')
        .drop_duplicates(subset=['cooperativa'], keep='last')[['cooperativa', 'segmento']]
        .set_index('cooperativa')['segmento']
    )
    coops_multi = df_final.groupby('cooperativa')['segmento'].nunique()
    coops_cambiaron = coops_multi[coops_multi > 1].index.tolist()
    if coops_cambiaron:
        print(f"  Cooperativas con cambio de segmento: {len(coops_cambiaron)} (unificando al último)")
    df_final['segmento'] = df_final['cooperativa'].map(ultimo_segmento)

    # Optimizar tipos de datos
    print("Optimizando tipos de datos...")
    df_final['segmento'] = df_final['segmento'].astype('category')
    df_final['cooperativa'] = df_final['cooperativa'].astype('category')
    df_final['nivel'] = df_final['nivel'].astype('int8')

    # Ordenar
    df_final = df_final.sort_values(['fecha', 'segmento', 'cooperativa', 'codigo'])
    df_final = df_final.reset_index(drop=True)

    # Estadísticas
    print("\n" + "=" * 60)
    print("ESTADÍSTICAS")
    print("=" * 60)
    print(f"Total registros: {len(df_final):,}")
    print(f"Cooperativas únicas: {df_final['cooperativa'].nunique()}")
    print(f"Segmentos: {df_final['segmento'].unique().tolist()}")
    print(f"Fechas: {df_final['fecha'].min().strftime('%Y-%m')} a {df_final['fecha'].max().strftime('%Y-%m')}")
    print(f"Meses únicos: {df_final['fecha'].nunique()}")
    print(f"Cuentas únicas: {df_final['codigo'].nunique()}")

    # Guardar parquet
    output_path = OUTPUT_DIR / "balance.parquet"
    df_final.to_parquet(output_path, engine='pyarrow', compression='snappy')

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nArchivo generado: {output_path}")
    print(f"Tamaño: {size_mb:.1f} MB")

    # Generar metadata
    metadata = {
        'fecha_procesamiento': datetime.now().isoformat(),
        'registros_totales': len(df_final),
        'cooperativas': df_final['cooperativa'].nunique(),
        'segmentos': df_final['segmento'].unique().tolist(),
        'fecha_min': df_final['fecha'].min().isoformat(),
        'fecha_max': df_final['fecha'].max().isoformat(),
        'meses': df_final['fecha'].nunique(),
        'cuentas': df_final['codigo'].nunique(),
        'archivos_procesados': [z.name for z in zips],
    }

    metadata_path = OUTPUT_DIR / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Metadata guardada: {metadata_path}")
    print("\n" + "=" * 60)
    print("PROCESO COMPLETADO")
    print("=" * 60)

    return df_final


if __name__ == "__main__":
    generar_balance_parquet()
