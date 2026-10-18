from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import PaymentOrder, User, get_db
from deps import get_current_user, get_optional_user
from services.admin_audit import record_admin_action
from services.crypto_verify import verify_crypto_payment
from services.plans import activate_plan, is_admin, plan_payload
from services.request_utils import client_ip

router = APIRouter()

PLANS = [
    {
        "id": "premium-1-week",
        "name": "7-Day Pass",
        "price_usd": 2.99,
        "duration_days": 7,
        "rank": "Premium",
        "badge": None,
        "css": "week",
        "cta": "Purchase Week",
        "features": [
            "All Platforms Access",
            "Unlimited Targets",
            "Cloudflare Bypass",
            "Discord Webhook",
        ],
    },
    {
        "id": "premium-1-month",
        "name": "1 Month Access",
        "price_usd": 9.99,
        "duration_days": 30,
        "rank": "Premium",
        "badge": "Most Popular",
        "css": "month",
        "cta": "Purchase Month",
        "savings": "Save ~$2 compared to weekly",
        "features": [
            "All Platforms Access",
            "Unlimited Targets",
            "Cloudflare Bypass",
            "Priority Support",
        ],
    },
    {
        "id": "premium-lifetime",
        "name": "Lifetime License",
        "price_usd": 49.99,
        "duration_days": None,
        "rank": "Lifetime",
        "badge": None,
        "css": "lifetime",
        "cta": "Purchase Lifetime",
        "features": [
            "Pay once, use forever",
            "All future updates",
            "Early Access Features",
            "Private Discord Role",
        ],
    },
]

PLAN_BY_ID = {p["id"]: p for p in PLANS}


class PayPalCheckoutRequest(BaseModel):
    plan_id: str


class CryptoCheckoutRequest(BaseModel):
    plan_id: str
    currency: Literal["BTC", "ETH", "LTC", "USDT"] = "USDT"
    sender_wallet: str = Field(default="", max_length=256)


class CryptoConfirmRequest(BaseModel):
    order_id: int
    tx_hash: str = Field(min_length=8, max_length=256)


def _get_plan(plan_id: str) -> dict:
    plan = PLAN_BY_ID.get(plan_id)
    if not plan:
        raise HTTPException(400, f"Unknown plan: {plan_id}")
    return plan


async def _maybe_auto_activate(db: AsyncSession, order: PaymentOrder, user: User) -> None:
    if not settings.billing_auto_activate:
        return
    plan = _get_plan(order.plan_id)
    await activate_plan(db, user, rank=plan["rank"], duration_days=plan["duration_days"])
    order.status = "completed"
    await db.commit()


async def _activate_verified_crypto(db: AsyncSession, order: PaymentOrder, buyer: User) -> None:
    plan = _get_plan(order.plan_id)
    await activate_plan(db, buyer, rank=plan["rank"], duration_days=plan["duration_days"])
    order.status = "completed"
    await db.commit()


@router.get("/plans")
async def list_plans():
    return {
        "plans": [
            {
                "id": p["id"],
                "name": p["name"],
                "price_usd": p["price_usd"],
                "duration_days": p["duration_days"],
                "badge": p["badge"],
                "css": p["css"],
                "cta": p.get("cta"),
                "savings": p.get("savings"),
                "features": p["features"],
            }
            for p in PLANS
        ],
        "paypal_email": settings.paypal_email or None,
        "crypto_addresses": {
            "BTC": settings.crypto_btc_address or None,
            "ETH": settings.crypto_eth_address or None,
            "LTC": settings.crypto_ltc_address or None,
            "USDT": settings.crypto_usdt_address or None,
        },
        "trial_limit_seconds": 300,
    }


@router.get("/subscription")
async def get_subscription(user: User | None = Depends(get_optional_user)):
    if not user:
        return {
            "active": False,
            "plan": None,
            "expires_at": None,
            "is_trial": False,
            "trial_remaining_seconds": None,
            "trial_exhausted": False,
        }
    payload = plan_payload(user)
    return {
        "active": payload["has_active_plan"],
        "plan": payload["rank"],
        "expires_at": payload["plan_expires_at"],
        "is_trial": payload["is_trial"],
        "trial_used_seconds": payload["trial_used_seconds"],
        "trial_limit_seconds": payload["trial_limit_seconds"],
        "trial_remaining_seconds": payload["trial_remaining_seconds"],
        "trial_exhausted": payload["trial_exhausted"],
    }


