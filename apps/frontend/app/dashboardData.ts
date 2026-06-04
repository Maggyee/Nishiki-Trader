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

export type DashboardSnapshot = {
  schema_version?: string;
  generated_at_ns?: number | string | null;
  boundaries?: Record<string, boolean>;
  project_status?: {
    last_updated?: string | null;
    current_phase?: string | null;
    current_objective?: string | null;
    live_trading_blocked?: boolean;
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
    snapshot_source: {
      path: snapshotPath,
      loaded: false,
      error: error instanceof Error ? error.message : String(error),
    },
  };
}
