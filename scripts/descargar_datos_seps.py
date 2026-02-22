# -*- coding: utf-8 -*-
"""
Descarga automática de datos de cooperativas desde el portal SEPS.

Hace scraping de https://estadisticas.seps.gob.ec/index.php/estadisticas-sfps/
para encontrar el enlace del año corriente y descarga el ZIP de Estados
Financieros Mensuales (EEFF).

Exit codes:
  0 - Descargó datos nuevos correctamente
  1 - Error durante el proceso
  2 - No hay datos nuevos (el ZIP ya está descargado)
"""

import sys
import json
import re
import requests
from pathlib import Path
from datetime import datetime

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 no está instalado. Ejecuta: pip install beautifulsoup4")
    sys.exit(1)

# Rutas
BASE_DIR = Path(__file__).parent.parent
BALANCES_DIR = BASE_DIR / "balances_cooperativas"
INDICADORES_DIR = BASE_DIR / "indicadores"
MASTER_DATA_DIR = BASE_DIR / "master_data"
METADATA_PATH = MASTER_DATA_DIR / "metadata.json"

# Portal SEPS
URL_SEPS = "https://estadisticas.seps.gob.ec/index.php/estadisticas-sfps/"
BASE_DOWNLOAD_URL = "https://estadisticas.seps.gob.ec/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def obtener_fecha_actual_datos():
    """Lee metadata.json para saber hasta qué fecha están los datos actuales."""
    if not METADATA_PATH.exists():
        return None
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return meta.get("fecha_max")  # ej: "2025-12-31"


