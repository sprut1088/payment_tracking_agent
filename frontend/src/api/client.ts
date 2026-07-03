// API client for the ACH Payment Tracking Agent frontend demo shell.
// Dashboards use SME-aligned mock fixtures, while local-folder demo-flow
// controls call backend HTTP endpoints under /api/demo-flow.

import type {
  AgentTraceStep,
  BatchSummary,
  CustomerSummary,
  DemoFlowConfig,
  DemoFlowScanResult,
  DemoFlowState,
  DashboardResponse,
  EvidenceRef,
  PaymentLedgerView,
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
    id: "scenario-sme-local-demo",
    name: "SME-aligned local demo - 11:00 / 11:04",
    description:
      "11:00 uploads 4 payments ($400 total), receives settlement summary for $300 and scheme reject evidence for $100. 11:04 processes a NACHA return for one prior payment.",
    cycleSchedule: ["11:00", "11:04", "11:08"],
    mode: "ACCELERATED_4MIN",
  },
];

// ---------------------------------------------------------------------------
// Payment fixtures for the SME-confirmed story
// ---------------------------------------------------------------------------

const CUSTOMERS: Array<{ id: string; name: string; dfi: string; account: string }> = [
  { id: "CUS-3001", name: "Harbor Steel Works", dfi: "021000021", account: "****1041" },
  { id: "CUS-3002", name: "Blue Ridge Clinics", dfi: "011000015", account: "****5572" },
  { id: "CUS-3003", name: "Northline Components", dfi: "026009593", account: "****8830" },
  { id: "CUS-3004", name: "Cedar Freight Group", dfi: "031201360", account: "****2406" },
];

const BENEFICIARIES = [
  "ACME VENDOR SERVICES",
  "ORION BENEFITS LLC",
  "PIONEER LOGISTICS LTD",
  "WATERFRONT PAYROLL INC",
];

const BATCH_11_00 = "BATCH-2026-07-03-11-00";
const CCD_11_00 = "ccd-batch-11-00.txt";
const SETTLEMENT_11_00 = "settlement-summary-11-00.rpt";
const SCHEME_REJECT_11_00 = "scheme-reject-11-00.txt";
const RETURN_11_04 = "returns-11-04.ach";

const ccdEvidence = (file: string): EvidenceRef => ({
  kind: "CCD",
  sourceFile: file,
  summary: `CCD entry detail captured from ${file}`,
});

const engineEvidence = (file: string): EvidenceRef => ({
  kind: "PROCESSING_ENGINE",
  sourceFile: file,
  summary: `Submission acknowledged by processing engine for ${file}`,
});

const settlementSummaryEvidence = (file: string): EvidenceRef => ({
  kind: "SETTLEMENT",
  sourceFile: file,
  summary:
    `Settlement summary ${file} received for aggregate amount only; no payment-level clearing is claimed from summary settlement evidence.`,
});

const schemeRejectEvidence = (file: string): EvidenceRef => ({
  kind: "SCHEME_REJECT",
  sourceFile: file,
  summary: `Scheme reject evidence in ${file} matched one submitted payment for $100.`,
});

const returnEvidence = (file: string, code: string): EvidenceRef => ({
  kind: "RETURN",
  sourceFile: file,
  summary: `Return file matched original trace with NACHA code ${code}.`,
});

type PaymentOutcome =
  | "WITH_BENEFICIARY_BANK"
  | "REJECTED_BY_SCHEME"
  | "REJECTED_BY_BENEFICIARY_BANK";

interface PaymentSeed {
  trace: string;
  customerIndex: number;
  beneficiaryIndex: number;
  amount: number;
  outcome: PaymentOutcome;
  returnCode?: string;
  riskLevel?: PaymentRecord["riskLevel"];
  riskReason?: string;
}

