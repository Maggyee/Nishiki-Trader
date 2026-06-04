import {
  type AdviceRow,
  type DashboardSnapshot,
  type PaperBundle,
  type TestnetBundle,
  loadDashboardSnapshot,
} from "./dashboardData";

export const dynamic = "force-dynamic";

const BOUNDARY_LABELS: Record<string, string> = {
  live_path_allowed: "Live path",
  signal_event_write_allowed: "SignalEvent writes",
  source_policy_mutation_allowed: "SourcePolicy mutation",
  exchange_api_access_allowed: "Exchange API",
};

export default function DashboardPage() {
  const snapshot = loadDashboardSnapshot();
  const advice = snapshot.agent_advice ?? {};
  const latestAdvice = advice.latest ?? [];
  const paperBundles = snapshot.paper_bundles ?? [];
  const testnetBundles = snapshot.testnet_bundles ?? [];

  return (
    <main className="min-h-screen bg-stone-100 text-zinc-950">
      <Header snapshot={snapshot} />

      <section className="mx-auto grid max-w-[1480px] gap-4 px-4 py-4 sm:px-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(360px,0.6fr)]">
        <div className="grid gap-4">
          <StatusGrid snapshot={snapshot} />
          <EvidenceStrip paperBundles={paperBundles} testnetBundles={testnetBundles} />
          <AdviceTable rows={latestAdvice} />
        </div>

        <aside className="grid content-start gap-4">
          <BoundaryPanel boundaries={snapshot.boundaries ?? {}} />
          <FlowPanel />
          <BundlePanel paperBundles={paperBundles} testnetBundles={testnetBundles} />
        </aside>
      </section>
    </main>
  );
}

function Header({ snapshot }: { snapshot: DashboardSnapshot }) {
  const status = snapshot.project_status ?? {};
  return (
    <header className="border-b border-zinc-300 bg-white">
      <div className="mx-auto flex max-w-[1480px] flex-col gap-3 px-4 py-4 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-normal text-emerald-700">
            Trader Dashboard
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-zinc-950 md:text-3xl">
            Phase 5 Read-Only Operations
          </h1>
        </div>
        <div className="grid gap-2 text-sm text-zinc-700 sm:grid-cols-2 lg:min-w-[560px]">
          <HeaderFact label="Snapshot" value={snapshot.schema_version ?? "unknown"} />
          <HeaderFact
            label="Loaded"
            value={snapshot.snapshot_source.loaded ? "yes" : "fallback"}
            tone={snapshot.snapshot_source.loaded ? "good" : "warn"}
          />
          <HeaderFact label="Phase" value={status.current_phase ?? "unknown"} wide />
          <HeaderFact
            label="Live trading"
            value={status.live_trading_blocked ? "blocked" : "unknown"}
            tone={status.live_trading_blocked ? "stop" : "warn"}
          />
        </div>
      </div>
    </header>
  );
}

