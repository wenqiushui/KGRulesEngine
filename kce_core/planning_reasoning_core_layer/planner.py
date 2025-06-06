from typing import List, Dict, Any, Optional, Set, Tuple, Union
import rdflib

# Assuming interfaces.py is two levels up
from ..interfaces import (
    IPlanner, IKnowledgeLayer, IPlanExecutor, IRuleEngine, IRuntimeStateLogger,
    ExecutionPlan, ExecutionResult, TargetDescription, RDFGraph
)
# Assuming utils are one level up then in common
# from ..common.utils import generate_instance_uri # Not directly used in this version of planner

# Define KCE namespace (ideally from a central place)
KCE = rdflib.Namespace("http://kce.com/ontology/core#")
RDF = rdflib.RDF
RDFS = rdflib.RDFS
EX = rdflib.Namespace("http://example.com/ns#") # For test/example URIs

# Goal can be any structure, but for this planner, it's part of TargetDescription
MAX_PLANNING_DEPTH = 10 # Max iterations for planning loop

class Planner(IPlanner):
    def __init__(self,
                 runtime_state_logger: Optional[IRuntimeStateLogger] = None):
        self.logger = runtime_state_logger

    def _log_event(self, run_id: str, event_type: str, operation_uri: Optional[str], status: str,
                   inputs: Any, outputs: Any, message: Optional[str] = None, kl: Optional[IKnowledgeLayer] = None):
        if self.logger and kl:
            self.logger.log_event(run_id, event_type, operation_uri, status, inputs, outputs, message, kl)
        else:
            # Basic print log if no proper logger/kl is available (e.g. during early tests)
            log_msg_parts = [
                f"PLANNER_LOG (run:{run_id}",
                f"type:{event_type}",
                f"op:{operation_uri if operation_uri else 'System'}", # Changed N/A to System for clarity
                f"status:{status})"
            ]
            if message: log_msg_parts.append(f": {message}")
            print(" ".join(log_msg_parts))

    def _check_goal_achieved(self, target_description: TargetDescription, knowledge_layer: IKnowledgeLayer, run_id: str) -> bool:
        # Assumes target_description contains a SPARQL ASK query to check if goal is met
        ask_query = target_description.get("sparql_ask_query")
        if not ask_query:
            self._log_event(run_id, "GoalCheck", None, "Failed", {"reason": "No sparql_ask_query in target_description"}, None, "Goal condition undefined.", knowledge_layer)
            return False

        try:
            result = knowledge_layer.execute_sparql_query(ask_query)
            if isinstance(result, bool):
                return result
            else:
                self._log_event(run_id, "GoalCheck", None, "Failed", {"query": ask_query, "result_type": str(type(result))}, None, "Goal check query returned non-boolean.", knowledge_layer)
                return False
        except Exception as e:
            self._log_event(run_id, "GoalCheck", None, "Failed", {"query": ask_query, "error": str(e)}, None, f"Error checking goal: {e}", knowledge_layer)
            return False

    def _find_relevant_nodes(self, current_goal_or_subgoal: TargetDescription, knowledge_layer: IKnowledgeLayer, run_id: str) -> List[rdflib.URIRef]:
        # MVP: Returns all AtomicNodes.
        # Future: Filter by effects declared to be relevant to achieving the current_goal_or_subgoal.
        # For now, current_goal_or_subgoal is not used to filter nodes.
        query = f"""PREFIX kce: <{KCE}> SELECT ?node_uri WHERE {{ ?node_uri a kce:AtomicNode . }}"""
        try:
            results = knowledge_layer.execute_sparql_query(query)
            node_uris = []
            if isinstance(results, list):
                for row in results:
                    if 'node_uri' in row and isinstance(row['node_uri'], rdflib.URIRef):
                         node_uris.append(row['node_uri'])
            return node_uris
        except Exception as e:
            self._log_event(run_id, "FindRelevantNodes", None, "Failed", {"query": query, "error": str(e)}, None, f"Error finding relevant nodes: {e}", knowledge_layer)
            return []

    def _check_node_preconditions(self, node_uri: rdflib.URIRef, knowledge_layer: IKnowledgeLayer, run_id: str) -> Tuple[bool, Optional[str]]:
        # Fetches and checks the kce:hasPrecondition for the node.
        precond_query_sparql = f"""PREFIX kce: <{KCE}> SELECT ?precondition_query WHERE {{ <{node_uri}> kce:hasPrecondition ?precondition_query . }} LIMIT 1"""
        try:
            results = knowledge_layer.execute_sparql_query(precond_query_sparql)
            precondition_query_str: Optional[str] = None
            if isinstance(results, list) and results and 'precondition_query' in results[0] and results[0]['precondition_query'] is not None:
                precondition_query_str = str(results[0]['precondition_query']) # Convert Literal to string

                final_ask_query = precondition_query_str.strip()
                if not final_ask_query.upper().startswith("ASK"): # Ensure it's an ASK query
                    final_ask_query = f"ASK {{ {final_ask_query} }}"

                is_met = knowledge_layer.execute_sparql_query(final_ask_query)
                if isinstance(is_met, bool): return is_met, (None if is_met else final_ask_query)
                else:
                    self._log_event(run_id, "PreconditionCheck", str(node_uri), "Failed", {"query": final_ask_query, "result_type": str(type(is_met))}, None, "Precondition query returned non-boolean.", knowledge_layer)
                    return False, final_ask_query
            else: # No precondition defined for the node
                return True, None
        except Exception as e:
            self._log_event(run_id, "PreconditionCheck", str(node_uri), "Failed", {"query_fetch_error": str(e)}, None, f"Error fetching/checking precondition for <{node_uri}>: {e}", knowledge_layer)
            return False, precond_query_sparql # Return the query used to fetch the precondition itself

    def solve(self,
              target_description: TargetDescription,
              initial_state_graph: RDFGraph,
              knowledge_layer: IKnowledgeLayer,
              plan_executor: IPlanExecutor,
              rule_engine: IRuleEngine,
              run_id: str,
              mode: str) -> ExecutionResult:

        self._log_event(run_id, "PlanningProcessStart", None, "Started",
                        {"target_desc_type": str(type(target_description)), "mode": mode, "initial_state_size": len(initial_state_graph)},
                        None, "Planner starting problem resolution.", knowledge_layer)

        if initial_state_graph and len(initial_state_graph) > 0:
            knowledge_layer.add_graph(initial_state_graph, context_uri=rdflib.URIRef(f"urn:kce:run:{run_id}:initial_problem_state"))
            self._log_event(run_id, "InitialStateLoad", None, "Succeeded", {"graph_size": len(initial_state_graph)}, None, "Initial state loaded into KL.", knowledge_layer)

        self._log_event(run_id, "InitialReasoningTrigger", None, "Triggered", None, None, "Triggering initial reasoning.", knowledge_layer)
        knowledge_layer.trigger_reasoning()
        self._log_event(run_id, "InitialReasoning", None, "Completed", None, None, "Initial reasoning complete.", knowledge_layer)

        self._log_event(run_id, "InitialRuleApplicationTrigger", None, "Triggered", None, None, "Triggering initial rule application.", knowledge_layer)
        if rule_engine.apply_rules(knowledge_layer, run_id): # apply_rules logs its own events
            self._log_event(run_id, "InitialRuleApplication", None, "Completed", None, {"rules_applied_in_cycle": True}, "Initial rules applied cycle resulted in changes.", knowledge_layer)
            self._log_event(run_id, "PostInitialRuleReasoningTrigger", None, "Triggered", None, None, "Triggering reasoning post-initial rules.", knowledge_layer)
            knowledge_layer.trigger_reasoning()
            self._log_event(run_id, "PostInitialRuleReasoning", None, "Completed", None, None, "Reasoning completed post-initial rules.", knowledge_layer)
        else:
            self._log_event(run_id, "InitialRuleApplication", None, "Completed", None, {"rules_applied_in_cycle": False}, "Initial rules applied cycle resulted in no changes.", knowledge_layer)


        current_plan_steps: ExecutionPlan = [] # Stores the sequence of executed steps
        for depth in range(MAX_PLANNING_DEPTH):
            self._log_event(run_id, "PlanningIteration", None, "Started", {"depth": depth + 1, "current_plan_length": len(current_plan_steps)}, None, f"Planning iteration {depth + 1}.", knowledge_layer)

            if self._check_goal_achieved(target_description, knowledge_layer, run_id):
                self._log_event(run_id, "GoalAchieved", None, "Succeeded", {"plan_length": len(current_plan_steps)}, {"plan": current_plan_steps}, "Goal achieved.", knowledge_layer)
                return {"status": "success", "message": "Goal achieved.", "run_id": run_id, "plan_executed": current_plan_steps}

            candidate_nodes = self._find_relevant_nodes(target_description, knowledge_layer, run_id)
            if not candidate_nodes:
                self._log_event(run_id, "NodeSelection", None, "Failed", {"reason": "No candidate nodes found"}, None, "No candidate nodes found by planner.", knowledge_layer)
                return {"status": "failure", "message": "Planner stuck: No candidate nodes found.", "run_id": run_id, "plan_executed": current_plan_steps}

            executable_node_uri_str: Optional[str] = None
            unmet_preconditions: Dict[str, Optional[str]] = {} # Store unmet preconditions for logging

            for node_uri_cand in candidate_nodes:
                is_met, precond_query_if_failed = self._check_node_preconditions(node_uri_cand, knowledge_layer, run_id)
                if is_met:
                    executable_node_uri_str = str(node_uri_cand)
                    break
                else:
                    unmet_preconditions[str(node_uri_cand)] = precond_query_if_failed

            if executable_node_uri_str:
                self._log_event(run_id, "NodeSelectedForExecution", executable_node_uri_str, "Selected", None, None, f"Node <{executable_node_uri_str}> selected for execution.", knowledge_layer)

                # Execute this single node
                single_step_plan: ExecutionPlan = [{"operation_type": "node", "operation_uri": executable_node_uri_str}]
                # The PlanExecutor will log the details of this single step execution
                execution_result = plan_executor.execute_plan(single_step_plan, run_id, knowledge_layer, initial_graph=None)

                current_plan_steps.extend(single_step_plan) # Add to the overall plan being built

                if execution_result["status"] == "failure":
                    self._log_event(run_id, "NodeExecutionInPlanningFailed", executable_node_uri_str, "Failed",
                                    {"node_execution_result": execution_result}, None,
                                    f"Execution of node <{executable_node_uri_str}> failed during planning.", knowledge_layer)
                    return execution_result # Propagate failure

                self._log_event(run_id, "NodeExecutionInPlanningOK", executable_node_uri_str, "Succeeded",
                                {"node_execution_result": execution_result}, None,
                                f"Node <{executable_node_uri_str}> executed successfully in planning.", knowledge_layer)

                # Post-node execution: trigger reasoning and rule application
                self._log_event(run_id, "PostNodeReasoningTrigger", executable_node_uri_str, "Triggered", None, None, f"Triggering reasoning post-node <{executable_node_uri_str}>.", knowledge_layer)
                knowledge_layer.trigger_reasoning()
                self._log_event(run_id, "PostNodeReasoning", executable_node_uri_str, "Completed", None, None, f"Reasoning completed post-node <{executable_node_uri_str}>.", knowledge_layer)

                self._log_event(run_id, "PostNodeRuleApplicationTrigger", executable_node_uri_str, "Triggered", None, None, f"Triggering rules post-node <{executable_node_uri_str}>.", knowledge_layer)
                if rule_engine.apply_rules(knowledge_layer, run_id):
                    self._log_event(run_id, "PostNodeRuleApplication", executable_node_uri_str, "Completed", None, {"rules_applied_in_cycle": True}, f"Rules applied post-node <{executable_node_uri_str}>.", knowledge_layer)
                    self._log_event(run_id, "PostNodeRuleReasoningTrigger", executable_node_uri_str, "Triggered", None, None, f"Triggering reasoning post-rules (post-node <{executable_node_uri_str}>).", knowledge_layer)
                    knowledge_layer.trigger_reasoning()
                    self._log_event(run_id, "PostNodeRuleReasoning", executable_node_uri_str, "Completed", None, None, f"Reasoning completed post-rules (post-node <{executable_node_uri_str}>).", knowledge_layer)
                else:
                    self._log_event(run_id, "PostNodeRuleApplication", executable_node_uri_str, "Completed", None, {"rules_applied_in_cycle": False}, f"No rules applied post-node <{executable_node_uri_str}>.", knowledge_layer)

            else: # No executable node found in this iteration
                self._log_event(run_id, "NoExecutableNodeFound", None, "Failed",
                                {"candidate_nodes_count": len(candidate_nodes), "unmet_preconditions_sample": dict(list(unmet_preconditions.items())[:3])}, # Log a sample of unmet
                                None, "Planner stuck: no executable node found whose preconditions are met.", knowledge_layer)
                return {"status": "failure", "message": "Planner stuck: No executable node found.", "run_id": run_id, "plan_executed": current_plan_steps}

        # If loop finishes, max depth was reached without achieving goal
        self._log_event(run_id, "MaxPlanningDepthReached", None, "Failed", {"depth": MAX_PLANNING_DEPTH, "plan_length": len(current_plan_steps)}, None, "Maximum planning depth reached. Aborting.", knowledge_layer)
        return {"status": "failure", "message": "Maximum planning depth reached.", "run_id": run_id, "plan_executed": current_plan_steps}