const paymentSeeds: PaymentSeed[] = [
  {
    trace: "110000001",
    customerIndex: 0,
    beneficiaryIndex: 0,
    amount: 100,
    outcome: "WITH_BENEFICIARY_BANK",
    riskLevel: "LOW",
  },
  {
    trace: "110000002",
    customerIndex: 1,
    beneficiaryIndex: 1,
    amount: 100,
    outcome: "WITH_BENEFICIARY_BANK",
    riskLevel: "LOW",
  },
  {
    trace: "110000003",
    customerIndex: 2,
    beneficiaryIndex: 2,
    amount: 100,
    outcome: "REJECTED_BY_BENEFICIARY_BANK",
    returnCode: "R01",
    riskLevel: "MEDIUM",
    riskReason: "Beneficiary had prior return pattern in last 60 days",
  },
  {
    trace: "110000004",
    customerIndex: 3,
    beneficiaryIndex: 3,
    amount: 100,
    outcome: "REJECTED_BY_SCHEME",
    returnCode: "SCH01",
    riskLevel: "LOW",
  },
];

function buildStatusHistory(seed: PaymentSeed): StatusHistoryEvent[] {
  const base: StatusHistoryEvent[] = [
    {
      timestamp: "11:00:05",
      status: "WITH BANK",
      internalStatus: "WITH_BANK_UPLOADED",
      source: ccdEvidence(CCD_11_00),
      agent: "BeforePaymentSubmissionAgent",
      reason: `Entry detail parsed from ${CCD_11_00} into batch ${BATCH_11_00}`,
    },
    {
      timestamp: "11:00:10",
      status: "WITH BANK",
      internalStatus: "WITH_BANK_VALIDATING",
      source: ccdEvidence(CCD_11_00),
      agent: "BeforePaymentSubmissionAgent",
      reason: "Bank-side syntax validation passed",
    },
    {
      timestamp: "11:00:18",
      status: "SENT TO SCHEME",
      internalStatus: "WITH_SCHEME_SUBMITTED",
      source: engineEvidence(CCD_11_00),
      agent: "AfterPaymentSubmissionAgent",
      reason: "Payment submitted to scheme successfully",
    },
  ];

  if (seed.outcome === "REJECTED_BY_SCHEME") {
    base.push({
      timestamp: "11:00:48",
      status: "REJECTED BY SCHEME",
      internalStatus: "REJECTED_BY_SCHEME_FILE",
      source: schemeRejectEvidence(SCHEME_REJECT_11_00),
      agent: "AfterPaymentSubmissionAgent",
      reason:
        "Scheme reject file matched this payment; status moved to WITH BANK / REJECTED BY SCHEME",
    });
    return base;
  }

  base.push({
    timestamp: "11:00:52",
    status: "WITH BENEFICIARY BANK",
    internalStatus: "WITH_BENEFICIARY_BANK_PENDING",
    source: settlementSummaryEvidence(SETTLEMENT_11_00),
    agent: "AfterPaymentSubmissionAgent",
    reason:
      "Settlement summary evidence received. Payment moved to WITH BENEFICIARY BANK; no payment-level clearing is claimed.",
  });

  if (seed.outcome === "REJECTED_BY_BENEFICIARY_BANK" && seed.returnCode) {
    base.push({
      timestamp: "11:04:18",
      status: "REJECTED BY BENEFICIARY BANK",
      internalStatus: "REJECTED_BY_RETURN_FILE",
      source: returnEvidence(RETURN_11_04, seed.returnCode),
      agent: "ReturnFileAgent",
      reason:
        "NACHA return file matched original trace after beneficiary-bank stage",
    });
  }

  return base;
}

function buildPayment(seed: PaymentSeed): PaymentRecord {
  const customer = CUSTOMERS[seed.customerIndex];
  const history = buildStatusHistory(seed);
  const final = history[history.length - 1];

  return {
    paymentId: `PAY-${seed.trace}`,
    traceNumber: seed.trace,
    batchId: BATCH_11_00,
    cycleTime: "11:00",
    sourceFile: CCD_11_00,
    companyId: "COMP-9001",
    customerId: customer.id,
    customerName: customer.name,
    beneficiaryName: BENEFICIARIES[seed.beneficiaryIndex],
    receivingDfi: customer.dfi,
    maskedAccount: customer.account,
    amount: seed.amount,
    currency: "USD",
    currentStatus: final.status,
    internalStatus: final.internalStatus,
    statusSince: final.timestamp,
    statusHistory: history,
    returnReasonCode: seed.returnCode,
    riskLevel: seed.riskLevel ?? "LOW",
    riskReason: seed.riskReason,
    recommendedAction:
      final.status === "REJECTED BY SCHEME"
        ? "Review scheme reject detail and correct file content before re-submission."
        : final.status === "REJECTED BY BENEFICIARY BANK"
          ? "Contact customer and beneficiary to resolve return reason before retry."
          : "Await beneficiary-bank confirmation or later return-file evidence.",
    customerFriendlyMessage:
      final.status === "REJECTED BY SCHEME"
        ? "The payment was rejected by the scheme before beneficiary-bank processing."
        : final.status === "REJECTED BY BENEFICIARY BANK"
          ? "The payment reached the beneficiary bank but was later returned."
          : "The payment has been sent onward and is currently with the beneficiary bank.",
    evidence: history.map((h) => h.source),
  };
}