function HeaderFact({
  label,
  value,
  tone = "neutral",
  wide = false,
}: {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "warn" | "stop";
  wide?: boolean;
}) {
  return (
    <div className={`fact ${wide ? "sm:col-span-2" : ""}`} data-tone={tone}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusGrid({ snapshot }: { snapshot: DashboardSnapshot }) {
  const status = snapshot.project_status ?? {};
  const advice = snapshot.agent_advice ?? {};
  return (
    <section className="grid gap-3 md:grid-cols-4">
      <Metric
        label="AgentAdvice"
        value={formatCount(advice.total)}
        detail={`${Object.keys(advice.by_type ?? {}).length} types`}
        tone="blue"
      />
      <Metric
        label="Advice DB"
        value={advice.db_exists ? "present" : "missing"}
        detail={snapshot.snapshot_source.path}
        tone={advice.db_exists ? "green" : "amber"}
      />
      <Metric
        label="Snapshot Age"
        value={formatGenerated(snapshot.generated_at_ns)}
        detail={status.last_updated ?? "project status timestamp unavailable"}
        tone="green"
      />
      <Metric
        label="Order Path"
        value="sealed"
        detail="No trading controls exposed"
        tone="red"
      />
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: "green" | "blue" | "amber" | "red";
}) {
  return (
    <article className="panel min-h-[132px]" data-accent={tone}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}

function EvidenceStrip({
  paperBundles,
  testnetBundles,
}: {
  paperBundles: PaperBundle[];
  testnetBundles: TestnetBundle[];
}) {
  const cleanTestnet = testnetBundles.filter((bundle) => bundle.clean_for_retro).length;
  const paperFills = sum(paperBundles.map((bundle) => bundle.fills));
  const testnetFills = sum(testnetBundles.map((bundle) => bundle.fills));
  const alerts = sum(testnetBundles.map((bundle) => bundle.alert_count));

  return (
    <section className="panel">
      <div className="section-head">
        <h2>Evidence</h2>
        <span>read-only snapshot totals</span>
      </div>
      <div className="evidence-grid">
        <EvidenceBar label="Paper bundles" value={paperBundles.length} max={8} tone="blue" />
        <EvidenceBar label="Paper fills" value={paperFills} max={2000} tone="green" />
        <EvidenceBar label="Clean testnet" value={cleanTestnet} max={16} tone="green" />
        <EvidenceBar label="Testnet alerts" value={alerts} max={12} tone="red" />
        <EvidenceBar label="Testnet fills" value={testnetFills} max={48} tone="amber" />
      </div>
    </section>
  );
}

function EvidenceBar({
  label,
  value,
  max,
  tone,
}: {
  label: string;
  value: number;
  max: number;
  tone: "green" | "blue" | "amber" | "red";
}) {
  const width = Math.min(Math.max((value / max) * 100, value > 0 ? 7 : 0), 100);
  return (
    <div className="evidence-row" data-tone={tone}>
      <div>
        <span>{label}</span>
        <strong>{formatCount(value)}</strong>
      </div>
      <div className="bar-track" aria-hidden="true">
        <span style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function AdviceTable({ rows }: { rows: AdviceRow[] }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>AgentAdvice</h2>
        <span>{rows.length ? `${rows.length} latest rows` : "no rows in snapshot"}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Type</th>
              <th>Status</th>
              <th>Confidence</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.slice(0, 8).map((row) => (
                <tr key={row.advice_id ?? `${row.agent_name}-${row.created_at_ns}`}>
                  <td>{row.agent_name ?? "unknown"}</td>
                  <td>{row.advice_type ?? "unknown"}</td>
                  <td>
                    <StatusPill value={row.status ?? "unknown"} />
                  </td>
                  <td>{formatConfidence(row.confidence)}</td>
                  <td>{row.summary ?? "No summary"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>No AgentAdvice rows are present in this snapshot.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BoundaryPanel({ boundaries }: { boundaries: Record<string, boolean> }) {
  const entries = Object.entries(BOUNDARY_LABELS);
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Boundaries</h2>
        <span>must remain false</span>
      </div>
      <div className="boundary-list">
        {entries.map(([key, label]) => {
          const allowed = boundaries[key] === true;
          return (
            <div className="boundary-row" key={key} data-open={String(allowed)}>
              <span>{label}</span>
              <strong>{allowed ? "open" : "closed"}</strong>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function FlowPanel() {
  return (
    <section className="panel flow-panel">
      <div className="section-head">
        <h2>Research Flow</h2>
        <span>audited path</span>
      </div>
      <div className="flow-rail" aria-hidden="true">
        <span data-step="1" />
        <span data-step="2" />
        <span data-step="3" />
        <span data-step="4" />
      </div>
      <div className="flow-labels">
        <span>Research</span>
        <span>AgentAdvice</span>
        <span>Snapshot</span>
        <span>Dashboard</span>
      </div>
    </section>
  );
}

function BundlePanel({
  paperBundles,
  testnetBundles,
}: {
  paperBundles: PaperBundle[];
  testnetBundles: TestnetBundle[];
}) {
  const latestPaper = paperBundles[0];
  const latestTestnet = testnetBundles[0];
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Bundle Inputs</h2>
        <span>{paperBundles.length + testnetBundles.length} attached</span>
      </div>
      <BundleSummary title="Paper" bundle={latestPaper} />
      <BundleSummary title="Testnet" bundle={latestTestnet} />
    </section>
  );
}

function BundleSummary({
  title,
  bundle,
}: {
  title: string;
  bundle: PaperBundle | TestnetBundle | undefined;
}) {
  if (!bundle) {
    return (
      <div className="bundle-summary">
        <strong>{title}</strong>
        <span>No bundle summary in snapshot</span>
      </div>
    );
  }

  return (
    <div className="bundle-summary">
      <strong>{title}</strong>
      <span>{bundle.run_id ?? "unknown run"}</span>
      <small>{bundle.recommendation ?? "no recommendation"}</small>
    </div>
  );
}

function StatusPill({ value }: { value: string }) {
  const tone = value === "reviewed" ? "good" : value === "archived" ? "warn" : "neutral";
  return (
    <span className="status-pill" data-tone={tone}>
      {value}
    </span>
  );
}

function formatCount(value: number | undefined): string {
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

function formatConfidence(value: number | undefined): string {
  if (typeof value !== "number") {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}

function formatGenerated(value: DashboardSnapshot["generated_at_ns"]): string {
  if (value === null || value === undefined) {
    return "not generated";
  }
  const raw = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(raw)) {
    return "unknown";
  }
  const date = new Date(Math.floor(raw / 1_000_000));
  return date.toISOString().replace("T", " ").slice(0, 19);
}

function sum(values: Array<number | undefined>): number {
  return values.reduce<number>((total, value) => total + (value ?? 0), 0);
}
