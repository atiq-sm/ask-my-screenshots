from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from .config import AppConfig
from .db import Database
from .query import search


class ResultItem(ListItem):
    def __init__(self, hit: dict) -> None:
        super().__init__()
        self.hit = hit

    def compose(self) -> ComposeResult:
        yield Label(f"[{self.hit['score']:.3f}] {Path(self.hit['path']).name}")


class ScreenshotSearchApp(App):
    TITLE = "Ask My Screenshots"
    BINDINGS = [
        Binding("enter", "open_image", "Open", show=True),
        Binding("y", "copy_path", "Copy path", show=True),
        Binding("o", "reveal", "Reveal", show=True),
        Binding("slash", "focus_search", "Search", show=False),
    ]

    CSS = """
    #search { dock: top; margin: 1; }
    #main { height: 1fr; }
    #results { width: 45%; border-right: solid $primary; }
    #preview { width: 55%; padding: 1; }
    #caption { margin-top: 1; }
    #ocr { color: $text-muted; }
    """

    def __init__(self, db_path: str, config: AppConfig | None = None) -> None:
        super().__init__()
        self.db_path = db_path
        self.config = config or AppConfig()
        self._results: list[dict] = []
        self._debounce_timer: threading.Timer | None = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search screenshots…", id="search")
        with Horizontal(id="main"):
            yield ListView(id="results")
            with Vertical(id="preview"):
                yield Static("Select a result", id="thumb")
                yield Static("", id="caption")
                yield Static("", id="ocr")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search":
            return
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        query = event.value.strip()
        self._debounce_timer = threading.Timer(0.3, lambda: self.call_from_thread(self._run_search, query))
        self._debounce_timer.start()

    def _run_search(self, query: str) -> None:
        if not query:
            self._results = []
            self._refresh_list()
            return
        self._results = search(query, self.db_path, config=self.config)
        self._refresh_list()

    def _refresh_list(self) -> None:
        list_view = self.query_one("#results", ListView)
        list_view.clear()
        for hit in self._results:
            list_view.append(ResultItem(hit))
        if self._results:
            list_view.index = 0
            self._show_preview(self._results[0])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ResultItem):
            self._show_preview(event.item.hit)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, ResultItem):
            self._show_preview(event.item.hit)

    def _show_preview(self, hit: dict) -> None:
        caption = self.query_one("#caption", Static)
        ocr = self.query_one("#ocr", Static)
        thumb = self.query_one("#thumb", Static)
        caption.update(hit.get("caption") or "(no caption)")
        ocr_text = hit.get("ocr_text") or ""
        snippet = ocr_text[:500] + ("…" if len(ocr_text) > 500 else "")
        ocr.update(snippet or "(no OCR text)")
        thumb.update(f"Path: {hit['path']}")
        db = Database(self.db_path)
        try:
            row = db.get_by_path(hit["path"])
            if row and row.get("thumbnail_blob"):
                thumb_path = self._write_temp_thumb(row["thumbnail_blob"])
                if thumb_path:
                    thumb.update(f"Thumbnail: {thumb_path}")
        finally:
            db.close()

    def _write_temp_thumb(self, blob: bytes) -> str | None:
        try:
            cache = Path.home() / ".cache" / "ams" / "thumbs"
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / f"preview_{hash(blob) & 0xFFFFFFFF:x}.jpg"
            path.write_bytes(blob)
            return str(path)
        except OSError:
            return None

    def _selected_hit(self) -> dict | None:
        list_view = self.query_one("#results", ListView)
        if list_view.highlighted_child and isinstance(
            list_view.highlighted_child, ResultItem
        ):
            return list_view.highlighted_child.hit
        if self._results:
            return self._results[0]
        return None

    def action_open_image(self) -> None:
        hit = self._selected_hit()
        if not hit:
            return
        path = hit["path"]
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)

    def action_copy_path(self) -> None:
        hit = self._selected_hit()
        if not hit:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["clip"],
                    input=hit["path"],
                    text=True,
                    check=False,
                    shell=True,
                )
            elif sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=hit["path"], text=True, check=False)
            else:
                for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
                    try:
                        subprocess.run(cmd, input=hit["path"], text=True, check=False)
                        break
                    except FileNotFoundError:
                        continue
            self.notify("Path copied")
        except Exception:
            self.notify("Copy failed", severity="error")

    def action_reveal(self) -> None:
        hit = self._selected_hit()
        if not hit:
            return
        path = hit["path"]
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", path], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", path], check=False)
        else:
            subprocess.run(["xdg-open", str(Path(path).parent)], check=False)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()


def run_tui(db_path: str, config: AppConfig | None = None) -> None:
    app = ScreenshotSearchApp(db_path, config=config)
    app.run()
