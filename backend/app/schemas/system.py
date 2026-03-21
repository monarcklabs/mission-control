"""System administration schemas for self-update / branch switching."""

from __future__ import annotations

from pydantic import Field
from sqlmodel import SQLModel


class SystemInfoResponse(SQLModel):
    """Current system state including git branch and self-update availability."""

    current_branch: str = Field(description="Current git branch name.")
    commit_sha: str = Field(description="Current HEAD commit SHA.")
    remote_branches: list[str] = Field(
        description="Available remote branches (origin/*)."
    )
    self_update_available: bool = Field(
        description="Whether self-update (branch switching) is available."
    )


class BranchSwitchRequest(SQLModel):
    """Request to switch to a different git branch and rebuild."""

    branch: str = Field(
        description="Target branch name to switch to.",
        min_length=1,
    )


class BranchSwitchResponse(SQLModel):
    """Result of a branch switch request."""

    status: str = Field(description="'ok' or 'error'.")
    message: str = Field(description="Human-readable status message.")