const allPayments: PaymentRecord[] = paymentSeeds.map(buildPayment);

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
    sentToScheme: count("SENT TO SCHEME"),
    withBeneficiaryBank: count("WITH BENEFICIARY BANK"),
    rejectedByScheme: count("REJECTED BY SCHEME"),
    rejectedByBeneficiaryBank: count("REJECTED BY BENEFICIARY BANK"),
  };
}

function summarizeCustomers(): CustomerSummary[] {
  const byCustomer = new Map<string, PaymentRecord[]>();
  for (const payment of allPayments) {
    const list = byCustomer.get(payment.customerId) ?? [];
    list.push(payment);
    byCustomer.set(payment.customerId, list);
  }

  return Array.from(byCustomer.entries()).map(([customerId, rows]) => {
    const rejectedByScheme = rows.filter((r) => r.currentStatus === "REJECTED BY SCHEME").length;
    const rejectedByBeneficiaryBank = rows.filter(
      (r) => r.currentStatus === "REJECTED BY BENEFICIARY BANK",
    ).length;
    const withBeneficiaryBank = rows.filter(
      (r) => r.currentStatus === "WITH BENEFICIARY BANK",
    ).length;
    const sentToScheme = rows.filter((r) => r.currentStatus === "SENT TO SCHEME").length;
    const lastRejection = rows
      .filter(
        (r) =>
          r.currentStatus === "REJECTED BY SCHEME" ||
          r.currentStatus === "REJECTED BY BENEFICIARY BANK",
      )
      .map((r) => r.statusSince)
      .sort()
      .at(-1);

    return {
      customerId,
      customerName: rows[0].customerName,
      totalPayments: rows.length,
      sentToScheme,
      withBeneficiaryBank,
      rejectedByScheme,
      rejectedByBeneficiaryBank,
      lastRejectionDate: lastRejection,
      historicalRejectionCount:
        rejectedByScheme + rejectedByBeneficiaryBank + (customerId === "CUS-3003" ? 1 : 0),
    };
  });
}

