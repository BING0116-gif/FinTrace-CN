"""Canonical A-share symbol parsing.

Internal code uses ``600519.SH``/``000333.SZ``/``920xxx.BJ``.  Provider-specific
spellings (for example Yahoo's ``.SS``) must be translated at an adapter edge,
never stored in a snapshot or passed between domain services.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import UnsupportedSymbolError


_WITH_SUFFIX = re.compile(r"^(?P<code>\d{6})\.(?P<suffix>SH|SZ|BJ|SS)$", re.IGNORECASE)
_BARE_CODE = re.compile(r"^\d{6}$")


@dataclass(frozen=True)
class CanonicalSymbol:
    """A validated mainland China listed-equity identifier."""

    code: str
    exchange: str

    @property
    def value(self) -> str:
        return f"{self.code}.{self.exchange}"

    def __str__(self) -> str:
        return self.value


def _infer_exchange(code: str) -> str:
    if code.startswith(("60", "68")):
        return "SH"
    if code.startswith(("00", "30")):
        return "SZ"
    if code.startswith("920"):
        return "BJ"
    raise UnsupportedSymbolError(
        f"Cannot infer an A-share exchange for '{code}'. Use a canonical code such as "
        "600519.SH, 000333.SZ, or 920xxx.BJ."
    )


def normalize_cn_symbol(value: str) -> CanonicalSymbol:
    """Normalize a supported A-share code to its canonical internal form.

    ``.SS`` is accepted only as an import compatibility alias and becomes ``.SH``.
    Historic Beijing Exchange aliases (83/87/88 prefixes) intentionally fail: a
    future alias table must map them to their official ``920xxx.BJ`` successors
    instead of guessing.
    """
    cleaned = (value or "").strip().upper().replace(" ", "")
    if _BARE_CODE.fullmatch(cleaned):
        return CanonicalSymbol(code=cleaned, exchange=_infer_exchange(cleaned))

    match = _WITH_SUFFIX.fullmatch(cleaned)
    if not match:
        raise UnsupportedSymbolError(f"Unsupported A-share symbol: '{value}'.")

    code = match.group("code")
    suffix = match.group("suffix").upper()
    exchange = "SH" if suffix == "SS" else suffix
    inferred = _infer_exchange(code)
    if exchange != inferred:
        raise UnsupportedSymbolError(
            f"'{value}' has an invalid exchange suffix; expected {code}.{inferred}."
        )
    return CanonicalSymbol(code=code, exchange=exchange)
