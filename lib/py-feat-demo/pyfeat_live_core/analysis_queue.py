from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class QueueItem:
    id: str
    kind: str
    label: str = ""
    image: str = ""
    video: str = ""
    status: str = "pending"
    progress: float = 0.0
    error: str = ""
    session_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self, include_payload: bool = False) -> dict:
        payload = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_payload:
            payload["image"] = self.image
            payload["video"] = self.video
        return payload


class AnalysisQueue:
    def __init__(self):
        self.items: list[QueueItem] = []
        self.state = "idle"

    def add_image(self, image: str, label: str = "") -> QueueItem:
        item = QueueItem(id=uuid.uuid4().hex[:12], kind="image", image=image, label=label)
        self.items.append(item)
        return item

    def add_video(self, video: str, label: str = "") -> QueueItem:
        item = QueueItem(id=uuid.uuid4().hex[:12], kind="video", video=video, label=label)
        self.items.append(item)
        return item

    def list_items(self) -> list[dict]:
        return [item.to_dict() for item in self.items]

    def get(self, item_id: str) -> QueueItem | None:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def remove(self, item_id: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item.id != item_id]
        return len(self.items) != before

    def pending_items(self) -> list[QueueItem]:
        return [item for item in self.items if item.status in {"pending", "error"}]

    def set_state(self, state: str) -> None:
        self.state = state

    def snapshot(self) -> dict:
        return {"state": self.state, "items": self.list_items()}


def touch(item: QueueItem) -> None:
    item.updated_at = datetime.now(timezone.utc).isoformat()
