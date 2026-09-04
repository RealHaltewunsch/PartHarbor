from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from easyeda2kicad.__main__ import _process_component
from easyeda2kicad.easyeda.easyeda_api import EasyedaApi


LCSC_ID_RE = re.compile(r"\bC\d+\b", re.IGNORECASE)
CAPACITANCE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)(p|n|u|µ)$", re.IGNORECASE)
RESISTANCE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)(k)$", re.IGNORECASE)
VOLTAGE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)v$", re.IGNORECASE)
QUERY_SYNONYMS = {
    "nmos": "N-channel MOSFET",
    "n-mos": "N-channel MOSFET",
    "nmosfet": "N-channel MOSFET",
    "pmos": "P-channel MOSFET",
    "p-mos": "P-channel MOSFET",
    "pmosfet": "P-channel MOSFET",
}


def default_library_base() -> Path:
    """Return the existing easyeda2kicad library base used by KiCad."""
    return Path.home() / "Documents" / "KiCad" / "easyeda2kicad" / "easyeda2kicad"


def normalize_lcsc_ids(raw: str | Iterable[str]) -> list[str]:
    """Extract, normalize and de-duplicate LCSC C-numbers while preserving order."""
    text = raw if isinstance(raw, str) else " ".join(raw)
    seen: set[str] = set()
    result: list[str] = []
    for match in LCSC_ID_RE.finditer(text):
        part_id = match.group(0).upper()
        if part_id not in seen:
            seen.add(part_id)
            result.append(part_id)
    return result


def normalize_component_query(query: str) -> str:
    """Expand common electronics shorthand into terms accepted by JLCPCB search."""
    normalized: list[str] = []
    for token in query.split():
        cap = CAPACITANCE_RE.match(token)
        resistance = RESISTANCE_RE.match(token)
        voltage = VOLTAGE_RE.match(token)
        synonym = QUERY_SYNONYMS.get(token.casefold())
        if synonym:
            normalized.append(synonym)
        elif cap:
            normalized.append(f"{cap.group(1)}{cap.group(2)}F")
        elif resistance:
            normalized.append(f"{resistance.group(1)}{resistance.group(2)}Ω")
        elif voltage:
            normalized.append(f"{voltage.group(1)}V")
        else:
            normalized.append(token)
    return " ".join(normalized)


def format_price(part: dict[str, Any]) -> str:
    """Format the first available price tier without inventing a currency."""
    price = part.get("price")
    quantity = part.get("min_qty", 1)
    tiers = part.get("price_breaks") or []
    if price is None and tiers:
        price = tiers[0].get("price")
        quantity = tiers[0].get("qty", quantity)
    if price is None:
        return "Unavailable" if part.get("stock", 0) else "—"
    try:
        value = f"{float(price):.8f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        value = str(price)
    return f"{value} @ {quantity}+"


def format_price_tiers(part: dict[str, Any]) -> str:
    tiers = part.get("price_breaks") or []
    if not tiers:
        return format_price(part)
    return " | ".join(
        format_price(
            {
                "price": tier.get("price"),
                "min_qty": tier.get("qty", 1),
                "stock": part.get("stock", 0),
            }
        )
        for tier in tiers
    )


@dataclass(frozen=True)
class ImportOptions:
    symbol: bool = True
    footprint: bool = True
    model_3d: bool = True
    overwrite: bool = False
    use_cache: bool = True
    output: Path = default_library_base()

    def validate(self) -> None:
        if not any((self.symbol, self.footprint, self.model_3d)):
            raise ValueError("Select at least a symbol, footprint, or 3D model.")


def converter_arguments(options: ImportOptions) -> dict[str, Any]:
    options.validate()
    output = options.output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    return {
        "symbol": options.symbol,
        "footprint": options.footprint,
        "3d": options.model_3d,
        "svg": False,
        "full": options.symbol and options.footprint and options.model_3d,
        "overwrite": options.overwrite,
        "project_relative": False,
        "custom_field": [],
        "custom_fields": {},
        "use_cache": options.use_cache,
        "output": str(output),
        # Preserve the path used by the original tool in generated footprints.
        "use_default_folder": output == default_library_base(),
    }


