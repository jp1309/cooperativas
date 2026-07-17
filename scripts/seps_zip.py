# -*- coding: utf-8 -*-
"""Validaciones compartidas para los ZIP mensuales publicados por la SEPS."""

from __future__ import annotations

import calendar
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


MESES = {
    "ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12,
}

SEGMENTOS_ESPERADOS = {
    "SEGMENTO 1",
    "SEGMENTO 2",
    "SEGMENTO 3",
    "SEGMENTO 1 MUTUALISTA",
}


@dataclass(frozen=True)
class ResultadoInspeccionZip:
    fecha_corte: datetime
    segmentos: frozenset[str]
    archivos_xlsm: tuple[str, ...]


def _detectar_segmento(nombre: str) -> str | None:
    nombre_lower = nombre.lower()
    if "mutualista" in nombre_lower:
        return "SEGMENTO 1 MUTUALISTA"
    if "segmento 1" in nombre_lower or "segmento_1" in nombre_lower:
        return "SEGMENTO 1"
    if "segmento 2" in nombre_lower or "segmento_2" in nombre_lower:
        return "SEGMENTO 2"
    if "segmento 3" in nombre_lower or "segmento_3" in nombre_lower:
        return "SEGMENTO 3"
    return None


def _extraer_fecha_nombre(nombre: str) -> datetime | None:
    patron_meses = "|".join(sorted(MESES, key=len, reverse=True))
    match = re.search(
        rf"_({patron_meses})_(\d{{4}})\.xlsm$",
        Path(nombre).name.lower(),
    )
    if not match:
        return None
    mes = MESES[match.group(1)]
    anio = int(match.group(2))
    return datetime(anio, mes, calendar.monthrange(anio, mes)[1])


def inspeccionar_zip_seps(zip_path: Path) -> ResultadoInspeccionZip:
    """Exige los cuatro segmentos y una sola fecha de corte reconocible."""
    zip_path = Path(zip_path)
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"El archivo descargado no es un ZIP valido: {zip_path}")

    fechas: dict[str, datetime] = {}
    segmentos: set[str] = set()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for nombre in zf.namelist():
            nombre_lower = nombre.lower()
            if not nombre_lower.endswith(".xlsm"):
                continue
            if "conafips" in nombre_lower or "financoop" in nombre_lower:
                continue
            segmento = _detectar_segmento(nombre)
            fecha = _extraer_fecha_nombre(nombre)
            if segmento is None or fecha is None:
                continue
            segmentos.add(segmento)
            fechas[nombre] = fecha

    faltantes = SEGMENTOS_ESPERADOS - segmentos
    if faltantes:
        raise ValueError(
            "El ZIP no contiene todos los segmentos esperados: "
            + ", ".join(sorted(faltantes))
        )

    fechas_unicas = set(fechas.values())
    if len(fechas_unicas) != 1:
        detalle = ", ".join(
            f"{Path(nombre).name}={fecha.date()}"
            for nombre, fecha in sorted(fechas.items())
        )
        raise ValueError(f"El ZIP mezcla fechas de corte: {detalle}")

    return ResultadoInspeccionZip(
        fecha_corte=fechas_unicas.pop(),
        segmentos=frozenset(segmentos),
        archivos_xlsm=tuple(sorted(fechas)),
    )


def seleccionar_zips_procesamiento(
    archivos_zip: Iterable[Path],
    incremental: bool,
) -> list[Path]:
    """En modo incremental procesa solo los ZIP del año más reciente."""
    archivos = sorted(Path(path) for path in archivos_zip)
    if not incremental or not archivos:
        return archivos

    archivos_con_anio = []
    for path in archivos:
        match = re.search(r"(\d{4})", path.name)
        if match:
            archivos_con_anio.append((int(match.group(1)), path))
    if not archivos_con_anio:
        return archivos

    anio_reciente = max(anio for anio, _ in archivos_con_anio)
    return [path for anio, path in archivos_con_anio if anio == anio_reciente]
