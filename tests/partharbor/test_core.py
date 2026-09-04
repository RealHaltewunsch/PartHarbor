from pathlib import Path

import pytest

import partharbor.core as core
from easyeda2kicad.easyeda.easyeda_api import RateLimitExceededError
from partharbor.core import (
    ImportOptions,
    converter_arguments,
    filter_component_results,
    format_price,
    format_price_tiers,
    normalize_component_query,
    normalize_lcsc_ids,
    plan_catalog_sync,
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


def test_local_symbol_index_accepts_multiline_kicad_properties(
    tmp_path: Path,
) -> None:
    library = tmp_path / "parts.kicad_sym"
    library.write_text(
        '(kicad_symbol_lib\n  (symbol "CL05B104"\n'
        '    (property\n      "LCSC Part"\n      "C1525"\n'
        '      (at 0 0 0)\n    )\n  )\n)',
        encoding="utf-8",
    )
    assert core.index_local_symbols(library)[0]["lcsc"] == "C1525"


def test_batch_pauses_after_repeated_network_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeApi:
        def __init__(self, **kwargs: object) -> None:
            self.last_error_status: int | None = None

    def fail(_part_id: str, _arguments: object, api: FakeApi) -> bool:
        api.last_error_status = 429
        return False

    monkeypatch.setattr(core, "EasyedaApi", FakeApi)
    monkeypatch.setattr(core, "_process_component", fail)
    result = core.import_components(
        ["C1", "C2", "C3", "C4", "C5"],
        ImportOptions(symbol=True, footprint=False, model_3d=False, output=tmp_path / "lib"),
        metadata_by_id={f"C{number}": {} for number in range(1, 6)},
    )
    assert list(result.outcomes) == ["C1", "C2", "C3"]
    assert result.remaining_ids == ["C4", "C5"]
    assert result.paused_for_network


def test_batch_reports_exhausted_rate_limit_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeApi:
        def __init__(self, **kwargs: object) -> None:
            self.last_error_status: int | None = None

    def rate_limited(*args: object, **kwargs: object) -> bool:
        raise RateLimitExceededError(429, 60)

    monkeypatch.setattr(core, "EasyedaApi", FakeApi)
    monkeypatch.setattr(core, "_process_component", rate_limited)
    result = core.import_components(
        ["C1", "C2"],
        ImportOptions(symbol=True, footprint=False, model_3d=False, output=tmp_path / "lib"),
        metadata_by_id={"C1": {}, "C2": {}},
    )
    assert result.outcomes == {"C1": False}
    assert result.remaining_ids == ["C2"]
    assert result.paused_for_network
    assert "HTTP 429" in result.pause_reason


def test_batch_applies_per_component_asset_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeApi:
        def __init__(self, **kwargs: object) -> None:
            self.last_error_status: int | None = None

    selected: list[tuple[bool, bool, bool]] = []

    def capture(_part_id: str, arguments: dict[str, object], _api: FakeApi) -> bool:
        selected.append(
            (
                bool(arguments["symbol"]),
                bool(arguments["footprint"]),
                bool(arguments["3d"]),
            )
        )
        return True

    monkeypatch.setattr(core, "EasyedaApi", FakeApi)
    monkeypatch.setattr(core, "_process_component", capture)
    result = core.import_components(
        ["C1"],
        ImportOptions(output=tmp_path / "lib"),
        metadata_by_id={"C1": {}},
        asset_needs_by_id={"C1": core.AssetNeeds(model_3d=True)},
    )
    assert result.outcomes == {"C1": True}
    assert selected == [(False, False, True)]


def test_catalog_sync_plan_imports_difference_or_overwrites(tmp_path: Path) -> None:
    library = tmp_path / "parts.kicad_sym"
    library.write_text(
        '(kicad_symbol_lib\n\t(symbol "Existing"\n'
        '\t\t(property "LCSC Part" "C1")\n\t)\n)',
        encoding="utf-8",
    )
    parts = [
        {"lcsc": "C1", "type": "Basic"},
        {"lcsc": "C2", "type": "Preferred"},
    ]
    difference = plan_catalog_sync(
        parts,
        library,
        ImportOptions(
            symbol=True,
            footprint=False,
            model_3d=False,
            overwrite=False,
            output=tmp_path / "parts",
        ),
    )
    overwrite = plan_catalog_sync(
        parts,
        library,
        ImportOptions(
            symbol=True,
            footprint=False,
            model_3d=False,
            overwrite=True,
            output=tmp_path / "parts",
        ),
    )
    assert difference.missing_ids == ["C2"]
    assert difference.import_ids == ["C2"]
    assert overwrite.import_ids == ["C1", "C2"]
    assert difference.basic_count == 1
    assert difference.preferred_count == 1


def test_catalog_sync_plans_only_missing_3d_model(tmp_path: Path) -> None:
    base = tmp_path / "parts"
    library = Path(f"{base}.kicad_sym")
    library.write_text(
        '(kicad_symbol_lib\n  (symbol "Part"\n'
        '    (property "Footprint" "parts:FP1")\n'
        '    (property "LCSC Part" "C1")\n  )\n)',
        encoding="utf-8",
    )
    footprint_dir = Path(f"{base}.pretty")
    footprint_dir.mkdir()
    (footprint_dir / "FP1.kicad_mod").write_text(
        '(footprint "FP1"\n  (model "${EASYEDA2KICAD}/parts.3dshapes/M1.wrl")\n)',
        encoding="utf-8",
    )
    options = ImportOptions(output=base)
    plan = plan_catalog_sync([{"lcsc": "C1", "type": "Basic"}], library, options)
    assert plan.import_ids == ["C1"]
    assert plan.asset_needs_by_id["C1"] == core.AssetNeeds(model_3d=True)
    assert plan.missing_symbol_count == 0
    assert plan.missing_footprint_count == 0
    assert plan.missing_model_3d_count == 1

    model_dir = Path(f"{base}.3dshapes")
    model_dir.mkdir()
    (model_dir / "M1.wrl").write_text("model", encoding="utf-8")
    complete = plan_catalog_sync(
        [{"lcsc": "C1", "type": "Basic"}], library, options
    )
    assert complete.import_ids == []