if __name__ == '__main__':
    # Mocks for interfaces
    class MockKnowledgeLayer(IKnowledgeLayer):
        def __init__(self):
            self.graph = rdflib.Graph()
            # Add a sample node definition
            self.graph.add((EX.Node1, RDF.type, KCE.AtomicNode))
            self.graph.add((EX.Node1, KCE.hasPrecondition, rdflib.Literal("ASK { ex:PreCondData kce:isSet true . }")))
            # Add initial state for precondition data
            self.graph.add((EX.PreCondData, KCE.isSet, rdflib.Literal(False))) # Initially false
        def execute_sparql_query(self, query: str) -> Union[List[Dict[str, Any]], bool, RDFGraph]:
            # print(f"MockKL Query: {query}")
            if "SELECT ?node_uri WHERE { ?node_uri a kce:AtomicNode . }" in query: return [{'node_uri': EX.Node1}]
            if "SELECT ?precondition_query WHERE { <" + str(EX.Node1) + "> kce:hasPrecondition ?precondition_query . }" in query:
                return [{'precondition_query': rdflib.Literal("ASK { ex:PreCondData kce:isSet true . }")}]
            if query.strip() == "ASK { ex:PreCondData kce:isSet true . }":
                return (None, KCE.isSet, rdflib.Literal(True)) in self.graph # Check current state
            if query.strip() == "ASK { ex:GoalData kce:isAchieved true . }":
                return (None, KCE.isAchieved, rdflib.Literal(True)) in self.graph
            return False # Default for other ASK queries
        def execute_sparql_update(self, update_statement: str): pass # Not used by this planner directly
        def trigger_reasoning(self): print("MockKL: Triggering reasoning.")
        def add_graph(self, g: RDFGraph, context_uri: Optional[rdflib.URIRef] = None): self.graph += g; print(f"MockKL: Added {len(g)} triples. Total: {len(self.graph)}")
        def get_graph(self, context_uri: Optional[rdflib.URIRef] = None) -> RDFGraph: return self.graph
        def store_human_readable_log(self, run_id: str, event_id: str, log_content: str) -> str: return f"logs/{run_id}/{event_id}.log"
        def get_human_readable_log(self, log_location: str) -> Optional[str]: return "log content"

    class MockPlanExecutor(IPlanExecutor):
        def execute_plan(self, plan: ExecutionPlan, run_id: str, knowledge_layer: IKnowledgeLayer, initial_graph: Optional[RDFGraph] = None) -> ExecutionResult:
            print(f"MockPlanExecutor: Executing plan with {len(plan)} step(s) for run {run_id}.")
            for step in plan: # This test planner only plans one step at a time for PlanExecutor
                if step["operation_uri"] == str(EX.Node1):
                    # Simulate Node1's effect: makes GoalData achieved
                    effect_graph = rdflib.Graph()
                    effect_graph.add((EX.GoalData, KCE.isAchieved, rdflib.Literal(True)))
                    knowledge_layer.add_graph(effect_graph)
                    print(f"MockPlanExecutor: Simulated effect of Node1. GoalData isAchieved set to True.")
            return {"status": "success", "message": "Mock plan executed by PlanExecutor", "run_id": run_id}

    class MockRuleEngine(IRuleEngine):
        def apply_rules(self, knowledge_layer: IKnowledgeLayer, run_id: Optional[str] = None) -> bool:
            print("MockRuleEngine: Applying rules.")
            return False # Simulate no rules applied for simplicity in this test

    class MockRuntimeStateLogger(IRuntimeStateLogger):
        def log_event(self, run_id: str, event_type: str, operation_uri: Optional[str], status: str, inputs: Any, outputs: Any, message: Optional[str]=None, knowledge_layer: Optional[IKnowledgeLayer]=None):
            print(f"Logger: Event='{event_type}', Op='{operation_uri}', Status='{status}', Run='{run_id}' {message if message else ''}")

    # Test setup
    mock_kl_instance = MockKnowledgeLayer()
    mock_pe_instance = MockPlanExecutor()
    mock_re_instance = MockRuleEngine()
    mock_rsl_instance = MockRuntimeStateLogger()

    planner = Planner(runtime_state_logger=mock_rsl_instance)

    target_desc: TargetDescription = {"sparql_ask_query": "ASK { ex:GoalData kce:isAchieved true . }"}
    initial_state_g = rdflib.Graph() # Empty for this test, initial state is in MockKL directly

    print("\n--- Test Planner Scenario 1: Precondition Initially False (Expect Failure) ---")
    # Ensure Goal is not met initially
    mock_kl_instance.graph.remove((EX.GoalData, KCE.isAchieved, rdflib.Literal(True)))
    # Ensure Precondition is False
    mock_kl_instance.graph.remove((EX.PreCondData, KCE.isSet, rdflib.Literal(True)))
    mock_kl_instance.graph.add((EX.PreCondData, KCE.isSet, rdflib.Literal(False)))

    result1 = planner.solve(target_desc, initial_state_g, mock_kl_instance, mock_pe_instance, mock_re_instance, "run_planner_test1", "auto")
    print(f"Planner Result 1: Status='{result1['status']}', Message='{result1.get('message', 'N/A')}'")
    assert result1['status'] == 'failure' # Fails because no node is executable (precondition of Node1 is False)
    assert not ((EX.GoalData, KCE.isAchieved, rdflib.Literal(True)) in mock_kl_instance.graph) # Goal should not be achieved

    print("\n--- Test Planner Scenario 2: Precondition Becomes True (Expect Success) ---")
    # Ensure Goal is not met initially
    mock_kl_instance.graph.remove((EX.GoalData, KCE.isAchieved, rdflib.Literal(True)))
    # Set Precondition to True
    mock_kl_instance.graph.remove((EX.PreCondData, KCE.isSet, rdflib.Literal(False)))
    mock_kl_instance.graph.add((EX.PreCondData, KCE.isSet, rdflib.Literal(True)))

    result2 = planner.solve(target_desc, initial_state_g, mock_kl_instance, mock_pe_instance, mock_re_instance, "run_planner_test2", "auto")
    print(f"Planner Result 2: Status='{result2['status']}', Message='{result2.get('message', 'N/A')}'")
    assert result2['status'] == 'success'
    assert (EX.GoalData, KCE.isAchieved, rdflib.Literal(True)) in mock_kl_instance.graph # Goal should be achieved

    print("Planner tests complete.")
