"""Narada Gateway package.

This package is the boundary between conventional email (SMTP/IMAP) and the
Narada protocol. The current Openmail-derived server still speaks IMAP/SMTP
directly; this gateway is the planned extraction point.

Initially empty: the IMAP/SMTP client code currently lives in
``node/src/modules/openmail/{imap,smtp}.py`` and is reused from the Narada
node. Once the Narada node has its own delivery pipeline, the gateway will
import these modules to bridge Narada <-> conventional email.
"""

from __future__ import annotations

__all__: list[str] = []
