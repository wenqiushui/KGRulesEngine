# kce_core/execution/rule_evaluator.py

import logging
from typing import List, Tuple, Optional

from rdflib import URIRef

from kce_core.common.utils import (
    kce_logger,
    KCEError,
    KCE, RDF, RDFS, # Namespaces
)
from kce_core.rdf_store.store_manager import StoreManager
from kce_core.provenance.logger import ProvenanceLogger # For logging rule evaluation events
from kce_core.rdf_store import sparql_queries


class RuleEvaluator:
    """
    Evaluates kce:Rule instances defined in the RDF graph.
    If a rule's condition (SPARQL ASK query) is met, it identifies the action to be taken
    (e.g., a node to be triggered).
    """

    def __init__(self, store_manager: StoreManager, provenance_logger: Optional[ProvenanceLogger] = None):
        """
        Initializes the RuleEvaluator.

        Args:
            store_manager: An instance of StoreManager.
            provenance_logger: An optional instance of ProvenanceLogger for logging rule events.
        """
        self.store = store_manager
        self.prov_logger = provenance_logger
        kce_logger.info("RuleEvaluator initialized.")

    def evaluate_rules(self, current_run_id_uri: Optional[URIRef] = None) -> List[URIRef]:
        """
        Fetches all active rules, evaluates their conditions, and returns a list of
        node URIs that should be triggered based on the rules that fired.

        Args:
            current_run_id_uri: The URI of the current workflow execution log, for event logging.

        Returns:
            A list of kce:Node URIs to be potentially executed.
            The WorkflowExecutor will decide how to integrate these into the current execution flow.
        """
        triggered_action_node_uris: List[URIRef] = []
        
        rules_query = sparql_queries.format_query(sparql_queries.GET_ALL_ACTIVE_RULES)
        active_rules = self.store.query(rules_query)

        if not active_rules:
            kce_logger.debug("No active rules found to evaluate.")
            return []

        kce_logger.info(f"Evaluating {len(active_rules)} active rule(s)...")

        # Rules are already ordered by priority (DESC) and then URI by the SPARQL query.
        # This simple MVP evaluator doesn't handle complex conflict resolution beyond this ordering.
        for rule_data in active_rules:
            rule_uri = rule_data.get('rule_uri')
            condition_sparql = str(rule_data.get('condition_sparql'))
            action_node_uri = rule_data.get('action_node_uri')
            rule_label = self._get_rule_label(rule_uri) # For logging

            if not (rule_uri and condition_sparql and action_node_uri):
                kce_logger.warning(f"Rule {rule_uri or 'UnknownRule'} has incomplete definition (missing condition or action). Skipping.")
                continue

            kce_logger.debug(f"Evaluating rule: {rule_label} ({rule_uri})")
            kce_logger.debug(f"  Condition SPARQL (ASK): {condition_sparql}")

            try:
                condition_met = self.store.ask(condition_sparql)
            except Exception as e:
                kce_logger.error(f"Error executing condition SPARQL for rule {rule_label} ({rule_uri}): {e}")
                if self.prov_logger and current_run_id_uri:
                    self.prov_logger.log_generic_event(
                        run_id_uri=current_run_id_uri,
                        event_type=KCE.RuleEvaluationErrorEvent, # Define this event type
                        message=f"Error evaluating condition for rule '{rule_label}': {e}",
                        related_entity_uri=rule_uri,
                        severity="ERROR"
                    )
                continue # Skip to the next rule

            if condition_met:
                kce_logger.info(f"Rule FIRED: {rule_label} ({rule_uri}). Condition met.")
                if self.prov_logger and current_run_id_uri:
                    self.prov_logger.log_generic_event(
                        run_id_uri=current_run_id_uri,
                        event_type=KCE.RuleFiredEvent, # Define this event type
                        message=f"Rule '{rule_label}' fired. Action: Trigger node <{action_node_uri}>.",
                        related_entity_uri=rule_uri,
                        severity="INFO"
                    )
                
                # Add the action node URI to the list of nodes to be triggered
                # The WorkflowExecutor will handle potential duplicates or ordering.
                if action_node_uri not in triggered_action_node_uris: # Avoid duplicates in this list
                     triggered_action_node_uris.append(action_node_uri)
                
                # For MVP, we might assume a "fire once" or "fire and continue" semantic.
                # More complex rule chaining or "fire until no change" is post-MVP.

            else:
                kce_logger.debug(f"Rule condition NOT MET for: {rule_label} ({rule_uri})")
                if self.prov_logger and current_run_id_uri:
                     self.prov_logger.log_generic_event(
                        run_id_uri=current_run_id_uri,
                        event_type=KCE.RuleConditionNotMetEvent, # Define this event type
                        message=f"Condition not met for rule '{rule_label}'.",
                        related_entity_uri=rule_uri,
                        severity="DEBUG" # Or INFO, depending on desired log verbosity
                    )


        if triggered_action_node_uris:
            kce_logger.info(f"Rules evaluation resulted in triggering {len(triggered_action_node_uris)} action node(s): {triggered_action_node_uris}")
        else:
            kce_logger.info("No rules fired or no actions triggered from rule evaluation.")
            
        return triggered_action_node_uris

    def _get_rule_label(self, rule_uri: URIRef) -> str:
        """Fetches the rdfs:label of a rule, or returns its URI part if no label."""
        label_val = self.store.get_single_property_value(rule_uri, RDFS.label)
        return str(label_val) if label_val else rule_uri.split('/')[-1].split('#')[-1]


