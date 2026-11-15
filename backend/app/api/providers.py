from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.providers.base import VideoProvider
from agent.providers.registry import provider_catalog

from ..config import settings
from ..database import get_db
from ..deps import require_user
from ..models import ProviderAccount, User
from ..schemas import MessageOut, ProviderConnectIn, ProviderOut
from ..security import decrypt_secret, encrypt_secret, utcnow
from ..services.project_service import ensure_simulated_account

router = APIRouter(prefix="/providers", tags=["providers"])


def _display_name(provider: str) -> str:
    return {"simulated": "Simulated Provider", "taaft": "TAAFT (gated)"}.get(provider, provider)


def _taaft_session_path(user_id: str) -> Path:
    path = settings.storage_path / "_sessions" / "api" / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path / "storage_state.json"


def _validate_storage_state(raw: str) -> str:
    """Accept a Playwright storage_state JSON document (cookies and/or origins)."""
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="storage_state must be valid Playwright storage_state JSON") from exc
    if not isinstance(data, dict) or not (data.get("cookies") or data.get("origins")):
        raise HTTPException(status_code=400, detail="storage_state JSON must contain cookies or origins")
    cookies = data.get("cookies") or []
    origins = data.get("origins") or []
    if not cookies and not origins:
        raise HTTPException(status_code=400, detail="storage_state contains an empty session")
    return raw


async def _get_taaft_account(db: AsyncSession, user_id: str) -> ProviderAccount | None:
    return (
        await db.execute(
            select(ProviderAccount).where(
                ProviderAccount.user_id == user_id, ProviderAccount.provider == "taaft"
            )
        )
    ).scalar_one_or_none()


