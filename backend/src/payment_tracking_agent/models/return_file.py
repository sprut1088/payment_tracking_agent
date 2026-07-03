"""Models for NACHA return file processing."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# NACHA return reason code → human-readable description
RETURN_REASON_DESCRIPTIONS: dict[str, str] = {
    "R01": "Insufficient Funds",
    "R02": "Account Closed",
    "R03": "No Account / Unable to Locate Account",
    "R04": "Invalid Account Number Structure",
    "R05": "Unauthorized Debit to Consumer Account",
    "R06": "Returned per ODFI Request",
    "R07": "Authorization Revoked by Customer",
    "R08": "Payment Stopped",
    "R09": "Uncollected Funds",
    "R10": "Customer Advises Not Authorized",
    "R11": "Check Truncation Entry Return",
    "R12": "Branch Sold to Another DFI",
    "R13": "RDFI Not Qualified to Participate",
    "R14": "Representative Payee Deceased or Unable to Continue",
    "R15": "Beneficiary or Account Holder Deceased",
    "R16": "Account Frozen / Blocked",
    "R17": "File Record Edit Criteria",
    "R20": "Non-Transaction Account",
    "R21": "Invalid Company Identification",
    "R22": "Invalid Individual ID Number",
    "R23": "Credit Entry Refused by Receiver",
    "R24": "Duplicate Entry",
    "R29": "Corporate Customer Advises Not Authorized",
    "R31": "Permissible Return Entry",
}


class ReturnRecord(BaseModel):
    """One matched or unmatched return entry from a NACHA return file."""

    trace_number: str
    return_reason_code: str
    return_reason_description: str
    individual_name: str
    amount_cents: int
    amount: float
    receiving_dfi: str
    # Set when the trace number matched a stored payment
    matched_upload_id: str | None = None
    matched: bool = False


class ProcessedReturnFile(BaseModel):
    """Result of processing a NACHA return file."""

    return_file_id: str
    file_name: str
    file_path: str
    processed_at: datetime
    return_records: list[ReturnRecord]
    matched_count: int
    unmatched_count: int
