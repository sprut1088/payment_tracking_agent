// API client for the ACH Payment Tracking Agent frontend demo shell.
// Dashboards use SME-aligned mock fixtures, while local-folder demo-flow
// controls call backend HTTP endpoints under /api/demo-flow.

import type {
  AgentTraceStep,
  BackendPaymentListItem,
  BatchSummary,
  BusinessStatus,
  CustomerSummary,
  DemoFlowConfig,
  DemoFlowScanResult,
  DemoFlowState,
  DashboardResponse,
  DropStatusResponse,
  EvidenceRef,
  EventLogEntry,
  PaymentRecord,
  Scenario,
  SimulationState,
  StatusHistoryEvent,
  UnderReviewItem,
  UploadSummary,
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

export function computeFileRiskLevel(rows: PaymentRecord[]): import("../types/api").RiskLevel {
  if (rows.some((r) => r.riskLevel === "HIGH")) return "HIGH";
  if (rows.some((r) => r.riskLevel === "MEDIUM")) return "MEDIUM";
  return "LOW";
}

/** Batch-level risk: combines current rejection rate AND individual payment history risk.
 *
 * For a freshly uploaded batch with no rejections yet, the individual riskLevel
 * on each payment (computed by the backend risk engine from all historical data)
 * is used as a forward-looking signal:
 *   - Any HIGH individual risk  → batch shows MEDIUM (likely to fail again)
 *   - Any MEDIUM individual risk → batch shows MEDIUM
 *   - Current rejections > 50%  → HIGH
 *   - Current rejections + HIGH individual risk → HIGH
 *   - No rejections, no history risk → LOW
 */
export function computeBatchRiskLevel(rows: PaymentRecord[]): import("../types/api").RiskLevel {
  if (rows.length === 0) return "LOW";
  const rejected = rows.filter(
    (r) =>
      r.currentStatus === "REJECTED BY SCHEME" ||
      r.currentStatus === "REJECTED BY BENEFICIARY BANK",
  ).length;
  const rate = (rejected / rows.length) * 100;
  const highHistCount   = rows.filter((r) => r.riskLevel === "HIGH").length;
  const mediumHistCount = rows.filter((r) => r.riskLevel === "MEDIUM").length;

  if (rate > 50) return "HIGH";
  if (rejected > 0) return "MEDIUM";                  // any current rejections → MEDIUM
  if (highHistCount > 0) return "MEDIUM";             // high historical risk → likely to fail → MEDIUM
  if (mediumHistCount > 0) return "MEDIUM";           // medium historical risk → MEDIUM
  return "LOW";
}

export function computeBatchRiskReason(rows: PaymentRecord[]): string {
  if (rows.length === 0) return "No payments in batch.";
  const rejectedByScheme = rows.filter((r) => r.currentStatus === "REJECTED BY SCHEME").length;
  const rejectedByBeneficiary = rows.filter(
    (r) => r.currentStatus === "REJECTED BY BENEFICIARY BANK",
  ).length;
  const rejected = rejectedByScheme + rejectedByBeneficiary;
  const rate = (rejected / rows.length) * 100;
  const highHistCount   = rows.filter((r) => r.riskLevel === "HIGH").length;
  const mediumHistCount = rows.filter((r) => r.riskLevel === "MEDIUM").length;

  const parts: string[] = [];
  if (rejected > 0)
    parts.push(`Current rejection rate: ${rate.toFixed(1)}% (${rejected}/${rows.length} payments).`);
  if (rejectedByScheme > 0) parts.push(`${rejectedByScheme} rejected by scheme.`);
  if (rejectedByBeneficiary > 0) parts.push(`${rejectedByBeneficiary} rejected by beneficiary bank.`);
  if (highHistCount > 0)
    parts.push(`${highHistCount} payment${highHistCount !== 1 ? "s" : ""} carry HIGH historical risk from prior rejections — likely to fail again.`);
  if (mediumHistCount > 0)
    parts.push(`${mediumHistCount} payment${mediumHistCount !== 1 ? "s" : ""} carry MEDIUM historical risk — monitor closely.`);
  if (parts.length === 0)
    return `Batch rejection rate: 0% \u2014 all ${rows.length} payment${rows.length !== 1 ? "s" : ""} clean with no elevated historical risk.`;
  return parts.join(" ");
}

export function computeFileRiskReason(rows: PaymentRecord[]): string {
  const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 } as Record<string, number>;
  for (const r of rows) counts[r.riskLevel] = (counts[r.riskLevel] ?? 0) + 1;
  const parts: string[] = [];
  if (counts["HIGH"]) parts.push(`${counts["HIGH"]} HIGH`);
  if (counts["MEDIUM"]) parts.push(`${counts["MEDIUM"]} MEDIUM`);
  if (counts["LOW"]) parts.push(`${counts["LOW"]} LOW`);
  const breakdown = `Risk breakdown: ${parts.join(", ")} across ${rows.length} payment${rows.length !== 1 ? "s" : ""}.`;
  const topReason = ["HIGH", "MEDIUM"].flatMap((lvl) =>
    rows.filter((r) => r.riskLevel === lvl && r.riskReason).map((r) => r.riskReason!),
  )[0];
  return topReason ? `${breakdown} ${topReason}` : breakdown;
}

