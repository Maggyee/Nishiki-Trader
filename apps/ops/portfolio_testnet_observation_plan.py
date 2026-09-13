"""Replay pinned originals to size a historical route/interval plan; no network."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from collections import deque
from pathlib import Path

from apps.ops.portfolio_testnet_admission import review_admission
from apps.strategies_nautilus.portfolio_market_depth_archive import replay_depth
from apps.strategies_nautilus.portfolio_observation_plan import observation_plan
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical

LIMITS = {"initial": 8, "account": 64, "market": 32, "depth": 64}


def plan_from_originals(raws, hashes, *, collection):
    if set(raws) != set(LIMITS) or set(hashes) != set(LIMITS):
        raise ValueError("all original inputs required")
    for key, limit in LIMITS.items():
        if (
            not isinstance(raws[key], bytes)
            or not 0 < len(raws[key]) <= limit * 1048576
            or hashlib.sha256(raws[key]).hexdigest() != hashes[key]
        ):
            raise ValueError("selected original input changed")
    admission = review_admission(
        raws["account"],
        raws["market"],
        raws["initial"],
        archive_sha256=hashes["account"],
        collection_id=collection,
        market_sha256=hashes["market"],
        selection_sha256=hashes["initial"],
    )
    depth = replay_depth(raws["depth"], expected_sha256=hashes["depth"], revision=2)
    result = observation_plan(admission, depth)
    # Structural integrity/profile/time semantics were checked by depth replay above.
    rows = [json.loads(line) for line in raws["depth"].splitlines()]
    frames = [
        (r["monotonic_ns"], len(base64.b64decode(r["raw_b64"])))
        for r in rows
        if r["kind"] == "depth_frame"
    ]
    pending, size, peak_count, peak_size = deque(), 0, 0, 0
    for stamp, length in frames:
        while pending and stamp - pending[0][0] >= 1000000000:
            size -= pending.popleft()[1]
        pending.append((stamp, length))
        size += length
        peak_count = max(peak_count, len(pending))
        peak_size = max(peak_size, size)
    result["inputs"] = {
        "sha256": hashes,
        "account_collection": collection,
        "source_binding_sha256": admission["inputs"]["source_binding_sha256"],
        "depth_completion_sha256": depth["completion_sha256"],
    }
    result["btc_only_transport_observation"] = {
        "started_ns": rows[0]["received_ns"],
        "completed_ns": rows[-1]["received_ns"],
        "duration_ns": rows[-1]["monotonic_ns"] - rows[0]["monotonic_ns"],
        "raw_frames": len(frames),
        "raw_payload_bytes": sum(n for _, n in frames),
        "max_frame_bytes": max(n for _, n in frames),
        "max_frames_in_rolling_second": peak_count,
        "max_raw_bytes_in_rolling_second": peak_size,
        "archive_bytes": len(raws["depth"]),
        "native_quote_count": depth["summary"]["native_quote_count"],
        "native_quotes_sha256": depth["summary"]["native_quotes_sha256"],
        "extrapolation_to_other_symbols_qualified": False,
        "joint_account_market_capture_verified": False,
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in LIMITS:
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("new output required")
        raws = {k: private_read(getattr(args, k), limit=v * 1048576) for k, v in LIMITS.items()}
        hashes = {k: getattr(args, k + "_sha256") for k in LIMITS}
        report = plan_from_originals(raws, hashes, collection=args.collection)
        raw = canonical(report) + b"\n"
        write_private_new(args.output, raw)
    except Exception:
        print(json.dumps({"status": "observation_plan_failed", "runtime_ready": False}))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "assets_recorded": report["assets_recorded"],
                "route_symbols": len(report["all_required_symbols"]),
                "pilot_symbols": report["pilot"]["symbols"],
                "pilot_weight": report["pilot"]["budget"]["total_documented_weight"],
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "runtime_ready": False,
                "new_probe_authorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
