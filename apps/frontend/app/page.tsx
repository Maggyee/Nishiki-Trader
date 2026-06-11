import {
  type AdviceRow,
  type DashboardSnapshot,
  type ObservabilityRun,
  type ObservabilitySnapshot,
  type PaperBundle,
  type ReferenceLink,
  type SignalReasonCount,
  type SignalSummary,
  type TestnetBundle,
  loadDashboardSnapshot,
} from "./dashboardData";

export const dynamic = "force-dynamic";

const LANGUAGES = ["en", "zh-CN"] as const;
type Language = (typeof LANGUAGES)[number];
type SearchParams = Record<string, string | string[] | undefined>;
type Copy = (typeof COPY)[Language];

const BOUNDARY_KEYS = [
  "live_path_allowed",
  "signal_event_write_allowed",
  "source_policy_mutation_allowed",
  "exchange_api_access_allowed",
] as const;

const COPY = {
  en: {
    languageLabel: "Language",
    languageOptions: {
      en: "EN",
      "zh-CN": "简体中文",
    },
    brand: "Trader Dashboard",
    title: "Operations Console",
    header: {
      snapshot: "Snapshot",
      loaded: "Loaded",
      phase: "Phase",
      liveTrading: "Live trading",
      loadedYes: "yes",
      loadedFallback: "fallback",
    },
    command: {
      posture: "Operational posture",
      postureUnknown: "Read-only dashboard posture unknown.",
      noObjective: "No project objective was found in the snapshot.",
      liveGate: "Live gate",
      strictContinuity: "Strict continuity",
      generated: "Generated",
    },
    metrics: {
      agentAdvice: "AgentAdvice",
      evidenceInputs: "Evidence Inputs",
      blockers: "Blockers",
      blockersDetail: "review, promotion, and boundary blockers",
      orderPath: "Order Path",
      sealed: "sealed",
      liveGateBlocked: "Live gate blocked",
      liveGateUnknown: "Live gate unknown",
    },
    sections: {
      consoleBrief: "Console Brief",
      evidenceMatrix: "Evidence Matrix",
      evidenceSubtitle: "read-only snapshot totals",
      runtimeHealth: "Runtime Health",
      runtimeSubtitle: "textfile collector snapshot",
      signalSummary: "Signals & Rejections",
      agentAdviceQueue: "AgentAdvice Queue",
      operatorChecklist: "Operator Checklist",
      watchlist: "Watchlist",
      verification: "Verification",
      referenceLinks: "Reference Links",
      boundaryLedger: "Boundary Ledger",
    },
    evidence: {
      paperBundles: "Paper bundles",
      paperFills: "Paper fills",
      cleanTestnet: "Clean testnet",
      testnetAlerts: "Testnet alerts",
      testnetFills: "Testnet fills",
      paper: "Paper",
      testnet: "Testnet",
      unknownRun: "unknown run",
      noRecommendation: "no recommendation",
      noBundles: "No bundle summaries attached",
      attachBundles: "pass --paper-bundle or --testnet-bundle when generating snapshot",
    },
    runtime: {
      noRuns: "No textfile collector runs were found.",
      sourceMissing: "Textfile directory is absent",
      sourceReady: "Textfile directory loaded",
      textfiles: "Textfiles",
      latestHeartbeat: "Latest heartbeat",
      ws: "WS",
      dataLag: "Data lag",
      openState: "Open state",
      connected: "connected",
      disconnected: "disconnected",
      unknown: "unknown",
      bar: "bar",
      signal: "signal",
      orders: "orders",
      positions: "positions",
      alerts: "alerts",
      errors: "errors",
      reconnects: "reconnects",
      reason: "reason",
      states: {
        healthy: "healthy",
        stale: "stale",
        attention: "attention",
        disconnected: "disconnected",
        unknown: "unknown",
      },
    },
    signal: {
      attachedBundles: "bundles",
      signals: "Signals",
      accepted: "Accepted",
      skipped: "Skipped",
      rejections: "Rejections",
      sourceModel: "Source / model",
      bundles: "Bundles",
      topReasons: "Top reasons",
      runLedger: "Run ledger",
      noRows: "No signal-source summaries attached.",
      noRuns: "No run-level signal summaries.",
      unknownSource: "unknown source",
      unknownModel: "unknown model",
      noReasons: "none",
      reasons: {
        data_gap: "data gap",
        expired: "expired",
        kill_switch: "kill switch",
        low_confidence: "low confidence",
        reject_other: "other rejects",
        signal_lag: "signal lag",
        suppressed: "suppressed",
        unauthorized: "unauthorized",
      },
    },
    advice: {
      noRowsSnapshot: "no rows in snapshot",
      latestRows: "latest rows",
      agent: "Agent",
      type: "Type",
      status: "Status",
      confidence: "Confidence",
      summary: "Summary",
      noRows: "No AgentAdvice rows are present in this snapshot.",
      noSummary: "No summary",
    },
    checklist: {
      items: "items",
      item: "Checklist item",
      noDetail: "No detail provided.",
    },
    watchlist: {
      blockedDeferred: "Blocked / Deferred",
      nextSteps: "Next Steps",
      noBlockers: "No blockers listed.",
      noNextSteps: "No next steps listed.",
    },
    verification: {
      latestBlock: "latest block",
      none: "none",
      latestChecks: "Latest checks",
      noItems: "No verification items were parsed from project status.",
    },
    reference: {
      subtitle: "docs and read-only monitoring",
      noLinks: "No reference links are present in this snapshot.",
      sourcePath: "source path",
      open: "open",
      localOnly: "local only",
      groups: {
        docs: "Docs",
        evidence: "Evidence",
        grafana: "Grafana",
        ops: "Ops",
        frontend: "Frontend",
      },
      kinds: {
        adr: "ADR",
        dashboard: "dashboard",
        progress: "progress",
        runbook: "runbook",
        status: "status",
      },
    },
    boundary: {
      mustRemainFalse: "must remain false",
      open: "open",
      closed: "closed",
    },
    boundaries: {
      live_path_allowed: "Live path",
      signal_event_write_allowed: "SignalEvent writes",
      source_policy_mutation_allowed: "SourcePolicy mutation",
      exchange_api_access_allowed: "Exchange API",
    },
    states: {
      guarded: "guarded",
      attention: "attention",
      breach: "breach",
    },
    statusValues: {
      ok: "ok",
      reviewed: "reviewed",
      warn: "warn",
      manual: "manual",
      archived: "archived",
      blocked: "blocked",
      breach: "breach",
      unknown: "unknown",
    },
    generated: {
      notGenerated: "not generated",
      unknown: "unknown",
    },
    fallback: {
      summary: "No operations summary is present in the snapshot.",
    },
    common: {
      blocked: "blocked",
      unknown: "unknown",
      fallback: "fallback",
      checks: "checks",
      types: "types",
      recorded: "recorded",
      paper: "paper",
      testnet: "testnet",
      nA: "n/a",
    },
    known: {
      "Read-only operations are guarded; live trading remains blocked.":
        "Read-only operations are guarded; live trading remains blocked.",
      "A dashboard or agent boundary is open.": "A dashboard or agent boundary is open.",
      "Review blockers exist in attached evidence.": "Review blockers exist in attached evidence.",
      "Live gate state is not explicitly blocked.":
        "Live gate state is not explicitly blocked.",
      "Live trading is blocked by ADR gates.": "Live trading is blocked by ADR gates.",
      "Live trading gate is not explicitly blocked in project status.":
        "Live trading gate is not explicitly blocked in project status.",
      "All dashboard/agent mutation boundaries are closed.":
        "All dashboard/agent mutation boundaries are closed.",
      "No recorded AgentAdvice rows in the snapshot.":
        "No recorded AgentAdvice rows in the snapshot.",
      "Strict continuity is 0/14; do not claim live readiness.":
        "Strict continuity is 0/14; do not claim live readiness.",
      "Run apps.ops.dashboard_snapshot before operational review.":
        "Run apps.ops.dashboard_snapshot before operational review.",
      "Frontend must not expose order, SignalEvent, SourcePolicy, or exchange writes.":
        "Frontend must not expose order, SignalEvent, SourcePolicy, or exchange writes.",
      "SourcePolicy changes must go through promotion_review, not the dashboard.":
        "SourcePolicy changes must go through promotion_review, not the dashboard.",
      "Refresh dashboard snapshot": "Refresh dashboard snapshot",
      "Keep trading mutations closed": "Keep trading mutations closed",
      "Review AgentAdvice queue": "Review AgentAdvice queue",
      "Respect paused continuity": "Respect paused continuity",
      "Use promotion review for policy changes": "Use promotion review for policy changes",
    },
  },
  "zh-CN": {
    languageLabel: "语言",
    languageOptions: {
      en: "English",
      "zh-CN": "简体中文",
    },
    brand: "交易看板",
    title: "运维观察台",
    header: {
      snapshot: "快照",
      loaded: "加载状态",
      phase: "阶段",
      liveTrading: "实盘交易",
      loadedYes: "已加载",
      loadedFallback: "兜底数据",
    },
    command: {
      posture: "运维姿态",
      postureUnknown: "只读看板姿态未知。",
      noObjective: "当前快照没有找到项目目标。",
      liveGate: "实盘闸门",
      strictContinuity: "严格连续性",
      generated: "生成时间",
    },
    metrics: {
      agentAdvice: "AgentAdvice",
      evidenceInputs: "证据输入",
      blockers: "阻塞项",
      blockersDetail: "审阅、promotion 与边界阻塞",
      orderPath: "订单路径",
      sealed: "已封闭",
      liveGateBlocked: "实盘闸门已阻塞",
      liveGateUnknown: "实盘闸门未知",
    },
    sections: {
      consoleBrief: "控制台简报",
      evidenceMatrix: "证据矩阵",
      evidenceSubtitle: "只读快照汇总",
      runtimeHealth: "运行健康",
      runtimeSubtitle: "textfile collector 快照",
      signalSummary: "信号与拒绝",
      agentAdviceQueue: "AgentAdvice 队列",
      operatorChecklist: "操作员检查表",
      watchlist: "关注列表",
      verification: "验证记录",
      referenceLinks: "参考链接",
      boundaryLedger: "边界账本",
    },
    evidence: {
      paperBundles: "Paper bundle",
      paperFills: "Paper 成交",
      cleanTestnet: "干净 testnet",
      testnetAlerts: "Testnet 告警",
      testnetFills: "Testnet 成交",
      paper: "Paper",
      testnet: "Testnet",
      unknownRun: "未知运行",
      noRecommendation: "无建议",
      noBundles: "未附加 bundle 摘要",
      attachBundles: "生成快照时传入 --paper-bundle 或 --testnet-bundle",
    },
    runtime: {
      noRuns: "没有找到 textfile collector 运行记录。",
      sourceMissing: "Textfile 目录不存在",
      sourceReady: "Textfile 目录已加载",
      textfiles: "Textfile",
      latestHeartbeat: "最新心跳",
      ws: "WS",
      dataLag: "数据延迟",
      openState: "未平状态",
      connected: "已连接",
      disconnected: "已断开",
      unknown: "未知",
      bar: "K 线",
      signal: "信号",
      orders: "订单",
      positions: "仓位",
      alerts: "告警",
      errors: "错误",
      reconnects: "重连",
      reason: "原因",
      states: {
        healthy: "健康",
        stale: "过期",
        attention: "需关注",
        disconnected: "已断开",
        unknown: "未知",
      },
    },
    signal: {
      attachedBundles: "个 bundle",
      signals: "信号",
      accepted: "接受",
      skipped: "跳过",
      rejections: "拒绝",
      sourceModel: "来源 / 模型",
      bundles: "Bundle",
      topReasons: "主要原因",
      runLedger: "运行账本",
      noRows: "当前快照没有信号来源摘要。",
      noRuns: "当前快照没有运行级信号摘要。",
      unknownSource: "未知来源",
      unknownModel: "未知模型",
      noReasons: "无",
      reasons: {
        data_gap: "数据缺口",
        expired: "过期",
        kill_switch: "熔断",
        low_confidence: "低置信度",
        reject_other: "其他拒绝",
        signal_lag: "信号延迟",
        suppressed: "抑制",
        unauthorized: "未授权",
      },
    },
    advice: {
      noRowsSnapshot: "快照中没有记录",
      latestRows: "条最近记录",
      agent: "Agent",
      type: "类型",
      status: "状态",
      confidence: "置信度",
      summary: "摘要",
      noRows: "当前快照没有 AgentAdvice 记录。",
      noSummary: "无摘要",
    },
    checklist: {
      items: "项",
      item: "检查项",
      noDetail: "没有详情。",
    },
    watchlist: {
      blockedDeferred: "阻塞 / 暂缓",
      nextSteps: "下一步",
      noBlockers: "没有列出的阻塞项。",
      noNextSteps: "没有列出的下一步。",
    },
    verification: {
      latestBlock: "最新记录",
      none: "无",
      latestChecks: "最近检查",
      noItems: "没有从项目状态中解析到验证记录。",
    },
    reference: {
      subtitle: "文档与只读监控",
      noLinks: "当前快照没有参考链接。",
      sourcePath: "源路径",
      open: "打开",
      localOnly: "本地路径",
      groups: {
        docs: "文档",
        evidence: "证据",
        grafana: "Grafana",
        ops: "运维",
        frontend: "前端",
      },
      kinds: {
        adr: "ADR",
        dashboard: "看板",
        progress: "进度",
        runbook: "runbook",
        status: "状态",
      },
    },
    boundary: {
      mustRemainFalse: "必须保持 false",
      open: "打开",
      closed: "关闭",
    },
    boundaries: {
      live_path_allowed: "实盘路径",
      signal_event_write_allowed: "SignalEvent 写入",
      source_policy_mutation_allowed: "SourcePolicy 修改",
      exchange_api_access_allowed: "交易所 API",
    },
    states: {
      guarded: "受控",
      attention: "需关注",
      breach: "越界",
    },
    statusValues: {
      ok: "正常",
      reviewed: "已审阅",
      warn: "警告",
      manual: "人工",
      archived: "已归档",
      blocked: "阻塞",
      breach: "越界",
      unknown: "未知",
    },
    generated: {
      notGenerated: "未生成",
      unknown: "未知",
    },
    fallback: {
      summary: "当前快照没有运维摘要。",
    },
    common: {
      blocked: "阻塞",
      unknown: "未知",
      fallback: "兜底",
      checks: "项检查",
      types: "种类型",
      recorded: "条待审阅",
      paper: "paper",
      testnet: "testnet",
      nA: "无",
    },
    known: {
      "Read-only operations are guarded; live trading remains blocked.":
        "只读运维状态受控；实盘交易仍保持阻塞。",
      "A dashboard or agent boundary is open.": "有 dashboard 或 agent 边界被打开。",
      "Review blockers exist in attached evidence.": "附加证据中存在需要审阅的阻塞项。",
      "Live gate state is not explicitly blocked.": "实盘闸门未明确处于阻塞状态。",
      "Live trading is blocked by ADR gates.": "实盘交易被 ADR gate 阻塞。",
      "Live trading gate is not explicitly blocked in project status.":
        "项目状态里没有明确阻塞实盘闸门。",
      "All dashboard/agent mutation boundaries are closed.":
        "所有 dashboard / agent 写入边界都保持关闭。",
      "No recorded AgentAdvice rows in the snapshot.": "快照中没有待审阅的 AgentAdvice 记录。",
      "Strict continuity is 0/14; do not claim live readiness.":
        "严格连续性为 0/14；不能声称已具备实盘条件。",
      "Run apps.ops.dashboard_snapshot before operational review.":
        "运维审阅前先运行 apps.ops.dashboard_snapshot。",
      "Frontend must not expose order, SignalEvent, SourcePolicy, or exchange writes.":
        "前端不能暴露订单、SignalEvent、SourcePolicy 或交易所写入能力。",
      "SourcePolicy changes must go through promotion_review, not the dashboard.":
        "SourcePolicy 变更必须走 promotion_review，不能从 dashboard 发起。",
      "Refresh dashboard snapshot": "刷新 dashboard 快照",
      "Keep trading mutations closed": "保持交易写入关闭",
      "Review AgentAdvice queue": "审阅 AgentAdvice 队列",
      "Respect paused continuity": "尊重已暂停的连续性",
      "Use promotion review for policy changes": "策略变更使用 promotion review",
    },
  },
} as const;

