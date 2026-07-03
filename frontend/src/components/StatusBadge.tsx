import type { ReactNode } from "react";
import type { BusinessStatus } from "../types/api";

interface StatusBadgeProps {
  status: BusinessStatus;
  size?: "sm" | "md";
  icon?: ReactNode;
}

const statusToClass: Record<BusinessStatus, string> = {
  "WITH BANK": "status-badge status-badge--with-bank",
  "WITH SCHEME": "status-badge status-badge--with-scheme",
  "WITH BENEFICIARY BANK": "status-badge status-badge--with-beneficiary",
  CLEARED: "status-badge status-badge--cleared",
  REJECTED: "status-badge status-badge--rejected",
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
