import type {
  LedgerPayment,
  LedgerPaymentStatus,
  PaymentLedgerView,
} from "../types/api";
import { api } from "./client";

export const LEDGER_STATUS_ORDER: LedgerPaymentStatus[] = [
  "WITH BANK",
  "SENT TO SCHEME",
  "WITH BENEFICIARY BANK",
  "REJECTED BY SCHEME",
  "REJECTED BY BENEFICIARY BANK",
];

export function fetchLiveLedger(): Promise<PaymentLedgerView> {
  return api.getDemoFlowPayments();
}

export function formatDollars(amountCents: number): string {
  return (amountCents / 100).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
  });
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function latestEvidenceSummary(payment: LedgerPayment): string {
  const history = payment.status_history;
  if (history.length > 0) return history[history.length - 1].evidence.summary;
  const evidence = payment.evidence;
  if (evidence.length > 0) return evidence[evidence.length - 1].summary;
  return "";
}

export function countByStatus(
  payments: LedgerPayment[],
): Record<LedgerPaymentStatus, number> {
  const counts: Record<LedgerPaymentStatus, number> = {
    "WITH BANK": 0,
    "SENT TO SCHEME": 0,
    "WITH BENEFICIARY BANK": 0,
    "REJECTED BY SCHEME": 0,
    "REJECTED BY BENEFICIARY BANK": 0,
  };
  for (const payment of payments) {
    counts[payment.current_status] += 1;
  }
  return counts;
}

export interface LedgerBatchGroup {
  batchKey: string;
  sourceFile: string;
  payments: LedgerPayment[];
  counts: Record<LedgerPaymentStatus, number>;
}

export function groupByBatch(payments: LedgerPayment[]): LedgerBatchGroup[] {
  const map = new Map<string, LedgerBatchGroup>();
  for (const payment of payments) {
    const key = payment.batch_key;
    let group = map.get(key);
    if (!group) {
      group = {
        batchKey: key,
        sourceFile: payment.source_file,
        payments: [],
        counts: {
          "WITH BANK": 0,
          "SENT TO SCHEME": 0,
          "WITH BENEFICIARY BANK": 0,
          "REJECTED BY SCHEME": 0,
          "REJECTED BY BENEFICIARY BANK": 0,
        },
      };
      map.set(key, group);
    }
    group.payments.push(payment);
    group.counts[payment.current_status] += 1;
  }
  return Array.from(map.values()).sort((a, b) =>
    a.batchKey.localeCompare(b.batchKey),
  );
}

export interface LedgerCustomerGroup {
  individualId: string;
  individualName: string;
  payments: LedgerPayment[];
  counts: Record<LedgerPaymentStatus, number>;
}

export function groupByCustomer(
  payments: LedgerPayment[],
): LedgerCustomerGroup[] {
  const map = new Map<string, LedgerCustomerGroup>();
  for (const payment of payments) {
    const key = `${payment.individual_id_number}||${payment.individual_name}`;
    let group = map.get(key);
    if (!group) {
      group = {
        individualId: payment.individual_id_number,
        individualName: payment.individual_name,
        payments: [],
        counts: {
          "WITH BANK": 0,
          "SENT TO SCHEME": 0,
          "WITH BENEFICIARY BANK": 0,
          "REJECTED BY SCHEME": 0,
          "REJECTED BY BENEFICIARY BANK": 0,
        },
      };
      map.set(key, group);
    }
    group.payments.push(payment);
    group.counts[payment.current_status] += 1;
  }
  return Array.from(map.values()).sort((a, b) => {
    const nameOrder = a.individualName.localeCompare(b.individualName);
    if (nameOrder !== 0) return nameOrder;
    return a.individualId.localeCompare(b.individualId);
  });
}

export function sortPaymentsByPaymentId(
  payments: LedgerPayment[],
): LedgerPayment[] {
  return [...payments].sort((a, b) => a.payment_id.localeCompare(b.payment_id));
}
