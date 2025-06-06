import rdflib
from typing import List, Dict, Any, Optional, Union

# Assuming interfaces.py is two levels up
from ..interfaces import IRuleEngine, IKnowledgeLayer, IRuntimeStateLogger

# Define KCE namespace (ideally from a central place)
KCE = rdflib.Namespace("http://kce.com/ontology/core#")
RDF = rdflib.RDF
RDFS = rdflib.RDFS
XSD = rdflib.XSD # Corrected: XSD is a namespace, not rdflib.namespace.XSD

class RuleEngine(IRuleEngine):
    def __init__(self, runtime_state_logger: Optional[IRuntimeStateLogger] = None):
        self.logger = runtime_state_logger

    def _get_all_rules(self, knowledge_layer: IKnowledgeLayer) -> List[Dict[str, Any]]:
        '''Fetches all rule definitions from the KnowledgeLayer, ordered by priority.'''
        # Note: XSD.integer might need to be xsd:integer in the query string itself for SPARQL.
        # rdflib handles casting if ?priority_val is already an XSD.integer Literal.
        # If it's a plain literal, explicit casting in SPARQL is better.
        query = f"""
        PREFIX kce: <{KCE}>
        PREFIX rdfs: <{RDFS}>
        PREFIX xsd: <{XSD}>
        SELECT ?rule_uri ?antecedent ?consequent ?priority
        WHERE {{
            ?rule_uri a kce:Rule .
            ?rule_uri kce:hasAntecedent ?antecedent .
            ?rule_uri kce:hasConsequent ?consequent .
            OPTIONAL {{ ?rule_uri kce:hasPriority ?priority_val . }}
            BIND(COALESCE(xsd:integer(?priority_val), 0) AS ?priority)
        }}
        ORDER BY DESC(?priority)
        """
        # Using ?priority directly in ORDER BY DESC as it's already cast by BIND.

        results = knowledge_layer.execute_sparql_query(query)
        if isinstance(results, list):
            # Ensure priority is python int for easier sorting if SPARQL sort fails or is not fully trusted
            # However, the SPARQL ORDER BY should handle it.
            # For safety, one might re-sort here in Python if issues are seen with specific triple stores.
            return results
        return []

    def _check_antecedent(self, antecedent_query: str, knowledge_layer: IKnowledgeLayer) -> bool:
        '''Checks if a rule's antecedent (SPARQL query) is true.'''

        ask_query = antecedent_query.strip()
        # Convert SELECT to ASK if needed, or handle SELECT returning results.
        if ask_query.upper().startswith("SELECT"):
            try:
                result = knowledge_layer.execute_sparql_query(ask_query)
                return isinstance(result, list) and len(result) > 0
            except Exception as e:
                print(f"Error checking SELECT antecedent '{ask_query[:100]}...': {e}")
                return False
        elif not ask_query.upper().startswith("ASK"):
            # If it's just a WHERE clause, wrap it.
            # This might be too simplistic; complex WHERE clauses might not work directly.
            # Assume antecedent_query is either a full ASK or a full SELECT.
            # For just a WHERE clause, it should be written as "ASK { ... }" in the definition.
             print(f"Warning: Antecedent query '{ask_query[:100]}...' is not a full ASK or SELECT. Assuming it's a WHERE clause and wrapping in ASK.")
             ask_query = f"ASK {{ {antecedent_query} }}" # This might be risky if original query was not just a WHERE part

        try:
            result = knowledge_layer.execute_sparql_query(ask_query) # This must be an ASK query
            if isinstance(result, bool):
                return result
            # If KL returns something else for an ASK (e.g. a dict from some stores), handle it.
            # For rdflib, q_result.askAnswer should be a bool.
            print(f"Warning: Antecedent check for ASK query '{ask_query[:100]}...' returned unexpected type: {type(result)}. Expected bool.")
            return False # Or try to interpret, e.g. result.get('boolean', False) if it's a dict
        except Exception as e:
            print(f"Error checking ASK antecedent '{ask_query[:100]}...': {e}")
            return False

    def _execute_consequent(self, consequent_sparql: str, knowledge_layer: IKnowledgeLayer, rule_uri: str, run_id: Optional[str]):
        '''Executes a rule's consequent (SPARQL UPDATE or CONSTRUCT query).'''

        consequent_upper = consequent_sparql.strip().upper()
        try:
            if any(keyword in consequent_upper for keyword in ["INSERT", "DELETE", "WITH"]): # More robust check for UPDATEs
                knowledge_layer.execute_sparql_update(consequent_sparql)
                return True
            elif "CONSTRUCT" in consequent_upper: # Simpler check for CONSTRUCT
                result_graph = knowledge_layer.execute_sparql_query(consequent_sparql)
                if isinstance(result_graph, rdflib.Graph):
                    if len(result_graph) > 0:
                        knowledge_layer.add_graph(result_graph)
                    return True
                else:
                    err_msg = f"CONSTRUCT query for rule <{rule_uri}> did not return a graph. Got: {type(result_graph)}"
                    print(f"Error: {err_msg}")
                    if self.logger and run_id:
                         self.logger.log_event(run_id, "RuleEffectExecution", rule_uri, "Failed",
                                               {"consequent_query": consequent_sparql, "error": err_msg},
                                               None, err_msg, knowledge_layer)
                    return False
            else:
                # Default to attempting as an update if not clearly CONSTRUCT
                print(f"Warning: Rule <{rule_uri}> consequent type unclear. Attempting as UPDATE. Query: {consequent_sparql[:100]}...")
                knowledge_layer.execute_sparql_update(consequent_sparql)
                return True
        except Exception as e:
            error_message = f"Error executing consequent for rule <{rule_uri}>: {e}. Query: {consequent_sparql[:100]}..."
            print(error_message)
            if self.logger and run_id:
                 self.logger.log_event(run_id, "RuleEffectExecution", rule_uri, "Failed",
                                       {"consequent_query": consequent_sparql, "error": str(e)}, None, error_message, knowledge_layer)
            return False

    def apply_rules(self, knowledge_layer: IKnowledgeLayer, run_id: Optional[str] = None) -> bool:
        rules_applied_this_cycle = 0

        # In a more advanced engine, this loop might repeat until no more rules fire (fixed-point iteration)
        # For now, one pass through all rules.

        all_rules = self._get_all_rules(knowledge_layer)

        if not all_rules:
            if self.logger and run_id:
                self.logger.log_event(run_id, "RuleEngineCycle", "System", "Completed",
                                      {"message": "No rules found in knowledge base."}, {"rules_applied_count": 0}, None, knowledge_layer)
            return False

        for rule_def in all_rules:
            rule_uri = str(rule_def['rule_uri'])
            antecedent = str(rule_def['antecedent'])
            consequent = str(rule_def['consequent'])

            if self.logger and run_id:
                self.logger.log_event(run_id, "RuleEvaluationStart", rule_uri, "Started",
                                      {"antecedent_query": antecedent}, None, None, knowledge_layer)

            if self._check_antecedent(antecedent, knowledge_layer):
                if self.logger and run_id:
                    self.logger.log_event(run_id, "RuleAntecedentMet", rule_uri, "Succeeded",
                                          {"antecedent_query": antecedent}, None, "Antecedent is true.", knowledge_layer)

                if self._execute_consequent(consequent, knowledge_layer, rule_uri, run_id):
                    rules_applied_this_cycle += 1
                    if self.logger and run_id:
                        self.logger.log_event(run_id, "RuleConsequentApplied", rule_uri, "Succeeded",
                                              {"consequent_query": consequent}, {"knowledge_updated": True},
                                              f"Rule <{rule_uri}> consequent applied.", knowledge_layer)
                # else: Failure already logged by _execute_consequent
            else:
                if self.logger and run_id:
                    self.logger.log_event(run_id, "RuleAntecedentNotMet", rule_uri, "Completed",
                                          {"antecedent_query": antecedent}, None, "Antecedent is false.", knowledge_layer)

        if self.logger and run_id:
            self.logger.log_event(run_id, "RuleEngineCycleEnd", "System", "Completed",
                                  {"total_rules_evaluated": len(all_rules)},
                                  {"rules_applied_this_cycle": rules_applied_this_cycle},
                                  f"Rule engine cycle completed. {rules_applied_this_cycle} rules applied.", knowledge_layer)

        return rules_applied_this_cycle > 0

