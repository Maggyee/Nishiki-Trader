"""LiveClock full-account testnet bootstrap and callback qualification, GET-only.

A probe cannot prepare, dispatch or cancel an order. It exercises actual clocks,
source-bound callbacks and native recovery without consuming the matching scope.
"""

from __future__ import annotations

import hashlib
import json
import threading
from decimal import Decimal as D
from types import SimpleNamespace

import msgspec
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.config import BinanceExecClientConfig
from nautilus_trader.adapters.binance.spot.execution import BinanceSpotExecutionClient
from nautilus_trader.adapters.binance.spot.providers import BinanceSpotInstrumentProvider
from nautilus_trader.adapters.binance.spot.schemas.market import BinanceSpotSymbolInfo
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.config import LiveExecEngineConfig, StrategyConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.live.execution_engine import LiveExecutionEngine
from nautilus_trader.model.enums import AccountType, CurrencyType
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.identifiers import AccountId, TraderId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import AccountBalance, Currency, Money
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.trading.strategy import Strategy

from apps.strategies_nautilus.portfolio_session_account import SessionCashAccount
from apps.strategies_nautilus.portfolio_session_bridge import (
    SessionBinanceFixtureClient,
    SessionBridge,
)
from apps.strategies_nautilus.portfolio_session_ledger import (
    INSTRUMENT,
    SessionLedger,
    SessionLedgerError,
    balances,
)
from apps.strategies_nautilus.portfolio_session_recovery import recover_session
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_mapping import _map_observed_balances
from apps.strategies_nautilus.portfolio_testnet_observation import account_balances

RUNTIME_PROFILE = "testnet_liveclock_readonly_probe_v1"


class ReadOnlyRuntimeLedger(SessionLedger):
    """Explicit wall-clock profile; every order operation remains forbidden."""

    def _owner(self, owner):
        if (
            self._fd is None
            or self._poisoned
            or threading.get_ident() != self._thread
            or not isinstance(owner.clock, LiveClock)
        ):
            raise SessionLedgerError("healthy owning LiveClock probe writer required")
        if self.state is not None and owner.clock.timestamp_ns() < self.state["updated_ns"]:
            raise SessionLedgerError("probe clock regressed")

    def _started_ns(self, owner):
        started = owner.cache.accounts()[0].events[0].ts_event
        if not 0 <= owner.clock.timestamp_ns() - started <= 5_000_000_000:
            raise SessionLedgerError("fresh observed native baseline required")
        return started

    def _persist(self, owner):
        existing = self.state.get("runtime_profile")
        if existing is not None and existing != RUNTIME_PROFILE:
            raise SessionLedgerError("probe cannot convert another runtime profile")
        self.state["runtime_profile"] = RUNTIME_PROFILE
        super()._persist(owner)

    def _blocked(self, *args, **kwargs):
        raise SessionLedgerError("read-only probe cannot prepare, dispatch or cancel orders")

    prepare = _blocked
    prepare_cancel = _blocked
    record_dispatch = _blocked


