// Shared API types for the ACH Payment Tracking Agent frontend.
// Backed by a mocked client during Prompt 02.

export type BusinessStatus =
  | "WITH BANK"
  | "SENT TO SCHEME"
  | "WITH BENEFICIARY BANK"
  | "REJECTED BY SCHEME"
  | "REJECTED BY BENEFICIARY BANK";

export type InternalStatus =
  | "WITH_BANK_UPLOADED"
  | "WITH_BANK_VALIDATING"
  | "WITH_BANK_READY_FOR_SCHEME"
  | "WITH_SCHEME_SUBMITTED"
  | "WITH_BENEFICIARY_BANK_PENDING"
  | "REJECTED_BY_SCHEME_FILE"
  | "REJECTED_BY_RETURN_FILE"
  | "REVIEW_REQUIRED";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type AgentName =
  | "BeforePaymentSubmissionAgent"
  | "AfterPaymentSubmissionAgent"
  | "ReturnFileAgent"
  | "PaymentLifecycleOrchestrator"
  | "AIExplanationAgent";

export interface Scenario {
  id: string;
  name: string;
  description: string;
  cycleSchedule: string[];
  mode: "REAL_DAY" | "ACCELERATED_2MIN" | "ACCELERATED_4MIN" | "MANUAL";
}

export interface CyclePlanEntry {
  cycleTime: string;
  label: string;
  ccdFile?: string;
  settlementFile?: string;
  schemeRejectFile?: string;
  returnFile?: string;
  expectedMovedToBeneficiaryBank: number;
  expectedRejectedByScheme: number;
  expectedRejectedByBeneficiaryBank: number;
}

export interface CycleRunSummary {
  cycleTime: string;
  status: "PENDING" | "RUNNING" | "COMPLETE";
  paymentsCreated: number;
  movedToBeneficiaryBank: number;
  rejectedByScheme: number;
  rejectedByBeneficiaryBank: number;
  ranAt?: string;
}

export interface EventLogEntry {
  timestamp: string;
  cycleTime: string;
  agent: AgentName;
  message: string;
}

export interface SimulationState {
  scenarioId: string;
  currentSimTime: string;
  activeCycle?: string;
  plan: CyclePlanEntry[];
  runs: CycleRunSummary[];
  summary: {
    totalPayments: number;
    withBank: number;
    sentToScheme: number;
    withBeneficiaryBank: number;
    rejectedByScheme: number;
    rejectedByBeneficiaryBank: number;
  };
  events: EventLogEntry[];
}

export interface AgentTraceStep {
  timestamp: string;
  agent: AgentName;
  action: string;
  detail: string;
}

export interface EvidenceRef {
  kind:
    | "CCD"
    | "PROCESSING_ENGINE"
    | "SETTLEMENT"
    | "SCHEME_REJECT"
    | "RETURN"
    | "HISTORICAL";
  sourceFile?: string;
  summary: string;
}

export interface StatusHistoryEvent {
  timestamp: string;
  status: BusinessStatus;
  internalStatus: InternalStatus;
  source: EvidenceRef;
  agent: AgentName;
  reason: string;
}

export interface PaymentRecord {
  paymentId: string;
  traceNumber: string;
  batchId: string;
  cycleTime: string;
  sourceFile: string;
  companyId: string;
  customerId: string;
  customerName: string;
  beneficiaryName: string;
  receivingDfi: string;
  maskedAccount: string;
  amount: number;
  currency: "USD";
  currentStatus: BusinessStatus;
  internalStatus: InternalStatus;
  statusSince: string;
  statusHistory: StatusHistoryEvent[];
  returnReasonCode?: string;
  riskLevel: RiskLevel;
  riskReason?: string;
  recommendedAction?: string;
  customerFriendlyMessage?: string;
  evidence: EvidenceRef[];
}

export interface BatchSummary {
  batchId: string;
  cycleTime: string;
  sourceFile: string;
  paymentCount: number;
  sentToScheme: number;
  withBeneficiaryBank: number;
  rejectedByScheme: number;
  rejectedByBeneficiaryBank: number;
  withBank: number;
}

export interface CustomerSummary {
  customerId: string;
  customerName: string;
  totalPayments: number;
  sentToScheme: number;
  withBeneficiaryBank: number;
  rejectedByScheme: number;
  rejectedByBeneficiaryBank: number;
  lastRejectionDate?: string;
  historicalRejectionCount: number;
}

export interface DashboardResponse<T> {
  rows: T[];
  generatedAt: string;
}

export type DemoFlowFileKind = "ccd" | "settlement" | "scheme_reject" | "return";

export type DemoFlowBatchStatus =
  | "AWAITING_SETTLEMENT"
  | "AWAITING_RETURNS"
  | "RETURN_EVIDENCE_RECEIVED";

export type SettlementSchemeEvidenceStatus =
  | "NONE_AVAILABLE"
  | "SETTLEMENT_AVAILABLE"
  | "SCHEME_REJECT_AVAILABLE"
  | "SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE";

export interface DemoFlowDetectedFile {
  path: string;
  filename: string;
  kind: DemoFlowFileKind;
  size_bytes: number;
  modified_at: string;
  discovered_at: string;
}

export interface DemoFlowBatch {
  batch_id: string;
  ccd_file: DemoFlowDetectedFile;
  uploaded_at: string;
  expected_settlement_scan_at: string;
  expected_returns_scan_at: string;
  status: DemoFlowBatchStatus;
  settlement_scheme_status: SettlementSchemeEvidenceStatus;
  settlement_files: DemoFlowDetectedFile[];
  scheme_reject_files: DemoFlowDetectedFile[];
  return_files: DemoFlowDetectedFile[];
}

export interface DemoFlowScanResult {
  scanned_at: string;
  new_files: DemoFlowDetectedFile[];
  new_batches: string[];
  batches_advanced: string[];
}

export interface DemoFlowState {
  as_of: string;
  batches: DemoFlowBatch[];
  detected_files: DemoFlowDetectedFile[];
}

export interface DemoFlowConfig {
  demo_flow_root: string;
  inbox_dir: string;
  settlement_dir: string;
  scheme_reject_dir: string;
  returns_dir: string;
  processed_dir: string;
  settlement_delay_seconds: number;
  returns_delay_seconds: number;
  poll_interval_seconds: number;
}

export type LedgerPaymentStatus = BusinessStatus;

export interface LedgerPaymentEvidence {
  source: string;
  summary: string;
  recorded_at: string;
}

export interface LedgerPaymentStatusEvent {
  status: LedgerPaymentStatus;
  at: string;
  evidence: LedgerPaymentEvidence;
}

export interface LedgerPayment {
  payment_id: string;
  batch_key: string;
  source_file: string;
  trace_number: string;
  transaction_code: string;
  receiving_dfi_identification: string;
  masked_account_number: string;
  amount_cents: number;
  individual_id_number: string;
  individual_name: string;
  current_status: LedgerPaymentStatus;
  status_history: LedgerPaymentStatusEvent[];
  evidence: LedgerPaymentEvidence[];
}

export interface PaymentLedgerView {
  as_of: string;
  payments: LedgerPayment[];
}

export interface AIExplanationResponse {
  payment_id: string;
  provider: string;
  model: string;
  summary: string;
  status_explanation: string;
  evidence_used: string[];
  limitations: string[];
  recommended_action: string;
  customer_safe_message: string;
  generated_at: string;
}
