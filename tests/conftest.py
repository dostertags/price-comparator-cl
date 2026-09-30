"""Fixtures compartidas. Los tests unitarios no pueden salir a la red."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fx():
    """Devuelve el contenido de un fixture HTML por nombre."""

    def _read(name: str) -> str:
        return (FIXTURES / "html" / name).read_text(encoding="utf-8")

    return _read


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    """Falla cualquier intento de conexión real, salvo en tests marcados `live`."""
    if request.node.get_closest_marker("live"):
        return

    def _guard(*_args, **_kwargs):
        raise RuntimeError("Test intentó usar la red; usa un fetcher falso.")

    monkeypatch.setattr(socket.socket, "connect", _guard)
