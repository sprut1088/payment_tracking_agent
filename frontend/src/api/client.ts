// API client for the ACH Payment Tracking Agent frontend demo shell.
// Most pages still use mock fixtures, while local-folder demo-flow controls
// call the backend HTTP endpoints under /api/demo-flow.

import type {
  AgentTraceStep,
  BatchSummary,
  CustomerSummary,
  DemoFlowConfig,
  DemoFlowScanResult,
  DemoFlowState,
  DashboardResponse,
  EvidenceRef,
  PaymentRecord,
  Scenario,
  SimulationState,
  StatusHistoryEvent,
} from "../types/api";

// ---------------------------------------------------------------------------
// Scenario fixtures
// ---------------------------------------------------------------------------

const scenarios: Scenario[] = [
  {
    id: "scenario-accelerated-2min",
    name: "Accelerated demo — 2 minute cycles",
    description:
      "10:00 uploads 20 payments (18 cleared, 2 held). 10:02 uploads 15 payments (12 cleared) and a return file resolves the 2 held payments to REJECTED.",
    cycleSchedule: ["10:00", "10:02", "10:04", "10:06"],
    mode: "ACCELERATED_2MIN",
  },
  {
    id: "scenario-real-day",
    name: "Real day — 10:00 / 14:00 / 18:00 GMT",
    description:
      "Realistic bank day using the three real ACH cycles. Same lifecycle events as the accelerated demo, on real GMT times.",
    cycleSchedule: ["10:00", "14:00", "18:00"],
    mode: "REAL_DAY",
  },
];

// ---------------------------------------------------------------------------
// Payment fixtures for the accelerated 2-minute scenario
// ---------------------------------------------------------------------------

const CUSTOMERS: Array<{ id: string; name: string; dfi: string; account: string }> = [
  { id: "CUS-1001", name: "Riverbend Manufacturing", dfi: "021000021", account: "****4821" },
  { id: "CUS-1002", name: "Blue Harbor Logistics", dfi: "011000015", account: "****9330" },
  { id: "CUS-1003", name: "Northwind Grocers", dfi: "026009593", account: "****1177" },
  { id: "CUS-1004", name: "Cedar Peak Contractors", dfi: "031201360", account: "****6042" },
  { id: "CUS-1005", name: "Silverline Software", dfi: "121000248", account: "****2288" },
];

const BENEFICIARIES = [
  "APEX PAYROLL SERVICES",
  "GLOBAL LEASING CORP",
  "STATEWIDE UTILITIES",
  "PACIFIC BENEFITS INC",
  "MIDLAND SUPPLY CO",
];

const ccdEvidence = (file: string): EvidenceRef => ({
  kind: "CCD",
  sourceFile: file,
  summary: `Entry detail record parsed from ${file}`,
});

const engineEvidence = (file: string): EvidenceRef => ({
  kind: "PROCESSING_ENGINE",
  sourceFile: file,
  summary: `Processing engine accepted entry from ${file}`,
});

const settlementEvidence = (file: string): EvidenceRef => ({
  kind: "SETTLEMENT",
  sourceFile: file,
  summary: `Trace present in cleared trace list attached to ${file}`,
});

const returnEvidence = (file: string, code: string): EvidenceRef => ({
  kind: "RETURN",
  sourceFile: file,
  summary: `NACHA return code ${code} matched on original trace`,
});

interface PaymentSeed {
  trace: string;
  customerIndex: number;
  beneficiaryIndex: number;
  amount: number;
  outcome: "CLEARED" | "WITH_BENEFICIARY_BANK" | "REJECTED";
  returnCode?: string;
  riskLevel?: PaymentRecord["riskLevel"];
  riskReason?: string;
}

