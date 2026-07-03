// Shared API types for the ACH Payment Tracking Agent frontend.
// Backed by a mocked client during Prompt 02.

export type BusinessStatus =
  | "WITH BANK"
  | "WITH SCHEME"
  | "WITH BENEFICIARY BANK"
  | "CLEARED"
  | "REJECTED";

export type InternalStatus =
  | "WITH_BANK_UPLOADED"
  | "WITH_BANK_VALIDATING"
  | "WITH_BANK_READY_FOR_SCHEME"
  | "WITH_SCHEME_SUBMITTED"
  | "WITH_SCHEME_ACKNOWLEDGED"
  | "WITH_BENEFICIARY_BANK_PENDING"
  | "CLEARED_BY_SETTLEMENT"
  | "REJECTED_BY_RETURN_FILE"
  | "RECONCILIATION_EXCEPTION"
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
  returnFile?: string;
  expectedCleared: number;
  expectedWithBeneficiaryBank: number;
  expectedRejectedFromPriorCycle: number;
}

export interface CycleRunSummary {
  cycleTime: string;
  status: "PENDING" | "RUNNING" | "COMPLETE";
  paymentsCreated: number;
  cleared: number;
  withBeneficiaryBank: number;
  rejectedFromPriorCycle: number;
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
    withScheme: number;
    withBeneficiaryBank: number;
    cleared: number;
    rejected: number;
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
  kind: "CCD" | "PROCESSING_ENGINE" | "SETTLEMENT" | "RETURN" | "HISTORICAL";
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
  cleared: number;
  withBeneficiaryBank: number;
  rejected: number;
  withBank: number;
  withScheme: number;
}

export interface CustomerSummary {
  customerId: string;
  customerName: string;
  totalPayments: number;
  cleared: number;
  rejected: number;
  withBeneficiaryBank: number;
  lastRejectionDate?: string;
  historicalRejectionCount: number;
}

export interface DashboardResponse<T> {
  rows: T[];
  generatedAt: string;
}