export default async function DashboardPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const snapshot = loadDashboardSnapshot();
  const params = (await searchParams) ?? {};
  const language = resolveLanguage(params.lang);
  const copy = COPY[language];
  const status = snapshot.project_status ?? {};
  const sections = status.sections ?? {};
  const advice = snapshot.agent_advice ?? {};
  const paperBundles = snapshot.paper_bundles ?? [];
  const testnetBundles = snapshot.testnet_bundles ?? [];
  const observability = snapshot.observability ?? {};
  const signalSummary = snapshot.signal_summary ?? {};
  const referenceLinks = snapshot.reference_links ?? [];
  const ops = snapshot.ops_status ?? {};

  return (
    <main className="min-h-screen bg-stone-100 text-zinc-950" lang={language === "zh-CN" ? "zh-Hans" : "en"}>
      <Header snapshot={snapshot} language={language} copy={copy} />

      <section className="mx-auto grid max-w-[1540px] gap-4 px-4 py-4 sm:px-5">
        <CommandBand snapshot={snapshot} copy={copy} />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.55fr)]">
          <div className="grid gap-4">
            <StatusGrid snapshot={snapshot} language={language} copy={copy} />
            <RuntimeHealthPanel observability={observability} language={language} copy={copy} />
            <SignalSummaryPanel signalSummary={signalSummary} language={language} copy={copy} />
            <OpsSummary summary={ops.summary ?? []} copy={copy} />
            <EvidenceMatrix
              paperBundles={paperBundles}
              testnetBundles={testnetBundles}
              language={language}
              copy={copy}
            />
            <AdviceTable rows={advice.latest ?? []} language={language} copy={copy} />
          </div>

          <aside className="grid content-start gap-4">
            <ChecklistPanel items={snapshot.operator_checklist ?? []} copy={copy} />
            <WatchlistPanel
              blocked={sections.blocked_deferred ?? []}
              nextSteps={sections.next_steps ?? []}
              copy={copy}
            />
            <VerificationPanel items={sections.latest_verification ?? []} copy={copy} />
            <ReferenceLinksPanel links={referenceLinks} copy={copy} />
            <BoundaryPanel boundaries={snapshot.boundaries ?? {}} copy={copy} />
          </aside>
        </div>
      </section>
    </main>
  );
}