class ReadOnlyRuntimeBridge(SessionBridge):
    def __init__(self, owner, ledger):
        if type(ledger) is not ReadOnlyRuntimeLedger:
            raise SessionLedgerError("explicit read-only runtime ledger required")
        ledger._owner(owner)
        self.owner, self.ledger = owner, ledger
        self.failed = False
        self.processing = False
        self.waiters = {}
        self.account_updates = []
        self.balance_history = [balances(owner.cache.accounts()[0])]

    def require_healthy(self):
        raise SessionLedgerError("read-only runtime has no order admission")

    def checkpoint(self):
        super().checkpoint()
        self.balance_history.append(balances(self.owner.cache.accounts()[0]))
        if len(self.balance_history) > 2048:
            self.fail("account_correlation_history_exceeded")
            raise StreamError("account correlation history bound exceeded")
        self._correlate()

    def account_update(self, event):
        if (
            type(event.get("u")) is not int
            or not 0 < event["u"] <= event["E"]
            or not isinstance(event.get("B"), list)
            or not event["B"]
        ):
            raise StreamError("invalid source-bound account update")
        rows = {}
        for row in event["B"]:
            asset = row["a"]
            free, locked = D(row["f"]), D(row["l"])
            if (
                asset in rows
                or asset not in self.ledger.state["baseline"]
                or not all(v.is_finite() and v >= 0 for v in (free, locked))
            ):
                raise StreamError("invalid or unknown account update asset")
            rows[asset] = (free, locked)
            if asset not in {"BTC", "USDT"} and rows[asset] != tuple(
                map(D, self.ledger.state["baseline"][asset])
            ):
                self.fail("unexplained_unrelated_asset_delta")
                raise StreamError("unrelated asset delta cannot be owned by session")
        self.account_updates.append(rows)
        if len(self.account_updates) > 2048:
            raise StreamError("unresolved account update bound exceeded")
        self._correlate()

    def _correlate(self):
        self.account_updates = [
            rows
            for rows in self.account_updates
            if not any(
                all(tuple(map(D, snapshot[asset])) == amounts for asset, amounts in rows.items())
                for snapshot in self.balance_history
            )
        ]

    def assert_account_correlated(self):
        self._correlate()
        if self.account_updates or self.failed or self.ledger.state["halt_reasons"]:
            self.fail("unresolved_account_update_or_native_halt")
            raise StreamError("account updates require complete native reconciliation")


class ReadOnlyRuntimeEngine(LiveExecutionEngine):
    def __init__(self, owner, bridge, loop):
        self.bridge = bridge
        if not isinstance(owner.clock, LiveClock):
            raise StreamError("explicit LiveClock probe required")
        super().__init__(
            loop=loop,
            msgbus=owner.msgbus,
            cache=owner.cache,
            clock=owner.clock,
            config=LiveExecEngineConfig(
                reconciliation=False, generate_missing_orders=False, inflight_check_interval_ms=0
            ),
        )

    def execute(self, command):
        raise StreamError("probe execution commands forbidden")

    def register_client(self, client):
        raise StreamError("probe execution clients forbidden")

    def _handle_event_with_tracking(self, event):
        self.bridge.processing = True
        try:
            super()._handle_event_with_tracking(event)
            self.bridge.checkpoint()
        except Exception:
            self.bridge.fail("native_probe_event_failure")
        finally:
            self.bridge.processing = False


class SessionEventReceiver(SessionBinanceFixtureClient):
    """Native callback parser with a GET-only client and no connected execution WS."""

    def __init__(self, owner, bridge, http, credentials, provider, loop):
        self.bridge = bridge
        BinanceSpotExecutionClient.__init__(
            self,
            loop=loop,
            client=http,
            msgbus=owner.msgbus,
            cache=owner.cache,
            clock=owner.clock,
            instrument_provider=provider,
            base_url_ws="wss://ws-api.testnet.binance.vision/ws-api/v3",
            config=BinanceExecClientConfig(max_retries=0, use_position_ids=True),
            environment=BinanceEnvironment.TESTNET,
            api_key=credentials.api_key,
            api_secret=credentials.private_key_pem,
        )
        self._set_account_id(owner.cache.accounts()[0].id)
        self._received_trades, self._received_totals, self._received_venue_ids = {}, {}, {}

    def receive(self, raw):
        self._handle_user_ws_message(raw)
        if self.bridge.failed:
            raise StreamError("native session execution callback rejected")