if __name__ == '__main__':
    # --- Example Usage and Basic Test ---
    kce_logger.setLevel(logging.DEBUG)

    # --- Mock StoreManager and ProvenanceLogger ---
    class MockStoreManager:
        def __init__(self):
            self.query_results_map = {}
            self.ask_results_map = {} # Map ASK query string to boolean result
            kce_logger.info("MockStoreManager for RuleEvaluator test initialized.")

        def query(self, sparql_query_str):
            kce_logger.debug(f"MockStore: Received query:\n{sparql_query_str}")
            for q_key, results in self.query_results_map.items():
                if q_key in sparql_query_str: # Simple substring match for test
                    kce_logger.debug(f"MockStore: Matched query key '{q_key}', returning {len(results)} results.")
                    return results
            kce_logger.warning(f"MockStore: No mock result for query: {sparql_query_str}")
            return []

        def ask(self, sparql_ask_query_str):
            kce_logger.debug(f"MockStore: Received ASK query:\n{sparql_ask_query_str}")
            for q_key, result in self.ask_results_map.items():
                if q_key in sparql_ask_query_str:
                    kce_logger.debug(f"MockStore: Matched ASK key '{q_key}', returning {result}.")
                    return result
            kce_logger.warning(f"MockStore: No mock ASK result for query: {sparql_ask_query_str}")
            return False # Default if not found

        def get_single_property_value(self, subject_uri, property_uri, default=None):
            # Simplified for test, assume labels are part of the rule data from query
            if property_uri == RDFS.label:
                if subject_uri == KCE.RuleWillFire: return Literal("Rule That Fires")
                if subject_uri == KCE.RuleWontFire: return Literal("Rule That Does Not Fire")
            return default

    class MockProvenanceLogger:
        def __init__(self):
            self.events_logged = []
            kce_logger.info("MockProvenanceLogger for RuleEvaluator test initialized.")
        def log_generic_event(self, run_id_uri, event_type, message, related_entity_uri=None, severity="INFO"):
            log_entry = {
                "run_id": run_id_uri, "event_type": event_type, "message": message,
                "related_entity": related_entity_uri, "severity": severity
            }
            self.events_logged.append(log_entry)
            kce_logger.debug(f"MockProv: Logged generic event: {log_entry}")

    # --- Setup Mocks and Evaluator ---
    mock_store = MockStoreManager()
    mock_prov = MockProvenanceLogger()
    rule_evaluator = RuleEvaluator(mock_store, mock_prov)

    test_run_uri = KCE["run/testevalrun"]

    # --- Mock Rule Definitions (as if returned by GET_ALL_ACTIVE_RULES query) ---
    rule1_uri = KCE.RuleWillFire
    rule1_cond = "ASK { ?s <ex:prop1> 'value1' . }" # Condition that will be true
    rule1_action = KCE.ActionNode1

    rule2_uri = KCE.RuleWontFire
    rule2_cond = "ASK { ?s <ex:prop2> 'value_false' . }" # Condition that will be false
    rule2_action = KCE.ActionNode2
    
    rule3_uri = KCE.RuleAlsoFires
    rule3_cond = "ASK { ?s <ex:prop3> true . }" # Condition that will be true
    rule3_action = KCE.ActionNode3
    rule3_priority = Literal(10) # Higher priority

    rule4_uri = KCE.RuleWithNoLabel
    rule4_cond = "ASK { ?s <ex:prop4> 123 . }"
    rule4_action = KCE.ActionNode4
    rule4_priority = Literal(5)


    mock_store.query_results_map[sparql_queries.GET_ALL_ACTIVE_RULES] = [
        {"rule_uri": rule3_uri, "condition_sparql": Literal(rule3_cond), "action_node_uri": rule3_action, "priority": rule3_priority},
        {"rule_uri": rule1_uri, "condition_sparql": Literal(rule1_cond), "action_node_uri": rule1_action, "priority": None}, # No priority, default order
        {"rule_uri": rule4_uri, "condition_sparql": Literal(rule4_cond), "action_node_uri": rule4_action, "priority": rule4_priority},
        {"rule_uri": rule2_uri, "condition_sparql": Literal(rule2_cond), "action_node_uri": rule2_action, "priority": None},
    ]

    # --- Mock ASK Query Results ---
    mock_store.ask_results_map[rule1_cond] = True
    mock_store.ask_results_map[rule2_cond] = False
    mock_store.ask_results_map[rule3_cond] = True
    mock_store.ask_results_map[rule4_cond] = True # This one also fires

    # --- Evaluate Rules ---
    kce_logger.info("\n--- Testing Rule Evaluation ---")
    triggered_nodes = rule_evaluator.evaluate_rules(current_run_id_uri=test_run_uri)

    kce_logger.info(f"Triggered action nodes: {triggered_nodes}")

    # --- Assertions ---
    assert len(triggered_nodes) == 3, f"Expected 3 triggered nodes, got {len(triggered_nodes)}"
    # Order depends on priority in query (DESC) then original list order if priorities are same/None
    # So, Rule3 (prio 10), then Rule4 (prio 5), then Rule1 (no prio)
    expected_triggered_order = [rule3_action, rule4_action, rule1_action]
    assert triggered_nodes == expected_triggered_order, f"Triggered nodes {triggered_nodes} not in expected order {expected_triggered_order}"


    assert rule1_action in triggered_nodes
    assert rule3_action in triggered_nodes
    assert rule4_action in triggered_nodes
    assert rule2_action not in triggered_nodes # This one should not fire

    # Check provenance logs
    assert len(mock_prov.events_logged) >= 4 # At least one "fired" or "not met" per rule
    
    fired_events = [e for e in mock_prov.events_logged if e["event_type"] == KCE.RuleFiredEvent]
    assert len(fired_events) == 3
    
    fired_rule_uris = {e["related_entity"] for e in fired_events}
    assert rule1_uri in fired_rule_uris
    assert rule3_uri in fired_rule_uris
    assert rule4_uri in fired_rule_uris


    not_met_events = [e for e in mock_prov.events_logged if e["event_type"] == KCE.RuleConditionNotMetEvent]
    if not_met_events: # Only if we log "not met" events with DEBUG/INFO
      assert len(not_met_events) == 1
      assert not_met_events[0]["related_entity"] == rule2_uri
    
    kce_logger.info("RuleEvaluator tests completed.")