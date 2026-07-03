import type { ReactNode } from "react";
import type { BusinessStatus } from "../types/api";

interface StatusBadgeProps {
  status: BusinessStatus;
  size?: "sm" | "md";
  icon?: ReactNode;
}

const statusToClass: Record<BusinessStatus, string> = {
  "WITH BANK": "status-badge status-badge--with-bank",
  "SENT TO SCHEME": "status-badge status-badge--sent-scheme",
  "WITH BENEFICIARY BANK": "status-badge status-badge--with-beneficiary",
  "REJECTED BY SCHEME": "status-badge status-badge--rejected-scheme",
  "REJECTED BY BENEFICIARY BANK":
    "status-badge status-badge--rejected-beneficiary",
};

export function StatusBadge({ status, size = "md", icon }: StatusBadgeProps) {
  const cls = `${statusToClass[status]} status-badge--${size}`;
  return (
    <span className={cls}>
      {icon && <span className="status-badge__icon">{icon}</span>}
      {status}
    </span>
  );
}
