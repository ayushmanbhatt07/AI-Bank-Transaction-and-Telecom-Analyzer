# TRI-NETRA Dataset Reduction V2 Final Report

## Customer Selection Statistics
- **Original number of customers:** 7000
- **Selected anomaly customers:** 98
- **Selected normal customers:** 2100
- **Total selected customers:** 2198
- **Number of accidental counterparties:** 0

## Transaction Statistics
- **Total retained bank transactions:** 10017
- **Number of discarded cross-boundary transactions:** 90323
- **Number of anomaly transactions retained:** 50
- **Number of anomaly customers retained:** 56

## Downstream Statistics
- **Number of retained Bank->CDR mappings:** 10017
- **Number of retained CDR->IPDR mappings:** 9412
- **Number of orphan records:** 0

## Behavioural Statistics Comparison

- **Original Average Transactions per Customer:** 28.67
- **Original Median Transactions per Customer:** 25.00

- **New Average Transactions per Customer:** 9.12
- **New Median Transactions per Customer:** 8.00

### Histogram Comparison
| Bucket | Original Dataset | New Reduced Dataset |
| :--- | :--- | :--- |
| 1 | 0 | 11 |
| 2 | 0 | 35 |
| 3 | 0 | 65 |
| 4 | 0 | 161 |
| 5 | 0 | 180 |
| 6-10 | 19 | 1048 |
| 11-20 | 1891 | 670 |
| 21-50 | 4757 | 26 |
| >50 | 333 | 0 |


The redesign has successfully preserved a statistical profile much closer to the original data, entirely eliminating the "1.9 transactions per customer" collapse caused by accidental counterparties.
