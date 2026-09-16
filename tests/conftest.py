"""Shared fixtures and document builders.

The PDF builder writes raw PDF syntax rather than pulling in a rendering
library: the parser only ever sees `pypdf`'s text extraction, so a minimal
uncompressed page exercises exactly the path that matters, and the test suite
keeps the dependency list in ``CLAUDE.md`` unchanged.
"""

from __future__ import annotations

import asyncio
import inspect
import io
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"


def build_pdf(lines: list[str], *, pages: int = 1) -> bytes:
    """A single-font, uncompressed PDF containing ``lines``."""
    per_page = max(1, -(-len(lines) // pages))
    chunks = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    objects: list[bytes] = []
    page_ids = [4 + index * 2 for index in range(len(chunks))]

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(chunks)} >>".encode("latin-1")
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for chunk in chunks:
        content = ["BT", "/F1 11 Tf", "14 TL", "56 760 Td"]
        for line in chunk:
            content.append(f"({_escape(line)}) Tj")
            content.append("T*")
        content.append("ET")
        stream = "\n".join(content).encode("latin-1", "replace")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
            + str(len(objects) + 2).encode("ascii")
            + b" 0 R >>"
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode("ascii"))
        out.write(body)
        out.write(b"\nendobj\n")

    xref_at = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return out.getvalue()


def _escape(value: str) -> str:
    safe = value.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_docx(paragraphs: list[str], *, table: list[list[str]] | None = None) -> bytes:
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for col_index, cell in enumerate(row):
                grid.cell(row_index, col_index).text = cell
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


SAMPLE_CV_LINES = [
    "Dilek Aydin",
    "Backend Engineer - Istanbul",
    "dilek@example.com",
    "",
    "Experience",
    "Acme Payments - Backend Engineer, 2018-2024",
    "Built payment reconciliation services in Go.",
    "Migrated the reporting pipeline to PostgreSQL and k8s.",
    "Led a team of 4 engineers across two time zones.",
    "Reduced settlement errors by 18% across the ledger.",
    "",
    "Education",
    "MSc Computer Science, Bogazici University, 2016",
    "",
    "Skills",
    "Go, Python, PostgreSQL, Kubernetes, Kafka, Terraform-free infra",
]

SAMPLE_POSTING = """Senior Backend Engineer
Northwind Ledger - Remote (EU)

About us
Northwind Ledger builds settlement infrastructure for marketplaces.

Requirements
- 5+ years of backend engineering experience
- Strong production experience with Go
- Experience running services on Kubernetes
- Working knowledge of PostgreSQL and schema migrations
- Experience leading a small team

Nice to have
- Payments or fintech domain experience
- Familiarity with Kafka

Benefits
- Private health insurance and a learning budget
- 30 days of paid leave

Apply now
Accept all cookies
"""


@pytest.fixture
def sample_cv_text() -> str:
    return "\n".join(SAMPLE_CV_LINES)


@pytest.fixture
def sample_posting() -> str:
    return SAMPLE_POSTING


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run ``async def`` tests on a fresh loop.

    The engine is async because the host protocol is; adding pytest-asyncio or
    anyio just to await three pipelines would widen the dependency list in
    ``CLAUDE.md`` for no coverage.
    """
    function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(function):
        return None
    kwargs: dict[str, Any] = {
        name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(function(**kwargs))
    return True
