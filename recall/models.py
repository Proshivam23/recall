from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class SavedCommand:
    command: str
    description: str
    tags: list[str]
    tool: str                      # git, docker, azure, etc.
    id: Optional[int] = None
    created_at: Optional[str] = None
    use_count: int = 0

    def tags_str(self) -> str:
        return ", ".join(self.tags) if self.tags else ""

    @staticmethod
    def from_row(row: tuple) -> "SavedCommand":
        id_, command, description, tags_raw, tool, created_at, use_count = row
        tags = tags_raw.split(",") if tags_raw else []
        return SavedCommand(
            id=id_,
            command=command,
            description=description,
            tags=[t.strip() for t in tags],
            tool=tool,
            created_at=created_at,
            use_count=use_count,
        )
