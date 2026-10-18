"""On-chain crypto payment verification (BTC / LTC / ETH / USDT-ERC20).

Uses public Blockchair + public Ethereum JSON-RPC / Blockscout-style explorers.
No API keys required for basic verification. Amounts are checked with a tolerance
because users send USD-equivalent at spot rate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Accept payments within ±12% of expected USD (spot rate drift + fees)
AMOUNT_TOLERANCE = 0.12
MIN_CONFIRMATIONS = {
    "BTC": 1,
    "LTC": 1,
    "ETH": 1,
    "USDT": 1,
}


@dataclass
class VerifyResult:
    ok: bool
    status: str  # verified | pending | failed
    message: str
    amount_received: float | None = None
    confirmations: int | None = None
    details: dict[str, Any] | None = None


async def _get_json(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        res = await client.get(url, headers={"User-Agent": "UserSniperBilling/1.0"})
        res.raise_for_status()
        data = res.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected JSON response")
        return data


async def _usd_price(symbol: str) -> float:
    """Spot USD price via CoinGecko (no key)."""
    ids = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "LTC": "litecoin",
        "USDT": "tether",
    }
    coin_id = ids.get(symbol.upper())
    if not coin_id:
        raise ValueError(f"Unsupported symbol: {symbol}")
    if symbol.upper() == "USDT":
        return 1.0
    data = await _get_json(
        f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
    )
    price = float(data[coin_id]["usd"])
    if price <= 0:
        raise ValueError("Invalid spot price")
    return price


def _amount_ok(received_usd: float, expected_usd: float) -> bool:
    if expected_usd <= 0:
        return received_usd > 0
    low = expected_usd * (1 - AMOUNT_TOLERANCE)
    return received_usd >= low


async def _verify_utxo(
    *,
    chain: str,
    tx_hash: str,
    expected_address: str,
    expected_usd: float,
    symbol: str,
) -> VerifyResult:
    url = f"https://api.blockchair.com/{chain}/dashboards/transaction/{tx_hash}"
    try:
        data = await _get_json(url)
    except Exception as exc:
        logger.warning("blockchair %s lookup failed: %s", chain, exc)
        return VerifyResult(False, "pending", f"Could not reach {chain} explorer — try again shortly")

    payload = (data.get("data") or {}).get(tx_hash) or (data.get("data") or {}).get(tx_hash.lower())
    if not payload:
        return VerifyResult(False, "failed", "Transaction not found on-chain")

    outputs = payload.get("outputs") or []
    target = expected_address.strip().lower()
    received_sats = 0
    for out in outputs:
        addr = (out.get("recipient") or out.get("address") or "").strip().lower()
        if addr == target:
            received_sats += int(out.get("value") or 0)

    if received_sats <= 0:
        return VerifyResult(
            False,
            "failed",
            f"No output to our {symbol} address in this transaction",
        )

    received_coin = received_sats / 1e8
    try:
        price = await _usd_price(symbol)
    except Exception as exc:
        logger.warning("price lookup failed: %s", exc)
        return VerifyResult(False, "pending", "Could not fetch spot price — try again shortly")

    received_usd = received_coin * price
    conf = int((payload.get("transaction") or {}).get("block_id") or 0)
    # Blockchair uses block_id = -1 for unconfirmed txs — must not count as confirmed.
    confirmations = 1 if conf >= 1 else 0
    if confirmations < MIN_CONFIRMATIONS.get(symbol, 1):
        return VerifyResult(
            False,
            "pending",
            "Transaction seen but not confirmed yet",
            amount_received=received_usd,
            confirmations=confirmations,
        )

    if not _amount_ok(received_usd, expected_usd):
        return VerifyResult(
            False,
            "failed",
            f"Amount too low (~${received_usd:.2f} received, expected ~${expected_usd:.2f})",
            amount_received=received_usd,
            confirmations=confirmations,
        )

    return VerifyResult(
        True,
        "verified",
        f"Payment verified on {symbol} (~${received_usd:.2f})",
        amount_received=received_usd,
        confirmations=confirmations,
    )


async def _verify_eth_native(
    *,
    tx_hash: str,
    expected_address: str,
    expected_usd: float,
) -> VerifyResult:
    url = f"https://api.blockchair.com/ethereum/dashboards/transaction/{tx_hash}"
    try:
        data = await _get_json(url)
    except Exception as exc:
        logger.warning("blockchair eth lookup failed: %s", exc)
        return VerifyResult(False, "pending", "Could not reach Ethereum explorer — try again shortly")

    payload = (data.get("data") or {}).get(tx_hash) or (data.get("data") or {}).get(tx_hash.lower())
    if not payload:
        return VerifyResult(False, "failed", "Transaction not found on-chain")

    tx = payload.get("transaction") or {}
    recipient = (tx.get("recipient") or tx.get("to") or "").strip().lower()
    if recipient != expected_address.strip().lower():
        return VerifyResult(False, "failed", "ETH was not sent to our wallet address")

    # value is in wei
    value_wei = int(tx.get("value") or 0)
    received_eth = value_wei / 1e18
    if received_eth <= 0:
        return VerifyResult(False, "failed", "Transaction has zero ETH value (maybe a token transfer?)")

    try:
        price = await _usd_price("ETH")
    except Exception:
        return VerifyResult(False, "pending", "Could not fetch ETH price — try again shortly")

    received_usd = received_eth * price
    block_id = int(tx.get("block_id") or 0)
    confirmations = 1 if block_id >= 1 else 0
    if confirmations < 1:
        return VerifyResult(
            False,
            "pending",
            "Transaction seen but not confirmed yet",
            amount_received=received_usd,
            confirmations=0,
        )

    if not _amount_ok(received_usd, expected_usd):
        return VerifyResult(
            False,
            "failed",
            f"Amount too low (~${received_usd:.2f} received, expected ~${expected_usd:.2f})",
            amount_received=received_usd,
            confirmations=confirmations,
        )

    return VerifyResult(
        True,
        "verified",
        f"Payment verified on ETH (~${received_usd:.2f})",
        amount_received=received_usd,
        confirmations=confirmations,
    )


# Tether USD (USDT) ERC-20 on Ethereum mainnet
USDT_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"


async def _verify_usdt_erc20(
    *,
    tx_hash: str,
    expected_address: str,
    expected_usd: float,
) -> VerifyResult:
    """Verify USDT ERC-20 transfer via Blockchair Ethereum token calls / eth_getTransactionReceipt via public RPC."""
    # Use public Ethereum RPC for receipt logs
    rpc_urls = [
        "https://eth.llamarpc.com",
        "https://rpc.ankr.com/eth",
        "https://ethereum.publicnode.com",
    ]
    receipt = None
    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=20.0) as client:
        for rpc in rpc_urls:
            try:
                res = await client.post(
                    rpc,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_getTransactionReceipt",
                        "params": [tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"],
                    },
                )
                res.raise_for_status()
                body = res.json()
                receipt = body.get("result")
                if receipt:
                    break
            except Exception as exc:
                last_err = exc
                continue

    if not receipt:
        msg = "USDT transaction not found yet"
        if last_err:
            msg = f"Could not query Ethereum RPC ({last_err})"
        return VerifyResult(False, "pending", msg)

    if int(receipt.get("status") or "0x0", 16) != 1:
        return VerifyResult(False, "failed", "Transaction failed on-chain")

    # Transfer(address,address,uint256) topic
    transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    target = expected_address.strip().lower().replace("0x", "")
    contract = USDT_CONTRACT.lower()
    received = 0

    for log in receipt.get("logs") or []:
        if (log.get("address") or "").lower() != contract:
            continue
        topics = log.get("topics") or []
        if not topics or topics[0].lower() != transfer_topic:
            continue
        if len(topics) < 3:
            continue
        to_addr = topics[2].lower().replace("0x", "")[-40:]
        if to_addr != target:
            continue
        raw = log.get("data") or "0x0"
        received += int(raw, 16)

    # USDT has 6 decimals
    received_usdt = received / 1e6
    if received_usdt <= 0:
        return VerifyResult(False, "failed", "No USDT transfer to our address in this transaction")

    received_usd = received_usdt  # ~1:1
    if not _amount_ok(received_usd, expected_usd):
        return VerifyResult(
            False,
            "failed",
            f"Amount too low (~${received_usd:.2f} USDT, expected ~${expected_usd:.2f})",
            amount_received=received_usd,
            confirmations=1,
        )

    return VerifyResult(
        True,
        "verified",
        f"Payment verified on USDT (~${received_usd:.2f})",
        amount_received=received_usd,
        confirmations=1,
    )


async def verify_crypto_payment(
    *,
    currency: str,
    tx_hash: str,
    expected_usd: float,
) -> VerifyResult:
    currency = (currency or "").upper().strip()
    tx_hash = (tx_hash or "").strip()
    if len(tx_hash) < 8:
        return VerifyResult(False, "failed", "Invalid transaction hash")

    addr_map = {
        "BTC": settings.crypto_btc_address,
        "ETH": settings.crypto_eth_address,
        "LTC": settings.crypto_ltc_address,
        "USDT": settings.crypto_usdt_address,
    }
    expected_address = (addr_map.get(currency) or "").strip()
    if not expected_address:
        return VerifyResult(False, "failed", f"{currency} receive address is not configured")

    if currency == "BTC":
        return await _verify_utxo(
            chain="bitcoin",
            tx_hash=tx_hash,
            expected_address=expected_address,
            expected_usd=expected_usd,
            symbol="BTC",
        )
    if currency == "LTC":
        return await _verify_utxo(
            chain="litecoin",
            tx_hash=tx_hash,
            expected_address=expected_address,
            expected_usd=expected_usd,
            symbol="LTC",
        )
    if currency == "ETH":
        return await _verify_eth_native(
            tx_hash=tx_hash,
            expected_address=expected_address,
            expected_usd=expected_usd,
        )
    if currency == "USDT":
        return await _verify_usdt_erc20(
            tx_hash=tx_hash,
            expected_address=expected_address,
            expected_usd=expected_usd,
        )
    return VerifyResult(False, "failed", f"Unsupported currency: {currency}")