def import_components(
    ids: Iterable[str],
    options: ImportOptions,
    progress: Callable[[str, bool], None] | None = None,
) -> dict[str, bool]:
    normalized = normalize_lcsc_ids(ids)
    if not normalized:
        raise ValueError("No valid LCSC number found (example: C2040).")
    arguments = converter_arguments(options)
    api = EasyedaApi(use_cache=options.use_cache)
    result: dict[str, bool] = {}
    for part_id in normalized:
        metadata = api.search_jlcpcb_components(part_id, page_size=20)
        exact = next(
            (part for part in metadata.get("results", []) if part.get("lcsc") == part_id),
            None,
        )
        arguments["custom_fields"] = _metadata_fields(exact) if exact else {}
        ok = _process_component(part_id, arguments, api)
        result[part_id] = ok
        if progress:
            progress(part_id, ok)
    return result


def search_jlcpcb(
    query: str, part_type: str | None = "base", page_size: int = 50
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("Enter a search term.")
    normalized = normalize_component_query(query.strip())
    return EasyedaApi(use_cache=False).search_jlcpcb_components(
        normalized, page_size=page_size, part_type=part_type
    )


def _metadata_fields(part: dict[str, Any]) -> dict[str, str]:
    attributes = " ".join(
        f"{item.get('name', '')} {item.get('value', '')}"
        for item in part.get("attributes", [])
    )
    searchable = " ".join(
        str(part.get(key, ""))
        for key in ("lcsc", "name", "model", "brand", "package", "category", "type", "description")
    )
    return {
        "Manufacturer": str(part.get("brand", "")),
        "Manufacturer Part": str(part.get("model", "")),
        "JLCPCB Type": str(part.get("type", "")),
        "JLCPCB Package": str(part.get("package", "")),
        "JLCPCB Search": f"{searchable} {attributes}".strip(),
    }


def _property(block: str, name: str) -> str:
    match = re.search(
        rf'^\s*\(property\s+"{re.escape(name)}"\s+"((?:[^"\\]|\\.)*)"',
        block,
        re.MULTILINE,
    )
    return match.group(1).replace(r'\"', '"') if match else ""


def index_local_symbols(symbol_library: Path) -> list[dict[str, str]]:
    """Build a light-weight searchable index from a KiCad symbol library."""
    if not symbol_library.is_file():
        return []
    text = symbol_library.read_text(encoding="utf-8", errors="replace")
    starts = list(re.finditer(r'^\t\(symbol\s+"([^"]+)"', text, re.MULTILINE))
    parts: list[dict[str, str]] = []
    for number, start in enumerate(starts):
        end = starts[number + 1].start() if number + 1 < len(starts) else len(text)
        block = text[start.start() : end]
        all_properties = " ".join(
            match.group(1).replace(r'\"', '"')
            for match in re.finditer(
                r'^\s*\(property\s+"[^"]+"\s+"((?:[^"\\]|\\.)*)"',
                block,
                re.MULTILINE,
            )
        )
        parts.append(
            {
                "name": start.group(1),
                "lcsc": _property(block, "LCSC Part"),
                "description": _property(block, "Description"),
                "footprint": _property(block, "Footprint"),
                "keywords": _property(block, "ki_keywords"),
                "search": all_properties,
            }
        )
    return parts


def search_local_symbols(query: str, symbol_library: Path) -> list[dict[str, str]]:
    tokens = [token.casefold() for token in query.split() if token]
    if not tokens:
        return []
    matches: list[tuple[int, dict[str, str]]] = []
    for part in index_local_symbols(symbol_library):
        haystack = " ".join(part.values()).casefold()
        if all(token in haystack for token in tokens):
            exact = 100 if part["lcsc"].casefold() == query.strip().casefold() else 0
            prefix = sum(5 for token in tokens if part["name"].casefold().startswith(token))
            matches.append((exact + prefix, part))
    return [part for _, part in sorted(matches, key=lambda item: (-item[0], item[1]["name"]))]
