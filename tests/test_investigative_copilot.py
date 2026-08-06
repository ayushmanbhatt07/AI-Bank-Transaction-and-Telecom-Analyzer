"""Tests for the standalone LLM Investigative Co-Pilot module."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from investigative_copilot.db_builder import CopilotDBBuilder
from investigative_copilot.graph_engine import CopilotGraphEngine
from investigative_copilot.copilot_engine import InvestigativeCoPilotEngine

@pytest.fixture(scope="module")
def db_conn():
    builder = CopilotDBBuilder()
    conn = builder.build_database()
    return conn

@pytest.fixture(scope="module")
def graph_engine(db_conn):
    return CopilotGraphEngine(db_conn)

@pytest.fixture(scope="module")
def copilot_engine(db_conn):
    return InvestigativeCoPilotEngine(conn=db_conn)

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

def test_db_builder_schema_and_counts(db_conn):
    cursor = db_conn.cursor()
    cursor.execute("SELECT count(*) as c FROM bank_transactions")
    bank_cnt = cursor.fetchone()["c"]
    assert bank_cnt > 0, "bank_transactions table should not be empty"

    cursor.execute("SELECT count(*) as c FROM cdr_records")
    cdr_cnt = cursor.fetchone()["c"]
    assert cdr_cnt > 0, "cdr_records table should not be empty"

    cursor.execute("SELECT count(*) as c FROM ipdr_records")
    ipdr_cnt = cursor.fetchone()["c"]
    assert ipdr_cnt > 0, "ipdr_records table should not be empty"

    cursor.execute("SELECT count(*) as c FROM bank_cdr_links")
    b_cdr_cnt = cursor.fetchone()["c"]
    assert b_cdr_cnt > 0, "bank_cdr_links table should not be empty"

    cursor.execute("SELECT count(*) as c FROM cdr_ipdr_links")
    c_ipdr_cnt = cursor.fetchone()["c"]
    assert c_ipdr_cnt > 0, "cdr_ipdr_links table should not be empty"

def test_graph_engine_3_hops(graph_engine, db_conn):
    cursor = db_conn.cursor()
    cursor.execute("SELECT sender_account_number FROM bank_transactions LIMIT 1")
    acc = cursor.fetchone()["sender_account_number"]
    
    trace_res = graph_engine.trace_mule_chain(acc, max_hops=3)
    assert trace_res["found"] is True
    assert trace_res["max_hops"] == 3
    assert "layers" in trace_res
    assert "Layer-1 Mules" in trace_res["layers"]

def test_copilot_west_bengal_query(copilot_engine):
    res = copilot_engine.analyze_query("Show me all accounts that received money within 5 minutes of a call originating from West Bengal tower locations.")
    assert res["execution_success"] is True
    assert len(res["chain_of_thought"]) == 5
    assert "West Bengal" in res["intent"] or "5 minutes" in res["intent"]
    assert res["executive_summary"] != ""

def test_copilot_mule_trace_query(copilot_engine):
    res = copilot_engine.analyze_query("Trace the 3-hop mule money flow from ACC_1001.")
    assert res["execution_success"] is True
    assert "graph_traversal" in res
    assert res["graph_traversal"]["max_hops"] == 3

def test_sql_safety_guard(copilot_engine):
    with pytest.raises(ValueError, match="Security violation"):
        copilot_engine._execute_safe_sql("DROP TABLE bank_transactions;")

    with pytest.raises(ValueError, match="Security violation"):
        copilot_engine._execute_safe_sql("DELETE FROM cdr_records;")

def test_fastapi_copilot_endpoints(client):
    # GET /api/v1/copilot/stats
    resp_stats = client.get("/api/v1/copilot/stats")
    assert resp_stats.status_code == 200
    data_stats = resp_stats.json()
    assert data_stats["dataset_source"] == "data/new_reduced"
    assert data_stats["max_graph_hops"] == 3

    # GET /api/v1/copilot/schema
    resp_schema = client.get("/api/v1/copilot/schema")
    assert resp_schema.status_code == 200
    assert len(resp_schema.json()["sample_queries"]) >= 4

    # POST /api/v1/copilot/query
    resp_q = client.post("/api/v1/copilot/query", json={
        "query": "Show me all accounts that received money within 5 minutes of a call originating from West Bengal tower locations."
    })
    assert resp_q.status_code == 200
    data_q = resp_q.json()
    assert data_q["execution_success"] is True
    assert len(data_q["chain_of_thought"]) == 5

    # POST /api/v1/copilot/summarize-cluster (with real account)
    resp_sum = client.post("/api/v1/copilot/summarize-cluster", json={
        "entity_ids": ["365749599063", "449243629194"]
    })
    assert resp_sum.status_code == 200
    data_sum = resp_sum.json()
    assert "executive_summary" in data_sum
    assert "Layer-1 mule" in data_sum["executive_summary"]

    # POST /api/v1/copilot/summarize-cluster (with transaction ID)
    resp_tx = client.post("/api/v1/copilot/summarize-cluster", json={
        "entity_ids": ["TXN250101PJA1WJ"]
    })
    assert resp_tx.status_code == 200
    data_tx = resp_tx.json()
    assert data_tx["graph_analysis"]["found"] is True
    assert "Layer-1 mule" in data_tx["executive_summary"]
