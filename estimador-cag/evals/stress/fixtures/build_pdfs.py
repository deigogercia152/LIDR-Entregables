"""Genera los PDFs sintéticos del escenario de adjuntos (determinísticos, no se comitean).

El tamaño se mide en caracteres de texto extraíble: N KB ≈ N * 1000 caracteres, que
es lo que cuenta contra `MAX_TEXT_CHARS_PER_FILE` (60.000). El texto lleva tres
"canarios" (principio, mitad y final) con un nombre de ERP distinto cada uno: sirven
para medir cuánto del adjunto sobrevive en la respuesta.

    uv run python -m evals.stress.fixtures.build_pdfs [--out DIR] [--sizes 5,20,50,100]
"""

import argparse
import random
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

DEFAULT_SIZES_KB = (5, 20, 50, 100)
DEFAULT_OUT = Path(__file__).parent
CANARIES = {"start": "Zafiro", "middle": "Obsidiana", "end": "Turquesa"}

_SUBJECTS = ["El modulo de reservas", "El portal de clientes", "La API publica", "El panel de administracion",
             "El servicio de notificaciones", "El sistema de facturacion", "El motor de informes"]  # fmt: skip
_VERBS = ["debe registrar", "debe validar", "debe exponer", "debe sincronizar", "debe auditar", "debe cifrar"]
_OBJECTS = ["las reservas de cada sala", "los datos del cliente", "los eventos de acceso",
            "las facturas mensuales", "los permisos por rol", "el historial de cambios"]  # fmt: skip
_CLOSERS = ["con trazabilidad completa.", "en menos de dos segundos.", "segun la politica del cliente.",
            "con copia de seguridad diaria.", "sin intervencion manual."]  # fmt: skip


def synthetic_text(size_kb: int, seed: int = 7) -> str:
    """Texto ASCII determinista de ~size_kb*1000 caracteres con tres canarios."""
    target = size_kb * 1000
    rng = random.Random(seed)

    def canary(position: str) -> str:
        return (f"REQUISITO CRITICO: el sistema debe integrarse con el ERP {CANARIES[position]} "
                "para sincronizar facturas y clientes.")  # fmt: skip

    sentences: list[str] = []
    length = 0
    while length < target:
        sentence = f"{rng.choice(_SUBJECTS)} {rng.choice(_VERBS)} {rng.choice(_OBJECTS)} {rng.choice(_CLOSERS)}"
        sentences.append(sentence)
        length += len(sentence) + 1
    sentences.insert(0, canary("start"))
    sentences.insert(len(sentences) // 2, canary("middle"))
    sentences.append(canary("end"))
    return " ".join(sentences)[: target + 400]


def build_pdf(size_kb: int) -> bytes:
    pdf = FPDF()
    pdf.set_creation_date(datetime(2026, 1, 1, tzinfo=timezone.utc))  # bytes reproducibles
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    text = synthetic_text(size_kb)
    paragraph = 12  # frases por párrafo, para que el PDF tenga estructura de páginas reales
    sentences = text.split(". ")
    for start in range(0, len(sentences), paragraph):
        pdf.multi_cell(0, 6, ". ".join(sentences[start : start + paragraph]))
        pdf.ln(2)
    return bytes(pdf.output())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES_KB))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for size in (int(s) for s in args.sizes.split(",") if s.strip() and int(s) > 0):
        path = args.out / f"attach_{size}kb.pdf"
        path.write_bytes(build_pdf(size))
        print(f"{path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
