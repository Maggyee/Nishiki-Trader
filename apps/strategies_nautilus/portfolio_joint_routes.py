"""Original-input route fixation and dispatch budgets for loopback acceptance.

This separate profile never accepts the old synthetic journal as source evidence.
Logical Binance selectors are exercised only against explicit local fixture peers.
"""

from __future__ import annotations

from collections import deque
from urllib.parse import urlsplit

from apps.strategies_nautilus.portfolio_joint_observation import (
    DESIGN_SHA256,
    JointEvidence,
    digest,
)
from apps.strategies_nautilus.portfolio_market_depth import (
    MAX_FRAME,
    REST,
    SECOND,
    DepthBook,
    DepthError,
    integer,
)
from apps.strategies_nautilus.portfolio_market_depth_archive import decode
from apps.strategies_nautilus.portfolio_observation_plan import PILOT_ASSETS, request_budget
from apps.strategies_nautilus.portfolio_testnet_observation import account_balances
from apps.strategies_nautilus.portfolio_testnet_valuation import indicative_valuation

PROFILE = "portfolio.loopback_joint_observation.v1"


def loopback_url(url, scheme):
    parsed = urlsplit(url)
    if (
        parsed.scheme != scheme
        or parsed.hostname != "127.0.0.1"
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise DepthError("explicit_loopback_endpoint_required")
    return f"{scheme}://127.0.0.1:{parsed.port}"


def selected_initial(raw, expected_sha256):
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= 8 * MAX_FRAME
        or digest(raw) != expected_sha256
    ):
        raise DepthError("joint_initial_selection_changed")
    wrapped = decode(raw)
    if (
        wrapped["schema_version"] != "portfolio.testnet_initial_account_observation.v1"
        or wrapped["endpoint"] != REST
        or wrapped["path"] != "/api/v3/account"
        or digest(wrapped["response_body"].encode()) != wrapped["response_sha256"]
    ):
        raise DepthError("joint_initial_source_mismatch")
    key = wrapped["key_sha256"]
    if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise DepthError("joint_selected_key_digest_required")
    account = decode(wrapped["response_body"].encode())
    account_balances(account, str(account["uid"]))
    return {"endpoint": REST, "account_uid": str(account["uid"]), "key_sha256": key}, account