const simulationState: SimulationState = {
  scenarioId: scenarios[0].id,
  currentSimTime: "11:04",
  activeCycle: "11:04",
  plan: [
    {
      cycleTime: "11:00",
      label: "Upload 4 x $100 CCD entries; settlement summary $300 and scheme reject $100",
      ccdFile: CCD_11_00,
      settlementFile: SETTLEMENT_11_00,
      schemeRejectFile: SCHEME_REJECT_11_00,
      expectedMovedToBeneficiaryBank: 3,
      expectedRejectedByScheme: 1,
      expectedRejectedByBeneficiaryBank: 0,
    },
    {
      cycleTime: "11:04",
      label: "NACHA return file matches 1 prior payment from beneficiary-bank stage",
      returnFile: RETURN_11_04,
      expectedMovedToBeneficiaryBank: 2,
      expectedRejectedByScheme: 1,
      expectedRejectedByBeneficiaryBank: 1,
    },
    {
      cycleTime: "11:08",
      label: "Awaiting next cycle",
      expectedMovedToBeneficiaryBank: 2,
      expectedRejectedByScheme: 1,
      expectedRejectedByBeneficiaryBank: 1,
    },
  ],
  runs: [
    {
      cycleTime: "11:00",
      status: "COMPLETE",
      paymentsCreated: 4,
      movedToBeneficiaryBank: 3,
      rejectedByScheme: 1,
      rejectedByBeneficiaryBank: 0,
      ranAt: "11:00:00",
    },
    {
      cycleTime: "11:04",
      status: "COMPLETE",
      paymentsCreated: 0,
      movedToBeneficiaryBank: 2,
      rejectedByScheme: 1,
      rejectedByBeneficiaryBank: 1,
      ranAt: "11:04:00",
    },
    {
      cycleTime: "11:08",
      status: "PENDING",
      paymentsCreated: 0,
      movedToBeneficiaryBank: 0,
      rejectedByScheme: 0,
      rejectedByBeneficiaryBank: 0,
    },
  ],
  summary: {
    totalPayments: allPayments.length,
    withBank: allPayments.filter((p) => p.currentStatus === "WITH BANK").length,
    sentToScheme: allPayments.filter((p) => p.currentStatus === "SENT TO SCHEME").length,
    withBeneficiaryBank: allPayments.filter(
      (p) => p.currentStatus === "WITH BENEFICIARY BANK",
    ).length,
    rejectedByScheme: allPayments.filter((p) => p.currentStatus === "REJECTED BY SCHEME").length,
    rejectedByBeneficiaryBank: allPayments.filter(
      (p) => p.currentStatus === "REJECTED BY BENEFICIARY BANK",
    ).length,
  },
  events: [
    {
      timestamp: "11:00:05",
      cycleTime: "11:00",
      agent: "BeforePaymentSubmissionAgent",
      message: `${CCD_11_00}: 4 payments parsed at $100 each, syntax validation passed`,
    },
    {
      timestamp: "11:00:18",
      cycleTime: "11:00",
      agent: "AfterPaymentSubmissionAgent",
      message: "4 payments moved to SENT TO SCHEME",
    },
    {
      timestamp: "11:00:52",
      cycleTime: "11:00",
      agent: "AfterPaymentSubmissionAgent",
      message:
        "Settlement summary ($300) and scheme reject file ($100) applied: 3 WITH BENEFICIARY BANK, 1 REJECTED BY SCHEME",
    },
    {
      timestamp: "11:04:18",
      cycleTime: "11:04",
      agent: "ReturnFileAgent",
      message:
        "Return file matched one prior trace: status moved to REJECTED BY BENEFICIARY BANK",
    },
    {
      timestamp: "11:04:25",
      cycleTime: "11:04",
      agent: "AIExplanationAgent",
      message:
        "Generated evidence-based explanations; no payment-level clearing is claimed from summary settlement",
    },
  ],
};

const agentTrace: AgentTraceStep[] = [
  {
    timestamp: "11:00:05",
    agent: "BeforePaymentSubmissionAgent",
    action: "parse_ccd",
    detail: `${CCD_11_00}: parsed 4 entry detail records`,
  },
  {
    timestamp: "11:00:10",
    agent: "BeforePaymentSubmissionAgent",
    action: "syntax_validate",
    detail: "Bank-side syntax validation passed for all 4 records",
  },
  {
    timestamp: "11:00:18",
    agent: "AfterPaymentSubmissionAgent",
    action: "submit_to_scheme",
    detail: "4 payments set to SENT TO SCHEME",
  },
  {
    timestamp: "11:00:48",
    agent: "AfterPaymentSubmissionAgent",
    action: "apply_settlement_and_scheme_reject",
    detail:
      `Settlement summary ${SETTLEMENT_11_00} ($300) and scheme reject ${SCHEME_REJECT_11_00} ($100) processed`,
  },
  {
    timestamp: "11:04:18",
    agent: "ReturnFileAgent",
    action: "match_returns",
    detail: `Return file ${RETURN_11_04} matched trace 110000003 (R01)`,
  },
  {
    timestamp: "11:04:25",
    agent: "AIExplanationAgent",
    action: "explain_statuses",
    detail:
      "Produced payment explanations with explicit settlement-summary limitations",
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
      generatedAt: "11:04:25",
      rows: [summarizeBatch(BATCH_11_00, "11:00", CCD_11_00)],
    });
  },

  getCustomerDashboard(): Promise<DashboardResponse<CustomerSummary>> {
    return delay({ generatedAt: "11:04:25", rows: summarizeCustomers() });
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

  getDemoFlowPayments(): Promise<PaymentLedgerView> {
    return requestJson<PaymentLedgerView>("/api/demo-flow/payments");
  },

  resetDemoFlow(): Promise<void> {
    return requestNoContent("/api/demo-flow/reset", { method: "POST" });
  },
};

export type Api = typeof api;
