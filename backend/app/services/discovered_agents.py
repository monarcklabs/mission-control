"""Read-only discovery helpers for gateway-configured agents."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.gateways import Gateway
from app.schemas.agents import DiscoveredAgentRead
from app.services.openclaw.gateway_resolver import gateway_client_config
from app.services.openclaw.provisioning import _gateway_config_agent_list


def _normalize_model(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, Mapping):
        primary = value.get("primary")
        if isinstance(primary, str):
            normalized = primary.strip()
            return normalized or None
    return None


def _normalize_skills(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        skill = str(item).strip()
        if skill:
            result.append(skill)
    return result


async def list_discovered_agents(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> list[DiscoveredAgentRead]:
    """Read configured agents directly from each organization gateway."""
    gateways = await Gateway.objects.filter_by(organization_id=organization_id).all(session)
    discovered: list[DiscoveredAgentRead] = []

    for gateway in gateways:
        _hash, raw_agents, _config = await _gateway_config_agent_list(gateway_client_config(gateway))
        for raw_agent in raw_agents:
            if not isinstance(raw_agent, Mapping):
                continue
            config_agent_id = str(raw_agent.get("id") or "").strip()
            if not config_agent_id:
                continue
            name = str(raw_agent.get("name") or config_agent_id).strip() or config_agent_id
            heartbeat = raw_agent.get("heartbeat")
            heartbeat_every = None
            if isinstance(heartbeat, Mapping):
                raw_every = heartbeat.get("every")
                if isinstance(raw_every, str):
                    heartbeat_every = raw_every.strip() or None
            discovered.append(
                DiscoveredAgentRead(
                    config_agent_id=config_agent_id,
                    name=name,
                    gateway_id=gateway.id,
                    gateway_name=gateway.name,
                    workspace=(
                        str(raw_agent.get("workspace")).strip()
                        if raw_agent.get("workspace") is not None
                        else None
                    )
                    or None,
                    model=_normalize_model(raw_agent.get("model")),
                    heartbeat_every=heartbeat_every,
                    skills=_normalize_skills(raw_agent.get("skills")),
                )
            )

    discovered.sort(key=lambda item: (item.gateway_name.lower(), item.name.lower()))
    return discovered