def scrape_download_id(anio: int) -> str | None:
    """
    Scrapea la página de la SEPS y extrae el download_id para el año dado.

    Busca dentro del bloque "Estados Financieros Mensuales" el enlace
    cuyo texto sea el año indicado (ej: "2026").
    """
    print(f"  Accediendo a {URL_SEPS} ...")
    try:
        resp = requests.get(URL_SEPS, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR al acceder al portal SEPS: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Buscar el h5 "Estados Financieros Mensuales"
    seccion = None
    for h5 in soup.find_all("h5"):
        if "estados financieros mensuales" in h5.get_text(strip=True).lower():
            seccion = h5.find_next_sibling("div")
            break

    if seccion is None:
        # Fallback: buscar directamente cualquier enlace con el año en el texto
        print("  Advertencia: no se encontró la sección 'Estados Financieros Mensuales'.")
        print("  Intentando búsqueda general de enlaces...")
        seccion = soup

    # Buscar enlace con download_id cuyo texto sea el año
    anio_str = str(anio)
    for a in seccion.find_all("a", href=True):
        href = a["href"]
        texto = a.get_text(strip=True)
        if anio_str in texto and "download_id" in href:
            # Extraer el download_id
            match = re.search(r"download_id=(\d+)", href)
            if match:
                download_id = match.group(1)
                print(f"  Encontrado: año {anio_str} → download_id={download_id}")
                return download_id

    print(f"  No se encontró enlace de descarga para el año {anio_str}.")
    return None


def descargar_zip(download_id: str, destino: Path) -> bool:
    """Descarga el ZIP del SEPS dado el download_id y lo guarda en destino."""
    url = f"{BASE_DOWNLOAD_URL}?sdm_process_download=1&download_id={download_id}"
    print(f"  Descargando desde: {url}")
    print(f"  Destino: {destino}")

    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=300) as resp:
            resp.raise_for_status()

            # Verificar que es un ZIP
            content_type = resp.headers.get("Content-Type", "")
            if "html" in content_type.lower():
                print(f"  ERROR: La respuesta es HTML, no un ZIP. "
                      f"Puede que el enlace haya cambiado o el ID sea incorrecto.")
                return False

            total = int(resp.headers.get("Content-Length", 0))
            descargado = 0
            with open(destino, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1 MB chunks
                    f.write(chunk)
                    descargado += len(chunk)
                    if total:
                        pct = descargado / total * 100
                        print(f"  {descargado / 1024 / 1024:.1f} MB / "
                              f"{total / 1024 / 1024:.1f} MB ({pct:.0f}%)", end="\r")

        print(f"\n  Descarga completa: {destino.stat().st_size / 1024 / 1024:.1f} MB")
        return True

    except requests.RequestException as e:
        print(f"  ERROR al descargar: {e}")
        if destino.exists():
            destino.unlink()  # Eliminar archivo parcial
        return False


def hay_datos_nuevos(anio: int, mes_actual: int) -> bool:
    """
    Verifica si los datos actuales ya incluyen el mes anterior al mes corriente.
    Si los datos llegan hasta el mes pasado, no hay nada nuevo que descargar.
    """
    fecha_max_str = obtener_fecha_actual_datos()
    if fecha_max_str is None:
        return True  # Sin metadata, asumir que hay datos nuevos

    fecha_max = datetime.fromisoformat(fecha_max_str.split("T")[0])
    mes_esperado = mes_actual - 1 if mes_actual > 1 else 12
    anio_esperado = anio if mes_actual > 1 else anio - 1

    print(f"  Datos actuales hasta: {fecha_max.strftime('%B %Y')}")
    print(f"  Mes esperado: {mes_esperado:02d}/{anio_esperado}")

    if fecha_max.year == anio_esperado and fecha_max.month >= mes_esperado:
        return False  # Ya tenemos los datos del mes pasado
    return True


def nombre_zip_balance(anio: int) -> str:
    """Genera el nombre estándar del ZIP de balance para un año dado."""
    # La SEPS usa patrones inconsistentes; usamos el más reciente como referencia
    if anio <= 2021:
        return f"{anio}-EEFF-MEN.zip"
    else:
        return f"{anio}_EEFF-Men.zip"


def nombre_zip_indicadores(anio: int) -> str:
    """Genera el nombre estándar del ZIP de indicadores para un año dado."""
    return f"{anio}-EEFF-MEN.zip"


def main():
    ahora = datetime.now()
    anio = ahora.year
    mes = ahora.month

    print("=" * 60)
    print("DESCARGA AUTOMÁTICA DE DATOS SEPS")
    print(f"Fecha de ejecución: {ahora.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Crear directorios si no existen
    BALANCES_DIR.mkdir(exist_ok=True)
    INDICADORES_DIR.mkdir(exist_ok=True)

    # Verificar si ya tenemos los datos actualizados
    print("\n[1/3] Verificando si hay datos nuevos...")
    if not hay_datos_nuevos(anio, mes):
        print("  Los datos ya están actualizados. No hay nada que descargar.")
        print("\nSaliendo con código 2 (sin datos nuevos).")
        sys.exit(2)
    print("  Hay datos nuevos disponibles. Procediendo con la descarga.")

    # Scraping para obtener el download_id del año corriente
    print(f"\n[2/3] Buscando enlace de descarga para el año {anio}...")
    download_id = scrape_download_id(anio)

    if download_id is None:
        # Si no encontramos el año corriente, puede que aún no esté publicado
        # Intentar con el año anterior si estamos en enero
        if mes == 1:
            print(f"  Intentando con el año {anio - 1} (estamos en enero)...")
            download_id = scrape_download_id(anio - 1)

    if download_id is None:
        print("\nERROR: No se pudo encontrar el enlace de descarga en el portal SEPS.")
        print("Puede que la SEPS haya cambiado la estructura de su web.")
        sys.exit(1)

    # Descarga del ZIP de balances
    print(f"\n[3/3] Descargando ZIP de Estados Financieros Mensuales {anio}...")
    nombre_zip = nombre_zip_balance(anio)
    destino_zip = BALANCES_DIR / nombre_zip

    # Si el ZIP ya existe, hacer backup antes de sobreescribir
    if destino_zip.exists():
        backup = destino_zip.with_suffix(".zip.bak")
        destino_zip.rename(backup)
        print(f"  Backup del ZIP anterior guardado en: {backup.name}")

    ok = descargar_zip(download_id, destino_zip)

    if not ok:
        # Restaurar backup si falló
        backup = destino_zip.with_suffix(".zip.bak")
        if backup.exists():
            backup.rename(destino_zip)
            print("  Backup restaurado.")
        sys.exit(1)

    # Limpiar backup si todo salió bien
    backup = destino_zip.with_suffix(".zip.bak")
    if backup.exists():
        backup.unlink()

    print("\n" + "=" * 60)
    print(f"DESCARGA COMPLETADA: {nombre_zip}")
    print("Proceder con el pipeline ETL.")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
