from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Any

import wx

from .core import (
    ImportOptions,
    default_library_base,
    import_components,
    normalize_lcsc_ids,
    search_jlcpcb,
    search_local_symbols,
)


class PartHarborFrame(wx.Frame):
    def __init__(self, parent: wx.Window | None = None) -> None:
        super().__init__(parent, title="PartHarbor", size=(980, 700))
        self.remote_results: list[dict[str, Any]] = []
        self._build_ui()
        self.Centre()

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label="PartHarbor – LCSC/JLCPCB → KiCad")
        title.SetFont(title.GetFont().Bold().Scale(1.35))
        outer.Add(title, 0, wx.ALL, 12)

        notebook = wx.Notebook(panel)
        notebook.AddPage(self._search_page(notebook), "JLCPCB-Suche")
        notebook.AddPage(self._direct_page(notebook), "C-Nummern importieren")
        notebook.AddPage(self._local_page(notebook), "Lokale Bibliothek")
        outer.Add(notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        settings = wx.StaticBoxSizer(wx.VERTICAL, panel, "Importoptionen")
        path_row = wx.BoxSizer(wx.HORIZONTAL)
        path_row.Add(wx.StaticText(panel, label="Bibliotheksbasis:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.output = wx.TextCtrl(panel, value=str(default_library_base()))
        path_row.Add(self.output, 1, wx.RIGHT, 6)
        choose = wx.Button(panel, label="Auswählen…")
        choose.Bind(wx.EVT_BUTTON, self._choose_output)
        path_row.Add(choose)
        settings.Add(path_row, 0, wx.EXPAND | wx.ALL, 8)

        option_row = wx.BoxSizer(wx.HORIZONTAL)
        self.symbol = wx.CheckBox(panel, label="Symbol")
        self.footprint = wx.CheckBox(panel, label="Footprint")
        self.model_3d = wx.CheckBox(panel, label="3D-Modell")
        self.overwrite = wx.CheckBox(panel, label="Vorhandene Teile überschreiben")
        self.cache = wx.CheckBox(panel, label="Downloads cachen")
        for checkbox in (self.symbol, self.footprint, self.model_3d, self.cache):
            checkbox.SetValue(True)
        for checkbox in (self.symbol, self.footprint, self.model_3d, self.overwrite, self.cache):
            option_row.Add(checkbox, 0, wx.RIGHT, 18)
        settings.Add(option_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        outer.Add(settings, 0, wx.EXPAND | wx.ALL, 12)

        self.status = wx.StaticText(panel, label="Bereit")
        outer.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        panel.SetSizer(outer)

    def _search_page(self, parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.query = wx.TextCtrl(panel, value="100n 0402 16v", style=wx.TE_PROCESS_ENTER)
        self.query.Bind(wx.EVT_TEXT_ENTER, self._search_remote)
        row.Add(self.query, 1, wx.RIGHT, 8)
        self.part_type = wx.Choice(panel, choices=["Basic / Preferred", "Alle", "Extended"])
        self.part_type.SetSelection(0)
        row.Add(self.part_type, 0, wx.RIGHT, 8)
        search = wx.Button(panel, label="Suchen")
        search.Bind(wx.EVT_BUTTON, self._search_remote)
        row.Add(search)
        layout.Add(row, 0, wx.EXPAND | wx.ALL, 8)

        self.results = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for idx, (label, width) in enumerate(
            [("LCSC", 90), ("Typ", 90), ("Bestand", 90), ("Gehäuse", 110), ("Herstellerteil", 185), ("Beschreibung", 330)]
        ):
            self.results.InsertColumn(idx, label, width=width)
        self.results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._import_selected)
        layout.Add(self.results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        import_button = wx.Button(panel, label="Ausgewähltes Teil importieren")
        import_button.Bind(wx.EVT_BUTTON, self._import_selected)
        buttons.Add(import_button, 0, wx.RIGHT, 8)
        details = wx.Button(panel, label="LCSC-Seite öffnen")
        details.Bind(wx.EVT_BUTTON, self._open_selected)
        buttons.Add(details)
        layout.Add(buttons, 0, wx.ALL, 8)
        panel.SetSizer(layout)
        return panel

    def _direct_page(self, parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(wx.StaticText(panel, label="Eine oder mehrere C-Nummern (Leerzeichen, Komma oder Zeilenumbruch):"), 0, wx.ALL, 8)
        self.ids = wx.TextCtrl(panel, style=wx.TE_MULTILINE, value="C2040")
        layout.Add(self.ids, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        button = wx.Button(panel, label="Importieren")
        button.Bind(wx.EVT_BUTTON, self._import_direct)
        layout.Add(button, 0, wx.ALL, 8)
        panel.SetSizer(layout)
        return panel

    def _local_page(self, parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.local_query = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.local_query.SetHint("C2040, Bauteilname, Beschreibung …")
        self.local_query.Bind(wx.EVT_TEXT_ENTER, self._search_local)
        row.Add(self.local_query, 1, wx.RIGHT, 8)
        button = wx.Button(panel, label="Lokal suchen")
        button.Bind(wx.EVT_BUTTON, self._search_local)
        row.Add(button)
        layout.Add(row, 0, wx.EXPAND | wx.ALL, 8)
        self.local_results = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for idx, (label, width) in enumerate(
            [("LCSC", 100), ("Symbol", 230), ("Footprint", 250), ("Beschreibung", 330)]
        ):
            self.local_results.InsertColumn(idx, label, width=width)
        layout.Add(self.local_results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
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
        with wx.DirDialog(self, "Bibliotheksordner auswählen") as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                folder = Path(dialog.GetPath())
                self.output.SetValue(str(folder / folder.name))

    def _run(self, label: str, job: Any, done: Any) -> None:
        self.status.SetLabel(label)

        def worker() -> None:
            try:
                value = job()
            except Exception as exc:  # GUI boundary: show actionable error
                wx.CallAfter(self._show_error, str(exc))
            else:
                wx.CallAfter(done, value)

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, message: str) -> None:
        self.status.SetLabel("Fehler")
        wx.MessageBox(message, "PartHarbor", wx.OK | wx.ICON_ERROR, self)

    def _search_remote(self, _event: wx.CommandEvent) -> None:
        kind = ["base", None, "expand"][self.part_type.GetSelection()]
        self._run("JLCPCB wird durchsucht …", lambda: search_jlcpcb(self.query.GetValue(), kind), self._show_remote)

    def _show_remote(self, payload: dict[str, Any]) -> None:
        self.remote_results = payload.get("results", [])
        self.results.DeleteAllItems()
        for part in self.remote_results:
            row = self.results.InsertItem(self.results.GetItemCount(), str(part.get("lcsc", "")))
            values = [part.get("type", ""), part.get("stock", 0), part.get("package", ""), part.get("model", ""), part.get("name", "")]
            for column, value in enumerate(values, 1):
                self.results.SetItem(row, column, str(value))
        self.status.SetLabel(f"{len(self.remote_results)} von {payload.get('total', 0)} Treffern geladen")

    def _selected_remote(self) -> dict[str, Any] | None:
        index = self.results.GetFirstSelected()
        return self.remote_results[index] if 0 <= index < len(self.remote_results) else None

    def _import_selected(self, _event: wx.CommandEvent) -> None:
        part = self._selected_remote()
        if not part:
            self._show_error("Bitte zuerst einen Treffer auswählen.")
            return
        self._start_import([part["lcsc"]])

    def _import_direct(self, _event: wx.CommandEvent) -> None:
        self._start_import(normalize_lcsc_ids(self.ids.GetValue()))

    def _start_import(self, ids: list[str]) -> None:
        options = self._options()
        self._run(
            f"Importiere {len(ids)} Bauteil(e) …",
            lambda: import_components(ids, options),
            self._import_done,
        )

    def _import_done(self, result: dict[str, bool]) -> None:
        ok = [part_id for part_id, success in result.items() if success]
        failed = [part_id for part_id, success in result.items() if not success]
        message = f"Importiert: {', '.join(ok) or '–'}"
        if failed:
            message += f"\nFehlgeschlagen/übersprungen: {', '.join(failed)}"
        message += "\n\nIn KiCad ggf. Symbolbibliotheken neu laden. Die C-Nummer ist als Suchbegriff hinterlegt."
        self.status.SetLabel(message.splitlines()[0])
        wx.MessageBox(message, "PartHarbor", wx.OK | (wx.ICON_WARNING if failed else wx.ICON_INFORMATION), self)

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
        self.status.SetLabel(f"{len(matches)} lokale Treffer")


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