const cycle1Seeds: PaymentSeed[] = Array.from({ length: 20 }, (_, i) => ({
  trace: `10000100${(i + 1).toString().padStart(2, "0")}`,
  customerIndex: i % CUSTOMERS.length,
  beneficiaryIndex: i % BENEFICIARIES.length,
  amount: 1250 + i * 145.5,
  outcome: i < 18 ? "CLEARED" : "WITH_BENEFICIARY_BANK",
  riskLevel: i === 18 ? "MEDIUM" : i === 19 ? "HIGH" : "LOW",
  riskReason:
    i === 18
      ? "Beneficiary has 1 prior R03 in last 90 days"
      : i === 19
        ? "Customer has 3 prior R01 (insufficient funds) in last 60 days"
        : undefined,
}));

// Cycle 1 held payments (indexes 18, 19) get resolved to REJECTED by the return
// file that arrives during cycle 2. We flip their outcome after cycle 2 runs.
const cycle1RejectedByCycle2 = new Set(["1000010019", "1000010020"]);

const cycle2Seeds: PaymentSeed[] = Array.from({ length: 15 }, (_, i) => ({
  trace: `10000200${(i + 1).toString().padStart(2, "0")}`,
  customerIndex: (i + 2) % CUSTOMERS.length,
  beneficiaryIndex: (i + 1) % BENEFICIARIES.length,
  amount: 875 + i * 210.25,
  outcome: i < 12 ? "CLEARED" : "WITH_BENEFICIARY_BANK",
  riskLevel: i === 14 ? "MEDIUM" : "LOW",
  riskReason:
    i === 14 ? "Beneficiary added within the last 7 days" : undefined,
}));

function buildStatusHistory(
  seed: PaymentSeed,
  batchId: string,
  cycleTime: string,
  ccdFile: string,
  settlementFile: string,
  returnFile: string | undefined,
  finalStatus: PaymentRecord["currentStatus"],
): StatusHistoryEvent[] {
  const base: StatusHistoryEvent[] = [
    {
      timestamp: `${cycleTime}:05`,
      status: "WITH BANK",
      internalStatus: "WITH_BANK_UPLOADED",
      source: ccdEvidence(ccdFile),
      agent: "BeforePaymentSubmissionAgent",
      reason: `Entry detail parsed from ${ccdFile} into batch ${batchId}`,
    },
    {
      timestamp: `${cycleTime}:12`,
      status: "WITH BANK",
      internalStatus: "WITH_BANK_READY_FOR_SCHEME",
      source: ccdEvidence(ccdFile),
      agent: "BeforePaymentSubmissionAgent",
      reason: "Syntax validation passed and historical risk check complete",
    },
    {
      timestamp: `${cycleTime}:20`,
      status: "WITH SCHEME",
      internalStatus: "WITH_SCHEME_SUBMITTED",
      source: engineEvidence(ccdFile),
      agent: "AfterPaymentSubmissionAgent",
      reason: "Processing engine acknowledged submission to scheme",
    },
  ];

  if (finalStatus === "CLEARED") {
    base.push({
      timestamp: `${cycleTime}:45`,
      status: "CLEARED",
      internalStatus: "CLEARED_BY_SETTLEMENT",
      source: settlementEvidence(settlementFile),
      agent: "AfterPaymentSubmissionAgent",
      reason: "Trace number present in cleared trace list for this cycle",
    });
  } else if (finalStatus === "WITH BENEFICIARY BANK") {
    base.push({
      timestamp: `${cycleTime}:46`,
      status: "WITH BENEFICIARY BANK",
      internalStatus: "WITH_BENEFICIARY_BANK_PENDING",
      source: settlementEvidence(settlementFile),
      agent: "AfterPaymentSubmissionAgent",
      reason:
        "Submitted to scheme but trace not present in settlement and no return received",
    });
  } else if (finalStatus === "REJECTED") {
    base.push({
      timestamp: `${cycleTime}:46`,
      status: "WITH BENEFICIARY BANK",
      internalStatus: "WITH_BENEFICIARY_BANK_PENDING",
      source: settlementEvidence(settlementFile),
      agent: "AfterPaymentSubmissionAgent",
      reason:
        "Submitted to scheme but trace not present in settlement — awaiting return or clearing",
    });
    if (returnFile && seed.returnCode) {
      base.push({
        timestamp: "10:02:35",
        status: "REJECTED",
        internalStatus: "REJECTED_BY_RETURN_FILE",
        source: returnEvidence(returnFile, seed.returnCode),
        agent: "ReturnFileAgent",
        reason: `NACHA return code ${seed.returnCode} received; original trace matched`,
      });
    }
  }

  return base;
}

