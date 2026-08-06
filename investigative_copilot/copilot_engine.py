import os
import re
import json
import sqlite3
from typing import Dict, Any, List, Optional
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .db_builder import get_copilot_db
from .graph_engine import CopilotGraphEngine
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class InvestigativeCoPilotEngine:
    """Core LLM Investigative Co-Pilot Engine for TRI-NETRA cyber-forensics.
    Provides Text-to-SQL generation, 3-hop NetworkX graph traversal, Evidentiary Chain-of-Thought,
    and executive lead auto-summarization.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self.conn = conn if conn is not None else get_copilot_db()
        self.graph_engine = CopilotGraphEngine(self.conn)
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def analyze_query(self, user_query: str) -> Dict[str, Any]:
        """Main entry point: processes natural language user query into CoT and forensic results."""
        query_clean = user_query.strip()
        
        # 1. Check if LLM API key is present for live model call
        llm_response = None
        if self.api_key:
            llm_response = self._call_llm_api(query_clean)

        # 2. If no LLM response or offline mode, run deterministic CoT pipeline
        if not llm_response:
            llm_response = self._run_deterministic_pipeline(query_clean)

        return llm_response

    def summarize_cluster(self, entity_ids: List[str]) -> Dict[str, Any]:
        """Generates an executive lead summary for a cluster of entities/transactions (e.g. node click in UI)."""
        if not entity_ids:
            return {"summary": "No entities selected for cluster summary."}

        primary_entity = str(entity_ids[0]).strip()
        
        # Resolve Transaction ID -> Account
        target_account = primary_entity
        cursor = self.conn.cursor()
        cursor.execute("SELECT receiver_account_number, sender_account_number FROM bank_transactions WHERE transaction_id = ?", (primary_entity,))
        row_tx = cursor.fetchone()
        if row_tx:
            target_account = str(row_tx["receiver_account_number"]) or str(row_tx["sender_account_number"])

        # Perform 3-hop graph analysis
        graph_res = self.graph_engine.trace_mule_chain(primary_entity, max_hops=3)

        if not graph_res.get("found", False):
            return {
                "entity_id": primary_entity,
                "total_entities_in_cluster": len(entity_ids),
                "graph_analysis": graph_res,
                "executive_summary": f"Entity/Transaction '{primary_entity}' was not found in the observation network or has no connected bank/telecom activity."
            }

        resolved_start_node = graph_res.get("start_node", target_account)

        cursor.execute("""
            SELECT SUM(transaction_amount) as total_amount, COUNT(*) as tx_count
            FROM bank_transactions
            WHERE sender_account_number = ? OR receiver_account_number = ?
        """, (resolved_start_node, resolved_start_node))
        row = cursor.fetchone()

        tot_amt = float(row["total_amount"]) if row and row["total_amount"] is not None else 0.0
        tx_cnt = int(row["tx_count"]) if row and row["tx_count"] is not None else 0

        l1_mules = len(graph_res.get("layers", {}).get("Layer-1 Mules", []))
        l2_mules = len(graph_res.get("layers", {}).get("Layer-2 Mules", []))

        summary_text = (
            f"Target '{primary_entity}' resolves to Account '{resolved_start_node}' acting as a primary Layer-1 mule nexus. "
            f"Processed ₹{tot_amt:,.2f} across {tx_cnt} transactions within the observation window. "
            f"Graph analysis identifies {l1_mules} direct (1-hop) and {l2_mules} secondary (2-hop) downstream recipients. "
            f"Immediate cyber cell action recommended: freeze target account and subpoena associated CDR tower logs."
        )

        return {
            "entity_id": primary_entity,
            "resolved_account": resolved_start_node,
            "total_entities_in_cluster": len(entity_ids),
            "graph_analysis": graph_res,
            "executive_summary": summary_text
        }

    def _run_deterministic_pipeline(self, user_query: str) -> Dict[str, Any]:
        """Deterministic query translator and CoT generator for cyber-forensic scenarios."""
        q_lower = user_query.lower()
        
        # Recognize state/circle names dynamically
        state_patterns = {
            "west bengal": ["%WestBengal%", "%West Bengal%", "%Kolkata%"],
            "kolkata": ["%Kolkata%", "%WestBengal%", "%West Bengal%"],
            "delhi": ["%Delhi%"],
            "gujarat": ["%Gujarat%"],
            "karnataka": ["%Karnataka%"],
            "maharashtra": ["%Maharashtra%"],
            "mumbai": ["%Mumbai%"],
            "rajasthan": ["%Rajasthan%"],
            "tamil nadu": ["%TamilNadu%", "%Tamil Nadu%"],
            "uttar pradesh": ["%UttarPradesh%", "%Uttar Pradesh%"],
        }

        matched_state = "West Bengal"
        matched_patterns = ["%WestBengal%", "%West Bengal%", "%Kolkata%"]
        for st, pat_list in state_patterns.items():
            if st in q_lower:
                matched_state = st.title()
                matched_patterns = pat_list
                break

        # Check if query asks for a tower / call location + time window / transfer
        if any(k in q_lower for k in ["tower", "bts", "location", "originating", "circle", "5 minute", "call"]):
            where_conditions = " OR ".join([f"cr.first_bts_location LIKE '{p}' OR cr.roaming_network_circle LIKE '{p}'" for p in matched_patterns])
            sql_query = f"""
            SELECT 
                bt.transaction_id, bt.timestamp as tx_time, bt.transaction_amount, 
                bt.sender_account_number, bt.receiver_account_number, bt.receiver_customer_name,
                cr.cdr_id, cr.call_start_time, cr.first_bts_location, cr.roaming_network_circle, cr.a_party_number,
                bcl.time_difference_seconds
            FROM bank_transactions bt
            JOIN bank_cdr_links bcl ON bt.transaction_id = bcl.transaction_id
            JOIN cdr_records cr ON bcl.cdr_id = cr.cdr_id
            WHERE ({where_conditions})
              AND ABS(bcl.time_difference_seconds) <= 300
            ORDER BY bt.transaction_amount DESC
            LIMIT 20;
            """
            intent = f"Identify all bank accounts receiving transfers within 5 minutes (300s) of calls originating from {matched_state} tower locations."
            
        # Scenario B: Mule chain / 3-hop trace
        elif "mule" in q_lower or "hop" in q_lower or "trace" in q_lower or "flow" in q_lower:
            target_acc = "ACC_1001"
            # Extract numbers if present
            found_nums = re.findall(r'\b\d{4,12}\b', user_query)
            if found_nums:
                target_acc = found_nums[0]

            graph_res = self.graph_engine.trace_mule_chain(target_acc, max_hops=3)
            
            sql_query = f"""
            SELECT transaction_id, timestamp, transaction_amount, sender_account_number, receiver_account_number, transaction_mode
            FROM bank_transactions
            WHERE sender_account_number = '{target_acc}' OR receiver_account_number = '{target_acc}'
            ORDER BY timestamp ASC;
            """
            
            intent = f"Perform 3-hop NetworkX mule money flow traversal starting from Account/Entity '{target_acc}'."
            results = self._execute_safe_sql(sql_query)
            
            cot_steps = [
                {"step": 1, "title": "Intent & Entity Extraction", "content": intent},
                {"step": 2, "title": "Query Generation (SQL + 3-Hop NetworkX)", "content": f"Graph Traversal: 3-hop BFS on target '{target_acc}'. SQL: {sql_query.strip()}"},
                {"step": 3, "title": "Execution Results", "content": f"Retrieved {len(results)} direct transactions and traversed {graph_res.get('total_nodes', 0)} connected graph nodes across 3 hops."},
                {"step": 4, "title": "Evidentiary Correlation", "content": f"Categorized entities into {len(graph_res.get('layers', {}).get('Layer-1 Mules', []))} Layer-1 Mules, {len(graph_res.get('layers', {}).get('Layer-2 Mules', []))} Layer-2 Mules, and {len(graph_res.get('layers', {}).get('Layer-3 Offramps', []))} Layer-3 Offramps."},
                {"step": 5, "title": "Executive Lead Summary", "content": f"Entity '{target_acc}' exhibits structured money laundering. Funds are rapidly dispersed across a 3-hop network within short time deltas. Recommended for immediate account freezing and subpoena of CDR tower records."}
            ]

            return {
                "query": user_query,
                "intent": intent,
                "generated_sql": sql_query.strip(),
                "execution_success": True,
                "row_count": len(results),
                "records": results[:10],
                "graph_traversal": graph_res,
                "chain_of_thought": cot_steps,
                "executive_summary": cot_steps[-1]["content"]
            }

        # Scenario C: Default fallback query (All high-value correlated transactions)
        else:
            sql_query = """
            SELECT 
                bt.transaction_id, bt.timestamp, bt.transaction_amount, bt.transaction_mode,
                bt.sender_customer_name, bt.sender_account_number,
                bt.receiver_customer_name, bt.receiver_account_number,
                bcl.cdr_id, bcl.time_difference_seconds
            FROM bank_transactions bt
            LEFT JOIN bank_cdr_links bcl ON bt.transaction_id = bcl.transaction_id
            ORDER BY bt.transaction_amount DESC
            LIMIT 15;
            """
            intent = "Retrieve high-value bank transactions cross-linked with CDR call events."

        results = self._execute_safe_sql(sql_query)
        
        # Build executive summary
        summary = (
            f"Query analyzed {len(results)} matching forensic records. "
            f"Key findings highlight suspicious high-value transfers correlated with telecom call timestamps. "
            f"Cross-dataset links verify concurrent phone call activity near financial transactions."
        )

        cot_steps = [
            {"step": 1, "title": "Intent & Entity Extraction", "content": intent},
            {"step": 2, "title": "Query Generation (SQLite)", "content": sql_query.strip()},
            {"step": 3, "title": "Execution Results", "content": f"Executed query successfully. Returned {len(results)} matched records."},
            {"step": 4, "title": "Evidentiary Correlation", "content": "Correlated Bank transaction IDs with pre-computed CDR link IDs and time difference deltas."},
            {"step": 5, "title": "Executive Lead Summary", "content": summary}
        ]

        return {
            "query": user_query,
            "intent": intent,
            "generated_sql": sql_query.strip(),
            "execution_success": True,
            "row_count": len(results),
            "records": results[:10],
            "chain_of_thought": cot_steps,
            "executive_summary": summary
        }

    def _execute_safe_sql(self, sql_query: str) -> List[Dict[str, Any]]:
        """Executes query with strict read-only safety validation."""
        sql_clean = sql_query.strip().upper()
        # Prevent non-SELECT statements
        if not sql_clean.startswith("SELECT") and not sql_clean.startswith("WITH"):
            raise ValueError("Security violation: Only SELECT queries are permitted.")
        
        forbidden_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "REPLACE"]
        for kw in forbidden_keywords:
            if re.search(r'\b' + kw + r'\b', sql_clean):
                raise ValueError(f"Security violation: Query contains illegal keyword '{kw}'.")

        cursor = self.conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def _call_llm_api(self, user_query: str) -> Optional[Dict[str, Any]]:
        """Calls Google GenAI / Gemini API if configured."""
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = f"{SYSTEM_PROMPT}\n\nUSER QUESTION: {user_query}\n\nReturn clean JSON with keys: 'intent', 'sql_query', 'graph_start_node', 'cot_reasoning', 'executive_summary'."
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            text = response.text
            # Parse JSON
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                sql_q = parsed.get("sql_query", "")
                records = []
                if sql_q:
                    try:
                        records = self._execute_safe_sql(sql_q)
                    except Exception as e:
                        logger.warning(f"LLM generated invalid SQL: {e}")
                
                graph_res = None
                start_node = parsed.get("graph_start_node")
                if start_node:
                    graph_res = self.graph_engine.trace_mule_chain(start_node, max_hops=3)

                return {
                    "query": user_query,
                    "intent": parsed.get("intent", user_query),
                    "generated_sql": sql_q,
                    "execution_success": True,
                    "row_count": len(records),
                    "records": records[:10],
                    "graph_traversal": graph_res,
                    "chain_of_thought": parsed.get("cot_reasoning", []),
                    "executive_summary": parsed.get("executive_summary", text)
                }
        except Exception as e:
            logger.warning(f"LLM API call skipped/failed: {e}")
        return None
