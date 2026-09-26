"""Turn a PreToolUse payload into the exact change it proposes, as a unified diff."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from ..diff import classify_file, parse_patch
from ..models import FileKind, Hunk

FILE_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})


class ProposalError(ValueError):
    """The payload cannot be turned into an inspectable change."""


@dataclass(frozen=True)
class Proposal:
    tool: str
    path: str  # relative to the sandbox root, POSIX separators
    file_kind: FileKind
    before: str
    after: str
    hunks: tuple[Hunk, ...]

    @property
    def unchanged(self) -> bool:
        return self.before == self.after


def relative_path(root: Path, file_path: str) -> str:
    """Resolve `file_path` inside `root`; raise if it escapes the sandbox."""
    root = root.resolve()
    target = Path(file_path)
    target = (target if target.is_absolute() else root / target).resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        raise ProposalError(f"{file_path} is outside the sandbox") from None


def _apply_edit(text: str, old: str, new: str, replace_all: bool, path: str) -> str:
    if not old:
        raise ProposalError(f"empty old_string for {path}")
    count = text.count(old)
    if count == 0:
        raise ProposalError(f"old_string not found in {path}")
    if count > 1 and not replace_all:
        raise ProposalError(f"old_string is not unique in {path}")
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


def proposed_after(tool: str, tool_input: dict, before: str, path: str) -> str:
    if tool == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str):
            raise ProposalError("Write without string content")
        return content
    if tool == "Edit":
        return _apply_edit(
            before,
            str(tool_input.get("old_string", "")),
            str(tool_input.get("new_string", "")),
            bool(tool_input.get("replace_all", False)),
            path,
        )
    if tool == "MultiEdit":
        edits = tool_input.get("edits")
        if not isinstance(edits, list) or not edits:
            raise ProposalError("MultiEdit without edits")
        text = before
        for edit in edits:
            text = _apply_edit(
                text,
                str(edit.get("old_string", "")),
                str(edit.get("new_string", "")),
                bool(edit.get("replace_all", False)),
                path,
            )
        return text
    raise ProposalError(f"{tool} is not a file-editing tool")


def unified_diff(path: str, before: str, after: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=3
    )
    return "\n".join(lines)


def build_proposal(root: Path, tool: str, tool_input: dict) -> Proposal:
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        raise ProposalError(f"{tool} without file_path")
    path = relative_path(root, file_path)
    target = root.resolve() / path
    if target.exists() and not target.is_file():
        raise ProposalError(f"{path} is not a regular file")
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    after = proposed_after(tool, tool_input, before, path)
    return Proposal(
        tool=tool,
        path=path,
        file_kind=classify_file(path),
        before=before,
        after=after,
        hunks=tuple(parse_patch(path, unified_diff(path, before, after))),
    )