function buildPayment(
  seed: PaymentSeed,
  batchId: string,
  cycleTime: string,
  ccdFile: string,
  settlementFile: string,
  returnFile: string | undefined,
): PaymentRecord {
  const customer = CUSTOMERS[seed.customerIndex];
  const isRejected = returnFile !== undefined && cycle1RejectedByCycle2.has(seed.trace);
  const outcome: PaymentRecord["currentStatus"] = isRejected
    ? "REJECTED"
    : seed.outcome === "CLEARED"
      ? "CLEARED"
      : seed.outcome === "WITH_BENEFICIARY_BANK"
        ? "WITH BENEFICIARY BANK"
        : "REJECTED";

  const returnCode = isRejected
    ? seed.trace.endsWith("19")
      ? "R01"
      : "R03"
    : seed.returnCode;

  const enrichedSeed: PaymentSeed = { ...seed, returnCode };
  const history = buildStatusHistory(
    enrichedSeed,
    batchId,
    cycleTime,
    ccdFile,
    settlementFile,
    isRejected ? returnFile : undefined,
    outcome,
  );

  const internal = history[history.length - 1].internalStatus;
  const evidence: EvidenceRef[] = history.map((h) => h.source);

  return {
    paymentId: `PAY-${seed.trace}`,
    traceNumber: seed.trace,
    batchId,
    cycleTime,
    sourceFile: ccdFile,
    companyId: "COMP-9001",
    customerId: customer.id,
    customerName: customer.name,
    beneficiaryName: BENEFICIARIES[seed.beneficiaryIndex],
    receivingDfi: customer.dfi,
    maskedAccount: customer.account,
    amount: Number(seed.amount.toFixed(2)),
    currency: "USD",
    currentStatus: outcome,
    internalStatus: internal,
    statusSince: history[history.length - 1].timestamp,
    statusHistory: history,
    returnReasonCode: returnCode,
    riskLevel: seed.riskLevel ?? "LOW",
    riskReason: seed.riskReason,
    recommendedAction:
      outcome === "REJECTED"
        ? returnCode === "R01"
          ? "Contact customer to confirm funding, then re-originate."
          : "Verify beneficiary account details before re-origination."
        : outcome === "WITH BENEFICIARY BANK"
          ? "No action required. Awaiting settlement or return."
          : "None. Payment cleared normally.",
    customerFriendlyMessage:
      outcome === "REJECTED"
        ? returnCode === "R01"
          ? "The payment could not complete because the receiving account had insufficient funds."
          : "The payment could not complete because the receiving account details did not match."
        : outcome === "WITH BENEFICIARY BANK"
          ? "The payment has reached the beneficiary bank and is awaiting confirmation."
          : "The payment was completed successfully.",
    evidence,
  };
}

const CYCLE1_BATCH = "BATCH-2026-07-01-10-00";
const CYCLE2_BATCH = "BATCH-2026-07-01-10-02";
const CYCLE1_CCD = "customer-upload-1000.ccd";
const CYCLE2_CCD = "customer-upload-1002.ccd";
const CYCLE1_SETTLE = "settlement-1000.fedach";
const CYCLE2_SETTLE = "settlement-1002.fedach";
const CYCLE2_RETURN = "return-1002.nacha";

const cycle1Payments = cycle1Seeds.map((s) =>
  buildPayment(s, CYCLE1_BATCH, "10:00", CYCLE1_CCD, CYCLE1_SETTLE, CYCLE2_RETURN),
);

