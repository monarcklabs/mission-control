"""Helpers for syncing deployment-provided Mission Control profile config."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.boards import Board
from app.models.organizations import Organization
from app.models.task_custom_fields import BoardTaskCustomField, TaskCustomFieldDefinition

logger = get_logger(__name__)


@dataclass(frozen=True)
class MissionControlProfileField:
    """Normalized field definition loaded from deployment config."""

    field_key: str
    label: str
    field_type: str
    description: str | None
    required: bool


def _normalize_field_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"text_long", "long_text", "document_list"}:
        return "text_long"
    return "text"


def _normalize_profile_fields(raw: object) -> list[MissionControlProfileField]:
    if not isinstance(raw, list):
        return []

    results: list[MissionControlProfileField] = []
    seen = set[str]()
    for item in raw:
        if not isinstance(item, dict):
            continue
        field_key = str(item.get("key") or "").strip()
        label = str(item.get("label") or field_key).strip()
        if not field_key or not label or field_key in seen:
            continue
        seen.add(field_key)
        description = str(item.get("help_text") or "").strip() or None
        results.append(
            MissionControlProfileField(
                field_key=field_key,
                label=label,
                field_type=_normalize_field_type(item.get("type")),
                description=description,
                required=bool(item.get("required")),
            )
        )
    return results


def get_profile_fields_from_settings() -> list[MissionControlProfileField]:
    raw = settings.mission_control_config.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("mission_control.profile.invalid_json")
        return []
    intake_fields = parsed.get("intake_fields") if isinstance(parsed, dict) else None
    return _normalize_profile_fields(intake_fields)


async def sync_profile_fields_for_organization(
    *,
    session: AsyncSession,
    organization_id: UUID,
) -> int:
    """Upsert configured profile fields and bind them to all org boards."""
    profile_fields = get_profile_fields_from_settings()
    if not profile_fields:
        return 0

    board_ids = list(
        await session.exec(
            select(col(Board.id)).where(col(Board.organization_id) == organization_id)
        )
    )
    existing_definitions = list(
        await session.exec(
            select(TaskCustomFieldDefinition).where(
                col(TaskCustomFieldDefinition.organization_id) == organization_id
            )
        )
    )
    definitions_by_key = {definition.field_key: definition for definition in existing_definitions}

    changed = 0
    now = utcnow()
    for profile_field in profile_fields:
        definition = definitions_by_key.get(profile_field.field_key)
        if definition is None:
            definition = TaskCustomFieldDefinition(
                organization_id=organization_id,
                field_key=profile_field.field_key,
                label=profile_field.label,
                field_type=profile_field.field_type,
                ui_visibility="always",
                description=profile_field.description,
                required=profile_field.required,
                created_at=now,
                updated_at=now,
            )
            session.add(definition)
            await session.flush()
            definitions_by_key[profile_field.field_key] = definition
            changed += 1
        else:
            next_values = {
                "label": profile_field.label,
                "field_type": profile_field.field_type,
                "description": profile_field.description,
                "required": profile_field.required,
            }
            updated = False
            for key, value in next_values.items():
                if getattr(definition, key) != value:
                    setattr(definition, key, value)
                    updated = True
            if updated:
                definition.updated_at = now
                session.add(definition)
                changed += 1

        existing_board_ids = set(
            (
                await session.exec(
                    select(col(BoardTaskCustomField.board_id)).where(
                        col(BoardTaskCustomField.task_custom_field_definition_id) == definition.id
                    )
                )
            ).all()
        )
        for board_id in board_ids:
            if board_id in existing_board_ids:
                continue
            session.add(
                BoardTaskCustomField(
                    board_id=board_id,
                    task_custom_field_definition_id=definition.id,
                    created_at=now,
                )
            )
            changed += 1

    if changed:
        await session.commit()
    return changed


async def sync_profile_fields_for_all_organizations(session: AsyncSession) -> int:
    """Apply configured profile fields to every organization in the instance."""
    organization_ids = list(await session.exec(select(col(Organization.id))))
    total_changed = 0
    for organization_id in organization_ids:
        total_changed += await sync_profile_fields_for_organization(
            session=session,
            organization_id=organization_id,
        )
    if total_changed:
        logger.info("mission_control.profile.sync_complete changes=%s", total_changed)
    else:
        logger.info("mission_control.profile.sync_complete changes=0")
    return total_changed


async def bind_existing_custom_fields_to_board(
    *,
    session: AsyncSession,
    organization_id: UUID,
    board_id: UUID,
) -> int:
    """Ensure newly created boards inherit all org-level custom fields."""
    definition_ids = list(
        await session.exec(
            select(col(TaskCustomFieldDefinition.id)).where(
                col(TaskCustomFieldDefinition.organization_id) == organization_id
            )
        )
    )
    if not definition_ids:
        return 0

    existing_ids = set(
        (
            await session.exec(
                select(col(BoardTaskCustomField.task_custom_field_definition_id)).where(
                    col(BoardTaskCustomField.board_id) == board_id
                )
            )
        ).all()
    )
    now = utcnow()
    created = 0
    for definition_id in definition_ids:
        if definition_id in existing_ids:
            continue
        session.add(
            BoardTaskCustomField(
                board_id=board_id,
                task_custom_field_definition_id=definition_id,
                created_at=now,
            )
        )
        created += 1
    return created
