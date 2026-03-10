# ruff: noqa: INP001, S101
"""Tests for deployment-driven Mission Control profile syncing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import settings
from app.models.task_custom_fields import BoardTaskCustomField, TaskCustomFieldDefinition
from app.services import mission_control_profile


@dataclass
class _FakeExecResult:
    all_values: list[Any] | None = None

    def __iter__(self):
        return iter(self.all_values or [])

    def all(self) -> list[Any]:
        return list(self.all_values or [])


@dataclass
class _FakeSession:
    exec_results: list[Any]
    added: list[Any] = field(default_factory=list)
    committed: int = 0
    flushed: int = 0

    async def exec(self, _statement: Any) -> Any:
        if not self.exec_results:
            raise AssertionError("No more exec_results left for session.exec")
        return self.exec_results.pop(0)

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1


@pytest.mark.asyncio
async def test_sync_profile_fields_for_organization_creates_fields_and_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "mission_control_config",
        """
        {
          "intake_fields": [
            {"key":"task","label":"Task","type":"text","required":true,"help_text":"What to do"},
            {"key":"docs","label":"Docs","type":"document_list","required":false}
          ]
        }
        """.strip(),
    )
    session = _FakeSession(
        exec_results=[
            _FakeExecResult(all_values=[uuid4(), uuid4()]),
            _FakeExecResult(all_values=[]),
            _FakeExecResult(all_values=[]),
            _FakeExecResult(all_values=[]),
        ]
    )

    changes = await mission_control_profile.sync_profile_fields_for_organization(
        session=session,
        organization_id=uuid4(),
    )

    definitions = [item for item in session.added if isinstance(item, TaskCustomFieldDefinition)]
    bindings = [item for item in session.added if isinstance(item, BoardTaskCustomField)]

    assert changes == 6
    assert session.flushed == 2
    assert session.committed == 1
    assert [definition.field_key for definition in definitions] == ["task", "docs"]
    assert definitions[1].field_type == "text_long"
    assert len(bindings) == 4


@pytest.mark.asyncio
async def test_bind_existing_custom_fields_to_board_only_adds_missing_bindings() -> None:
    first_definition_id = uuid4()
    second_definition_id = uuid4()
    session = _FakeSession(
        exec_results=[
            _FakeExecResult(all_values=[first_definition_id, second_definition_id]),
            _FakeExecResult(all_values=[first_definition_id]),
        ]
    )

    created = await mission_control_profile.bind_existing_custom_fields_to_board(
        session=session,
        organization_id=uuid4(),
        board_id=uuid4(),
    )

    bindings = [item for item in session.added if isinstance(item, BoardTaskCustomField)]
    assert created == 1
    assert len(bindings) == 1
    assert bindings[0].task_custom_field_definition_id == second_definition_id