const cycle2Payments = cycle2Seeds.map((s) =>
  buildPayment(s, CYCLE2_BATCH, "10:02", CYCLE2_CCD, CYCLE2_SETTLE, undefined),
);

const allPayments: PaymentRecord[] = [...cycle1Payments, ...cycle2Payments];

// ---------------------------------------------------------------------------
// Aggregations
// ---------------------------------------------------------------------------

function summarizeBatch(batchId: string, cycleTime: string, sourceFile: string): BatchSummary {
  const rows = allPayments.filter((p) => p.batchId === batchId);
  const count = (status: PaymentRecord["currentStatus"]) =>
    rows.filter((r) => r.currentStatus === status).length;
  return {
    batchId,
    cycleTime,
    sourceFile,
    paymentCount: rows.length,
    withBank: count("WITH BANK"),
    withScheme: count("WITH SCHEME"),
    withBeneficiaryBank: count("WITH BENEFICIARY BANK"),
    cleared: count("CLEARED"),
    rejected: count("REJECTED"),
  };
}

function summarizeCustomers(): CustomerSummary[] {
  const byCustomer = new Map<string, PaymentRecord[]>();
  for (const p of allPayments) {
    const list = byCustomer.get(p.customerId) ?? [];
    list.push(p);
    byCustomer.set(p.customerId, list);
  }
  return Array.from(byCustomer.entries()).map(([customerId, rows]) => {
    const cleared = rows.filter((r) => r.currentStatus === "CLEARED").length;
    const rejected = rows.filter((r) => r.currentStatus === "REJECTED").length;
    const withBeneficiaryBank = rows.filter(
      (r) => r.currentStatus === "WITH BENEFICIARY BANK",
    ).length;
    const lastRejection = rows
      .filter((r) => r.currentStatus === "REJECTED")
      .map((r) => r.statusSince)
      .sort()
      .at(-1);
    return {
      customerId,
      customerName: rows[0].customerName,
      totalPayments: rows.length,
      cleared,
      rejected,
      withBeneficiaryBank,
      lastRejectionDate: lastRejection,
      historicalRejectionCount: rejected + (customerId === "CUS-1004" ? 2 : 0),
    };
  });
}