class RoutedJointEvidence(JointEvidence):
    profile = PROFILE

    def __init__(self):
        super().__init__()
        self.routes = None
        self.prepared = None
        self.prepared_count = 0
        self.usage = self.usage_ns = None
        self.connection_attempts = None
        self.raw_account_responses = []
        self.ws_response_ids = set()
        self.account_controls = deque()
        self.account_pongs = 0

    def validate_manifest(self, manifest):
        source, account = selected_initial(
            manifest["initial_raw"].encode(), manifest["initial_sha256"]
        )
        if (
            manifest["synthetic"] is not True
            or manifest["transport_scope"] != "loopback_only"
            or manifest["design_sha256"] != DESIGN_SHA256
            or manifest["source"] != source
            or manifest["initial_account"] != account
            or manifest["symbols"] != []
        ):
            raise DepthError("joint_loopback_manifest_required")
        for name, scheme in (("http", "http"), ("account", "ws"), ("market", "ws")):
            loopback_url(manifest["wire_endpoints"][name], scheme)
        if any(
            not isinstance(manifest[k], str) or not manifest[k]
            for k in ("account_epoch", "market_epoch")
        ):
            raise DepthError("joint_epoch_required")
        if manifest["account_epoch"] == manifest["market_epoch"]:
            raise DepthError("joint_independent_epochs_required")
        integer(manifest["subscription_id"])
        budget = manifest["budget_sample"]
        if budget["scope"] != "loopback_peer_shared_usage_fixture":
            raise DepthError("joint_budget_fixture_required")
        for key in ("observed_ns", "weight_limit", "connection_limit"):
            integer(budget[key], positive=True)
        self.usage = integer(budget["used_weight"])
        self.connection_attempts = integer(budget["connection_attempts"])
        self.usage_ns = budget["observed_ns"]
        if budget["weight_limit"] != 6000 or budget["connection_limit"] != 300:
            raise DepthError("joint_budget_limits_changed")

    def next_operation(self):
        if self.request_index == 1 and self.ws_index < 2:
            return {"kind": "ws", **self.budget["ws_api_operations"][self.ws_index]}
        if self.request_index == 7 and not self.market_connected:
            return {"kind": "market_connection", "weight": 0}
        if self.request_index < len(self.budget["rest_requests"]):
            return {"kind": "rest", **self.budget["rest_requests"][self.request_index]}
        if self.ws_index == 2:
            return {"kind": "ws", **self.budget["ws_api_operations"][2]}
        raise DepthError("joint_operation_scope_consumed")

    def extra_receipt(self, row):
        if row["kind"] == "account_pong":
            import base64

            raw = base64.b64decode(row["payload_b64"], validate=True)
            if (
                self.ws_index < 1  # Transport pings can precede subscription acknowledgement.
                or self.account_closed
                or row["epoch"] != self.manifest["account_epoch"]
                or len(raw) > 125
                or row["payload_b64"] != row["echo_b64"]
            ):
                raise DepthError("joint_account_control_invalid")
            mono = row["monotonic_ns"]
            while self.account_controls and mono - self.account_controls[0] >= SECOND:
                self.account_controls.popleft()
            if len(self.account_controls) >= 5:
                raise DepthError("joint_account_control_limit")
            self.account_controls.append(mono)
            self.account_pongs += 1
            return
        if row["kind"] != "operation_prepared" or self.prepared is not None:
            raise DepthError("joint_unexpected_or_repeated_preparation")
        operation = self.next_operation()
        now = row["received_ns"]
        sample = self.manifest["budget_sample"]
        if (
            row["operation"] != operation
            or type(row["operation_id"]) is not int
            or row["operation_id"] != self.prepared_count
            or not 0 <= now - self.usage_ns <= 5 * SECOND
            or now // (60 * SECOND) != sample["observed_ns"] // (60 * SECOND)
            or now // (300 * SECOND) != sample["observed_ns"] // (300 * SECOND)
        ):
            raise DepthError("joint_dispatch_usage_or_selection_invalid")
        remaining = sum(r["weight"] for r in self.budget["rest_requests"][self.request_index :])
        remaining += sum(r["weight"] for r in self.budget["ws_api_operations"][self.ws_index :])
        if self.routes is None:
            remaining += 15  # Reserve three depth GETs before the route union is known.
        connections_left = int(self.ws_index == 0) + int(not self.market_connected)
        if (
            self.usage + remaining > sample["weight_limit"]
            or self.connection_attempts + connections_left > sample["connection_limit"]
        ):
            raise DepthError("joint_dispatch_budget_exhausted")
        if (
            operation["kind"] == "market_connection"
            or operation.get("operation") == "ws_api_connection"
        ):
            self.connection_attempts += 1
        self.usage += operation["weight"]
        self.prepared = row
        self.prepared_count += 1

    def _consume(self, row, kind):
        prepared = self.prepared
        if (
            prepared is None
            or prepared["operation"]["kind"] != kind
            or row["operation_id"] != prepared["operation_id"]
            or type(row["operation_id"]) is not int
            or not 0 <= row["monotonic_ns"] - prepared["monotonic_ns"] <= 10 * SECOND
        ):
            raise DepthError("joint_prepared_operation_required")
        if kind == "rest":
            if any(
                row[k] != prepared["operation"][k] for k in ("phase", "method", "path", "params")
            ):
                raise DepthError("joint_prepared_selector_changed")
            if (
                row["sent_ns"] < prepared["received_ns"]
                or row["sent_monotonic_ns"] < prepared["monotonic_ns"]
            ):
                raise DepthError("joint_send_precedes_durable_preparation")
        elif kind == "ws" and row["operation"] != prepared["operation"]["operation"]:
            raise DepthError("joint_prepared_ws_changed")
        self.prepared = None

    def _feed(self, row, processed_ns, processed_mono):
        kind = row["kind"]
        if kind == "account_wire":
            body, _ = self._body(row, MAX_FRAME)
            if "id" in body:
                if self.prepared is None or self.prepared["operation"]["kind"] != "ws":
                    raise DepthError("joint_unsolicited_account_response")
                row = {
                    **row,
                    "kind": "ws_operation",
                    "operation": self.prepared["operation"]["operation"],
                    "operation_id": self.prepared["operation_id"],
                    "status": body.get("status"),
                    "request_id": self.prepared["request_id"],
                    "subscription_id": self.manifest["subscription_id"],
                }
            else:
                row = {**row, "kind": "account_frame"}
            kind = row["kind"]
        if kind == "ws_operation":
            self._consume(row, "ws")
            if row["operation"] != "ws_api_connection":
                body, _ = self._body(row, MAX_FRAME)
                request_id = body.get("id")
                expected = (
                    {"subscriptionId": self.manifest["subscription_id"]}
                    if row["operation"] == "userDataStream.subscribe.signature"
                    else {}
                )
                if (
                    not isinstance(request_id, str)
                    or request_id in self.ws_response_ids
                    or request_id != row["request_id"]
                    or type(body.get("status")) is not int
                    or body["status"] != 200
                    or body.get("result") != expected
                    or "error" in body
                    or "event" in body
                ):
                    raise DepthError("joint_ws_acknowledgement_invalid")
                self.ws_response_ids.add(request_id)
                limits = [
                    r
                    for r in body["rateLimits"]
                    if r["rateLimitType"] == "REQUEST_WEIGHT"
                    and r["interval"] == "MINUTE"
                    and r["intervalNum"] == 1
                ]
                if (
                    len(limits) != 1
                    or limits[0]["limit"] != self.manifest["budget_sample"]["weight_limit"]
                ):
                    raise DepthError("joint_ws_usage_missing")
                self.observe_usage(limits[0]["count"], row["received_ns"])
        elif kind == "market_connected":
            if self.routes is None:
                raise DepthError("joint_frozen_routes_required")
            self._consume(row, "market_connection")
        elif kind == "completed" and (self.routes is None or self.prepared is not None):
            raise DepthError("joint_unfinished_dispatch_or_routes")
        super()._feed(row, processed_ns, processed_mono)

    def observe_usage(self, value, now):
        if integer(value) < self.usage:
            raise DepthError("joint_usage_regressed_or_incomplete")
        if now // (60 * SECOND) != self.manifest["budget_sample"]["observed_ns"] // (60 * SECOND):
            raise DepthError("joint_usage_window_changed")
        self.usage, self.usage_ns = value, now

    def _response(self, row, processed_ns):
        self._consume(row, "rest")
        self.observe_usage(row["used_weight_1m"], row["received_ns"])
        if row["phase"] == "account_before":
            self.raw_account_responses.append(row)
        super()._response(row, processed_ns)
        if self.limit is not None and self.limit != self.manifest["budget_sample"]["weight_limit"]:
            raise DepthError("joint_advertised_budget_limit_changed")

    def route_snapshot(self, row, body, processed_ns):
        if self.routes is not None or len(self.collections) != 1 or self.metadata is None:
            raise DepthError("joint_single_route_fixation_required")
        collection = self.collections[0]
        if (
            not collection["ended_ns"]
            <= self.metadata["sent_ns"]
            <= self.metadata["received_ns"]
            <= row["sent_ns"]
            or not 0 <= processed_ns - collection["started_ns"] <= 60 * SECOND
            or processed_ns // (86400 * SECOND) != collection["started_ns"] // (86400 * SECOND)
        ):
            raise DepthError("joint_route_input_interval_invalid")
        account, _ = self._body(self.raw_account_responses[-1], 16 * MAX_FRAME)
        balances = account_balances(account, self.manifest["source"]["account_uid"])
        info, _ = self._body(self.metadata, 16 * MAX_FRAME)
        value = indicative_valuation(balances, info, body)
        by_asset = {r["asset"]: r for r in value["assets"]}
        if any(a not in by_asset or not by_asset[a]["path"] for a in PILOT_ASSETS):
            raise DepthError("joint_missing_pilot_route")
        symbols = sorted({leg["symbol"] for a in PILOT_ASSETS for leg in by_asset[a]["path"]})
        if len(symbols) > 3:
            raise DepthError("joint_route_union_exceeds_cap")
        unavailable = {r["symbol"] for r in value["unavailable_books"]}
        if unavailable.intersection(symbols) or any(
            a in value["depth_exceeded_assets"] for a in PILOT_ASSETS
        ):
            raise DepthError("joint_pilot_side_or_depth_unavailable")
        selected = {r["symbol"]: r for r in info["symbols"]}
        for symbol in symbols:
            data = selected[symbol]
            self.books[symbol] = DepthBook(
                {"symbols": [data]},
                revision=2,
                symbol=symbol,
                base_asset=data["baseAsset"],
                quote_asset=data["quoteAsset"],
            )
        # The immutable startup receipt keeps an empty symbol set. Only this state's
        # detached copy advances to the selection reproduced from these raw responses.
        self.manifest = {**self.manifest, "symbols": symbols}
        self.budget = request_budget(symbols)
        self.routes = {
            "policy": value["method"],
            "symbols": symbols,
            "fixed_at_ns": row["received_ns"],
            "initial_sha256": self.manifest["initial_sha256"],
            "account_receipt_sequences": collection["receipt_sequences"],
            "account_raw_sha256": collection["raw_sha256"],
            "metadata_receipt_seq": self.metadata["seq"],
            "metadata_raw_sha256": self.metadata["body_sha256"],
            "books_receipt_seq": row["seq"],
            "books_raw_sha256": row["body_sha256"],
            "assets": [
                {
                    "asset": r["asset"],
                    "required_symbols": sorted({p["symbol"] for p in r["path"]}),
                    "status": (
                        "unpriced"
                        if r["mark_usdt"] is None
                        else "outside_pilot"
                        if any(p["symbol"] not in symbols for p in r["path"])
                        else "selected_or_no_market_leg"
                    ),
                    "historical_top_book_exceeded": r["asset"] in value["depth_exceeded_assets"],
                }
                for r in value["assets"]
            ],
            "valuation_qualified": False,
        }

    def summary(self):
        return {
            **super().summary(),
            "route_fixation": self.routes,
            "prepared_operations": self.prepared_count,
            "account_pongs": self.account_pongs,
            "loopback_connection_attempts": self.connection_attempts,
            "loopback_observed_used_weight": self.usage,
            "original_inputs_replayed_for_routes": self.routes is not None,
            "actual_source_or_shared_ip_qualified": False,
        }
