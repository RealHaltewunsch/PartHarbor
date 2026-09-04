"""KiCad Action Plugin entry point for PartHarbor."""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew


PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


class PartHarborAction(pcbnew.ActionPlugin):
    def defaults(self) -> None:
        self.name = "PartHarbor"
        self.category = "Library"
        self.description = (
            "Synchronize all JLCPCB Basic/Preferred parts and import components into KiCad"
        )
        self.show_toolbar_button = True
        self.icon_file_name = str(PLUGIN_ROOT / "icon.png")

    def Run(self) -> None:  # KiCad API name
        from partharbor.gui import show_dialog

        show_dialog()


PartHarborAction().register()