const simulationState: SimulationState = {
  scenarioId: scenarios[0].id,
  currentSimTime: "10:02",
  activeCycle: "10:02",
  plan: [
    {
      cycleTime: "10:00",
      label: "Upload 20-payment CCD, settle 18, hold 2",
      ccdFile: CYCLE1_CCD,
      expectedCleared: 18,
      expectedWithBeneficiaryBank: 2,
      expectedRejectedFromPriorCycle: 0,
    },
    {
      cycleTime: "10:02",
      label: "Upload 15-payment CCD, settle 12, return file rejects 2 prior",
      ccdFile: CYCLE2_CCD,
      returnFile: CYCLE2_RETURN,
      expectedCleared: 12,
      expectedWithBeneficiaryBank: 3,
      expectedRejectedFromPriorCycle: 2,
    },
    {
      cycleTime: "10:04",
      label: "Awaiting further batches (not yet run)",
      expectedCleared: 0,
      expectedWithBeneficiaryBank: 0,
      expectedRejectedFromPriorCycle: 0,
    },
    {
      cycleTime: "10:06",
      label: "Awaiting further batches (not yet run)",
      expectedCleared: 0,
      expectedWithBeneficiaryBank: 0,
      expectedRejectedFromPriorCycle: 0,
    },
  ],
  runs: [
    {
      cycleTime: "10:00",
      status: "COMPLETE",
      paymentsCreated: 20,
      cleared: 18,
      withBeneficiaryBank: 2,
      rejectedFromPriorCycle: 0,
      ranAt: "10:00:00",
    },
    {
      cycleTime: "10:02",
      status: "COMPLETE",
      paymentsCreated: 15,
      cleared: 12,
      withBeneficiaryBank: 3,
      rejectedFromPriorCycle: 2,
      ranAt: "10:02:00",
    },
    {
      cycleTime: "10:04",
      status: "PENDING",
      paymentsCreated: 0,
      cleared: 0,
      withBeneficiaryBank: 0,
      rejectedFromPriorCycle: 0,
    },
    {
      cycleTime: "10:06",
      status: "PENDING",
      paymentsCreated: 0,
      cleared: 0,
      withBeneficiaryBank: 0,
      rejectedFromPriorCycle: 0,
    },
  ],
  summary: {
    totalPayments: allPayments.length,
    withBank: allPayments.filter((p) => p.currentStatus === "WITH BANK").length,
    withScheme: allPayments.filter((p) => p.currentStatus === "WITH SCHEME").length,
    withBeneficiaryBank: allPayments.filter(
      (p) => p.currentStatus === "WITH BENEFICIARY BANK",
    ).length,
    cleared: allPayments.filter((p) => p.currentStatus === "CLEARED").length,
    rejected: allPayments.filter((p) => p.currentStatus === "REJECTED").length,
  },
  events: [
    {
      timestamp: "10:00:05",
      cycleTime: "10:00",
      agent: "BeforePaymentSubmissionAgent",
      message: `Parsed ${CYCLE1_CCD}: 20 entry details, 0 syntax errors, 2 historical-risk flags`,
    },
    {
      timestamp: "10:00:20",
      cycleTime: "10:00",
      agent: "AfterPaymentSubmissionAgent",
      message: "Processing engine acknowledged submission of 20 entries to scheme",
    },
    {
      timestamp: "10:00:45",
      cycleTime: "10:00",
      agent: "AfterPaymentSubmissionAgent",
      message:
        "Settlement report loaded: 18 traces cleared, 2 traces not present — held as WITH BENEFICIARY BANK",
    },
    {
      timestamp: "10:02:05",
      cycleTime: "10:02",
      agent: "BeforePaymentSubmissionAgent",
      message: `Parsed ${CYCLE2_CCD}: 15 entry details, 0 syntax errors, 1 historical-risk flag`,
    },
    {
      timestamp: "10:02:35",
      cycleTime: "10:02",
      agent: "ReturnFileAgent",
      message:
        "NACHA return file processed: 2 original traces from 10:00 batch matched (R01, R03) — status set to REJECTED",
    },
    {
      timestamp: "10:02:45",
      cycleTime: "10:02",
      agent: "AfterPaymentSubmissionAgent",
      message:
        "Settlement report loaded: 12 traces cleared, 3 traces held as WITH BENEFICIARY BANK",
    },
  ],
};

const agentTrace: AgentTraceStep[] = [
  {
    timestamp: "10:00:05",
    agent: "BeforePaymentSubmissionAgent",
    action: "parse_ccd",
    detail: `${CYCLE1_CCD}: 1 file header, 1 batch header, 20 entry details, 1 batch control, 1 file control`,
  },
  {
    timestamp: "10:00:07",
    agent: "BeforePaymentSubmissionAgent",
    action: "syntax_validate",
    detail: "All 20 records passed syntax validation",
  },
  {
    timestamp: "10:00:09",
    agent: "BeforePaymentSubmissionAgent",
    action: "historical_risk_scan",
    detail: "Flagged 2 payments (1 MEDIUM, 1 HIGH) based on prior returns",
  },
  {
    timestamp: "10:00:20",
    agent: "AfterPaymentSubmissionAgent",
    action: "submit_to_scheme",
    detail: "Processing engine acknowledged 20/20 entries",
  },
  {
    timestamp: "10:00:45",
    agent: "AfterPaymentSubmissionAgent",
    action: "reconcile_settlement",
    detail: "18 cleared, 2 held WITH BENEFICIARY BANK (no settlement, no return)",
  },
  {
    timestamp: "10:02:05",
    agent: "BeforePaymentSubmissionAgent",
    action: "parse_ccd",
    detail: `${CYCLE2_CCD}: 15 entry details parsed`,
  },
  {
    timestamp: "10:02:35",
    agent: "ReturnFileAgent",
    action: "match_returns",
    detail:
      "2 returns matched to original traces 1000010019 (R01) and 1000010020 (R03) from 10:00 batch",
  },
  {
    timestamp: "10:02:45",
    agent: "AfterPaymentSubmissionAgent",
    action: "reconcile_settlement",
    detail: "12 cleared, 3 held WITH BENEFICIARY BANK",
  },
  {
    timestamp: "10:02:50",
    agent: "AIExplanationAgent",
    action: "explain_rejections",
    detail: "Generated customer-safe messages for 2 rejected payments (R01, R03)",
  },
];

