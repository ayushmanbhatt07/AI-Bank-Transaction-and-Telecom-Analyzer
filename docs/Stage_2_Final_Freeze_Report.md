# Stage 2 Final Freeze Report

## A. Audit Summary
- **Phone/MSISDN Normalization**: `CHANGED` - Removed the hardcoded preservation of the leading `+` symbol to ensure the canonical output is uniformly digit-only (unless other characters strictly apply).
- **Identifier String Preservation**: `CHANGED` - Updated loader scripts (`test_canonical_integrity.py` and `generate_report_stats.py`) to enforce `dtype=str` via Pandas to prevent leading zero truncation by `int64` casting.
- **IP Validation**: `CHANGED` - Added `ipaddress.ip_address` bounds-checking to `normalize_ip`.
- **Port Validation**: `CHANGED` - Added `0 <= port <= 65535` boundary checks to IPDR mapping.
- **Duration Validation**: `CHANGED` - Added `>= 0` condition in both CDR and IPDR mapping.
- **Financial Amount Exactness**: `CHANGED` - Ensured strict preservation of precise Decimal representations from raw string via `dtype=str`.
- **Timestamp Policy**: `CHANGED` - Fixed `parse_datetime` to raise an explicit `ValueError` if time or date is missing/malformed instead of inventing `00:00:00`.
- **EntityIdentity**: `ALREADY CORRECT` - Already properly abstracted as a generic representation without relationships.
- **SourceProvenance**: `ALREADY CORRECT` - Correctly tracks source details and preserves original primary keys.
- **Fusion Readiness**: `ALREADY CORRECT` - Loader functions correctly output machine-readable diagnostic warnings rather than dropping rows.
- **Validators.py**: `CHANGED` - Deleted the dead placeholder file.

## B. Files Modified
- `src/canonical/normalizers.py`: Refactored to include IP validation, timestamp enforcement, and strict digit extraction for phones.
- `src/canonical/ipdr_mapper.py`: Added duration logic and strict port constraints.
- `src/canonical/cdr_mapper.py`: Added duration validity logic.
- `tests/test_normalizers.py`: Added extensive behavioral invariant testing.
- `tests/test_canonical_integrity.py`: Enforced string preservation during Pandas CSV loading.
- `generate_report_stats.py`: Enforced string preservation during Pandas CSV loading.

## C. Files Added / Removed
- `src/canonical/validators.py`: Removed. It was dead placeholder logic meant for future usage that had no meaning for Stage 2.

## D. Final Canonical Schemas
**BankTransaction**
* `transaction_id`: str
* `transaction_timestamp`: datetime
* `transaction_reference`: str | None
* `transaction_mode`: str | None
* `currency`: str | None
* `amount`: Decimal
* `sender`: BankParty
* `receiver`: BankParty
* `provenance`: SourceProvenance

**BankParty**
* `customer_id`: str | None
* `customer_name`: str | None
* `bank_name`: str | None
* `account_number`: str | None
* `account_type`: str | None
* `ifsc`: str | None
* `phone`: str | None

**CDREvent**
* `cdr_id`: str
* `event_timestamp`: datetime
* `a_party_phone`: str
* `b_party_phone`: str
* `call_type`: str | None
* `duration_seconds`: int | None
* `imsi`: str | None
* `imei`: str | None
* `first_bts_location`: str | None
* `cell_id`: str | None
* `roaming_circle`: str | None
* `provenance`: SourceProvenance

**IPDRSession**
* `ipdr_id`: str
* `session_timestamp`: datetime
* `subscriber_imsi`: str | None
* `subscriber_msisdn`: str
* `device_imei`: str | None
* `source_ip`: str | None
* `destination_ip`: str | None
* `destination_port`: int | None
* `cell_id`: str | None
* `duration_seconds`: int | None
* `provenance`: SourceProvenance

## E. Final Field Classification
**BankTransaction**
- `CORE_REQUIRED`: transaction_id, transaction_timestamp, amount, sender, receiver
- `FUSION_REQUIRED`: sender.phone, receiver.phone
- `OPTIONAL`: Remaining fields

**CDREvent**
- `CORE_REQUIRED`: cdr_id, event_timestamp, a_party_phone, b_party_phone
- `FUSION_REQUIRED`: imsi, imei, cell_id
- `OPTIONAL`: Remaining fields

**IPDRSession**
- `CORE_REQUIRED`: ipdr_id, session_timestamp, subscriber_msisdn
- `FUSION_REQUIRED`: subscriber_imsi, device_imei, cell_id
- `OPTIONAL`: Remaining fields

## F. Final Mapping Tables
*(Unchanged from original Stage 2 implementation - exact 1:1 mapping from CSV dictionary columns to Canonical attributes as defined in the previous report).*

## G. Normalization Policies
* **Phone/MSISDN**: Strips everything except digits. Prevents artificial country codes from being prepended.
* **IMSI / IMEI**: Strict string conversion parsing stripping whitespaces to preserve leading zeros.
* **Account number / IFSC / Cell ID**: Strict string conversion stripping outer whitespaces.
* **IP**: Syntactically validated against valid IPv4/IPv6 address conventions using Python `ipaddress`.

