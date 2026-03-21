"""System administration endpoints for self-update / branch switching."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_org_admin
from app.core.config import settings
from app.schemas.system import (
    BranchSwitchRequest,
    BranchSwitchResponse,
    SystemInfoResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

DOCKER_SOCKET = Path("/var/run/docker.sock")


def _self_update_available() -> bool:
    """Check whether the self-update feature is available."""
    repo_path = settings.self_update_repo_path.strip()
    if not repo_path:
        return False
    repo = Path(repo_path)
    return repo.is_dir() and (repo / ".git").exists() and DOCKER_SOCKET.exists()


async def _run_git(*args: str) -> str:
    """Run a git command in the repo directory and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=settings.self_update_repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={proc.returncode}): {stderr.decode().strip()}"
        )
    return stdout.decode().strip()


@router.get(
    "/info",
    response_model=SystemInfoResponse,
    dependencies=[Depends(require_org_admin)],
)
async def system_info() -> SystemInfoResponse:
    """Return current branch, commit SHA, and available remote branches."""
    if not _self_update_available():
        return SystemInfoResponse(
            current_branch="unknown",
            commit_sha="unknown",
            remote_branches=[],
            self_update_available=False,
        )

    current_branch = await _run_git("rev-parse", "--abbrev-ref", "HEAD")
    commit_sha = await _run_git("log", "-1", "--format=%H")

    # Fetch latest refs from origin
    try:
        await _run_git("fetch", "--prune", "origin")
    except RuntimeError:
        logger.warning("git fetch failed, using cached branch list")

    raw_branches = await _run_git(
        "branch", "-r", "--format=%(refname:short)"
    )
    remote_branches = [
        b.removeprefix("origin/")
        for b in raw_branches.splitlines()
        if b.startswith("origin/") and not b.endswith("/HEAD")
    ]

    return SystemInfoResponse(
        current_branch=current_branch,
        commit_sha=commit_sha,
        remote_branches=sorted(remote_branches),
        self_update_available=True,
    )


@router.post(
    "/switch-branch",
    response_model=BranchSwitchResponse,
    dependencies=[Depends(require_org_admin)],
)
async def switch_branch(body: BranchSwitchRequest) -> BranchSwitchResponse:
    """Switch to a different branch and trigger a Docker Compose rebuild."""
    if not _self_update_available():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Self-update is not available. Ensure SELF_UPDATE_REPO_PATH is set and the repo + Docker socket are mounted.",
        )

    branch = body.branch.strip()
    repo_path = settings.self_update_repo_path
    compose_project = settings.self_update_compose_project

    try:
        await _run_git("fetch", "origin")
        await _run_git("checkout", branch)
        await _run_git("pull", "origin", branch)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Git operation failed: {exc}",
        ) from exc

    # Trigger docker compose rebuild in the background.
    # This will restart the containers (including this one), so we fire-and-forget.
    logger.info("Triggering Docker Compose rebuild for branch %s", branch)
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "-p",
        compose_project,
        "-f",
        "compose.yml",
        "up",
        "-d",
        "--build",
        "--force-recreate",
        "--remove-orphans",
        cwd=repo_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    # Don't await — the rebuild will kill this process
    _ = proc

    return BranchSwitchResponse(
        status="ok",
        message=f"Switched to branch '{branch}' and triggered rebuild. The app will restart shortly.",
    )
