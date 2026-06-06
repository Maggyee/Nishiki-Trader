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
  const status = snapshot.project_status ?? {};
  const sections = status.sections ?? {};
  const advice = snapshot.agent_advice ?? {};
  const paperBundles = snapshot.paper_bundles ?? [];
  const testnetBundles = snapshot.testnet_bundles ?? [];
  const ops = snapshot.ops_status ?? {};

  return (
    <main className="min-h-screen bg-stone-100 text-zinc-950">
      <Header snapshot={snapshot} />

      <section className="mx-auto grid max-w-[1540px] gap-4 px-4 py-4 sm:px-5">
        <CommandBand snapshot={snapshot} />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.55fr)]">
          <div className="grid gap-4">
            <StatusGrid snapshot={snapshot} />
            <OpsSummary summary={ops.summary ?? []} />
            <EvidenceMatrix paperBundles={paperBundles} testnetBundles={testnetBundles} />
            <AdviceTable rows={advice.latest ?? []} />
          </div>

          <aside className="grid content-start gap-4">
            <ChecklistPanel items={snapshot.operator_checklist ?? []} />
            <WatchlistPanel
              blocked={sections.blocked_deferred ?? []}
              nextSteps={sections.next_steps ?? []}
            />
            <VerificationPanel items={sections.latest_verification ?? []} />
            <BoundaryPanel boundaries={snapshot.boundaries ?? {}} />
          </aside>
        </div>
      </section>
    </main>
  );
}

