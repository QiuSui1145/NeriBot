"""备忘便签全栈插件实现。
展示如何通过独立 Tab 与 FastAPI 专属子路由构建独立前端管理页。
"""

import json
import time
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel

from src.plugins.base import BasePlugin


class NoteItem(BaseModel):
    id: str
    title: str
    content: str
    created_at: float


class AddNoteRequest(BaseModel):
    title: str
    content: str


class SampleNotesPlugin(BasePlugin):
    """备忘便签全栈插件主类。"""

    def __init__(self, context, manifest):
        super().__init__(context, manifest)
        self.router = APIRouter()
        self._setup_routes()

    def _get_notes_file(self):
        return self.context.data_dir / "notes.json"

    def _read_notes(self) -> list:
        f = self._get_notes_file()
        if f.exists():
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                pass
        return []

    def _save_notes(self, notes: list):
        f = self._get_notes_file()
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(notes, fp, ensure_ascii=False, indent=2)

    def _setup_routes(self):
        @self.router.get("/api/plugins/plugin_sample_notes/notes")
        async def get_notes():
            return {"status": "ok", "notes": self._read_notes()}

        @self.router.post("/api/plugins/plugin_sample_notes/notes")
        async def add_note(req: AddNoteRequest):
            notes = self._read_notes()
            new_note = {
                "id": f"note_{int(time.time() * 1000)}",
                "title": req.title,
                "content": req.content,
                "created_at": time.time(),
            }
            notes.insert(0, new_note)
            self._save_notes(notes)
            return {"status": "ok", "note": new_note}

        @self.router.delete("/api/plugins/plugin_sample_notes/notes/{note_id}")
        async def delete_note(note_id: str):
            notes = self._read_notes()
            notes = [n for n in notes if n.get("id") != note_id]
            self._save_notes(notes)
            return {"status": "ok"}

    async def on_enable(self) -> None:
        # 将子路由挂载至主应用
        from main import app
        app.include_router(self.router)
        self.context.logger.info("备忘便签专属路由已挂载至 /api/plugins/plugin_sample_notes/notes")
