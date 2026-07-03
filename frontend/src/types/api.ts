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
  riskLevel?: string;
  riskReason?: string | null;
}

export interface DashboardResponse<T> {
  rows: T[];
  generatedAt: string;
}

export interface UploadSummary {
  upload_id: string;
  file_name: string;
  uploaded_at: string;
  entry_count: number;
  batch_count: number;
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
  /** Only populated by the scan-ccd endpoint. */
  uploads?: ScanCcdUploadOutcome[];
}

export interface ScanCcdUploadOutcome {
  file_name: string;
  batch_id: string;
  is_valid: boolean;
  is_awaiting_review: boolean;
  upload_id?: string;
  entry_count: number;
  batch_count: number;
  errors: string[];
  validation_error_count: number;
  corrected_file_content?: string | null;
  corrected_lines?: Array<{ line_number: number; line: string; was_corrected: boolean }> | null;
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
  under_review_dir: string;
  settlement_delay_seconds: number;
  returns_delay_seconds: number;
  poll_interval_seconds: number;
}

// ---------------------------------------------------------------------------
// Drop folder status (GET /api/v1/drop-status)
// ---------------------------------------------------------------------------

export interface DropFileInfo {
  filename: string;
  /** e.g. "ccd/input", "settlement/processed", "returns/error" */
  subfolder: string;
  size_bytes: number;
  modified_at: string;
}

export interface DropStatusResponse {
  files: DropFileInfo[];
  scanned_at: string;
}

// ---------------------------------------------------------------------------
// Under-review / correction-review types
// ---------------------------------------------------------------------------

export interface CorrectedLineItem {
  line_number: number;
  line: string;
  was_corrected: boolean;
  explanation?: string | null;
}

export interface UnderReviewItem {
  file_name: string;
  batch_id: string;
  discovered_at: string;
  errors: string[];
  original_content: string;
  corrected_file_content: string | null;
  corrected_lines: CorrectedLineItem[] | null;
}

// ---------------------------------------------------------------------------
// Backend live API response shapes (GET /api/v1/payments)
// ---------------------------------------------------------------------------

export interface BackendPaymentListItem {
  upload_id: string;
  file_name: string;
  uploaded_at: string;
  trace_number: string;
  batch_number: string;
  individual_name: string;
  individual_id_number: string;
  amount: number;
  amount_cents: number;
  receiving_dfi: string;
  dfi_account_number_masked: string;
  status: string;
  business_status: string;
  corrective_action: string | null;
  return_reason_code: string | null;
  return_reason_description: string | null;
  return_customer_message: string | null;
  risk_level: string;
  risk_reason: string | null;
}
