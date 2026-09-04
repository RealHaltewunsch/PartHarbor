from pathlib import Path

import pytest

from partharbor.core import (
    ImportOptions,
    converter_arguments,
    normalize_component_query,
    normalize_lcsc_ids,
    search_local_symbols,
)


def test_normalize_lcsc_ids() -> None:
    assert normalize_lcsc_ids("c2040, C25744\nfoo C2040") == ["C2040", "C25744"]


def test_normalize_component_query() -> None:
    assert normalize_component_query("100n 0402 16v") == "100nF 0402 16V"
    assert normalize_component_query("10k 0603") == "10kΩ 0603"


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
