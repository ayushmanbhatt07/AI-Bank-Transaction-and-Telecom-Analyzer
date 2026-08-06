import sqlite3
import networkx as nx
from typing import Dict, Any, List, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)

class CopilotGraphEngine:
    """NetworkX Graph Engine for TRI-NETRA Investigative Co-Pilot.
    Builds a multi-layer graph across Bank, CDR, and IPDR entities,
    and performs 3-hop graph traversals to trace mule money flows and communication networks.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.graph = nx.MultiDiGraph()
        self._build_graph()

    def _build_graph(self) -> None:
        """Constructs the NetworkX graph from SQLite tables."""
        cursor = self.conn.cursor()

        # 1. Add Bank Transaction Edges (Account -> Account)
        cursor.execute("""
            SELECT sender_account_number, sender_customer_name, sender_phone_number,
                   receiver_account_number, receiver_customer_name, receiver_phone_number,
                   transaction_amount, timestamp, transaction_id, transaction_mode
            FROM bank_transactions
        """)
        for row in cursor.fetchall():
            s_acc = str(row["sender_account_number"]) if row["sender_account_number"] else None
            r_acc = str(row["receiver_account_number"]) if row["receiver_account_number"] else None
            
            if s_acc and r_acc:
                # Add nodes
                self.graph.add_node(s_acc, type="account", name=row["sender_customer_name"], phone=row["sender_phone_number"])
                self.graph.add_node(r_acc, type="account", name=row["receiver_customer_name"], phone=row["receiver_phone_number"])
                
                # Add directed money flow edge
                self.graph.add_edge(
                    s_acc, r_acc,
                    edge_type="bank_transfer",
                    amount=float(row["transaction_amount"]) if row["transaction_amount"] is not None else 0.0,
                    timestamp=str(row["timestamp"]),
                    tx_id=str(row["transaction_id"]),
                    mode=str(row["transaction_mode"])
                )

                # Connect account to sender phone
                s_phone = str(row["sender_phone_number"]) if row["sender_phone_number"] else None
                if s_phone and s_phone.strip() and s_phone != "nan":
                    self.graph.add_node(s_phone, type="phone")
                    self.graph.add_edge(s_acc, s_phone, edge_type="account_phone_link")

                r_phone = str(row["receiver_phone_number"]) if row["receiver_phone_number"] else None
                if r_phone and r_phone.strip() and r_phone != "nan":
                    self.graph.add_node(r_phone, type="phone")
                    self.graph.add_edge(r_acc, r_phone, edge_type="account_phone_link")

        # 2. Add CDR Call Edges (Phone -> Phone)
        cursor.execute("""
            SELECT a_party_number, b_party_number, call_duration_seconds,
                   call_start_time, cdr_id, first_bts_location, call_type
            FROM cdr_records
        """)
        for row in cursor.fetchall():
            a_num = str(row["a_party_number"]) if row["a_party_number"] else None
            b_num = str(row["b_party_number"]) if row["b_party_number"] else None

            if a_num and b_num:
                self.graph.add_node(a_num, type="phone")
                self.graph.add_node(b_num, type="phone")
                
                self.graph.add_edge(
                    a_num, b_num,
                    edge_type="cdr_call",
                    duration=int(row["call_duration_seconds"]) if row["call_duration_seconds"] is not None else 0,
                    timestamp=str(row["call_start_time"]),
                    cdr_id=str(row["cdr_id"]),
                    bts=str(row["first_bts_location"]),
                    call_type=str(row["call_type"])
                )

        # 3. Add Bank-CDR Correlated Edges
        cursor.execute("""
            SELECT transaction_id, cdr_id, time_difference_seconds, is_correlated
            FROM bank_cdr_links
            WHERE is_correlated = 1 OR is_correlated = '1'
        """)
        for row in cursor.fetchall():
            tx_id = str(row["transaction_id"])
            cdr_id = str(row["cdr_id"])
            
            # Find tx sender/receiver and cdr A/B numbers
            c_tx = self.conn.cursor()
            c_tx.execute("SELECT sender_account_number, receiver_account_number FROM bank_transactions WHERE transaction_id = ?", (tx_id,))
            tx_row = c_tx.fetchone()
            
            c_cdr = self.conn.cursor()
            c_cdr.execute("SELECT a_party_number, b_party_number FROM cdr_records WHERE cdr_id = ?", (cdr_id,))
            cdr_row = c_cdr.fetchone()
            
            if tx_row and cdr_row:
                acc = str(tx_row["receiver_account_number"]) or str(tx_row["sender_account_number"])
                phone = str(cdr_row["a_party_number"]) or str(cdr_row["b_party_number"])
                if acc in self.graph and phone in self.graph:
                    self.graph.add_edge(
                        acc, phone,
                        edge_type="correlated_event",
                        tx_id=tx_id,
                        cdr_id=cdr_id,
                        delta_sec=float(row["time_difference_seconds"]) if row["time_difference_seconds"] is not None else 0.0
                    )

        logger.info(f"Copilot Graph constructed with {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges.")

    def trace_mule_chain(self, start_entity_id: str, max_hops: int = 3) -> Dict[str, Any]:
        """Traces money transfers and communication networks up to max_hops (strictly 3 hops)."""
        start_node = str(start_entity_id).strip()
        
        # 1. Resolve Transaction ID -> Account Node
        if start_node not in self.graph:
            cursor = self.conn.cursor()
            cursor.execute("SELECT receiver_account_number, sender_account_number FROM bank_transactions WHERE transaction_id = ?", (start_node,))
            row_tx = cursor.fetchone()
            if row_tx:
                rec_acc = str(row_tx["receiver_account_number"]) if row_tx["receiver_account_number"] else None
                send_acc = str(row_tx["sender_account_number"]) if row_tx["sender_account_number"] else None
                start_node = rec_acc or send_acc or start_node

        # 2. Resolve CDR ID -> Phone Node
        if start_node not in self.graph:
            cursor = self.conn.cursor()
            cursor.execute("SELECT a_party_number, b_party_number FROM cdr_records WHERE cdr_id = ?", (start_node,))
            row_cdr = cursor.fetchone()
            if row_cdr:
                a_num = str(row_cdr["a_party_number"]) if row_cdr["a_party_number"] else None
                b_num = str(row_cdr["b_party_number"]) if row_cdr["b_party_number"] else None
                start_node = a_num or b_num or start_node

        # 3. Resolve IPDR ID -> MSISDN Node
        if start_node not in self.graph:
            cursor = self.conn.cursor()
            cursor.execute("SELECT subscriber_msisdn FROM ipdr_records WHERE ipdr_id = ?", (start_node,))
            row_ipdr = cursor.fetchone()
            if row_ipdr and row_ipdr["subscriber_msisdn"]:
                start_node = str(row_ipdr["subscriber_msisdn"])

        # 4. Partial string match fallback
        if start_node not in self.graph:
            matched_node = None
            for n in self.graph.nodes():
                if start_node in str(n):
                    matched_node = n
                    break
            if not matched_node:
                return {
                    "start_node": start_entity_id,
                    "found": False,
                    "max_hops": max_hops,
                    "nodes": [],
                    "edges": [],
                    "layers": {}
                }
            start_node = matched_node

        # BFS up to 3 hops max
        visited_nodes: Dict[str, int] = {start_node: 0}
        queue = [(start_node, 0)]
        collected_edges = []

        while queue:
            curr_node, depth = queue.pop(0)
            if depth >= max_hops:
                continue

            # Outgoing edges
            for successor in self.graph.successors(curr_node):
                if successor not in visited_nodes:
                    visited_nodes[successor] = depth + 1
                    queue.append((successor, depth + 1))
                
                # Get edge data
                edge_dict = self.graph.get_edge_data(curr_node, successor)
                for key, data in edge_dict.items():
                    collected_edges.append({
                        "source": curr_node,
                        "target": successor,
                        "hop_distance": depth + 1,
                        **data
                    })

            # Incoming edges for complete flow trace
            for predecessor in self.graph.predecessors(curr_node):
                if predecessor not in visited_nodes:
                    visited_nodes[predecessor] = depth + 1
                    queue.append((predecessor, depth + 1))

                edge_dict = self.graph.get_edge_data(predecessor, curr_node)
                for key, data in edge_dict.items():
                    collected_edges.append({
                        "source": predecessor,
                        "target": curr_node,
                        "hop_distance": depth + 1,
                        **data
                    })

        # Categorize node layers (Layer-1, Layer-2, Layer-3)
        layers: Dict[str, List[str]] = {
            "Layer-0 (Source)": [start_node],
            "Layer-1 Mules": [],
            "Layer-2 Mules": [],
            "Layer-3 Offramps": []
        }

        node_details = []
        for n, d in visited_nodes.items():
            attr = self.graph.nodes[n]
            node_details.append({
                "node_id": n,
                "type": attr.get("type", "unknown"),
                "name": attr.get("name", "Unknown Entity"),
                "phone": attr.get("phone", None),
                "hop_distance": d
            })
            if d == 1:
                layers["Layer-1 Mules"].append(n)
            elif d == 2:
                layers["Layer-2 Mules"].append(n)
            elif d == 3:
                layers["Layer-3 Offramps"].append(n)

        # Deduplicate edges
        seen_keys = set()
        unique_edges = []
        for e in collected_edges:
            key = (e["source"], e["target"], e.get("tx_id", e.get("cdr_id", e.get("timestamp"))))
            if key not in seen_keys:
                seen_keys.add(key)
                unique_edges.append(e)

        return {
            "start_node": start_node,
            "found": True,
            "max_hops": max_hops,
            "total_nodes": len(node_details),
            "total_edges": len(unique_edges),
            "nodes": node_details,
            "edges": unique_edges,
            "layers": layers
        }
