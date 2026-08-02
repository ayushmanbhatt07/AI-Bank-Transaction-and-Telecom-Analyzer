"""Quick validation script for the refactored parser modules."""
import sys
import os

# Ensure the pdf-parser directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("SCHEMA_MAPPER VALIDATION")
print("=" * 60)

import schema_mapper
print("  schema_mapper imports OK")
print(f"  Config keys: {len(schema_mapper.PARSER_CONFIG)} values")
print(f"  Bank aliases: {len(schema_mapper.BANK_ALIASES)} fields")
print(f"  CDR aliases: {len(schema_mapper.CDR_ALIASES)} fields")
print(f"  IPDR aliases: {len(schema_mapper.IPDR_ALIASES)} fields")
print(f"  Deterministic markers: {list(schema_mapper.DATASET_MARKERS.keys())}")
print(f"  All valid terms: {len(schema_mapper.get_all_valid_terms())} terms")

# Test dataset detection with known bank headers
bank_headers = ["Txn Date", "Description", "Ref No", "Debit", "Credit", "Balance"]
result = schema_mapper.detect_dataset_type(bank_headers)
print(f"  Bank detection test: {result} (expected: bank)")
assert result == "bank", f"Expected 'bank', got '{result}'"

# Test dataset detection with CDR headers
cdr_headers = ["Call Date", "Calling Number", "Called Number", "Duration", "IMEI", "Cell ID"]
result = schema_mapper.detect_dataset_type(cdr_headers)
print(f"  CDR detection test: {result} (expected: cdr)")
assert result == "cdr", f"Expected 'cdr', got '{result}'"

# Test dataset detection with IPDR headers
ipdr_headers = ["Session Date", "Source IP", "Dest IP", "Dest Port", "MSISDN", "Duration"]
result = schema_mapper.detect_dataset_type(ipdr_headers)
print(f"  IPDR detection test: {result} (expected: ipdr)")
assert result == "ipdr", f"Expected 'ipdr', got '{result}'"

# Test find_best_match
used = set()
match = schema_mapper.find_best_match("Txn Date", "bank", used)
print(f"  'Txn Date' -> {match}")
assert match is not None and match[0] == "Date"

match2 = schema_mapper.find_best_match("Calling Number", "cdr", used)
print(f"  'Calling Number' -> {match2}")
assert match2 is not None and match2[0] == "A_Party_Number"

match3 = schema_mapper.find_best_match("Src IP", "ipdr", used)
print(f"  'Src IP' -> {match3}")
assert match3 is not None and match3[0] == "Source_IP_Address"

print("\n" + "=" * 60)
print("PDF_PARSER VALIDATION")
print("=" * 60)

import pdf_parser
print("  pdf_parser imports OK")
print(f"  Min required fields: {list(pdf_parser.MINIMUM_REQUIRED_FIELDS.keys())}")

# Test amount parsing
test_cases = [
    ("(1,234.56)", -1234.56),
    ("1234.56-", -1234.56),
    ("Rs. 5,000 DR", -5000.0),
    ("1,23,456.78", 123456.78),
    ("-1,234.56", -1234.56),
    ("5000 CR", 5000.0),
    ("", None),
    ("INR 10,500.25", 10500.25),
    ("INR 999", 999.0),
    ("50.00", 50.0),
    ("(500)", -500.0),
]

print("  Amount parsing tests:")
all_passed = True
for input_val, expected in test_cases:
    result = pdf_parser._parse_amount(input_val)
    status = "PASS" if result == expected else "FAIL"
    if status == "FAIL":
        all_passed = False
    print(f"    {status}: '{input_val}' -> {result} (expected {expected})")

# Test validation with minimal bank fields
import pandas as pd
import numpy as np

# Should pass: has Date and Transaction_Amount
df_ok = pd.DataFrame({
    "Date": ["2024-01-01", "2024-01-02"],
    "Transaction_Amount": [100.0, -50.0],
})
warnings = pdf_parser._validate_schema(df_ok, "bank")
print(f"\n  Validation test (bank, minimal valid): PASS ({len(warnings)} warnings)")

# Should pass: has Date and Transaction_Amount_Merged
df_merged = pd.DataFrame({
    "Date": ["2024-01-01"],
    "Transaction_Amount_Merged": [100.0],
})
df_merged_schema = schema_mapper.ensure_schema(df_merged, "bank")
# Transaction_Amount will be NA but Transaction_Amount_Merged won't be in schema
# So we need to test with Transaction_Amount present
df_merged2 = pd.DataFrame({
    "Date": ["2024-01-01"],
    "Transaction_Amount": [pd.NA],
    "Transaction_Amount_Merged": [100.0],
})
warnings2 = pdf_parser._validate_schema(df_merged2, "bank")
print(f"  Validation test (bank, merged amount fallback): PASS ({len(warnings2)} warnings)")

# Should pass CDR: has Call_Date and B_Party_Number (not A_Party)
df_cdr = pd.DataFrame({
    "Call_Date": ["2024-01-01"],
    "B_Party_Number": ["9876543210"],
})
warnings3 = pdf_parser._validate_schema(df_cdr, "cdr")
print(f"  Validation test (CDR, B_Party only): PASS ({len(warnings3)} warnings)")

# Should pass IPDR: has Session_Date and Subscriber_MSISDN (not Source_IP)
df_ipdr = pd.DataFrame({
    "Session_Date": ["2024-01-01"],
    "Subscriber_MSISDN": ["9876543210"],
})
warnings4 = pdf_parser._validate_schema(df_ipdr, "ipdr")
print(f"  Validation test (IPDR, MSISDN only): PASS ({len(warnings4)} warnings)")

# Should FAIL: no amount field at all
df_fail = pd.DataFrame({
    "Date": ["2024-01-01"],
})
try:
    pdf_parser._validate_schema(df_fail, "bank")
    print("  Validation test (bank, no amount): FAIL - should have raised")
except ValueError as e:
    print(f"  Validation test (bank, no amount): PASS - correctly raised ValueError")

print("\n" + "=" * 60)
if all_passed:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED")
print("=" * 60)
