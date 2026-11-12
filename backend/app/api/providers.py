from __future__ import annotations

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
from ..security import utcnow
from ..services.project_service import ensure_simulated_account

router = APIRouter(prefix="/providers", tags=["providers"])


def _display_name(provider: str) -> str:
    return {"simulated": "Simulated Provider", "taaft": "TAAFT (gated)"}.get(provider, provider)


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
                    "TAAFT automation is disabled. TAAFT's Terms of Service prohibit automated access without "
                    "prior written consent. See TAAFT_INTEGRATION_FEASIBILITY.md. No bypass is implemented."
                ),
            )
        if not payload.accept_terms:
            raise HTTPException(status_code=400, detail="Explicit provider consent is required")
        raise HTTPException(
            status_code=501,
            detail=(
                "TAAFT operator gate is enabled, but remote browser onboarding is not enabled in this build. "
                "Complete the feasibility review and configure per-user session onboarding before use."
            ),
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
        raise HTTPException(status_code=409, detail="TAAFT automation is disabled pending provider authorization")
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