function Header({
  snapshot,
  language,
  copy,
}: {
  snapshot: DashboardSnapshot;
  language: Language;
  copy: Copy;
}) {
  const status = snapshot.project_status ?? {};
  return (
    <header className="border-b border-zinc-300 bg-white">
      <div className="mx-auto flex max-w-[1540px] flex-col gap-3 px-4 py-4 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="header-title-block">
          <div>
            <div className="text-xs font-semibold uppercase tracking-normal text-emerald-700">
              {copy.brand}
            </div>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal text-zinc-950 md:text-3xl">
              {copy.title}
            </h1>
          </div>
          <LanguageSwitch language={language} copy={copy} />
        </div>
        <div className="grid gap-2 text-sm text-zinc-700 sm:grid-cols-2 lg:min-w-[620px]">
          <HeaderFact label={copy.header.snapshot} value={snapshot.schema_version ?? copy.common.unknown} />
          <HeaderFact
            label={copy.header.loaded}
            value={snapshot.snapshot_source.loaded ? copy.header.loadedYes : copy.header.loadedFallback}
            tone={snapshot.snapshot_source.loaded ? "good" : "warn"}
          />
          <HeaderFact label={copy.header.phase} value={status.current_phase ?? copy.common.unknown} wide />
          <HeaderFact
            label={copy.header.liveTrading}
            value={status.live_trading_blocked ? copy.common.blocked : copy.common.unknown}
            tone={status.live_trading_blocked ? "stop" : "warn"}
          />
        </div>
      </div>
    </header>
  );
}

