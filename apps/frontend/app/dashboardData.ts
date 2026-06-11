import fs from "node:fs";
import path from "node:path";

export type AdviceRow = {
  advice_id?: string;
  agent_name?: string;
  created_at_ns?: number | string;
  advice_type?: string;
  summary?: string;
  confidence?: number;
  status?: string;
  review_decision?: string | null;
};

export type PaperBundle = {
  run_id?: string;
  source?: string | null;
  model_version?: string | null;
  signal_rows?: number;
  fills?: number;
  positions?: number;
  recommendation?: string;
  review_blockers?: string[];
  promotion_blockers?: string[];
};

export type TestnetBundle = {
  run_id?: string;
  clean_for_retro?: boolean;
  heartbeat_count?: number;
  alert_count?: number;
  fills?: number;
  realized_pnl_total?: number;
  recommendation?: string;
  review_blockers?: string[];
};

export type ReferenceLink = {
  group?: string;
  label?: string;
  kind?: string;
  href?: string | null;
  path?: string | null;
  detail?: string;
};

export type ObservabilityRun = {
  path?: string;
  kind?: string | null;
  run_id?: string | null;
  state?: string;
  state_reason?: string;
  parse_errors?: string[];
  heartbeat_timestamp_seconds?: number | null;
  heartbeat_age_seconds?: number | null;
  ws_connected?: boolean | null;
  ws_reconnect_total?: number | null;
  exchange_error_total?: number | null;
  open_orders?: number | null;
  open_positions?: number | null;
  daily_pnl_usdt?: number | null;
  account_total_usdt?: number | null;
  last_bar_timestamp_seconds?: number | null;
  last_bar_age_seconds?: number | null;
  last_signal_timestamp_seconds?: number | null;
  last_signal_age_seconds?: number | null;
  alert_total?: number;
  alerts_by_kind?: Record<string, number>;
};

export type ObservabilitySnapshot = {
  textfile_dir?: string | null;
  exists?: boolean;
  file_count?: number;
  stale_after_seconds?: number;
  counts?: Record<string, number>;
  latest?: ObservabilityRun | null;
  runs?: ObservabilityRun[];
};

export type DashboardSnapshot = {
  schema_version?: string;
  generated_at_ns?: number | string | null;
  boundaries?: Record<string, boolean>;
  project_status?: {
    last_updated?: string | null;
    current_phase?: string | null;
    current_objective?: string | null;
    live_trading_blocked?: boolean;
    strict_continuity?: string | null;
    sections?: {
      immediate_focus?: string[];
      next_steps?: string[];
      blocked_deferred?: string[];
      latest_verification?: string[];
    };
  };
  agent_advice?: {
    db_exists?: boolean;
    total?: number;
    by_status?: Record<string, number>;
    by_type?: Record<string, number>;
    by_agent?: Record<string, number>;
    latest?: AdviceRow[];
  };
  paper_bundles?: PaperBundle[];
  testnet_bundles?: TestnetBundle[];
  ops_status?: {
    state?: "guarded" | "attention" | "breach" | string;
    headline?: string;
    live_gate?: string;
    strict_continuity?: string | null;
    counts?: Record<string, number>;
    summary?: string[];
  };
  observability?: ObservabilitySnapshot;
  reference_links?: ReferenceLink[];
  operator_checklist?: Array<{
    label?: string;
    status?: "ok" | "warn" | "blocked" | "breach" | "manual" | string;
    detail?: string;
  }>;
  snapshot_source: {
    path: string;
    loaded: boolean;
    error?: string;
  };
};

export function defaultSnapshotPath(): string {
  return path.resolve(process.cwd(), "..", "..", "data", "frontend", "dashboard-snapshot.json");
}

export function loadDashboardSnapshot(): DashboardSnapshot {
  const snapshotPath = process.env.TRADER_DASHBOARD_SNAPSHOT || defaultSnapshotPath();
  try {
    const raw = fs.readFileSync(snapshotPath, "utf-8");
    const parsed = JSON.parse(raw) as Omit<DashboardSnapshot, "snapshot_source">;
    return {
      ...parsed,
      snapshot_source: {
        path: snapshotPath,
        loaded: true,
      },
    };
  } catch (error) {
    return fallbackSnapshot(snapshotPath, error);
  }
}

function fallbackSnapshot(snapshotPath: string, error: unknown): DashboardSnapshot {
  return {
    schema_version: "dashboard.snapshot.v1",
    generated_at_ns: null,
    boundaries: {
      live_path_allowed: false,
      signal_event_write_allowed: false,
      source_policy_mutation_allowed: false,
      exchange_api_access_allowed: false,
    },
    project_status: {
      last_updated: null,
      current_phase: "Phase 5 entry frontend shell",
      current_objective: "Read-only dashboard is waiting for a generated snapshot.",
      live_trading_blocked: true,
      strict_continuity: null,
      sections: {
        immediate_focus: ["Generate a dashboard snapshot before review."],
        next_steps: ["Run apps.ops.dashboard_snapshot and refresh the frontend."],
        blocked_deferred: ["No live trading."],
        latest_verification: [],
      },
    },
    agent_advice: {
      db_exists: false,
      total: 0,
      by_status: {},
      by_type: {},
      by_agent: {},
      latest: [],
    },
    paper_bundles: [],
    testnet_bundles: [],
    ops_status: {
      state: "attention",
      headline: "Dashboard is waiting for a generated snapshot.",
      live_gate: "blocked",
      strict_continuity: null,
      counts: {
        boundary_open_count: 0,
        recorded_advice: 0,
        paper_bundle_count: 0,
        testnet_bundle_count: 0,
        paper_review_blockers: 0,
        paper_promotion_blockers: 0,
        testnet_review_blockers: 0,
      },
      summary: [
        "No snapshot file was loaded.",
        "All trading mutation boundaries remain closed in fallback mode.",
      ],
    },
    observability: {
      textfile_dir: "data/observability/textfile",
      exists: false,
      file_count: 0,
      stale_after_seconds: 120,
      counts: {
        run_count: 0,
        connected_count: 0,
        stale_count: 0,
        attention_count: 0,
        open_orders: 0,
        open_positions: 0,
        alert_total: 0,
        parse_error_count: 0,
      },
      latest: null,
      runs: [],
    },
    reference_links: [
      {
        group: "docs",
        label: "Project status",
        kind: "status",
        href: null,
        path: "docs/project-status.md",
        detail: "Current phase, focus, blockers, next steps, and verification.",
      },
      {
        group: "grafana",
        label: "Signals overview",
        kind: "dashboard",
        href: "http://127.0.0.1:3000/d/signals-overview/signals-overview",
        path: "infra/grafana/dashboards/signals-overview.json",
        detail: "Read-only signal distribution dashboard backed by provisioned Grafana.",
      },
      {
        group: "grafana",
        label: "Current testnet canary",
        kind: "dashboard",
        href: "http://127.0.0.1:3000/d/canary-current/canary-current",
        path: "infra/grafana/dashboards/canary-current.json",
        detail: "Read-only heartbeat, alert, and runtime panels for the active canary.",
      },
    ],
    operator_checklist: [
      {
        label: "Generate dashboard snapshot",
        status: "manual",
        detail: "Run apps.ops.dashboard_snapshot before operational review.",
      },
    ],
    snapshot_source: {
      path: snapshotPath,
      loaded: false,
      error: error instanceof Error ? error.message : String(error),
    },
  };
}