function Header({ snapshot }: { snapshot: DashboardSnapshot }) {
  const status = snapshot.project_status ?? {};
  return (
    <header className="border-b border-zinc-300 bg-white">
      <div className="mx-auto flex max-w-[1540px] flex-col gap-3 px-4 py-4 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-normal text-emerald-700">
            Trader Dashboard
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-zinc-950 md:text-3xl">
            Operations Console
          </h1>
        </div>
        <div className="grid gap-2 text-sm text-zinc-700 sm:grid-cols-2 lg:min-w-[620px]">
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

function CommandBand({ snapshot }: { snapshot: DashboardSnapshot }) {
  const ops = snapshot.ops_status ?? {};
  const status = snapshot.project_status ?? {};
  const state = normalizeState(ops.state);
  return (
    <section className="command-band" data-state={state}>
      <div className="posture-block">
        <span>Operational posture</span>
        <strong>{labelState(state)}</strong>
      </div>
      <div className="posture-copy">
        <h2>{ops.headline ?? "Read-only dashboard posture unknown."}</h2>
        <p>{status.current_objective ?? "No project objective was found in the snapshot."}</p>
      </div>
      <div className="posture-meta">
        <MiniFact label="Live gate" value={ops.live_gate ?? "unknown"} />
        <MiniFact label="Strict continuity" value={ops.strict_continuity ?? "unknown"} />
        <MiniFact label="Generated" value={formatGenerated(snapshot.generated_at_ns)} />
      </div>
    </section>
  );
}

function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="mini-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusGrid({ snapshot }: { snapshot: DashboardSnapshot }) {
  const status = snapshot.project_status ?? {};
  const advice = snapshot.agent_advice ?? {};
  const counts = snapshot.ops_status?.counts ?? {};
  return (
    <section className="grid gap-3 md:grid-cols-4">
      <Metric
        label="AgentAdvice"
        value={formatCount(advice.total)}
        detail={`${Object.keys(advice.by_type ?? {}).length} types / ${formatCount(
          counts.recorded_advice,
        )} recorded`}
        tone={counts.recorded_advice ? "amber" : "blue"}
      />
      <Metric
        label="Evidence Inputs"
        value={formatCount((counts.paper_bundle_count ?? 0) + (counts.testnet_bundle_count ?? 0))}
        detail={`${formatCount(counts.paper_bundle_count)} paper / ${formatCount(
          counts.testnet_bundle_count,
        )} testnet`}
        tone="green"
      />
      <Metric
        label="Blockers"
        value={formatCount(totalBlockers(counts))}
        detail="review, promotion, and boundary blockers"
        tone={totalBlockers(counts) ? "red" : "green"}
      />
      <Metric
        label="Order Path"
        value="sealed"
        detail={status.live_trading_blocked ? "Live gate blocked" : "Live gate unknown"}
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

function OpsSummary({ summary }: { summary: string[] }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Console Brief</h2>
        <span>{summary.length ? `${summary.length} checks` : "fallback"}</span>
      </div>
      <div className="brief-grid">
        {(summary.length ? summary : ["No operations summary is present in the snapshot."]).map(
          (item) => (
            <div className="brief-item" key={item}>
              <span aria-hidden="true" />
              <p>{item}</p>
            </div>
          ),
        )}
      </div>
    </section>
  );
}

function EvidenceMatrix({
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
        <h2>Evidence Matrix</h2>
        <span>read-only snapshot totals</span>
      </div>
      <div className="evidence-grid">
        <EvidenceBar label="Paper bundles" value={paperBundles.length} max={8} tone="blue" />
        <EvidenceBar label="Paper fills" value={paperFills} max={2000} tone="green" />
        <EvidenceBar label="Clean testnet" value={cleanTestnet} max={16} tone="green" />
        <EvidenceBar label="Testnet alerts" value={alerts} max={12} tone="red" />
        <EvidenceBar label="Testnet fills" value={testnetFills} max={48} tone="amber" />
      </div>
      <div className="bundle-ledger">
        <BundleList title="Paper" bundles={paperBundles} />
        <BundleList title="Testnet" bundles={testnetBundles} />
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

function BundleList({
  title,
  bundles,
}: {
  title: string;
  bundles: Array<PaperBundle | TestnetBundle>;
}) {
  return (
    <div className="ledger-column">
      <strong>{title}</strong>
      {bundles.length ? (
        bundles.slice(0, 4).map((bundle) => (
          <div className="ledger-row" key={bundle.run_id ?? `${title}-unknown`}>
            <span>{bundle.run_id ?? "unknown run"}</span>
            <small>{bundle.recommendation ?? "no recommendation"}</small>
          </div>
        ))
      ) : (
        <div className="ledger-row">
          <span>No bundle summaries attached</span>
          <small>pass --paper-bundle or --testnet-bundle when generating snapshot</small>
        </div>
      )}
    </div>
  );
}

function AdviceTable({ rows }: { rows: AdviceRow[] }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>AgentAdvice Queue</h2>
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
              rows.slice(0, 10).map((row) => (
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

function ChecklistPanel({
  items,
}: {
  items: NonNullable<DashboardSnapshot["operator_checklist"]>;
}) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Operator Checklist</h2>
        <span>{items.length} items</span>
      </div>
      <div className="checklist">
        {items.map((item) => (
          <div className="check-row" data-status={normalizeChecklist(item.status)} key={item.label}>
            <strong>{item.label ?? "Checklist item"}</strong>
            <StatusPill value={item.status ?? "unknown"} />
            <p>{item.detail ?? "No detail provided."}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function WatchlistPanel({
  blocked,
  nextSteps,
}: {
  blocked: string[];
  nextSteps: string[];
}) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Watchlist</h2>
        <span>{blocked.length} blocked / {nextSteps.length} next</span>
      </div>
      <ListBlock title="Blocked / Deferred" items={blocked} empty="No blockers listed." />
      <ListBlock title="Next Steps" items={nextSteps} empty="No next steps listed." />
    </section>
  );
}

function VerificationPanel({ items }: { items: string[] }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Verification</h2>
        <span>{items.length ? "latest block" : "none"}</span>
      </div>
      <ListBlock
        title="Latest checks"
        items={items}
        empty="No verification items were parsed from project status."
      />
    </section>
  );
}

function ListBlock({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="list-block">
      <strong>{title}</strong>
      <ul>
        {(items.length ? items : [empty]).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function BoundaryPanel({ boundaries }: { boundaries: Record<string, boolean> }) {
  const entries = Object.entries(BOUNDARY_LABELS);
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Boundary Ledger</h2>
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

function StatusPill({ value }: { value: string }) {
  const tone =
    value === "ok" || value === "reviewed"
      ? "good"
      : value === "warn" || value === "manual" || value === "archived"
        ? "warn"
        : value === "blocked" || value === "breach"
          ? "stop"
          : "neutral";
  return (
    <span className="status-pill" data-tone={tone}>
      {value}
    </span>
  );
}

function normalizeState(value: unknown): "guarded" | "attention" | "breach" {
  if (value === "breach" || value === "attention" || value === "guarded") {
    return value;
  }
  return "attention";
}

function labelState(value: "guarded" | "attention" | "breach"): string {
  if (value === "guarded") {
    return "guarded";
  }
  if (value === "breach") {
    return "breach";
  }
  return "attention";
}

function normalizeChecklist(value: string | undefined): string {
  return value ?? "unknown";
}

function totalBlockers(counts: Record<string, number>): number {
  return (
    (counts.boundary_open_count ?? 0) +
    (counts.paper_review_blockers ?? 0) +
    (counts.paper_promotion_blockers ?? 0) +
    (counts.testnet_review_blockers ?? 0)
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
