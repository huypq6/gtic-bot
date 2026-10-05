"""Exchange connection check (docs/09): everything a TESTNET/LIVE account needs before bots trade.

Each check → {key, label, status: ok|warn|fail, detail, fix}. Read-only, except one auto-fix
on TESTNET only: hedge (dual-side) position mode → one-way. LIVE account settings are never
changed by the app; the check only tells you what to change on Binance.
"""

from app.config import Settings, settings

MAX_DRIFT_MS = 1000  # Binance recvWindow is 5000 ms; warn well before that


def _c(key: str, label: str, status: str, detail: str = "", fix: str = "") -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail, "fix": fix}


def _err(e: Exception) -> str:
    code = getattr(e, "code", None)
    msg = getattr(e, "message", None) or str(e)
    return f"{msg} (code {code})" if code is not None else msg


def _key_fix(e: Exception, mode: str) -> str:
    code = getattr(e, "code", None)
    env = "BINANCE_TESTNET_KEY/SECRET" if mode == "TESTNET" else "BINANCE_KEY/SECRET"
    if code in (-2014, -2015, -1022):
        where = (
            "a Demo Trading key (demo.binance.com → API Management) — a normal Binance key, or a "
            "key from the other sandbox (BINANCE_TESTNET_ENDPOINT), is rejected"
            if mode == "TESTNET"
            else "a live key with 'Enable Futures' ticked and this server's IP whitelisted"
        )
        return f"Check {env} in .env: it must be {where}. Restart the app after editing .env."
    if code == -1021:
        return "Server clock is off — enable NTP time sync (timedatectl set-ntp true)."
    return f"Check {env} and network access to Binance, then restart the app."


async def run_checks(
    client, mode: str, symbols: list[str], *, fix: bool = True, s: Settings = settings
) -> list[dict]:
    """`client` = BinanceFuturesClient (or a fake with the same methods)."""
    out: list[dict] = []
    endpoint = client.base_url
    out.append(_c("endpoint", "Endpoint", "ok", endpoint))

    # 1. connectivity + clock
    try:
        drift = await client.server_time_offset_ms()
    except Exception as e:  # noqa: BLE001
        out.append(_c("connect", "Connect to Binance", "fail", _err(e),
                      "This server cannot reach Binance (firewall/DNS/proxy?)."))
        return out
    st = "ok" if abs(drift) <= MAX_DRIFT_MS else "warn"
    out.append(_c("clock", "Clock drift", st, f"{drift:+d} ms vs exchange",
                  "" if st == "ok" else "Enable NTP time sync on this machine."))

    # 2. key + trading permission + balance
    try:
        acc = await client.raw_account()
    except Exception as e:  # noqa: BLE001
        out.append(_c("auth", "API key", "fail", _err(e), _key_fix(e, mode)))
        return out
    out.append(_c("auth", "API key", "ok", "signed request accepted"))
    if acc.get("canTrade") is False:
        out.append(_c("trade", "Trading permission", "fail", "canTrade = false",
                      "Edit the API key on Binance: tick 'Enable Futures'."))
    else:
        out.append(_c("trade", "Trading permission", "ok", "Futures trading enabled"))
    assets = {a.get("asset"): a for a in acc.get("assets", [])}
    usdt = float((assets.get("USDT") or {}).get("availableBalance") or 0)
    wallet = float(acc.get("totalWalletBalance") or 0)
    if usdt > 0:
        out.append(_c("balance", "USDT balance", "ok",
                      f"available {usdt:,.2f} USDT · wallet {wallet:,.2f}"))
    else:
        out.append(_c("balance", "USDT balance", "fail", "no available USDT in the Futures wallet",
                      "Demo Trading: use the balance reset / faucet on demo.binance.com."
                      if mode == "TESTNET"
                      else "Transfer USDT from Spot to the USDⓈ-M Futures wallet."))

    # 3. position mode — the app assumes one-way (one position per symbol)
    try:
        hedge = await client.hedge_mode()
        if hedge and mode == "TESTNET" and fix:
            try:
                await client.set_one_way()
                out.append(_c("posmode", "Position mode", "ok",
                              "was Hedge → switched to One-way automatically"))
            except Exception as e:  # noqa: BLE001 — e.g. -4068 open positions/orders exist
                out.append(_c("posmode", "Position mode", "fail", f"Hedge mode; {_err(e)}",
                              "Close all positions/orders, then set One-way mode in "
                              "Futures → Preferences → Position Mode."))
        elif hedge:
            out.append(_c("posmode", "Position mode", "fail", "Hedge mode",
                          "Set One-way mode on Binance: Futures → Preferences → Position Mode. "
                          "(The app never changes LIVE account settings.)"))
        else:
            out.append(_c("posmode", "Position mode", "ok", "One-way"))
    except Exception as e:  # noqa: BLE001
        out.append(_c("posmode", "Position mode", "warn", _err(e),
                      "Could not read; check manually."))

    try:
        if await client.multi_assets_mode():
            out.append(_c("multiasset", "Multi-assets mode", "warn", "on",
                          "Turn it off (Single-asset mode) so the USDT ledger matches the wallet."))
        else:
            out.append(_c("multiasset", "Multi-assets mode", "ok", "off (single-asset)"))
    except Exception as e:  # noqa: BLE001
        out.append(_c("multiasset", "Multi-assets mode", "warn", _err(e)))

    # 4. symbols the bots use must exist on this exchange
    try:
        listed = await client.listed()
        missing = sorted(x for x in set(symbols) if x not in listed)
        if missing:
            out.append(_c("symbols", "Symbols", "warn", "not listed: " + ", ".join(missing),
                          "Bots on these symbols cannot trade in this mode."))
        else:
            out.append(_c("symbols", "Symbols", "ok", f"{len(set(symbols))} checked, all listed"))
    except Exception as e:  # noqa: BLE001
        out.append(_c("symbols", "Symbols", "warn", _err(e)))
    return out


def overall(checks: list[dict]) -> str:
    st = {c["status"] for c in checks}
    return "fail" if "fail" in st else "warn" if "warn" in st else "ok"