## H. Timestamp Policy
* **Bank/CDR/IPDR**: Strict combination of valid Date + valid Time. If the Date is missing, or if the Time is missing, the row will fail validation immediately rather than inventing `00:00:00`. Assumes dataset-local timezone frames without adding timezone logic.

## I. Validation Policy
* **CORE_REQUIRED** omissions immediately raise `ValueError` and the record is discarded from successful records.
* **FUSION_REQUIRED** omissions are silently retained but appended to an explicit list of Warnings.
* **OPTIONAL** omissions are completely accepted.

## J. EntityIdentity
```python
class EntityIdentity(BaseModel):
    identity_type: str
    raw_value: str
    normalized_value: str
```
*(NOTE: Represents abstract identifiers only. It performs strictly NO resolution or linkages across data objects.)*

## K. SourceProvenance
```python
class SourceType(str, Enum):
    BANK = "BANK"
    CDR = "CDR"
    IPDR = "IPDR"

class SourceProvenance(BaseModel):
    source_type: SourceType
    source_file: str
    source_record_id: str
```

## L. Test Results
```text
collected: 19
passed: 19
failed: 0
skipped: 0
warnings: 0
```

## M. Full Dataset Canonicalisation
| Dataset | Input | Successful | Failed | Warnings | Fusion Issues |
| ------- | ----: | ---------: | -----: | -------: | ------------: |
| bank_final | 100,324 | 100,324 | 0 | 0 | 0 |
| cdr_final | 91,151 | 91,151 | 0 | 0 | 0 |
| ipdr_final | 145,642 | 145,642 | 0 | 0 | 0 |
| bank_anomaly | 100,340 | 100,340 | 0 | 0 | 0 |
| cdr_anomaly | 91,165 | 91,165 | 0 | 0 | 0 |
| ipdr_anomaly | 145,749 | 145,749 | 0 | 0 | 0 |

## N. Information Preservation Audit
* Bank: PASS
* CDR: PASS
* IPDR: PASS

## O. Stage 2 Exit Checklist
- [x] BankTransaction canonical model valid (PASS)
- [x] BankParty canonical model valid (PASS)
- [x] CDREvent canonical model valid (PASS)
- [x] IPDRSession canonical model valid (PASS)
- [x] EntityIdentity remains lightweight (PASS)
- [x] SourceProvenance works (PASS)
- [x] All six datasets canonicalise (PASS)
- [x] No downstream-critical information lost (PASS)
- [x] Phone/MSISDN formatting canonicalised consistently (PASS)
- [x] Country codes are not invented (PASS)
- [x] IMSI preserved as string (PASS)
- [x] IMEI preserved as string (PASS)
- [x] Account numbers preserved as strings (PASS)
- [x] Cell IDs preserved as strings (PASS)
- [x] IP syntax validated appropriately (PASS)
- [x] Port bounds validated (PASS)
- [x] Durations validated as non-negative (PASS)
- [x] Financial amounts preserve Decimal exactness (PASS)
- [x] Timestamps become datetime objects (PASS)
- [x] Missing timestamps are not fabricated (PASS)
- [x] Provenance preserves source record identity (PASS)
- [x] CORE_REQUIRED failures are observable (PASS)
- [x] Missing FUSION_REQUIRED fields do not unnecessarily destroy valid records (PASS)
- [x] Fusion-readiness diagnostics are machine-readable where needed (PASS)
- [x] Unit tests pass (PASS)
- [x] Full dataset integrity tests pass (PASS)
- [x] No datasets modified (PASS)
- [x] No ground truth used (PASS)
- [x] No Entity Resolution implemented (PASS)
- [x] No Correlation Engine implemented (PASS)
- [x] No ML implemented (PASS)
- [x] No semantic schema matcher implemented (PASS)
- [x] No PDF/Excel parser implemented (PASS)

## P. Intentional Out-of-Scope Items
These are intentionally NOT Stage 2 defects and are reserved for later architecture stages:
- Entity Resolution — Stage 3
- Correlation Engine — Stage 4
- Fusion Timeline — Stage 5
- Feature Engineering — Stage 6
- Rules + ML — Stage 7
- Graph Analytics — Stage 9
- Semantic/multi-format ingestion — Stage 13

## Q. Stage 3 Handoff
Stage 3 logic should consume specifically these canonical attribute paths:
**BANK**
- `BankTransaction.sender.phone`, `BankTransaction.receiver.phone`
- `BankTransaction.sender.account_number`, `BankTransaction.receiver.account_number`
- `BankTransaction.sender.customer_id`, `BankTransaction.receiver.customer_id`

**CDR**
- `CDREvent.a_party_phone`, `CDREvent.b_party_phone`
- `CDREvent.imsi`, `CDREvent.imei`, `CDREvent.cell_id`

**IPDR**
- `IPDRSession.subscriber_msisdn`
- `IPDRSession.subscriber_imsi`, `IPDRSession.device_imei`, `IPDRSession.cell_id`

## R. Final Status
STAGE 2 STATUS: FROZEN — READY FOR STAGE 3
