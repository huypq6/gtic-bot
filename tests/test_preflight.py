"""Exchange connection check (docs/09): statuses, fixes, TESTNET-only auto-fix of hedge mode."""

from app.execution.preflight import overall, run_checks


class ApiErr(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


class Fake:
    base_url = "https://demo-fapi.binance.com/fapi"

    def __init__(self, *, drift=10, acc=None, auth_err=None, hedge=False, one_way_err=None,
                 multi=False, listed=("BTCUSDT", "ETHUSDT")):
        self.drift, self.auth_err, self.hedge = drift, auth_err, hedge
        self.one_way_err, self.multi, self._listed = one_way_err, multi, set(listed)
        self.acc = acc or {"canTrade": True, "totalWalletBalance": "5000",
                           "assets": [{"asset": "USDT", "availableBalance": "4900"}]}
        self.switched = False

    async def server_time_offset_ms(self):
        return self.drift

    async def raw_account(self):
        if self.auth_err:
            raise self.auth_err
        return self.acc

    async def hedge_mode(self):
        return self.hedge

    async def set_one_way(self):
        if self.one_way_err:
            raise self.one_way_err
        self.switched, self.hedge = True, False

    async def multi_assets_mode(self):
        return self.multi

    async def listed(self):
        return self._listed


def by_key(checks):
    return {c["key"]: c for c in checks}


async def test_all_ok():
    checks = await run_checks(Fake(), "TESTNET", ["BTCUSDT"])
    assert overall(checks) == "ok"
    assert by_key(checks)["balance"]["detail"].startswith("available 4,900.00")


async def test_bad_key_stops_with_fix():
    f = Fake(auth_err=ApiErr(-2015, "Invalid API-key, IP, or permissions for action."))
    c = by_key(await run_checks(f, "TESTNET", ["BTCUSDT"]))
    assert c["auth"]["status"] == "fail"
    assert "demo.binance.com" in c["auth"]["fix"]
    assert "posmode" not in c  # nothing after a failed auth


async def test_hedge_mode_auto_fixed_on_testnet_only():
    f = Fake(hedge=True)
    c = by_key(await run_checks(f, "TESTNET", ["BTCUSDT"]))
    assert f.switched and c["posmode"]["status"] == "ok"

    f = Fake(hedge=True)
    c = by_key(await run_checks(f, "LIVE", ["BTCUSDT"]))
    assert not f.switched  # never touches LIVE account settings
    assert c["posmode"]["status"] == "fail"


async def test_hedge_switch_rejected_when_positions_open():
    f = Fake(hedge=True, one_way_err=ApiErr(-4068, "Position side cannot be changed"))
    c = by_key(await run_checks(f, "TESTNET", ["BTCUSDT"]))
    assert c["posmode"]["status"] == "fail" and "-4068" in c["posmode"]["detail"]


async def test_warnings_drift_multiasset_symbols_and_empty_balance():
    f = Fake(drift=2500, multi=True,
             acc={"canTrade": True, "totalWalletBalance": "0", "assets": []})
    checks = await run_checks(f, "TESTNET", ["BTCUSDT", "FOOUSDT"])
    c = by_key(checks)
    assert c["clock"]["status"] == "warn"
    assert c["multiasset"]["status"] == "warn"
    assert c["symbols"]["status"] == "warn" and "FOOUSDT" in c["symbols"]["detail"]
    assert c["balance"]["status"] == "fail"
    assert overall(checks) == "fail"


async def test_testnet_client_switches_to_one_way_on_connect():
    from app.execution.clients import _testnet_one_way

    f = Fake(hedge=True)
    await _testnet_one_way(f)
    assert f.switched
    f = Fake(hedge=True, one_way_err=ApiErr(-4068, "Position side cannot be changed"))
    await _testnet_one_way(f)  # logged, never raises
