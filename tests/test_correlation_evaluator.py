import os
import csv
from datetime import datetime
from src.correlation.evaluator import evaluate_predictions
from src.correlation.models import CorrelationRecord, RelationshipType, MatchStrength

def test_evaluator_precision_recall_f1(tmp_path):
    gt_file = tmp_path / "gt.csv"
    with open(gt_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["SourceID", "TargetID", "Is_Correlated"])
        writer.writerow(["S1", "T1", "1"]) # TP
        writer.writerow(["S2", "T2", "1"]) # TP
        writer.writerow(["S3", "T3", "1"]) # FN
        writer.writerow(["S4", "T4", "0"]) # Ignore
        
    predictions = [
        CorrelationRecord(
            correlation_id="1", relationship_type=RelationshipType.BANK_CDR,
            source_type="BANK", source_event_id="S1", source_timestamp=datetime.now(),
            target_type="CDR", target_event_id="T1", target_timestamp=datetime.now(),
            time_difference_seconds=0, identity_evidence=[], conflicting_evidence=[], match_strength=MatchStrength.STRONG, accepted=True
        ),
        CorrelationRecord(
            correlation_id="2", relationship_type=RelationshipType.BANK_CDR,
            source_type="BANK", source_event_id="S2", source_timestamp=datetime.now(),
            target_type="CDR", target_event_id="T2", target_timestamp=datetime.now(),
            time_difference_seconds=0, identity_evidence=[], conflicting_evidence=[], match_strength=MatchStrength.STRONG, accepted=True
        ),
        CorrelationRecord(
            correlation_id="3", relationship_type=RelationshipType.BANK_CDR,
            source_type="BANK", source_event_id="S5", source_timestamp=datetime.now(),
            target_type="CDR", target_event_id="T5", target_timestamp=datetime.now(),
            time_difference_seconds=0, identity_evidence=[], conflicting_evidence=[], match_strength=MatchStrength.STRONG, accepted=True
        ), # FP
    ]
    
    res = evaluate_predictions(predictions, str(gt_file), "SourceID", "TargetID")
    
    assert res["TP"] == 2
    assert res["FP"] == 1
    assert res["FN"] == 1
    
    assert res["precision"] == 2/3
    assert res["recall"] == 2/3
    assert res["f1"] == 2/3