// ---------------------------------------------------------------------------
// Public API (mock fixtures + backend demo-flow endpoints)
// ---------------------------------------------------------------------------

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 50));
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Ignore JSON parsing errors and keep default detail.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

async function requestNoContent(url: string, init?: RequestInit): Promise<void> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Ignore JSON parsing errors and keep default detail.
    }
    throw new Error(detail);
  }
}

export const api = {
  listScenarios(): Promise<Scenario[]> {
    return delay(scenarios);
  },

  getSimulationState(): Promise<SimulationState> {
    return delay(simulationState);
  },

  getAgentTrace(): Promise<AgentTraceStep[]> {
    return delay(agentTrace);
  },

  getBatchDashboard(): Promise<DashboardResponse<BatchSummary>> {
    return delay({
      generatedAt: "10:02:50",
      rows: [
        summarizeBatch(CYCLE1_BATCH, "10:00", CYCLE1_CCD),
        summarizeBatch(CYCLE2_BATCH, "10:02", CYCLE2_CCD),
      ],
    });
  },

  getCustomerDashboard(): Promise<DashboardResponse<CustomerSummary>> {
    return delay({ generatedAt: "10:02:50", rows: summarizeCustomers() });
  },

  listPayments(): Promise<PaymentRecord[]> {
    return delay(allPayments);
  },

  getPayment(paymentId: string): Promise<PaymentRecord | undefined> {
    return delay(allPayments.find((p) => p.paymentId === paymentId));
  },

  searchPayments(query: string): Promise<PaymentRecord[]> {
    const q = query.trim().toLowerCase();
    if (!q) return delay(allPayments);
    return delay(
      allPayments.filter(
        (p) =>
          p.paymentId.toLowerCase().includes(q) ||
          p.traceNumber.toLowerCase().includes(q) ||
          p.customerName.toLowerCase().includes(q) ||
          p.customerId.toLowerCase().includes(q) ||
          p.beneficiaryName.toLowerCase().includes(q) ||
          p.batchId.toLowerCase().includes(q),
      ),
    );
  },

  getDemoFlowConfig(): Promise<DemoFlowConfig> {
    return requestJson<DemoFlowConfig>("/api/demo-flow/config");
  },

  ensureDemoFlowFolders(): Promise<DemoFlowConfig> {
    return requestJson<DemoFlowConfig>("/api/demo-flow/ensure-folders", {
      method: "POST",
    });
  },

  scanDemoFlowCcd(): Promise<DemoFlowScanResult> {
    return requestJson<DemoFlowScanResult>("/api/demo-flow/scan-ccd", {
      method: "POST",
    });
  },

  checkDemoFlowSettlement(): Promise<DemoFlowScanResult> {
    return requestJson<DemoFlowScanResult>("/api/demo-flow/check-settlement", {
      method: "POST",
    });
  },

  checkDemoFlowReturns(): Promise<DemoFlowScanResult> {
    return requestJson<DemoFlowScanResult>("/api/demo-flow/check-returns", {
      method: "POST",
    });
  },

  getDemoFlowState(): Promise<DemoFlowState> {
    return requestJson<DemoFlowState>("/api/demo-flow/state");
  },

  resetDemoFlow(): Promise<void> {
    return requestNoContent("/api/demo-flow/reset", { method: "POST" });
  },
};

export type Api = typeof api;
