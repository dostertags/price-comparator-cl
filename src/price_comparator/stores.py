"""Las tiendas soportadas: única fuente de verdad de su nombre, orden y dominios."""

from __future__ import annotations

from urllib.parse import urlsplit

# El orden es el de las columnas del informe y el desempate del mejor precio.
STORES: tuple[str, ...] = ("Sodimac", "Falabella", "Hites")

# Dominios permitidos para las URL de las ofertas de cada tienda.
STORE_HOSTS: dict[str, tuple[str, ...]] = {
    "Sodimac": ("sodimac.cl",),
    "Falabella": ("falabella.com",),
    "Hites": ("hites.com",),
}


def host_matches(url: str, hosts: tuple[str, ...]) -> bool:
    """¿La URL es segura y pertenece a uno de `hosts`?

    Debe ser https, sin credenciales ni caracteres de control, y su host debe ser uno de
    `hosts` o un subdominio suyo (`sodimac.cl.evil.com` no cuenta).
    """
    if any(ord(c) <= 32 or ord(c) == 127 for c in url):
        return False
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    return any(host == h or host.endswith("." + h) for h in hosts)
