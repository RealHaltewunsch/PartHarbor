from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Any

import wx

from .core import (
    CatalogSyncPlan,
    ImportBatchResult,
    ImportOptions,
    default_library_base,
    fetch_jlcpcb_catalog,
    format_price,
    format_price_tiers,
    import_components,
    normalize_lcsc_ids,
    plan_catalog_sync,
    search_jlcpcb,
    search_local_symbols,
)


class PartHarborFrame(wx.Frame):
    def __init__(self, parent: wx.Window | None = None) -> None:
        super().__init__(parent, title="PartHarbor", size=(1220, 760))
        self.remote_results: list[dict[str, Any]] = []
        self._busy = False
        self._build_ui()
        self.Centre()

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label="PartHarbor – LCSC/JLCPCB → KiCad")
        title.SetFont(title.GetFont().Bold().Scale(1.35))
        outer.Add(title, 0, wx.ALL, 12)

        notebook = wx.Notebook(panel)
        notebook.AddPage(self._search_page(notebook), "JLCPCB Search")
        notebook.AddPage(self._direct_page(notebook), "Import C-Numbers")
        notebook.AddPage(self._catalog_page(notebook), "Catalog Sync")
        notebook.AddPage(self._local_page(notebook), "Local Library")
        outer.Add(notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        settings = wx.StaticBoxSizer(wx.VERTICAL, panel, "Import Options")
        path_row = wx.BoxSizer(wx.HORIZONTAL)
        path_row.Add(wx.StaticText(panel, label="Library base:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.output = wx.TextCtrl(panel, value=str(default_library_base()))
        path_row.Add(self.output, 1, wx.RIGHT, 6)
        choose = wx.Button(panel, label="Browse…")
        choose.Bind(wx.EVT_BUTTON, self._choose_output)
        path_row.Add(choose)
        settings.Add(path_row, 0, wx.EXPAND | wx.ALL, 8)

        option_row = wx.BoxSizer(wx.HORIZONTAL)
        self.symbol = wx.CheckBox(panel, label="Symbol")
        self.footprint = wx.CheckBox(panel, label="Footprint")
        self.model_3d = wx.CheckBox(panel, label="3D Model")
        self.overwrite = wx.CheckBox(panel, label="Overwrite existing parts")
        self.cache = wx.CheckBox(panel, label="Cache downloads")
        for checkbox in (self.symbol, self.footprint, self.model_3d, self.cache):
            checkbox.SetValue(True)
        for checkbox in (self.symbol, self.footprint, self.model_3d, self.overwrite, self.cache):
            option_row.Add(checkbox, 0, wx.RIGHT, 18)
        settings.Add(option_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        outer.Add(settings, 0, wx.EXPAND | wx.ALL, 12)

        self.status = wx.StaticText(panel, label="Ready")
        outer.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.progress = wx.Gauge(panel, range=100)
        outer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        panel.SetSizer(outer)

    def _search_page(self, parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.query = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.query.SetHint("e.g. 100n 0402 16v or NMOS 30V")
        self.query.Bind(wx.EVT_TEXT_ENTER, self._search_remote)
        row.Add(self.query, 1, wx.RIGHT, 8)
        self.part_type = wx.Choice(panel, choices=["Basic / Preferred", "All", "Extended"])
        self.part_type.SetSelection(0)
        row.Add(self.part_type, 0, wx.RIGHT, 8)
        search = wx.Button(panel, label="Search")
        search.Bind(wx.EVT_BUTTON, self._search_remote)
        row.Add(search)
        layout.Add(row, 0, wx.EXPAND | wx.ALL, 8)

        self.results = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for idx, (label, width) in enumerate(
            [
                ("LCSC", 85),
                ("Type", 80),
                ("Stock", 95),
                ("Package", 90),
                ("MPN", 170),
                ("Price", 120),
                ("Main characteristics", 470),
            ]
        ):
            self.results.InsertColumn(idx, label, width=width)
        self.results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._import_selected)
        layout.Add(self.results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.details = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SIMPLE,
            size=(-1, 105),
        )
        self.details.SetHint("Select a component to see its complete characteristics and price tiers.")
        self.results.Bind(wx.EVT_LIST_ITEM_SELECTED, self._show_selected_details)
        layout.Add(self.details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        import_button = wx.Button(panel, label="Import Selected Part")
        import_button.Bind(wx.EVT_BUTTON, self._import_selected)
        buttons.Add(import_button, 0, wx.RIGHT, 8)
        details = wx.Button(panel, label="Open LCSC Page")
        details.Bind(wx.EVT_BUTTON, self._open_selected)
        buttons.Add(details)
        layout.Add(buttons, 0, wx.ALL, 8)
        panel.SetSizer(layout)
        return panel

    def _direct_page(self, parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(wx.StaticText(panel, label="One or more C-numbers (separated by spaces, commas, or new lines):"), 0, wx.ALL, 8)
        self.ids = wx.TextCtrl(panel, style=wx.TE_MULTILINE, value="C2040")
        layout.Add(self.ids, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        button = wx.Button(panel, label="Import")
        button.Bind(wx.EVT_BUTTON, self._import_direct)
        layout.Add(button, 0, wx.ALL, 8)
        panel.SetSizer(layout)
        return panel

    def _local_page(self, parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.local_query = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.local_query.SetHint("C2040, part name, description …")
        self.local_query.Bind(wx.EVT_TEXT_ENTER, self._search_local)
        row.Add(self.local_query, 1, wx.RIGHT, 8)
        button = wx.Button(panel, label="Search Local Library")
        button.Bind(wx.EVT_BUTTON, self._search_local)
        row.Add(button)
        layout.Add(row, 0, wx.EXPAND | wx.ALL, 8)
        self.local_results = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for idx, (label, width) in enumerate(
            [("LCSC", 100), ("Symbol", 230), ("Footprint", 250), ("Description", 430)]
        ):
            self.local_results.InsertColumn(idx, label, width=width)
        layout.Add(self.local_results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        panel.SetSizer(layout)
        return panel

    def _catalog_page(self, parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        explanation = wx.StaticText(
            panel,
            label=(
                "Download the current JLCPCB catalogue, compare its C-numbers with "
                "the local symbol library, and import the difference. If ‘Overwrite "
                "existing parts’ is enabled below, existing catalogue parts are updated too."
            ),
        )
        explanation.Wrap(900)
        layout.Add(explanation, 0, wx.ALL, 12)

        choices = wx.BoxSizer(wx.HORIZONTAL)
        self.sync_basic = wx.CheckBox(panel, label="Include all Basic parts")
        self.sync_preferred = wx.CheckBox(panel, label="Include all Preferred parts")
        self.sync_basic.SetValue(True)
        choices.Add(self.sync_basic, 0, wx.RIGHT, 24)
        choices.Add(self.sync_preferred)
        layout.Add(choices, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        warning = wx.StaticText(
            panel,
            label=(
                "A full sync can import hundreds or more than a thousand parts and may "
                "take a long time when 3D models are enabled. You will see exact counts "
                "and must confirm before downloads start."
            ),
        )
        warning.Wrap(900)
        layout.Add(warning, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        button = wx.Button(panel, label="Check Online Catalogue and Sync…")
        button.Bind(wx.EVT_BUTTON, self._prepare_catalog_sync)
        layout.Add(button, 0, wx.LEFT | wx.BOTTOM, 12)
        panel.SetSizer(layout)
        return panel

    def _options(self) -> ImportOptions:
        return ImportOptions(
            symbol=self.symbol.GetValue(),
            footprint=self.footprint.GetValue(),
            model_3d=self.model_3d.GetValue(),
            overwrite=self.overwrite.GetValue(),
            use_cache=self.cache.GetValue(),
            output=Path(self.output.GetValue()).expanduser(),
        )

    def _choose_output(self, _event: wx.CommandEvent) -> None:
        with wx.DirDialog(self, "Select library folder") as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                folder = Path(dialog.GetPath())
                self.output.SetValue(str(folder / folder.name))

    def _run(self, label: str, job: Any, done: Any) -> None:
        if self._busy:
            self._show_error("Another PartHarbor operation is already running.")
            return
        self._busy = True
        self.status.SetLabel(label)

        def worker() -> None:
            try:
                value = job()
            except Exception as exc:  # GUI boundary: show actionable error
                wx.CallAfter(self._job_failed, str(exc))
            else:
                wx.CallAfter(self._job_done, done, value)

        threading.Thread(target=worker, daemon=True).start()

    def _job_done(self, done: Any, value: Any) -> None:
        self._busy = False
        done(value)

    def _job_failed(self, message: str) -> None:
        self._busy = False
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.status.SetLabel("Error")
        wx.MessageBox(message, "PartHarbor", wx.OK | wx.ICON_ERROR, self)

    def _search_remote(self, _event: wx.CommandEvent) -> None:
        kind = ["preferred", None, "expand"][self.part_type.GetSelection()]
        self._run("Searching JLCPCB …", lambda: search_jlcpcb(self.query.GetValue(), kind), self._show_remote)

    def _show_remote(self, payload: dict[str, Any]) -> None:
        self.remote_results = payload.get("results", [])
        self.results.DeleteAllItems()
        for part in self.remote_results:
            row = self.results.InsertItem(self.results.GetItemCount(), str(part.get("lcsc", "")))
            values = [
                part.get("type", ""),
                f"{part.get('stock', 0):,}",
                part.get("package", ""),
                part.get("model", ""),
                format_price(part),
                part.get("description", "") or part.get("name", ""),
            ]
            for column, value in enumerate(values, 1):
                self.results.SetItem(row, column, str(value))
        catalog_total = payload.get("catalog_total", payload.get("total", 0))
        self.status.SetLabel(
            f"Showing {len(self.remote_results)} matching results "
            f"from {payload.get('candidate_count', len(self.remote_results))} loaded "
            f"catalog candidates ({catalog_total} reported by JLCPCB)"
        )

    def _show_selected_details(self, event: wx.ListEvent) -> None:
        index = event.GetIndex()
        if not 0 <= index < len(self.remote_results):
            return
        part = self.remote_results[index]
        self.details.SetValue(
            f"{part.get('lcsc', '')} — {part.get('name', '')}\n"
            f"Main characteristics: {part.get('description', '')}\n"
            f"Category: {part.get('category', '')}    Package: {part.get('package', '')}    "
            f"Stock: {part.get('stock', 0):,}\n"
            f"Price tiers: {format_price_tiers(part)}"
        )

    def _selected_remote(self) -> dict[str, Any] | None:
        index = self.results.GetFirstSelected()
        return self.remote_results[index] if 0 <= index < len(self.remote_results) else None

    def _import_selected(self, _event: wx.CommandEvent) -> None:
        part = self._selected_remote()
        if not part:
            self._show_error("Select a search result first.")
            return
        self._start_import([part["lcsc"]])

    def _import_direct(self, _event: wx.CommandEvent) -> None:
        self._start_import(normalize_lcsc_ids(self.ids.GetValue()))

    def _start_import(
        self,
        ids: list[str],
        metadata_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        options = self._options()
        self.progress.SetRange(max(len(ids), 1))
        self.progress.SetValue(0)
        completed = 0

        def progress(part_id: str, _success: bool) -> None:
            nonlocal completed
            completed += 1
            wx.CallAfter(self.progress.SetValue, completed)
            wx.CallAfter(
                self.status.SetLabel,
                f"Processed {completed} of {len(ids)} catalogue parts — {part_id}",
            )

        self._run(
            f"Importing {len(ids)} part(s) …",
            lambda: import_components(
                ids,
                options,
                progress=progress,
                metadata_by_id=metadata_by_id,
            ),
            self._import_done,
        )

    def _prepare_catalog_sync(self, _event: wx.CommandEvent) -> None:
        include_basic = self.sync_basic.GetValue()
        include_preferred = self.sync_preferred.GetValue()
        options = self._options()
        self.progress.SetRange(100)
        self.progress.SetValue(0)

        def catalog_progress(loaded: int, total: int) -> None:
            wx.CallAfter(self.progress.SetRange, max(total, 1))
            wx.CallAfter(self.progress.SetValue, min(loaded, max(total, 1)))
            wx.CallAfter(
                self.status.SetLabel,
                f"Loading online catalogue: {loaded} of {total}",
            )

        def job() -> CatalogSyncPlan:
            parts = fetch_jlcpcb_catalog(
                include_basic,
                include_preferred,
                progress=catalog_progress,
            )
            return plan_catalog_sync(
                parts,
                Path(f"{options.output}.kicad_sym"),
                options.overwrite,
            )

        self._run("Loading the current JLCPCB catalogue …", job, self._confirm_catalog_sync)

    def _confirm_catalog_sync(self, plan: CatalogSyncPlan) -> None:
        existing_selected = len(plan.parts) - len(plan.missing_ids)
        message = (
            f"Online selection: {len(plan.parts):,} parts\n"
            f"  Basic: {plan.basic_count:,}\n"
            f"  Preferred: {plan.preferred_count:,}\n"
            f"Already present locally: {existing_selected:,}\n"
            f"Missing locally: {len(plan.missing_ids):,}\n\n"
            f"Parts to import now: {len(plan.import_ids):,}\n"
        )
        if self.overwrite.GetValue():
            message += "Overwrite is enabled: existing selected parts will be re-imported.\n"
        else:
            message += "Overwrite is disabled: only missing parts will be imported.\n"
        message += "\nContinue?"
        if not plan.import_ids:
            wx.MessageBox(
                message.replace("\nContinue?", "\nThe local library is up to date."),
                "PartHarbor Catalogue Sync",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.status.SetLabel("Local catalogue is up to date")
            return
        if wx.MessageBox(
            message,
            "PartHarbor Catalogue Sync",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        ) != wx.YES:
            self.status.SetLabel("Catalogue sync cancelled")
            return
        metadata = {str(part["lcsc"]): part for part in plan.parts}
        self._start_import(plan.import_ids, metadata)

    def _import_done(self, result: ImportBatchResult) -> None:
        ok = [part_id for part_id, success in result.outcomes.items() if success]
        failed = [
            part_id for part_id, success in result.outcomes.items() if not success
        ]
        message = f"Imported: {len(ok):,}\n{self._summarize_ids(ok)}"
        if failed:
            message += f"\n\nFailed/skipped: {len(failed):,}\n{self._summarize_ids(failed)}"
        if result.paused_for_network:
            message += (
                f"\n\n{result.pause_reason}\n"
                f"Not attempted yet: {len(result.remaining_ids):,}.\n"
                "Wait a while, then run Catalog Sync again. Parts already written "
                "will be detected locally and excluded automatically."
            )
        elif failed:
            message += (
                "\nThe part may already exist or no requested asset was available. "
                "Enable ‘Overwrite existing parts’ to update existing symbols."
            )
        message += "\n\nReload the symbol libraries in KiCad if needed. The C-number is stored as a search keyword."
        self.status.SetLabel(message.splitlines()[0])
        warning = failed or result.paused_for_network
        wx.MessageBox(
            message,
            "PartHarbor",
            wx.OK | (wx.ICON_WARNING if warning else wx.ICON_INFORMATION),
            self,
        )

    @staticmethod
    def _summarize_ids(ids: list[str], limit: int = 20) -> str:
        if not ids:
            return "—"
        visible = ", ".join(ids[:limit])
        remaining = len(ids) - limit
        return f"{visible} … and {remaining:,} more" if remaining > 0 else visible

    def _open_selected(self, _event: wx.CommandEvent) -> None:
        part = self._selected_remote()
        if part and part.get("url"):
            webbrowser.open(part["url"])

    def _search_local(self, _event: wx.CommandEvent) -> None:
        library = Path(f"{self.output.GetValue()}.kicad_sym")
        matches = search_local_symbols(self.local_query.GetValue(), library)
        self.local_results.DeleteAllItems()
        for part in matches[:500]:
            row = self.local_results.InsertItem(self.local_results.GetItemCount(), part["lcsc"])
            for column, key in enumerate(("name", "footprint", "description"), 1):
                self.local_results.SetItem(row, column, part[key])
        self.status.SetLabel(f"{len(matches)} local results")


_window: PartHarborFrame | None = None


def show_dialog(parent: wx.Window | None = None) -> PartHarborFrame:
    global _window
    if _window is None or not _window:
        _window = PartHarborFrame(parent)
    _window.Show()
    _window.Raise()
    return _window


def main() -> int:
    app = wx.App(False)
    show_dialog()
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