function LanguageSwitch({ language, copy }: { language: Language; copy: Copy }) {
  return (
    <nav className="language-switch" aria-label={copy.languageLabel}>
      {LANGUAGES.map((option) => (
        <a
          aria-current={language === option ? "page" : undefined}
          data-active={String(language === option)}
          href={`/?lang=${option}`}
          key={option}
        >
          {copy.languageOptions[option]}
        </a>
      ))}
    </nav>
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

function CommandBand({ snapshot, copy }: { snapshot: DashboardSnapshot; copy: Copy }) {
  const ops = snapshot.ops_status ?? {};
  const status = snapshot.project_status ?? {};
  const state = normalizeState(ops.state);
  return (
    <section className="command-band" data-state={state}>
      <div className="posture-block">
        <span>{copy.command.posture}</span>
        <strong>{labelState(state, copy)}</strong>
      </div>
      <div className="posture-copy">
        <h2>{localizeKnown(ops.headline, copy) || copy.command.postureUnknown}</h2>
        <p>{status.current_objective ?? copy.command.noObjective}</p>
      </div>
      <div className="posture-meta">
        <MiniFact label={copy.command.liveGate} value={localizeStatus(ops.live_gate, copy)} />
        <MiniFact label={copy.command.strictContinuity} value={ops.strict_continuity ?? copy.common.unknown} />
        <MiniFact label={copy.command.generated} value={formatGenerated(snapshot.generated_at_ns, copy)} />
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

function StatusGrid({
  snapshot,
  language,
  copy,
}: {
  snapshot: DashboardSnapshot;
  language: Language;
  copy: Copy;
}) {
  const status = snapshot.project_status ?? {};
  const advice = snapshot.agent_advice ?? {};
  const counts = snapshot.ops_status?.counts ?? {};
  const recordedAdvice = counts.recorded_advice ?? 0;
  const paperBundleCount = counts.paper_bundle_count ?? 0;
  const testnetBundleCount = counts.testnet_bundle_count ?? 0;
  const blockers = totalBlockers(counts);
  return (
    <section className="grid gap-3 md:grid-cols-4">
      <Metric
        label={copy.metrics.agentAdvice}
        value={formatCount(advice.total, language)}
        detail={formatAdviceDetail(Object.keys(advice.by_type ?? {}).length, recordedAdvice, language, copy)}
        tone={recordedAdvice ? "amber" : "blue"}
      />
      <Metric
        label={copy.metrics.evidenceInputs}
        value={formatCount(paperBundleCount + testnetBundleCount, language)}
        detail={formatEvidenceInputDetail(paperBundleCount, testnetBundleCount, language, copy)}
        tone="green"
      />
      <Metric
        label={copy.metrics.blockers}
        value={formatCount(blockers, language)}
        detail={copy.metrics.blockersDetail}
        tone={blockers ? "red" : "green"}
      />
      <Metric
        label={copy.metrics.orderPath}
        value={copy.metrics.sealed}
        detail={status.live_trading_blocked ? copy.metrics.liveGateBlocked : copy.metrics.liveGateUnknown}
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

function RuntimeHealthPanel({
  observability,
  language,
  copy,
}: {
  observability: ObservabilitySnapshot;
  language: Language;
  copy: Copy;
}) {
  const counts = observability.counts ?? {};
  const runs = observability.runs ?? [];
  const latest = observability.latest ?? runs[0] ?? null;
  const sourceLoaded = Boolean(observability.exists);

  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.runtimeHealth}</h2>
        <span>{sourceLoaded ? copy.runtime.sourceReady : copy.runtime.sourceMissing}</span>
      </div>
      <div className="runtime-facts">
        <RuntimeFact
          label={copy.runtime.textfiles}
          value={formatCount(observability.file_count, language)}
          detail={observability.textfile_dir ?? copy.common.unknown}
        />
        <RuntimeFact
          label={copy.runtime.latestHeartbeat}
          value={formatDuration(latest?.heartbeat_age_seconds, copy)}
          detail={latest?.run_id ?? copy.runtime.noRuns}
          tone={runtimeTone(latest?.state)}
        />
        <RuntimeFact
          label={copy.runtime.ws}
          value={formatWs(latest?.ws_connected, copy)}
          detail={`${copy.runtime.reconnects}: ${formatMaybeNumber(latest?.ws_reconnect_total, language, copy)}`}
          tone={latest?.ws_connected === true ? "green" : latest?.ws_connected === false ? "red" : "amber"}
        />
        <RuntimeFact
          label={copy.runtime.dataLag}
          value={`${copy.runtime.bar}: ${formatDuration(latest?.last_bar_age_seconds, copy)}`}
          detail={`${copy.runtime.signal}: ${formatDuration(latest?.last_signal_age_seconds, copy)}`}
          tone={runtimeLagTone(latest?.last_bar_age_seconds, observability.stale_after_seconds)}
        />
      </div>
      <div className="runtime-run-list">
        {runs.length ? (
          runs.slice(0, 4).map((run) => (
            <RuntimeRunRow copy={copy} key={run.run_id ?? run.path ?? "runtime-run"} language={language} run={run} />
          ))
        ) : (
          <div className="runtime-empty">{copy.runtime.noRuns}</div>
        )}
      </div>
      <div className="runtime-summary">
        <span>
          {copy.runtime.openState}: {copy.runtime.orders} {formatCount(counts.open_orders, language)} /{" "}
          {copy.runtime.positions} {formatCount(counts.open_positions, language)}
        </span>
        <span>
          {copy.runtime.alerts} {formatCount(counts.alert_total, language)} / {copy.runtime.errors}{" "}
          {formatCount(counts.parse_error_count, language)}
        </span>
      </div>
    </section>
  );
}

function RuntimeFact({
  label,
  value,
  detail,
  tone = "blue",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "green" | "blue" | "amber" | "red";
}) {
  return (
    <div className="runtime-fact" data-tone={tone}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function RuntimeRunRow({
  run,
  language,
  copy,
}: {
  run: ObservabilityRun;
  language: Language;
  copy: Copy;
}) {
  return (
    <div className="runtime-run" data-state={normalizeRuntimeState(run.state)}>
      <div className="runtime-run-head">
        <strong>{run.run_id ?? copy.common.unknown}</strong>
        <RuntimeStatePill state={run.state} copy={copy} />
      </div>
      <div className="runtime-run-grid">
        <span>
          {copy.runtime.latestHeartbeat}: {formatDuration(run.heartbeat_age_seconds, copy)}
        </span>
        <span>
          {copy.runtime.openState}: {copy.runtime.orders} {formatMaybeNumber(run.open_orders, language, copy)} /{" "}
          {copy.runtime.positions} {formatMaybeNumber(run.open_positions, language, copy)}
        </span>
        <span>
          {copy.runtime.alerts}: {formatCount(run.alert_total, language)}
        </span>
        <span>
          {copy.runtime.reason}: {run.state_reason ?? copy.common.unknown}
        </span>
      </div>
    </div>
  );
}

function RuntimeStatePill({ state, copy }: { state: string | undefined; copy: Copy }) {
  const normalized = normalizeRuntimeState(state);
  const labels = copy.runtime.states as Record<string, string>;
  return (
    <span className="runtime-state-pill" data-state={normalized}>
      {labels[normalized] ?? normalized}
    </span>
  );
}

function SignalSummaryPanel({
  signalSummary,
  language,
  copy,
}: {
  signalSummary: SignalSummary;
  language: Language;
  copy: Copy;
}) {
  const sourceRows = signalSummary.by_source_model ?? [];
  const runs = signalSummary.runs ?? [];
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.signalSummary}</h2>
        <span>
          {formatCount(signalSummary.bundle_count, language)} {copy.signal.attachedBundles}
        </span>
      </div>
      <div className="signal-facts">
        <RuntimeFact
          label={copy.signal.signals}
          value={formatCount(signalSummary.signal_rows, language)}
          detail={copy.signal.sourceModel}
          tone="blue"
        />
        <RuntimeFact
          label={copy.signal.accepted}
          value={formatCount(signalSummary.accepted_signals, language)}
          detail={formatSignalRate(signalSummary.accepted_signals, signalSummary.signal_rows, copy)}
          tone="green"
        />
        <RuntimeFact
          label={copy.signal.skipped}
          value={formatCount(signalSummary.skipped_signals, language)}
          detail={copy.signal.runLedger}
          tone={(signalSummary.skipped_signals ?? 0) > 0 ? "amber" : "green"}
        />
        <RuntimeFact
          label={copy.signal.rejections}
          value={formatCount(signalSummary.rejection_signals, language)}
          detail={formatReasonCounts(topReasonCounts(signalSummary.rejection_reason_counts), copy)}
          tone={(signalSummary.rejection_signals ?? 0) > 0 ? "red" : "green"}
        />
      </div>
      <div className="table-wrap signal-table-wrap">
        <table>
          <thead>
            <tr>
              <th>{copy.signal.sourceModel}</th>
              <th>{copy.signal.bundles}</th>
              <th>{copy.signal.signals}</th>
              <th>{copy.signal.accepted}</th>
              <th>{copy.signal.skipped}</th>
              <th>{copy.signal.topReasons}</th>
            </tr>
          </thead>
          <tbody>
            {sourceRows.length ? (
              sourceRows.slice(0, 6).map((row) => (
                <tr key={`${row.source ?? "unknown"}-${row.model_version ?? "unknown"}`}>
                  <td>
                    <strong>{row.source ?? copy.signal.unknownSource}</strong>
                    <br />
                    <small>{row.model_version ?? copy.signal.unknownModel}</small>
                  </td>
                  <td>{formatCount(row.bundle_count, language)}</td>
                  <td>{formatCount(row.signal_rows, language)}</td>
                  <td>{formatCount(row.accepted_signals, language)}</td>
                  <td>{formatCount(row.skipped_signals, language)}</td>
                  <td>{formatReasonCounts(row.top_rejection_reasons, copy)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6}>{copy.signal.noRows}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="signal-run-list">
        {runs.length ? (
          runs.slice(0, 4).map((run) => (
            <div className="signal-run" key={`${run.kind ?? "unknown"}-${run.run_id ?? "unknown"}`}>
              <strong>{run.run_id ?? copy.evidence.unknownRun}</strong>
              <span>
                {run.kind ?? copy.common.unknown} / {run.source ?? copy.signal.unknownSource}
              </span>
              <small>
                {copy.signal.accepted} {formatCount(run.accepted_signals, language)} / {copy.signal.rejections}{" "}
                {formatCount(run.rejection_signals, language)}
              </small>
            </div>
          ))
        ) : (
          <div className="runtime-empty">{copy.signal.noRuns}</div>
        )}
      </div>
    </section>
  );
}

function OpsSummary({ summary, copy }: { summary: string[]; copy: Copy }) {
  const items = summary.length ? summary : [copy.fallback.summary];
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.consoleBrief}</h2>
        <span>{summary.length ? `${summary.length} ${copy.common.checks}` : copy.common.fallback}</span>
      </div>
      <div className="brief-grid">
        {items.map((item) => (
          <div className="brief-item" key={item}>
            <span aria-hidden="true" />
            <p>{localizeKnown(item, copy)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function EvidenceMatrix({
  paperBundles,
  testnetBundles,
  language,
  copy,
}: {
  paperBundles: PaperBundle[];
  testnetBundles: TestnetBundle[];
  language: Language;
  copy: Copy;
}) {
  const cleanTestnet = testnetBundles.filter((bundle) => bundle.clean_for_retro).length;
  const paperFills = sum(paperBundles.map((bundle) => bundle.fills));
  const testnetFills = sum(testnetBundles.map((bundle) => bundle.fills));
  const alerts = sum(testnetBundles.map((bundle) => bundle.alert_count));

  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.evidenceMatrix}</h2>
        <span>{copy.sections.evidenceSubtitle}</span>
      </div>
      <div className="evidence-grid">
        <EvidenceBar
          label={copy.evidence.paperBundles}
          value={paperBundles.length}
          max={8}
          tone="blue"
          language={language}
        />
        <EvidenceBar label={copy.evidence.paperFills} value={paperFills} max={2000} tone="green" language={language} />
        <EvidenceBar
          label={copy.evidence.cleanTestnet}
          value={cleanTestnet}
          max={16}
          tone="green"
          language={language}
        />
        <EvidenceBar label={copy.evidence.testnetAlerts} value={alerts} max={12} tone="red" language={language} />
        <EvidenceBar
          label={copy.evidence.testnetFills}
          value={testnetFills}
          max={48}
          tone="amber"
          language={language}
        />
      </div>
      <div className="bundle-ledger">
        <BundleList title={copy.evidence.paper} bundles={paperBundles} copy={copy} />
        <BundleList title={copy.evidence.testnet} bundles={testnetBundles} copy={copy} />
      </div>
    </section>
  );
}

function EvidenceBar({
  label,
  value,
  max,
  tone,
  language,
}: {
  label: string;
  value: number;
  max: number;
  tone: "green" | "blue" | "amber" | "red";
  language: Language;
}) {
  const width = Math.min(Math.max((value / max) * 100, value > 0 ? 7 : 0), 100);
  return (
    <div className="evidence-row" data-tone={tone}>
      <div>
        <span>{label}</span>
        <strong>{formatCount(value, language)}</strong>
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
  copy,
}: {
  title: string;
  bundles: Array<PaperBundle | TestnetBundle>;
  copy: Copy;
}) {
  return (
    <div className="ledger-column">
      <strong>{title}</strong>
      {bundles.length ? (
        bundles.slice(0, 4).map((bundle) => (
          <div className="ledger-row" key={bundle.run_id ?? `${title}-unknown`}>
            <span>{bundle.run_id ?? copy.evidence.unknownRun}</span>
            <small>{bundle.recommendation ?? copy.evidence.noRecommendation}</small>
          </div>
        ))
      ) : (
        <div className="ledger-row">
          <span>{copy.evidence.noBundles}</span>
          <small>{copy.evidence.attachBundles}</small>
        </div>
      )}
    </div>
  );
}

function AdviceTable({
  rows,
  language,
  copy,
}: {
  rows: AdviceRow[];
  language: Language;
  copy: Copy;
}) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.agentAdviceQueue}</h2>
        <span>{rows.length ? `${formatCount(rows.length, language)} ${copy.advice.latestRows}` : copy.advice.noRowsSnapshot}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{copy.advice.agent}</th>
              <th>{copy.advice.type}</th>
              <th>{copy.advice.status}</th>
              <th>{copy.advice.confidence}</th>
              <th>{copy.advice.summary}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.slice(0, 10).map((row) => (
                <tr key={row.advice_id ?? `${row.agent_name}-${row.created_at_ns}`}>
                  <td>{row.agent_name ?? copy.common.unknown}</td>
                  <td>{row.advice_type ?? copy.common.unknown}</td>
                  <td>
                    <StatusPill value={row.status ?? "unknown"} copy={copy} />
                  </td>
                  <td>{formatConfidence(row.confidence, copy)}</td>
                  <td>{row.summary ?? copy.advice.noSummary}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>{copy.advice.noRows}</td>
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
  copy,
}: {
  items: NonNullable<DashboardSnapshot["operator_checklist"]>;
  copy: Copy;
}) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.operatorChecklist}</h2>
        <span>
          {items.length} {copy.checklist.items}
        </span>
      </div>
      <div className="checklist">
        {items.map((item) => (
          <div className="check-row" data-status={normalizeChecklist(item.status)} key={item.label}>
            <strong>{localizeKnown(item.label, copy) || copy.checklist.item}</strong>
            <StatusPill value={item.status ?? "unknown"} copy={copy} />
            <p>{localizeKnown(item.detail, copy) || copy.checklist.noDetail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function WatchlistPanel({
  blocked,
  nextSteps,
  copy,
}: {
  blocked: string[];
  nextSteps: string[];
  copy: Copy;
}) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.watchlist}</h2>
        <span>{formatWatchlistCount(blocked.length, nextSteps.length, copy)}</span>
      </div>
      <ListBlock title={copy.watchlist.blockedDeferred} items={blocked} empty={copy.watchlist.noBlockers} />
      <ListBlock title={copy.watchlist.nextSteps} items={nextSteps} empty={copy.watchlist.noNextSteps} />
    </section>
  );
}

function VerificationPanel({ items, copy }: { items: string[]; copy: Copy }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.verification}</h2>
        <span>{items.length ? copy.verification.latestBlock : copy.verification.none}</span>
      </div>
      <ListBlock title={copy.verification.latestChecks} items={items} empty={copy.verification.noItems} />
    </section>
  );
}

function ReferenceLinksPanel({ links, copy }: { links: ReferenceLink[]; copy: Copy }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.referenceLinks}</h2>
        <span>{links.length ? `${links.length} ${copy.reference.subtitle}` : copy.reference.localOnly}</span>
      </div>
      <div className="reference-list">
        {links.length ? (
          links.slice(0, 8).map((link) => (
            <ReferenceLinkRow
              copy={copy}
              key={`${link.group ?? "unknown"}-${link.label ?? link.path ?? link.href ?? "link"}`}
              link={link}
            />
          ))
        ) : (
          <div className="reference-row" data-linkable="false">
            <div className="reference-row-head">
              <strong>{copy.reference.noLinks}</strong>
              <span>{copy.reference.localOnly}</span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function ReferenceLinkRow({ link, copy }: { link: ReferenceLink; copy: Copy }) {
  const href = typeof link.href === "string" && isWebHref(link.href) ? link.href : null;
  const content = (
    <>
      <div className="reference-row-head">
        <strong>{link.label ?? copy.common.unknown}</strong>
        <span>
          {localizeReferenceGroup(link.group, copy)} / {localizeReferenceKind(link.kind, copy)}
        </span>
      </div>
      {link.detail ? <p>{link.detail}</p> : null}
      <div className="reference-target">
        <small>{href ? copy.reference.open : copy.reference.sourcePath}</small>
        <code>{link.path ?? link.href ?? copy.common.unknown}</code>
      </div>
    </>
  );

  if (href) {
    return (
      <a className="reference-row" data-linkable="true" href={href} rel="noreferrer" target="_blank">
        {content}
      </a>
    );
  }

  return (
    <div className="reference-row" data-linkable="false">
      {content}
    </div>
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

function BoundaryPanel({ boundaries, copy }: { boundaries: Record<string, boolean>; copy: Copy }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{copy.sections.boundaryLedger}</h2>
        <span>{copy.boundary.mustRemainFalse}</span>
      </div>
      <div className="boundary-list">
        {BOUNDARY_KEYS.map((key) => {
          const allowed = boundaries[key] === true;
          return (
            <div className="boundary-row" key={key} data-open={String(allowed)}>
              <span>{copy.boundaries[key]}</span>
              <strong>{allowed ? copy.boundary.open : copy.boundary.closed}</strong>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function StatusPill({ value, copy }: { value: string; copy: Copy }) {
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
      {localizeStatus(value, copy)}
    </span>
  );
}

function resolveLanguage(value: string | string[] | undefined): Language {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate === "zh-CN" ? "zh-CN" : "en";
}

function normalizeState(value: unknown): "guarded" | "attention" | "breach" {
  if (value === "breach" || value === "attention" || value === "guarded") {
    return value;
  }
  return "attention";
}

function labelState(value: "guarded" | "attention" | "breach", copy: Copy): string {
  return copy.states[value];
}

function normalizeRuntimeState(value: string | undefined): "healthy" | "stale" | "attention" | "disconnected" | "unknown" {
  if (value === "healthy" || value === "stale" || value === "attention" || value === "disconnected") {
    return value;
  }
  return "unknown";
}

function normalizeChecklist(value: string | undefined): string {
  return value ?? "unknown";
}

function localizeKnown(value: string | undefined | null, copy: Copy): string {
  if (!value) {
    return "";
  }
  const known = copy.known as Record<string, string>;
  return known[value] ?? value;
}

function localizeStatus(value: string | undefined | null, copy: Copy): string {
  if (!value) {
    return copy.common.unknown;
  }
  const labels = copy.statusValues as Record<string, string>;
  return labels[value] ?? localizeKnown(value, copy);
}

function totalBlockers(counts: Record<string, number>): number {
  return (
    (counts.boundary_open_count ?? 0) +
    (counts.paper_review_blockers ?? 0) +
    (counts.paper_promotion_blockers ?? 0) +
    (counts.testnet_review_blockers ?? 0)
  );
}

function formatAdviceDetail(countTypes: number, recorded: number, language: Language, copy: Copy): string {
  if (language === "zh-CN") {
    return `${formatCount(countTypes, language)} ${copy.common.types} / ${formatCount(recorded, language)} ${
      copy.common.recorded
    }`;
  }
  return `${formatCount(countTypes, language)} ${copy.common.types} / ${formatCount(recorded, language)} ${
    copy.common.recorded
  }`;
}

function formatEvidenceInputDetail(paper: number, testnet: number, language: Language, copy: Copy): string {
  return `${formatCount(paper, language)} ${copy.common.paper} / ${formatCount(testnet, language)} ${
    copy.common.testnet
  }`;
}

function formatWatchlistCount(blocked: number, nextSteps: number, copy: Copy): string {
  if (copy === COPY["zh-CN"]) {
    return `${blocked} 个阻塞 / ${nextSteps} 个下一步`;
  }
  return `${blocked} blocked / ${nextSteps} next`;
}

function runtimeTone(value: string | undefined): "green" | "blue" | "amber" | "red" {
  const state = normalizeRuntimeState(value);
  if (state === "healthy") {
    return "green";
  }
  if (state === "stale" || state === "disconnected") {
    return "red";
  }
  return state === "attention" ? "amber" : "blue";
}

function runtimeLagTone(value: number | null | undefined, staleAfter: number | undefined): "green" | "blue" | "amber" | "red" {
  if (typeof value !== "number") {
    return "blue";
  }
  const threshold = staleAfter ?? 120;
  if (value <= threshold) {
    return "green";
  }
  return value <= threshold * 3 ? "amber" : "red";
}

function localizeReferenceGroup(value: string | undefined, copy: Copy): string {
  if (!value) {
    return copy.common.unknown;
  }
  const labels = copy.reference.groups as Record<string, string>;
  return labels[value] ?? value;
}

function localizeReferenceKind(value: string | undefined, copy: Copy): string {
  if (!value) {
    return copy.common.unknown;
  }
  const labels = copy.reference.kinds as Record<string, string>;
  return labels[value] ?? value;
}

function isWebHref(value: string): boolean {
  return value.startsWith("https://") || value.startsWith("http://");
}

function formatCount(value: number | undefined, language: Language): string {
  return new Intl.NumberFormat(language === "zh-CN" ? "zh-CN" : "en-US").format(value ?? 0);
}

function formatMaybeNumber(value: number | null | undefined, language: Language, copy: Copy): string {
  return typeof value === "number" ? formatCount(value, language) : copy.common.nA;
}

function formatSignalRate(value: number | undefined, total: number | undefined, copy: Copy): string {
  if (!total) {
    return copy.common.nA;
  }
  return `${Math.round(((value ?? 0) / total) * 100)}%`;
}

function topReasonCounts(counts: Record<string, number> | undefined): SignalReasonCount[] {
  return Object.entries(counts ?? {})
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([reason, count]) => ({ reason, count }));
}

function formatReasonCounts(values: SignalReasonCount[] | undefined, copy: Copy): string {
  if (!values?.length) {
    return copy.signal.noReasons;
  }
  return values
    .map((item) => `${localizeSignalReason(item.reason, copy)} ${item.count ?? 0}`)
    .join(" / ");
}

function localizeSignalReason(value: string | undefined, copy: Copy): string {
  if (!value) {
    return copy.common.unknown;
  }
  const labels = copy.signal.reasons as Record<string, string>;
  return labels[value] ?? value;
}

function formatDuration(value: number | null | undefined, copy: Copy): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return copy.common.nA;
  }
  if (value < 60) {
    return `${Math.round(value)}s`;
  }
  if (value < 3600) {
    return `${Math.round(value / 60)}m`;
  }
  if (value < 86_400) {
    return `${Math.round(value / 3600)}h`;
  }
  return `${Math.round(value / 86_400)}d`;
}

function formatWs(value: boolean | null | undefined, copy: Copy): string {
  if (value === true) {
    return copy.runtime.connected;
  }
  if (value === false) {
    return copy.runtime.disconnected;
  }
  return copy.runtime.unknown;
}

function formatConfidence(value: number | undefined, copy: Copy): string {
  if (typeof value !== "number") {
    return copy.common.nA;
  }
  return `${Math.round(value * 100)}%`;
}

function formatGenerated(value: DashboardSnapshot["generated_at_ns"], copy: Copy): string {
  if (value === null || value === undefined) {
    return copy.generated.notGenerated;
  }
  const raw = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(raw)) {
    return copy.generated.unknown;
  }
  const date = new Date(Math.floor(raw / 1_000_000));
  return date.toISOString().replace("T", " ").slice(0, 19);
}

function sum(values: Array<number | undefined>): number {
  return values.reduce<number>((total, value) => total + (value ?? 0), 0);
}