@router.post("/paypal/checkout")
async def paypal_checkout(
    body: PayPalCheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = _get_plan(body.plan_id)
    email = (settings.paypal_email or "").strip()
    if not email:
        raise HTTPException(
            503,
            "PayPal is not configured yet — set PAYPAL_EMAIL on the API, or pay with crypto.",
        )

    order = PaymentOrder(
        user_id=user.id,
        plan_id=plan["id"],
        method="paypal",
        status="awaiting_payment",
        amount_usd=str(plan["price_usd"]),
        note=f"Send Friends & Family to {email}",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "order_id": order.id,
        "plan_id": plan["id"],
        "amount_usd": plan["price_usd"],
        "paypal_email": email,
        "instructions": (
            "Send the exact amount via PayPal Friends & Family (no note). "
            "After sending, keep this page open — an admin will activate your plan."
        ),
        "status": order.status,
    }


@router.post("/crypto/checkout")
async def crypto_checkout(
    body: CryptoCheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = _get_plan(body.plan_id)
    addr_map = {
        "BTC": settings.crypto_btc_address,
        "ETH": settings.crypto_eth_address,
        "LTC": settings.crypto_ltc_address,
        "USDT": settings.crypto_usdt_address,
    }
    address = (addr_map.get(body.currency) or "").strip()
    if not address:
        raise HTTPException(
            503,
            f"{body.currency} address is not configured — set CRYPTO_{body.currency}_ADDRESS on the API.",
        )

    order = PaymentOrder(
        user_id=user.id,
        plan_id=plan["id"],
        method="crypto",
        status="awaiting_payment",
        amount_usd=str(plan["price_usd"]),
        currency=body.currency,
        sender_wallet=(body.sender_wallet or "").strip() or None,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "order_id": order.id,
        "plan_id": plan["id"],
        "amount_usd": plan["price_usd"],
        "currency": body.currency,
        "address": address,
        "status": order.status,
        "instructions": (
            f"Send the USD-equivalent in {body.currency} to the address below. "
            "Then paste your transaction hash to confirm."
        ),
    }


@router.post("/crypto/confirm")
async def crypto_confirm(
    body: CryptoConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentOrder).where(
            PaymentOrder.id == body.order_id, PaymentOrder.user_id == user.id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.method != "crypto":
        raise HTTPException(400, "Not a crypto order")
    if order.status == "completed":
        return {
            "status": order.status,
            "order_id": order.id,
            "message": "Plan already activated",
            "verified": True,
        }

    tx_hash = body.tx_hash.strip()
    order.tx_hash = tx_hash
    await db.commit()

    try:
        expected = float(order.amount_usd)
    except (TypeError, ValueError):
        expected = 0.0

    verification = await verify_crypto_payment(
        currency=order.currency or "USDT",
        tx_hash=tx_hash,
        expected_usd=expected,
    )

    if verification.status == "pending":
        order.status = "pending_confirmations"
        order.note = verification.message
        await db.commit()
        return {
            "status": order.status,
            "order_id": order.id,
            "verified": False,
            "pending": True,
            "message": verification.message,
        }

    if not verification.ok:
        order.status = "failed_verification"
        order.note = verification.message
        await db.commit()
        raise HTTPException(400, verification.message)

    order.note = verification.message
    if settings.crypto_auto_activate or settings.billing_auto_activate:
        await _activate_verified_crypto(db, order, user)
        await db.refresh(order)
        return {
            "status": order.status,
            "order_id": order.id,
            "verified": True,
            "message": "Payment verified on-chain — plan activated",
        }

    order.status = "pending_review"
    await db.commit()
    return {
        "status": order.status,
        "order_id": order.id,
        "verified": True,
        "message": "Payment verified on-chain — awaiting admin activation",
    }


@router.post("/paypal/confirm")
async def paypal_confirm(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentOrder).where(PaymentOrder.id == order_id, PaymentOrder.user_id == user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.method != "paypal":
        raise HTTPException(400, "Not a PayPal order")
    # PayPal Friends & Family cannot be verified automatically — manual admin review only.
    order.status = "pending_review"
    order.note = "PayPal F&F — manual review required"
    await db.commit()
    await _maybe_auto_activate(db, order, user)
    await db.refresh(order)
    return {
        "status": order.status,
        "order_id": order.id,
        "message": "Payment marked as sent — an admin will activate your plan",
        "verified": False,
    }


def _require_admin(user: User) -> None:
    if not is_admin(user):
        raise HTTPException(403, "Admin only")


@router.get("/admin/orders")
async def admin_list_orders(
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    query = select(PaymentOrder).order_by(PaymentOrder.id.desc()).limit(100)
    if status:
        query = select(PaymentOrder).where(PaymentOrder.status == status).order_by(
            PaymentOrder.id.desc()
        ).limit(100)
    result = await db.execute(query)
    orders = result.scalars().all()
    user_ids = {o.user_id for o in orders}
    users_by_id: dict[int, User] = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    return {
        "orders": [
            {
                "id": o.id,
                "user_id": o.user_id,
                "username": users_by_id[o.user_id].username if o.user_id in users_by_id else None,
                "plan_id": o.plan_id,
                "method": o.method,
                "status": o.status,
                "amount_usd": o.amount_usd,
                "currency": o.currency,
                "tx_hash": o.tx_hash,
                "sender_wallet": o.sender_wallet,
                "note": o.note,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]
    }


@router.post("/admin/activate")
async def admin_activate(
    order_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)

    result = await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status == "completed":
        return {"ok": True, "already": True, "order_id": order.id}
    plan = _get_plan(order.plan_id)
    buyer = await db.get(User, order.user_id)
    if not buyer:
        raise HTTPException(404, "User not found")
    await activate_plan(db, buyer, rank=plan["rank"], duration_days=plan["duration_days"])
    order.status = "completed"
    await record_admin_action(
        db,
        actor=user,
        action="activate_order",
        target_user_id=buyer.id,
        target_username=buyer.username,
        detail=f"Activated order #{order.id} ({order.plan_id})",
        meta={
            "order_id": order.id,
            "plan_id": order.plan_id,
            "method": order.method,
            "amount_usd": order.amount_usd,
        },
        actor_ip=client_ip(request),
        commit=False,
    )
    await db.commit()
    return {"ok": True, "user_id": buyer.id, "username": buyer.username, "rank": buyer.rank}


@router.post("/admin/reject")
async def admin_reject(
    order_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(user)
    result = await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    buyer = await db.get(User, order.user_id)
    order.status = "rejected"
    await record_admin_action(
        db,
        actor=user,
        action="reject_order",
        target_user_id=order.user_id,
        target_username=buyer.username if buyer else None,
        detail=f"Rejected order #{order.id} ({order.plan_id})",
        meta={
            "order_id": order.id,
            "plan_id": order.plan_id,
            "method": order.method,
            "amount_usd": order.amount_usd,
        },
        actor_ip=client_ip(request),
        commit=False,
    )
    await db.commit()
    return {"ok": True, "order_id": order.id, "status": order.status}

