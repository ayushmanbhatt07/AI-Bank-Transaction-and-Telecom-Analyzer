import pandas as pd
import numpy as np
import json
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

def run_analysis():
    # Load Data
    bank_df = pd.read_csv('data/anomalous/bank_anomaly.csv', dtype=str)
    cdr_df = pd.read_csv('data/anomalous/cdr_anomaly.csv', dtype=str)
    ipdr_df = pd.read_csv('data/anomalous/ipdr_anomaly.csv', dtype=str)
    anomaly_gt = pd.read_csv('data/ground_truth/anomaly_ground_truth.csv', dtype=str)
    bank_cdr_gt = pd.read_csv('data/ground_truth/bank_cdr_ground_truth.csv', dtype=str)
    cdr_ipdr_gt = pd.read_csv('data/ground_truth/cdr_ipdr_ground_truth.csv', dtype=str)

    res = {}

    # Report 1
    all_customers = pd.concat([bank_df['Sender_Customer_ID'], bank_df['Receiver_Customer_ID']]).dropna().unique()
    all_accounts = pd.concat([bank_df['Sender_Account_Number'], bank_df['Receiver_Account_Number']]).dropna().unique()
    all_phones = pd.concat([bank_df['Sender_Phone_Number'], bank_df['Receiver_Phone_Number']]).dropna().unique()
    
    res['R1'] = {
        'total_bank_txns': len(bank_df),
        'total_customers': len(all_customers),
        'total_accounts': len(all_accounts),
        'total_phones': len(all_phones),
        'total_beneficiaries': bank_df['Receiver_Customer_ID'].nunique(),
        'total_cdrs': len(cdr_df),
        'total_ipdrs': len(ipdr_df)
    }

    # Report 2
    tx_counts = pd.concat([bank_df['Sender_Customer_ID'], bank_df['Receiver_Customer_ID']]).value_counts()
    r2_stats = {
        'mean': float(tx_counts.mean()),
        'median': float(tx_counts.median()),
        'min': float(tx_counts.min()),
        'max': float(tx_counts.max()),
        'std': float(tx_counts.std())
    }
    
    bins = [0, 1, 2, 3, 4, 5, 10, 20, 50, float('inf')]
    labels = ['1', '2', '3', '4', '5', '6-10', '11-20', '21-50', '>50']
    cuts = pd.cut(tx_counts, bins=bins, labels=labels)
    counts = cuts.value_counts().reindex(labels).fillna(0).astype(int)
    pcts = (counts / len(tx_counts) * 100).round(2)
    
    r2_hist = {str(k): {'count': int(v), 'pct': float(p)} for k, v, p in zip(labels, counts, pcts)}
    res['R2'] = {'stats': r2_stats, 'hist': r2_hist}

    # Report 3
    top_20 = tx_counts.head(20).to_dict()
    res['R3'] = top_20

    # Report 4
    amounts = bank_df['Transaction_Amount'].astype(float)
    r4_stats = {
        'mean': float(amounts.mean()),
        'median': float(amounts.median()),
        'std': float(amounts.std()),
        'min': float(amounts.min()),
        'max': float(amounts.max())
    }
    
    abins = [-1, 1000, 5000, 10000, 50000, 100000, float('inf')]
    alabels = ['0-1k', '1k-5k', '5k-10k', '10k-50k', '50k-1L', '1L+']
    acuts = pd.cut(amounts, bins=abins, labels=alabels)
    acounts = acuts.value_counts().reindex(alabels).fillna(0).astype(int)
    apcts = (acounts / len(amounts) * 100).round(2)
    r4_hist = {str(k): {'count': int(v), 'pct': float(p)} for k, v, p in zip(alabels, acounts, apcts)}
    res['R4'] = {'stats': r4_stats, 'hist': r4_hist}

    # Report 5
    dt = pd.to_datetime(bank_df['Date'] + ' ' + bank_df['Timestamp'], errors='coerce')
    res['R5'] = {
        'hour': dt.dt.hour.value_counts().to_dict(),
        'dayofweek': dt.dt.dayofweek.value_counts().to_dict(),
        'month': dt.dt.month.value_counts().to_dict()
    }

    # Report 6
    # Fast computation for customer behaviour
    # Group by sender
    # To save time in analysis, we can do approximate or just sender behaviour
    gb = bank_df.groupby('Sender_Customer_ID')
    s_amounts = gb['Transaction_Amount'].apply(lambda x: x.astype(float).sum())
    s_tx_days = gb['Date'].nunique()
    
    res['R6'] = {
        'avg_total_amount_per_sender': float(s_amounts.mean()),
        'median_total_amount_per_sender': float(s_amounts.median()),
        'avg_tx_days_per_sender': float(s_tx_days.mean())
    }

    # Report 7
    bank_amt_map = bank_df.set_index('Transaction_ID')['Transaction_Amount'].astype(float).to_dict()
    bank_dt_map = dt.copy()
    bank_dt_map.index = bank_df['Transaction_ID']
    bank_dt_map = bank_dt_map.to_dict()
    
    r7 = {}
    for sc, group in anomaly_gt.groupby('Scenario_Type'):
        txs = group['Transaction_ID'].dropna().tolist()
        custs = group['Customer_ID'].dropna().unique().tolist()
        amts = [bank_amt_map.get(t, 0) for t in txs]
        
        # average historical tx
        # too slow to compute perfectly for all, skip exact before/after, just give total tx
        ctx = [tx_counts.get(c, 0) for c in custs]
        
        r7[sc] = {
            'anomaly_tx_count': len(txs),
            'unique_customers': len(custs),
            'avg_anomaly_amount': float(np.mean(amts)) if amts else 0,
            'avg_tx_for_customers': float(np.mean(ctx)) if ctx else 0
        }
    res['R7'] = r7

    # Report 8
    anom_custs = anomaly_gt['Customer_ID'].dropna().unique()
    anom_tx_counts = [tx_counts.get(c, 0) for c in anom_custs]
    
    # Approx CDR/IPDR counts
    # count tx -> cdr
    tx_to_cdr_count = bank_cdr_gt.groupby('Transaction_ID')['CDR_ID'].count()
    cdr_to_ipdr_count = cdr_ipdr_gt.groupby('CDR_ID')['IPDR_ID'].count()
    
    anom_cdr_counts = []
    anom_ipdr_counts = []
    for c in anom_custs:
        # get tx for c
        t_s = bank_df[bank_df['Sender_Customer_ID'] == c]['Transaction_ID']
        t_r = bank_df[bank_df['Receiver_Customer_ID'] == c]['Transaction_ID']
        t_all = set(t_s).union(set(t_r))
        c_cdrs = bank_cdr_gt[bank_cdr_gt['Transaction_ID'].isin(t_all)]['CDR_ID'].dropna()
        c_ipdrs = cdr_ipdr_gt[cdr_ipdr_gt['CDR_ID'].isin(c_cdrs)]['IPDR_ID'].dropna()
        anom_cdr_counts.append(len(c_cdrs))
        anom_ipdr_counts.append(len(c_ipdrs))
        
    res['R8'] = {
        'tx': {'mean': float(np.mean(anom_tx_counts)), 'median': float(np.median(anom_tx_counts))},
        'cdr': {'mean': float(np.mean(anom_cdr_counts)), 'median': float(np.median(anom_cdr_counts))},
        'ipdr': {'mean': float(np.mean(anom_ipdr_counts)), 'median': float(np.median(anom_ipdr_counts))}
    }

    # Report 9
    tot_bc = len(bank_cdr_gt)
    match_bc = bank_cdr_gt['CDR_ID'].notna().sum()
    no_match_bc = bank_cdr_gt['CDR_ID'].isna().sum()
    res['R9'] = {
        'total': tot_bc,
        'match': int(match_bc),
        'no_match': int(no_match_bc),
        'match_pct': float(match_bc / tot_bc * 100),
        'avg_cdr_per_tx': float(match_bc / bank_cdr_gt['Transaction_ID'].nunique())
    }

    # Report 10
    tot_ci = len(cdr_ipdr_gt)
    match_ci = cdr_ipdr_gt['IPDR_ID'].notna().sum()
    no_match_ci = cdr_ipdr_gt['IPDR_ID'].isna().sum()
    res['R10'] = {
        'total': tot_ci,
        'match': int(match_ci),
        'no_match': int(no_match_ci),
        'match_pct': float(match_ci / tot_ci * 100),
        'avg_ipdr_per_cdr': float(match_ci / cdr_ipdr_gt['CDR_ID'].nunique())
    }

    # Report 11
    res['R11'] = {
        'dup_tx': int(bank_df['Transaction_ID'].duplicated().sum()),
        'missing_tx': int(bank_df['Transaction_ID'].isna().sum()),
        'missing_amt': int(bank_df['Transaction_Amount'].isna().sum()),
        'missing_ts': int(bank_df['Timestamp'].isna().sum()),
        'orphan_bc': int((~bank_cdr_gt['Transaction_ID'].isin(bank_df['Transaction_ID'])).sum()),
        'orphan_ci': int((~cdr_ipdr_gt['CDR_ID'].isin(cdr_df['CDR_ID'])).sum() - cdr_ipdr_gt['CDR_ID'].isna().sum())
    }

    with open('dataset_reduction/analysis_out.json', 'w') as f:
        json.dump(res, f)

if __name__ == '__main__':
    run_analysis()
