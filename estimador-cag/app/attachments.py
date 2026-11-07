"""Extracción local de texto de adjuntos (camino B): pypdf para PDF y python-docx para Word.

Los documentos se convierten a texto en el servicio y se concatenan al mensaje del
usuario, así que funciona igual con cualquier proveedor. Los límites protegen la
memoria y el coste de tokens: lo que supera un límite se rechaza, nunca se trunca
en silencio.
"""

import io
import re
import zipfile
from pathlib import PurePosixPath

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.schemas import Attachment

MAX_ATTACHMENTS = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS_PER_FILE = 60_000
MAX_TOTAL_TEXT_CHARS = 120_000
MAX_FILENAME_CHARS = 100

_UNSAFE_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f<>]")


class AttachmentError(ValueError):
    """Un adjunto no se puede usar. `status_code` es el código HTTP que le corresponde."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def _safe_filename(filename: str) -> str:
    """Solo el nombre base, sin saltos de línea ni `<>`: acaba dentro del prompt."""
    name = PurePosixPath(filename.replace("\\", "/")).name
    return _UNSAFE_FILENAME_CHARS.sub("", name).strip()[:MAX_FILENAME_CHARS] or "adjunto"


def _pdf_text(filename: str, content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise AttachmentError(f"{filename}: el PDF está protegido con contraseña.")
        parts: list[str] = []
        length = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            parts.append(page_text)
            length += len(page_text)
            if length > MAX_TEXT_CHARS_PER_FILE:  # no seguir leyendo un PDF enorme
                break
    except (PyPdfError, ValueError, OSError) as error:
        raise AttachmentError(f"{filename}: no se pudo leer el PDF ({error}).") from error
    return "\n".join(parts)


def _docx_text(filename: str, content: bytes) -> str:
    try:
        document = Document(io.BytesIO(content))
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError) as error:
        raise AttachmentError(f"{filename}: no se pudo leer el documento Word.") from error
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def extract_text(filename: str, content: bytes) -> str:
    """Devuelve el texto de un PDF o un .docx, o lanza `AttachmentError`."""
    extension = PurePosixPath(filename.lower()).suffix
    if extension not in (".pdf", ".docx"):
        raise AttachmentError(
            f"{filename}: formato no soportado (solo PDF y Word .docx).", status_code=415
        )
    if len(content) > MAX_FILE_BYTES:
        raise AttachmentError(
            f"{filename}: archivo demasiado grande (máximo {MAX_FILE_BYTES // (1024 * 1024)} MB).",
            status_code=413,
        )

    text = (_pdf_text if extension == ".pdf" else _docx_text)(filename, content).strip()
    if not text:
        raise AttachmentError(
            f"{filename}: no contiene texto extraíble (¿es un PDF escaneado o solo imágenes?)."
        )
    if len(text) > MAX_TEXT_CHARS_PER_FILE:
        raise AttachmentError(
            f"{filename}: demasiado texto (máximo {MAX_TEXT_CHARS_PER_FILE} caracteres por archivo).",
            status_code=413,
        )
    return text


def extract_attachments(files: list[tuple[str, bytes]]) -> list[Attachment]:
    """Extrae el texto de cada `(nombre, contenido)` respetando los límites globales."""
    if len(files) > MAX_ATTACHMENTS:
        raise AttachmentError(f"Se admiten como máximo {MAX_ATTACHMENTS} adjuntos.", status_code=413)

    result = [
        Attachment(filename=_safe_filename(filename), text=extract_text(filename, content))
        for filename, content in files
    ]
    if sum(len(attachment.text) for attachment in result) > MAX_TOTAL_TEXT_CHARS:
        raise AttachmentError(
            f"Demasiado texto entre todos los adjuntos (máximo {MAX_TOTAL_TEXT_CHARS} caracteres).",
            status_code=413,
        )
    return result