def build_observed_account(*, account, metadata_raw, binding, clock, http, profile=RUNTIME_PROFILE):
    """Construct a complete native account from selected fresh metadata and funds."""
    if not isinstance(clock, LiveClock):
        raise StreamError("LiveClock required for source-bound probe")
    observed_ns = clock.timestamp_ns()
    amounts = account_balances(account, binding.account_uid)
    metadata = json.loads(metadata_raw)
    if not 0 <= observed_ns - metadata["received_ns"] <= 60_000_000_000:
        raise StreamError("fresh full-account metadata required")
    mapping = _map_observed_balances(
        metadata_raw,
        expected_sha256=hashlib.sha256(metadata_raw).hexdigest(),
        balances=amounts,
        account_uid=binding.account_uid,
        observed_ns=observed_ns,
    )
    if not mapping["detached_native_account_balances_equal"]:
        raise StreamError("complete exact native asset mapping required")
    provider = BinanceSpotInstrumentProvider(
        client=http, clock=clock, environment=BinanceEnvironment.TESTNET
    )
    body = json.loads(metadata["response_body"])
    symbol = next(s for s in body["symbols"] if s["symbol"] == "BTCUSDT")
    parsed = msgspec.json.decode(canonical(symbol), type=BinanceSpotSymbolInfo)
    provider._parse_instrument(parsed, fee=None, ts_event=metadata["received_ns"])
    instrument = provider.find(INSTRUMENT)
    if instrument is None:
        raise StreamError("native BTCUSDT instrument parsing failed")
    fields = CurrencyPair.to_dict(instrument)
    # Accounting precision, not effective order sizing. Probe cannot submit.
    fields.update(size_precision=8, size_increment="0.00000001")
    instrument = CurrencyPair.from_dict(fields)
    cache = Cache()
    cache.add_instrument(instrument)
    native_balances = []
    for row in mapping["assets"]:
        asset = row["asset"]
        currency = Currency(asset, row["precision"], 0, asset, CurrencyType.CRYPTO)
        free, locked = amounts[asset]
        native_balances.append(
            AccountBalance(
                Money(free + locked, currency), Money(locked, currency), Money(free, currency)
            )
        )
    native = SessionCashAccount(
        AccountState(
            account_id=AccountId(f"BINANCE-{binding.account_uid}"),
            account_type=AccountType.CASH,
            base_currency=None,
            balances=native_balances,
            margins=[],
            reported=False,
            info={"profile": profile, "observed_source": True, "trading_enabled": False},
            event_id=UUID4(),
            ts_event=observed_ns,
            ts_init=observed_ns,
        ),
        cache=cache,
    )
    cache.add_account(native)
    bus = MessageBus(trader_id=TraderId("BACKTESTER-001"), clock=clock)
    portfolio = Portfolio(msgbus=bus, cache=cache, clock=clock)
    owner = SimpleNamespace(cache=cache, clock=clock, msgbus=bus, portfolio=portfolio)
    return owner, provider


def bootstrap_probe(
    *, account, metadata_raw, binding, path, clock, http, credentials, loop, session_id
):
    owner, provider = build_observed_account(
        account=account, metadata_raw=metadata_raw, binding=binding, clock=clock, http=http
    )
    ledger = ReadOnlyRuntimeLedger(path).create(owner, session_id=session_id, source=binding)
    owner.ledger = ledger
    owner.bridge = ReadOnlyRuntimeBridge(owner, ledger)
    owner.engine = ReadOnlyRuntimeEngine(owner, owner.bridge, loop)
    owner.engine.register_oms_type(
        Strategy(
            StrategyConfig(strategy_id="TESTNET-SESSION", order_id_tag="TS", oms_type="HEDGING")
        )
    )
    owner.receiver = SessionEventReceiver(owner, owner.bridge, http, credentials, provider, loop)
    owner.portfolio.initialize_orders()
    owner.portfolio.initialize_positions()
    owner.engine.start()
    return owner


def reconcile_collected(raw, receipt, journal, *, loop):
    """Keep actual source/fence checks around detached native numerical recovery."""
    selected = hashlib.sha256(raw).hexdigest()
    receipt.assert_current(journal, selected)
    result = recover_session(
        raw,
        canonical(receipt.evidence),
        expected_sha256=selected,
        evidence_sha256=receipt.evidence_sha256,
        now_ns=journal.clock_ns(),
        loop=loop,
    )
    receipt.assert_current(journal, selected)
    return result | {
        "signed_source_bound": True,
        "collection_id": receipt.collection_id,
        "stream_epoch": receipt.fence.epoch,
        "global_stream_continuity_verified": False,
        "runtime_ready": False,
        "matching_enabled": False,
    }
