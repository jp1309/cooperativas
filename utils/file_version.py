"""Versionado liviano de archivos para invalidar cachés de datos."""

from pathlib import Path


def version_archivo(path: Path) -> tuple[int, int] | None:
    """Devuelve una huella que cambia cuando el archivo es reemplazado."""
    try:
        estado = path.stat()
    except FileNotFoundError:
        return None
    return estado.st_size, estado.st_mtime_ns