function summarizeBatch(batchId: string, cycleTime: string, sourceFile: string): BatchSummary {
  const rows = allPayments.filter((p) => p.batchId === batchId);
  const count = (status: PaymentRecord["currentStatus"]) =>
    rows.filter((r) => r.currentStatus === status).length;
  const rejectedCount = count("REJECTED BY SCHEME") + count("REJECTED BY BENEFICIARY BANK");
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
    fileRiskLevel: computeBatchRiskLevel(rows),
    fileRiskReason: computeBatchRiskReason(rows),
    rejectedPercentage:
      rows.length > 0 ? Math.round((rejectedCount / rows.length) * 1000) / 10 : 0,
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
      withBank: rows.filter((r) => r.currentStatus === "WITH BANK").length,
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
      fileRiskLevel: "MEDIUM",
      fileRiskReason: "Risk breakdown: 1 MEDIUM, 3 LOW across 4 payments. Beneficiary had prior return pattern in last 60 days.",
    },
    {
      cycleTime: "11:04",
      status: "COMPLETE",
      paymentsCreated: 0,
      movedToBeneficiaryBank: 2,
      rejectedByScheme: 1,
      rejectedByBeneficiaryBank: 1,
      ranAt: "11:04:00",
      fileRiskLevel: "MEDIUM",
      fileRiskReason: "Risk breakdown: 1 MEDIUM, 3 LOW across 4 payments. R01 Insufficient Funds return confirmed for Northline Components.",
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

// ---------------------------------------------------------------------------
// Live backend helpers — used when Demo Mode is OFF
// ---------------------------------------------------------------------------

/** Map backend business_status string → frontend BusinessStatus. */
function mapBusinessStatus(
  businessStatus: string,
  internalStatus: string,
): PaymentRecord["currentStatus"] {
  if (businessStatus === "WITH SCHEME") return "SENT TO SCHEME";
  if (businessStatus === "REJECTED") {
    return internalStatus === "REJECTED_BY_RETURN_FILE"
      ? "REJECTED BY BENEFICIARY BANK"
      : "REJECTED BY SCHEME";
  }
  const known = [
    "WITH BANK",
    "SENT TO SCHEME",
    "WITH BENEFICIARY BANK",
    "REJECTED BY SCHEME",
    "REJECTED BY BENEFICIARY BANK",
  ] as const;
  const match = known.find((s) => s === businessStatus);
  return match ?? "WITH BANK";
}

/** Map backend internal status string → frontend InternalStatus. */
function mapInternalStatus(status: string): PaymentRecord["internalStatus"] {
  const known: PaymentRecord["internalStatus"][] = [
    "WITH_BANK_UPLOADED",
    "WITH_BANK_VALIDATING",
    "WITH_BANK_READY_FOR_SCHEME",
    "WITH_BANK_VALIDATION_FAILED",
    "WITH_SCHEME_SUBMITTED",
    "WITH_BENEFICIARY_BANK_PENDING",
    "REJECTED_BY_SCHEME_FILE",
    "REJECTED_BY_RETURN_FILE",
    "REVIEW_REQUIRED",
  ];
  const match = known.find((s) => s === status);
  return match ?? "WITH_BANK_UPLOADED";
}

function _defaultCustomerMessage(status: BusinessStatus): string {
  switch (status) {
    case "WITH BANK":
      return "The payment is currently with the bank pending validation and scheme submission. No action from the beneficiary is required at this stage.";
    case "SENT TO SCHEME":
      return "The payment has passed bank-side validation and has been submitted to the ACH scheme. It is awaiting scheme processing.";
    case "WITH BENEFICIARY BANK":
      return "Settlement summary evidence has been received for this batch. The payment is currently with the beneficiary bank. No return file has been received yet — the payment remains in this status pending any future return evidence.";
    case "REJECTED BY SCHEME":
      return "The payment was rejected by the ACH scheme before reaching the beneficiary bank. Bank-side correction is required before resubmission.";
    case "REJECTED BY BENEFICIARY BANK":
      return "The payment reached the beneficiary bank but was subsequently returned. Return reason details will be shown once the return file is processed.";
    default:
      return "Payment status is being tracked. Refer to the status timeline for the latest evidence.";
  }
}

function _defaultRecommendedAction(status: BusinessStatus): string {
  switch (status) {
    case "WITH BANK":
      return "No action required. Payment will be submitted to the scheme after bank-side validation completes.";
    case "SENT TO SCHEME":
      return "Await settlement summary evidence or scheme rejection notification. No action required at this time.";
    case "WITH BENEFICIARY BANK":
      return "Await beneficiary bank confirmation. If a return file is received, the payment status will update automatically. No payment-level clearing is claimed from settlement summary alone.";
    case "REJECTED BY SCHEME":
      return "Review the scheme rejection reason and correct the payment details before resubmission.";
    case "REJECTED BY BENEFICIARY BANK":
      return "Review the return reason code and contact the originating company. Correct the underlying issue before retrying.";
    default:
      return "Review the payment status and evidence trail for next steps.";
  }
}

/** Convert a backend PaymentListItem into a frontend PaymentRecord. */
function mapBackendPayment(item: BackendPaymentListItem): PaymentRecord {
  const currentStatus = mapBusinessStatus(item.business_status, item.status);
  const uploadedTime = new Date(item.uploaded_at).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return {
    paymentId: `PAY-${item.trace_number}`,
    traceNumber: item.trace_number,
    batchId: item.upload_id,           // unique per uploaded file — avoids collision when multiple files share the same NACHA batch number
    cycleTime: uploadedTime,
    sourceFile: item.file_name,
    companyId: "",
    customerId: item.individual_id_number.trim() || item.individual_name.trim() || item.trace_number,
    customerName: item.individual_name.trim() || "Unknown",
    beneficiaryName: item.individual_name.trim() || "Unknown",
    receivingDfi: item.receiving_dfi,
    maskedAccount: item.dfi_account_number_masked,
    amount: item.amount,
    currency: "USD",
    currentStatus,
    internalStatus: mapInternalStatus(item.status),
    statusSince: uploadedTime,
    statusHistory: [],
    riskLevel: (item.risk_level as PaymentRecord["riskLevel"]) ?? "LOW",
    riskReason: item.risk_reason ?? undefined,
    returnReasonCode: item.return_reason_code ?? undefined,
    evidence: item.return_reason_code
      ? [
          {
            kind: "RETURN" as const,
            sourceFile: item.file_name,
            summary: [
              `Return code ${item.return_reason_code}`,
              item.return_reason_description,
              item.return_customer_message,
            ]
              .filter(Boolean)
              .join(" — "),
          },
        ]
      : [],
    recommendedAction: item.corrective_action ?? _defaultRecommendedAction(currentStatus),
    customerFriendlyMessage: item.return_customer_message ?? _defaultCustomerMessage(currentStatus),
  };
}

// ---------------------------------------------------------------------------
// Short-TTL payment list cache — shared across all live-mode page fetches.
// Prevents redundant backend round-trips when navigating between pages.
// ---------------------------------------------------------------------------
const PAYMENTS_CACHE_TTL_MS = 4_000;   // 4 s — short enough to reflect scheme-push quickly
let _cacheGeneration = 0;              // incremented on invalidate so stale flights discard themselves
let _paymentsCache: { data: PaymentRecord[]; ts: number } | null = null;
let _paymentsFlight: Promise<PaymentRecord[]> | null = null;

/** Fetch all payments from the backend and convert to PaymentRecord[].
 *  Results are cached for PAYMENTS_CACHE_TTL_MS ms; concurrent callers share
 *  a single in-flight request rather than issuing duplicates.
 */
async function fetchLivePayments(): Promise<PaymentRecord[]> {
  const now = Date.now();
  if (_paymentsCache && now - _paymentsCache.ts < PAYMENTS_CACHE_TTL_MS) {
    return _paymentsCache.data;
  }
  if (_paymentsFlight) return _paymentsFlight;
  const gen = _cacheGeneration;
  _paymentsFlight = requestJson<BackendPaymentListItem[]>("/api/v1/payments")
    .then((items) => {
      const data = items.map(mapBackendPayment);
      // Only cache if invalidatePaymentsCache() was not called while in-flight
      if (gen === _cacheGeneration) {
        _paymentsCache = { data, ts: Date.now() };
      }
      _paymentsFlight = null;
      return data;
    })
    .catch((err) => {
      _paymentsFlight = null;
      throw err;
    });
  return _paymentsFlight;
}

/** Invalidate the payment cache (call after uploads or status-changing actions). */
export function invalidatePaymentsCache(): void {
  _cacheGeneration++;          // invalidates any in-flight response
  _paymentsCache = null;
  _paymentsFlight = null;
}

/** Build BatchSummary[] from a flat list of live PaymentRecords. */
function buildLiveBatchSummaries(payments: PaymentRecord[]): BatchSummary[] {
  const byBatch = new Map<string, PaymentRecord[]>();
  for (const p of payments) {
    const list = byBatch.get(p.batchId) ?? [];
    list.push(p);
    byBatch.set(p.batchId, list);
  }
  return Array.from(byBatch.entries()).map(([batchId, rows]) => {
    const rejectedByScheme = rows.filter((r) => r.currentStatus === "REJECTED BY SCHEME").length;
    const rejectedByBeneficiaryBank = rows.filter(
      (r) => r.currentStatus === "REJECTED BY BENEFICIARY BANK",
    ).length;
    const rejectedCount = rejectedByScheme + rejectedByBeneficiaryBank;
    return {
      batchId,
      cycleTime: rows[0].cycleTime,
      sourceFile: rows[0].sourceFile,
      paymentCount: rows.length,
      withBank: rows.filter((r) => r.currentStatus === "WITH BANK").length,
      sentToScheme: rows.filter((r) => r.currentStatus === "SENT TO SCHEME").length,
      withBeneficiaryBank: rows.filter((r) => r.currentStatus === "WITH BENEFICIARY BANK").length,
      rejectedByScheme,
      rejectedByBeneficiaryBank,
      fileRiskLevel: computeBatchRiskLevel(rows),
      fileRiskReason: computeBatchRiskReason(rows),
      rejectedPercentage:
        rows.length > 0 ? Math.round((rejectedCount / rows.length) * 1000) / 10 : 0,
    };
  });
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

  resetDemoFlow(): Promise<void> {
    return requestNoContent("/api/demo-flow/reset", { method: "POST" });
  },

  getUnderReview(): Promise<UnderReviewItem[]> {
    return requestJson<UnderReviewItem[]>("/api/demo-flow/under-review");
  },

  listPreSubmissionResults(): Promise<import("../types/api").BatchPreSubmissionResult[]> {
    return requestJson("/api/v1/pre-submission");
  },

  getPreSubmissionResult(uploadId: string): Promise<import("../types/api").BatchPreSubmissionResult | null> {
    return requestJson<import("../types/api").BatchPreSubmissionResult>(`/api/v1/uploads/${uploadId}/pre-submission`).catch(() => null);
  },

  releaseHold(uploadId: string): Promise<{ released: number }> {
    return requestJson(`/api/v1/uploads/${uploadId}/release-hold`, { method: "POST" });
  },

  rejectHold(uploadId: string): Promise<{ rejected: number }> {
    return requestJson(`/api/v1/uploads/${uploadId}/reject-hold`, { method: "POST" });
  },

  acceptCorrection(payload: {
    batch_id: string;
    file_name: string;
    corrected_content: string;
  }): Promise<unknown> {
    return requestJson("/api/demo-flow/accept-correction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  rejectCorrection(payload: { batch_id: string; file_name: string }): Promise<void> {
    return requestNoContent("/api/demo-flow/reject-correction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  // -------------------------------------------------------------------------
  // Live backend calls — used when Demo Mode is OFF
  // -------------------------------------------------------------------------

  // ---- On-demand drop-folder triggers ----------------------------------------

  triggerDropScanCcd(): Promise<void> {
    return requestNoContent("/api/v1/drop/scan-ccd", { method: "POST" });
  },

  triggerDropScanSettlement(): Promise<void> {
    return requestNoContent("/api/v1/drop/scan-settlement", { method: "POST" });
  },

  triggerDropScanReturns(): Promise<void> {
    return requestNoContent("/api/v1/drop/scan-returns", { method: "POST" });
  },

  async listPaymentsLive(): Promise<PaymentRecord[]> {
    return fetchLivePayments();
  },

  listUploadsLive(): Promise<UploadSummary[]> {
    return requestJson<UploadSummary[]>("/api/v1/uploads");
  },

  getDropStatus(): Promise<DropStatusResponse> {
    return requestJson<DropStatusResponse>("/api/v1/drop-status");
  },

  getEventsLive(): Promise<EventLogEntry[]> {
    return requestJson<EventLogEntry[]>("/api/v1/events");
  },

  async getBatchDashboardLive(): Promise<DashboardResponse<BatchSummary>> {
    const payments = await fetchLivePayments();
    return {
      generatedAt: new Date().toISOString(),
      rows: buildLiveBatchSummaries(payments),
    };
  },

  async getCustomerDashboardLive(): Promise<DashboardResponse<CustomerSummary>> {
    interface BackendCustomerSummary {
      customer_id: string;
      customer_name: string;
      total_payments: number;
      with_bank: number;
      sent_to_scheme: number;
      with_beneficiary_bank: number;
      rejected_by_scheme: number;
      rejected_by_beneficiary_bank: number;
      last_rejection_date: string | null;
      historical_rejection_count: number;
      risk_level: string;
      risk_reason: string | null;
    }
    const rows = await requestJson<BackendCustomerSummary[]>("/api/v1/customers");
    return {
      generatedAt: new Date().toISOString(),
      rows: rows.map((r) => ({
        customerId: r.customer_id,
        customerName: r.customer_name,
        totalPayments: r.total_payments,
        withBank: r.with_bank,
        sentToScheme: r.sent_to_scheme,
        withBeneficiaryBank: r.with_beneficiary_bank,
        rejectedByScheme: r.rejected_by_scheme,
        rejectedByBeneficiaryBank: r.rejected_by_beneficiary_bank,
        lastRejectionDate: r.last_rejection_date ?? undefined,
        historicalRejectionCount: r.historical_rejection_count,
        riskLevel: r.risk_level,
        riskReason: r.risk_reason,
      })),
    };
  },

  async searchPaymentsLive(query: string): Promise<PaymentRecord[]> {
    const payments = await fetchLivePayments();
    const q = query.trim().toLowerCase();
    if (!q) return payments;
    return payments.filter(
      (p) =>
        p.paymentId.toLowerCase().includes(q) ||
        p.traceNumber.toLowerCase().includes(q) ||
        p.customerName.toLowerCase().includes(q) ||
        p.customerId.toLowerCase().includes(q) ||
        p.beneficiaryName.toLowerCase().includes(q) ||
        p.batchId.toLowerCase().includes(q),
    );
  },
};

export type Api = typeof api;