@router.get("", response_model=list[ProviderOut])
async def list_providers(
    user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> list[ProviderOut]:
    accounts = {
        account.provider: account
        for account in (
            await db.execute(select(ProviderAccount).where(ProviderAccount.user_id == user.id))
        ).scalars()
    }
    items: list[ProviderOut] = []
    for entry in provider_catalog(taaft_enabled=settings.taaft_enabled):
        account = accounts.get(entry["provider"])
        items.append(
            ProviderOut(
                provider=entry["provider"],
                display_name=entry["display_name"],
                description=entry["description"],
                status=account.status if account else "disconnected",
                connectable=entry["connectable"],
                requires_consent=entry["requires_consent"],
                connected=bool(account and account.status == "connected"),
                account_ref=account.account_ref if account else None,
                usage=account.usage if account else None,
                last_verified_at=account.last_verified_at if account else None,
                notes=entry["notes"],
            )
        )
    return items


@router.post("/{provider}/connect", response_model=ProviderOut)
async def connect_provider(
    provider: str,
    payload: ProviderConnectIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProviderOut:
    if provider == "simulated":
        account = await ensure_simulated_account(db, user.id)
        account.status = "connected"
        account.last_verified_at = utcnow()
        await db.commit()
        return ProviderOut(
            provider="simulated",
            display_name=_display_name("simulated"),
            description="Local deterministic provider that renders real MP4 test clips.",
            status="connected",
            connectable=True,
            requires_consent=False,
            connected=True,
            account_ref=account.account_ref,
            usage=account.usage,
            last_verified_at=account.last_verified_at,
        )
    if provider == "taaft":
        if not settings.taaft_enabled:
            raise HTTPException(
                status_code=409,
                detail=(
                    "TAAFT automation is disabled on this deployment (TAAFT_ENABLED=false). "
                    "Enable it in the service environment to use real TAAFT automation."
                ),
            )
        if not payload.accept_terms:
            raise HTTPException(status_code=400, detail="Explicit provider consent is required")
        if not payload.storage_state:
            raise HTTPException(
                status_code=400,
                detail=(
                    "A Playwright storage_state JSON is required. Export it from a logged-in "
                    "TAAFT browser profile and upload it here to onboard the account."
                ),
            )
        state_json = _validate_storage_state(payload.storage_state)
        account = _get_taaft_account(db, user.id)
        if account is None:
            account = ProviderAccount(user_id=user.id, provider="taaft", status="disconnected")
            db.add(account)
        account.encrypted_session = encrypt_secret(state_json)
        account.session_meta = {
            "source": "storage_state_upload",
            "cookies": len(json.loads(state_json).get("cookies") or []),
            "origins": len(json.loads(state_json).get("origins") or []),
        }
        account.status = "connected"
        account.last_verified_at = utcnow()
        await db.commit()
        return ProviderOut(
            provider="taaft",
            display_name=_display_name("taaft"),
            description="Per-user TAAFT video generator automation via Playwright.",
            status=account.status,
            connectable=True,
            requires_consent=True,
            connected=True,
            account_ref=account.account_ref,
            usage=account.usage,
            last_verified_at=account.last_verified_at,
        )
    raise HTTPException(status_code=404, detail="Unknown provider")


@router.post("/{provider}/verify", response_model=ProviderOut)
async def verify_provider(
    provider: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ProviderOut:
    if provider == "simulated":
        account = await ensure_simulated_account(db, user.id)
        account.last_verified_at = utcnow()
        await db.commit()
        return ProviderOut(
            provider="simulated",
            display_name=_display_name("simulated"),
            description="Local deterministic provider that renders real MP4 test clips.",
            status="connected",
            connectable=True,
            requires_consent=False,
            connected=True,
            account_ref=account.account_ref,
            usage=account.usage,
            last_verified_at=account.last_verified_at,
        )
    if provider == "taaft":
        if not settings.taaft_enabled:
            raise HTTPException(status_code=409, detail="TAAFT automation is disabled on this deployment")
        account = _get_taaft_account(db, user.id)
        if account is None or not account.encrypted_session:
            raise HTTPException(status_code=404, detail="TAAFT is not connected; connect a session first")
        state_file = _taaft_session_path(user.id)
        state_file.write_text(decrypt_secret(account.encrypted_session), encoding="utf-8")

        from agent.providers.taaft import TaaftProvider

        provider = TaaftProvider(
            enabled=True,
            storage_state_path=state_file,
            chrome_path=settings.taaft_chrome_path or None,
            headless=settings.taaft_headless,
            poll_seconds=settings.taaft_poll_seconds,
            job_timeout_seconds=settings.taaft_job_timeout_seconds,
            tier="quality",
        )
        try:
            result = await asyncio.to_thread(provider._sync_verify)
        except Exception as exc:  # noqa: BLE001 - surface the provider error to the user
            raise HTTPException(status_code=502, detail=f"TAAFT verification failed: {exc}") from exc
        account.status = "connected"
        account.last_verified_at = utcnow()
        await db.commit()
        return ProviderOut(
            provider="taaft",
            display_name=_display_name("taaft"),
            description="Per-user TAAFT video generator automation via Playwright.",
            status=account.status,
            connectable=True,
            requires_consent=True,
            connected=True,
            account_ref=result.get("account_id"),
            usage=account.usage,
            last_verified_at=account.last_verified_at,
        )
    raise HTTPException(status_code=404, detail="Unknown provider")


@router.get("/{provider}/usage", response_model=dict)
async def provider_usage(
    provider: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    account = (
        await db.execute(
            select(ProviderAccount).where(
                ProviderAccount.user_id == user.id, ProviderAccount.provider == provider
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Provider is not connected")
    return {"provider": provider, "status": account.status, "usage": account.usage or {}}


@router.delete("/{provider}", response_model=MessageOut)
async def disconnect_provider(
    provider: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> MessageOut:
    account = (
        await db.execute(
            select(ProviderAccount).where(
                ProviderAccount.user_id == user.id, ProviderAccount.provider == provider
            )
        )
    ).scalar_one_or_none()
    if account is None:
        return MessageOut(message="Provider already disconnected")
    account.status = "disconnected"
    account.encrypted_session = None
    account.session_meta = None
    account.usage = None
    account.active_project_id = None
    await db.commit()
    return MessageOut(message="Provider session revoked")
