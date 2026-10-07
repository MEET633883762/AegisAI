"""In-memory, versioned repository for adaptive knowledge patches."""
from __future__ import annotations

from dataclasses import dataclass, field

from memory.knowledge_patch import KnowledgePatch, PatchStatus


@dataclass
class KnowledgeRepository:
    _patches: dict[str, KnowledgePatch] = field(default_factory=dict)
    _versions: dict[str, list[KnowledgePatch]] = field(default_factory=dict)

    def add_candidate(self, patch: KnowledgePatch) -> None:
        if patch.patch_id in self._patches:
            raise ValueError(f"duplicate patch id: {patch.patch_id}")
        versions = self._versions.setdefault(patch.patch_id, [])
        if patch.version != len(versions) + 1:
            raise ValueError("patch version must start at 1 and increase sequentially")
        self._patches[patch.patch_id] = patch.model_copy(deep=True)
        versions.append(patch.model_copy(deep=True))

    def update(self, patch: KnowledgePatch) -> None:
        if patch.patch_id not in self._patches:
            raise KeyError(patch.patch_id)
        current = self._patches[patch.patch_id]
        if patch.version <= current.version:
            raise ValueError("patch version must increase")
        self._patches[patch.patch_id] = patch.model_copy(deep=True)
        self._versions[patch.patch_id].append(patch.model_copy(deep=True))

    def get(self, patch_id: str) -> KnowledgePatch | None:
        patch = self._patches.get(patch_id)
        return None if patch is None else patch.model_copy(deep=True)

    def versions(self, patch_id: str) -> tuple[KnowledgePatch, ...]:
        return tuple(p.model_copy(deep=True) for p in self._versions.get(patch_id, []))

    def validated(self, role: str | None = None) -> tuple[KnowledgePatch, ...]:
        rows = [p for p in self._patches.values() if p.status is PatchStatus.VALIDATED]
        if role is not None:
            rows = [p for p in rows if p.role == role]
        return tuple(p.model_copy(deep=True) for p in sorted(rows, key=lambda p: p.patch_id))

    def revoke(self, patch_id: str) -> KnowledgePatch:
        current = self._patches.get(patch_id)
        if current is None:
            raise KeyError(patch_id)
        updated = current.revoke()
        # Revoke is a state transition and receives a new immutable version.
        updated = updated.model_copy(update={"version": current.version + 1})
        self.update(updated)
        return updated.model_copy(deep=True)
