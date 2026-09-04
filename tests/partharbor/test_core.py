from pathlib import Path

import pytest

from partharbor.core import (
    ImportOptions,
    converter_arguments,
    filter_component_results,
    format_price,
    format_price_tiers,
    normalize_component_query,
    normalize_lcsc_ids,
    search_local_symbols,
)


def test_normalize_lcsc_ids() -> None:
    assert normalize_lcsc_ids("c2040, C25744\nfoo C2040") == ["C2040", "C25744"]


def test_normalize_component_query() -> None:
    assert normalize_component_query("100n 0402 16v") == "100nF 0402 16V"
    assert normalize_component_query("10k 0603") == "10kΩ 0603"
    assert normalize_component_query("NMOS 30V") == "N-channel MOSFET 30V"
    assert normalize_component_query("pmos 20v") == "P-channel MOSFET 20V"


def test_price_formatting() -> None:
    part = {
        "price": 0.0173,
        "min_qty": 1,
        "stock": 264739,
        "price_breaks": [
            {"qty": 1, "price": 0.0173},
            {"qty": 500, "price": 0.0136},
        ],
    }
    assert format_price(part) == "0.0173 @ 1+"
    assert format_price_tiers(part) == "0.0173 @ 1+ | 0.0136 @ 500+"
    assert format_price({"stock": 10}) == "Unavailable"


def test_strict_package_and_mosfet_filtering() -> None:
    parts = [
        {"lcsc": "C1", "type": "Basic", "stock": 10, "package": "0402", "description": "1kΩ resistor"},
        {"lcsc": "C2", "type": "Basic", "stock": 50, "package": "1206", "description": "1kΩ resistor"},
        {"lcsc": "C3", "type": "Preferred", "stock": 100, "package": "SOT-23", "description": "30V N-channel MOSFET"},
        {"lcsc": "C4", "type": "Basic", "stock": 100, "package": "SOT-23", "description": "30V P-channel MOSFET"},
    ]
    assert [part["lcsc"] for part in filter_component_results("1k 0402", parts)] == ["C1"]
    assert [part["lcsc"] for part in filter_component_results("NMOS 30V", parts)] == ["C3"]


def test_options_require_one_asset(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        converter_arguments(ImportOptions(False, False, False, output=tmp_path / "lib"))


def test_local_symbol_search(tmp_path: Path) -> None:
    library = tmp_path / "parts.kicad_sym"
    library.write_text(
        '(kicad_symbol_lib\n\t(symbol "CL10B104"\n'
        '\t\t(property "Description" "100nF 16V MLCC")\n'
        '\t\t(property "Footprint" "parts:C0402")\n'
        '\t\t(property "LCSC Part" "C1591")\n'
        '\t\t(property "ki_keywords" "C1591 capacitor 100n")\n\t)\n)',
        encoding="utf-8",
    )
    assert search_local_symbols("100n C1591", library)[0]["name"] == "CL10B104"