if __name__ == '__main__':
    EX = rdflib.Namespace("http://example.com/ns#")
    class MockKnowledgeLayer(IKnowledgeLayer):
        def __init__(self):
            self.graph = rdflib.Graph()
            self.rules_data: List[Dict[str, Any]] = []
            self.updates_executed: List[str] = []
            self.graph.add((EX.Entity1, KCE.someCondition, rdflib.Literal(True)))
            self.graph.add((EX.Entity2, KCE.someCondition, rdflib.Literal(False)))

        def add_rule_def(self, uri: str, antecedent: str, consequent: str, priority: int = 0):
            self.rules_data.append({
                'rule_uri': rdflib.URIRef(uri),
                'antecedent': rdflib.Literal(antecedent),
                'consequent': rdflib.Literal(consequent),
                'priority': rdflib.Literal(priority, datatype=XSD.integer) # Ensure it's an XSD.integer Literal
            })

        def execute_sparql_query(self, query: str) -> Union[List[Dict[str, Any]], bool, rdflib.Graph]:
            query_upper = query.strip().upper()
            if "SELECT ?RULE_URI" in query_upper and "KCE:RULE" in query_upper :
                # Simulate rdflib's result format for SELECT queries
                # The query asks for ?rule_uri, ?antecedent, ?consequent, ?priority
                # The BIND in the query ensures ?priority is always present.

                # Simulate SPARQL ORDER BY
                def get_priority_from_literal(r_dict):
                    try:
                        return int(r_dict['priority']) # rdflib.Literal.toPython() or plain int if already converted
                    except (ValueError, TypeError):
                        return 0 # Default if conversion fails

                sorted_rules = sorted(self.rules_data, key=get_priority_from_literal, reverse=True)

                # Convert to list of dicts of rdflib terms as SPARQL results would be
                results = []
                for r in sorted_rules:
                    results.append({
                        'rule_uri': r['rule_uri'], # URIRef
                        'antecedent': r['antecedent'], # Literal
                        'consequent': r['consequent'], # Literal
                        'priority': r['priority'] # Literal (xsd:integer)
                    })
                return results

            if query_upper.startswith("ASK"):
                # Simplified mock ASK evaluation based on content
                if "EX:ENTITY1 KCE:SOMECONDITION TRUE" in query_upper: return True
                if "EX:ENTITYNONEXISTENT KCE:SOMECONDITION TRUE" in query_upper: return False
                if "EX:ENTITYFORHIGHPRIORITY KCE:SOMECONDITION TRUE" in query_upper: return True
                return False

            if query_upper.startswith("CONSTRUCT"):
                g_construct = rdflib.Graph()
                if "EX:CONSTRUCTRULE" in query_upper:
                    g_construct.add((EX.ConstructedData, RDF.type, KCE.DerivedByConstruct))
                return g_construct
            return []

        def execute_sparql_update(self, update_statement: str) -> None:
            self.updates_executed.append(update_statement)
            # Simulate effects of updates on the graph for testing assertions
            if "INSERT DATA" in update_statement and "Rule1Effect" in update_statement:
                self.graph.add((EX.Rule1Effect, RDF.type, KCE.RuleGeneratedData))
            if "INSERT DATA" in update_statement and "HighPriorityRuleEffect" in update_statement:
                self.graph.add((EX.HighPriorityRuleEffect, RDF.type, KCE.RuleGeneratedData))

        def trigger_reasoning(self): pass
        def add_graph(self, g: RDFGraph, context_uri: Optional[str] = None): self.graph += g
        def get_graph(self, context_uri: Optional[str] = None): return self.graph
        def store_human_readable_log(self, run_id: str, event_id: str, log_content: str) -> str: return f"logs/{run_id}/{event_id}.log"
        def get_human_readable_log(self, log_location: str) -> Optional[str]: return "log content"

    class MockRuntimeStateLogger(IRuntimeStateLogger):
        def log_event(self, run_id: str, event_type: str, operation_uri: Optional[str], status: str, inputs: Any, outputs: Any, message: Optional[str] = None, knowledge_layer: Optional[IKnowledgeLayer] = None):
            print(f"Logger: Event='{event_type}', Op='{str(operation_uri)}', Status='{status}', Run='{run_id}'")

    mock_kl_instance = MockKnowledgeLayer()
    mock_logger_instance = MockRuntimeStateLogger()
    rule_engine = RuleEngine(runtime_state_logger=mock_logger_instance)

    mock_kl_instance.add_rule_def("ex:Rule1", "ASK { ex:Entity1 kce:someCondition true . }", "INSERT DATA { ex:Rule1Effect rdf:type kce:RuleGeneratedData . }", 1)
    mock_kl_instance.add_rule_def("ex:Rule2_NoMet", "ASK { ex:EntityNonExistent kce:someCondition true . }", "INSERT DATA { ex:Rule2Effect rdf:type kce:RuleGeneratedData . }", 0)
    mock_kl_instance.add_rule_def("ex:Rule_HighPriority", "ASK { ex:EntityForHighPriority kce:someCondition true . }", "INSERT DATA { ex:HighPriorityRuleEffect rdf:type kce:RuleGeneratedData . }", 10)
    mock_kl_instance.add_rule_def("ex:ConstructRuleDef", "ASK { ex:Entity1 kce:someCondition true . }", "CONSTRUCT { ex:ConstructedData rdf:type kce:DerivedByConstruct . } WHERE { ex:Entity1 kce:someCondition true . }", 5)

    print("--- Test RuleEngine: apply_rules ---")
    mock_kl_instance.graph.add((EX.EntityForHighPriority, KCE.someCondition, rdflib.Literal(True)))

    initial_graph_len = len(mock_kl_instance.graph)
    initial_updates_count = len(mock_kl_instance.updates_executed)

    applied_any_result = rule_engine.apply_rules(mock_kl_instance, "test_rule_run_001")

    print(f"Rule engine applied rules: {applied_any_result}")
    assert applied_any_result == True
    assert (EX.Rule1Effect, RDF.type, KCE.RuleGeneratedData) in mock_kl_instance.graph
    assert (EX.HighPriorityRuleEffect, RDF.type, KCE.RuleGeneratedData) in mock_kl_instance.graph
    assert (EX.ConstructedData, RDF.type, KCE.DerivedByConstruct) in mock_kl_instance.graph
    assert len(mock_kl_instance.updates_executed) == initial_updates_count + 2
    assert len(mock_kl_instance.graph) == initial_graph_len + 3

    print("\n--- Test RuleEngine: no rules apply (condition not met in graph) ---")
    mock_kl_no_match_instance = MockKnowledgeLayer()
    # Rule expects ex:Entity1 kce:someCondition true, but Entity1 is false in this new KL instance by default (or not set)
    mock_kl_no_match_instance.graph.remove((EX.Entity1, KCE.someCondition, rdflib.Literal(True))) # Ensure it's not true
    mock_kl_no_match_instance.add_rule_def("ex:RuleWillNotApply", "ASK { ex:Entity1 kce:someCondition true . }", "INSERT DATA { ex:RuleWillNotApplyEffect rdf:type kce:RuleGeneratedData . }")
    applied_any_no_match_result = rule_engine.apply_rules(mock_kl_no_match_instance, "test_rule_run_002")
    assert applied_any_no_match_result == False

    print("RuleEngine test complete.")
