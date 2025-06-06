# kce_core/execution/workflow_executor.py

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Deque
from collections import deque

from rdflib import URIRef, Literal # Removed RDFNode as it should come from rdflib.term
from rdflib.term import Node as RDFNode # Correct import for RDFNode

from kce_core.common.utils import (
    kce_logger,
    ExecutionError,
    DefinitionError,
    KCE, RDF, RDFS, EX,
    load_json_string,
    to_uriref,
    to_literal
)
from kce_core.rdf_store.store_manager import StoreManager
from kce_core.provenance.logger import ProvenanceLogger
from kce_core.rdf_store import sparql_queries
from .node_executor import NodeExecutor
from .rule_evaluator import RuleEvaluator


class WorkflowExecutor:
    """
    Orchestrates the execution of kce:Workflow instances.
    Manages workflow steps, node execution, rule evaluation, and composite node expansion.
    """

    def __init__(self, store_manager: StoreManager,
                 node_executor: NodeExecutor,
                 rule_evaluator: RuleEvaluator,
                 provenance_logger: ProvenanceLogger):
        """
        Initializes the WorkflowExecutor.
        """
        self.store = store_manager
        self.node_executor = node_executor
        self.rule_evaluator = rule_evaluator
        self.prov_logger = provenance_logger
        kce_logger.info("WorkflowExecutor initialized.")

    def execute_workflow(self, workflow_uri: URIRef,
                         initial_parameters_json: Optional[str] = None,
                         instance_context_uri_override: Optional[URIRef] = None,
                         parent_run_id_uri: Optional[URIRef] = None,
                         parent_node_exec_uri: Optional[URIRef] = None
                         ) -> bool:
        """
        Executes a given kce:Workflow.
        """
        workflow_label = self._get_workflow_label(workflow_uri)
        
        initial_params_dict: Dict[str, Any] = {} # Ensure it's always defined
        if not parent_run_id_uri: # Top-level workflow execution
            if initial_parameters_json:
                try:
                    initial_params_dict = load_json_string(initial_parameters_json)
                except DefinitionError as e:
                    kce_logger.error(f"Invalid initial parameters JSON for workflow {workflow_uri}: {e}")
                    return False # Cannot start if params are bad for a top-level run
            current_run_id_uri = self.prov_logger.start_workflow_execution(workflow_uri, initial_params_dict)
            kce_logger.info(f"Starting top-level workflow execution: {workflow_label} ({workflow_uri}), Run ID: {current_run_id_uri}")
        else: # This is a sub-workflow execution (composite node)
            current_run_id_uri = parent_run_id_uri
            kce_logger.info(f"Executing sub-workflow: {workflow_label} ({workflow_uri}) "
                            f"as part of run {current_run_id_uri}")

        current_instance_context_uri: URIRef
        if instance_context_uri_override:
            current_instance_context_uri = instance_context_uri_override
            kce_logger.debug(f"Using provided instance context URI: {current_instance_context_uri}")
        elif not parent_run_id_uri: 
            # Generate a unique part for the context URI using the run_id_uri's unique part
            run_uuid_part = str(current_run_id_uri).split('/')[-1] # Assuming run_id_uri ends with UUID
            context_local_name = f"instance_data/{run_uuid_part}"
            current_instance_context_uri = KCE[context_local_name] # Use KCE namespace for this context
            kce_logger.debug(f"Created new instance context URI for top-level run: {current_instance_context_uri}")
            # Load initial parameters into this new context
            if initial_params_dict: # Check if there are params to load
                self._load_initial_parameters_to_context(current_instance_context_uri, initial_params_dict)
        else:
            current_instance_context_uri = parent_node_exec_uri or current_run_id_uri 
            kce_logger.warning(f"Sub-workflow {workflow_uri} using fallback instance context: {current_instance_context_uri}. "
                               "Ideally, composite nodes should provide specific context mapping.")

        execution_queue: Deque[URIRef] = deque()
        executed_nodes: Set[URIRef] = set()
        workflow_successful = True

        try:
            initial_steps = self._get_workflow_steps(workflow_uri)
            if not initial_steps:
                # Log an event or raise a less severe error if an empty workflow is permissible.
                # For MVP, let's assume a workflow must have steps to be meaningful.
                kce_logger.warning(f"Workflow <{workflow_uri}> has no defined steps. Completing as successful (no-op).")
                # If an empty workflow is an error state, change to False and log error
                # workflow_successful = False 
                # raise DefinitionError(f"Workflow {workflow_uri} has no defined steps.")
            else:
                for step_node_uri in initial_steps:
                    if step_node_uri not in execution_queue and step_node_uri not in executed_nodes:
                        execution_queue.append(step_node_uri)
                kce_logger.debug(f"Initial execution queue for <{workflow_uri}>: {list(execution_queue)}")

            while execution_queue:
                node_to_execute_uri = execution_queue.popleft()
                
                if node_to_execute_uri in executed_nodes:
                    kce_logger.debug(f"Skipping already executed node: <{node_to_execute_uri}>")
                    continue

                kce_logger.info(f"Processing node from queue: <{node_to_execute_uri}> for workflow <{workflow_uri}>")
                
                node_type = self._get_node_type(node_to_execute_uri)

                node_success = False # Initialize
                if node_type == KCE.AtomicNode:
                    node_success = self.node_executor.execute_node(
                        node_to_execute_uri,
                        current_run_id_uri,
                        current_instance_context_uri
                    )
                elif node_type == KCE.CompositeNode:
                    node_success = self._execute_composite_node(
                        node_to_execute_uri,
                        current_run_id_uri,
                        current_instance_context_uri
                    )
                else:
                    kce_logger.error(f"Unknown or undefined node type for node <{node_to_execute_uri}>. Node type found: {node_type}. Skipping.")
                    # workflow_successful = False # Mark workflow as failed if a step is unexecutable
                    # break # And stop processing

                executed_nodes.add(node_to_execute_uri)

                if not node_success:
                    workflow_successful = False
                    kce_logger.error(f"Node <{node_to_execute_uri}> failed. Workflow <{workflow_uri}> will be marked as failed.")
                    break 

                if workflow_successful:
                    kce_logger.debug(f"Evaluating rules after execution of node <{node_to_execute_uri}>...")
                    triggered_by_rules = self.rule_evaluator.evaluate_rules(current_run_id_uri)
                    for triggered_node_uri in triggered_by_rules:
                        if triggered_node_uri not in execution_queue and triggered_node_uri not in executed_nodes:
                            execution_queue.append(triggered_node_uri)
                            kce_logger.info(f"Rule triggered node <{triggered_node_uri}>, added to execution queue.")
                        else:
                             kce_logger.debug(f"Rule triggered node <{triggered_node_uri}> is already in queue or executed.")
            
            if not workflow_successful and execution_queue:
                kce_logger.warning(f"Workflow <{workflow_uri}> failed, remaining {len(execution_queue)} nodes in queue will not be processed.")

        except DefinitionError as e:
            kce_logger.error(f"Definition error during execution of workflow <{workflow_uri}> (Run ID: <{current_run_id_uri}>): {e}")
            workflow_successful = False
        except ExecutionError as e:
            kce_logger.error(f"Execution error during workflow <{workflow_uri}> (Run ID: <{current_run_id_uri}>): {e}")
            workflow_successful = False
        except Exception as e:
            kce_logger.exception(f"Unexpected error during execution of workflow <{workflow_uri}> (Run ID: <{current_run_id_uri}>): {e}")
            workflow_successful = False
        finally:
            if not parent_run_id_uri:
                final_status = "CompletedSuccess" if workflow_successful else "Failed"
                self.prov_logger.end_workflow_execution(current_run_id_uri, final_status)
                kce_logger.info(f"Top-level workflow execution finished: {workflow_label} (<{workflow_uri}>), Run ID: <{current_run_id_uri}>, Status: {final_status}")

        return workflow_successful

    def _load_initial_parameters_to_context(self, context_uri: URIRef, params_dict: Dict[str, Any]):
        """Writes initial parameters as RDF properties of the context_uri."""
        if not params_dict:
            return
        
        triples_to_add: List[Tuple[URIRef, URIRef, RDFNode]] = []
        triples_to_add.append((context_uri, RDF.type, KCE.WorkflowInstanceData)) 
    
        for key, value in params_dict.items():
            try:
                # EX is now defined/imported at the top of the file
                prop_uri = to_uriref(key, base_ns=EX) 
            except ValueError:
                kce_logger.warning(f"Could not resolve parameter key '{key}' to a URI. Skipping.")
                continue
            
            rdf_value = to_literal(value)
            triples_to_add.append((context_uri, prop_uri, rdf_value))
        
        if triples_to_add:
            self.store.add_triples(iter(triples_to_add), perform_reasoning=False)
            kce_logger.info(f"Loaded {len(params_dict)} initial parameters to context <{context_uri}>.")


    def _get_workflow_label(self, workflow_uri: URIRef) -> str:
        wf_def_q = sparql_queries.format_query(sparql_queries.GET_WORKFLOW_DEFINITION, workflow_uri=str(workflow_uri))
        res = self.store.query(wf_def_q)
        if res and 'label' in res[0] and res[0]['label'] is not None: # Check if label exists and is not None
            return str(res[0]['label'])
        return workflow_uri.split('/')[-1].split('#')[-1]

    def _get_workflow_steps(self, workflow_uri: URIRef) -> List[URIRef]:
        query_str = sparql_queries.format_query(
            sparql_queries.GET_WORKFLOW_STEPS,
            workflow_uri=str(workflow_uri)
        )
        step_results = self.store.query(query_str)
        return [row['executes_node_uri'] for row in step_results if 'executes_node_uri' in row]

    def _get_node_type(self, node_uri: URIRef) -> Optional[URIRef]:
        query = sparql_queries.format_query(
            "SELECT ?type WHERE {{ <{node_uri}> <{rdf_type}> ?type . FILTER(?type = <{atomic_type}> || ?type = <{composite_type}>) }} LIMIT 1",
            node_uri=str(node_uri),
            rdf_type=str(RDF.type),
            atomic_type=str(KCE.AtomicNode),
            composite_type=str(KCE.CompositeNode)
        )
        results = self.store.query(query)
        if results and 'type' in results[0]:
            return results[0]['type']
        
        # Fallback: Check if it's any kce:Node if specific types not found (e.g. definition incomplete)
        query_generic = sparql_queries.format_query(
            "ASK {{ <{node_uri}> <{rdf_type}> <{node_base_type}> . }}",
            node_uri=str(node_uri),
            rdf_type=str(RDF.type),
            node_base_type=str(KCE.Node) # Check if it's at least a KCE.Node
        )
        if self.store.ask(query_generic):
             kce_logger.warning(f"Node <{node_uri}> is of base type kce:Node, but not specifically Atomic or Composite. "
                                "Or, its specific type triple is missing. Cannot execute as a step.")
        else:
            kce_logger.error(f"Node <{node_uri}> is not a recognized KCE Node type (Atomic or Composite). Cannot execute.")
        return None


    def _execute_composite_node(self, composite_node_uri: URIRef,
                                parent_run_id_uri: URIRef,
                                parent_context_uri: URIRef) -> bool:
        comp_node_label = self._get_node_label(composite_node_uri)
        kce_logger.info(f"Executing composite node: {comp_node_label} (<{composite_node_uri}>)")

        node_def_query = sparql_queries.format_query(
            sparql_queries.GET_NODE_DEFINITION,
            node_uri=str(composite_node_uri)
        )
        node_def_results = self.store.query(node_def_query)
        if not node_def_results or not node_def_results[0].get('internal_workflow_uri'):
            # Log error before raising, as this is a critical definition issue
            err_msg = f"CompositeNode <{composite_node_uri}> definition incomplete or missing internal_workflow_uri."
            kce_logger.error(err_msg)
            raise DefinitionError(err_msg)
        
        internal_workflow_uri = node_def_results[0]['internal_workflow_uri']
        
        composite_node_exec_uri = self.prov_logger.start_node_execution(
            parent_run_id_uri, composite_node_uri, comp_node_label
        )

        # MVP: Direct use of parent_context_uri for sub-workflow.
        # Post-MVP: Implement input/output mapping to/from a dedicated sub_workflow_context_uri.
        sub_workflow_context_uri_to_use = parent_context_uri 
        kce_logger.debug(f"Composite node <{composite_node_uri}> will execute internal workflow <{internal_workflow_uri}> "
                         f"using context: <{sub_workflow_context_uri_to_use}> (MVP direct use).")

        inputs_used_by_composite: Dict[str, URIRef] = {} # Placeholder for MVP
        outputs_generated_by_composite: Dict[str, URIRef] = {} # Placeholder for MVP

        sub_workflow_success = self.execute_workflow(
            workflow_uri=internal_workflow_uri,
            instance_context_uri_override=sub_workflow_context_uri_to_use,
            parent_run_id_uri=parent_run_id_uri,
            parent_node_exec_uri=composite_node_exec_uri
        )

        final_status = "CompletedSuccess" if sub_workflow_success else "Failed"
        self.prov_logger.end_node_execution(
            composite_node_exec_uri, final_status,
            inputs_used=inputs_used_by_composite,
            outputs_generated=outputs_generated_by_composite
        )
        
        return sub_workflow_success

# ... (if __name__ == '__main__' block remains the same) ...
if __name__ == '__main__':
    # --- Example Usage and Basic Test (remains largely the same as previous version) ---
    kce_logger.setLevel(logging.DEBUG)

    class MockStoreManager:
        def __init__(self):
            self.graph_data: Dict[Tuple[str, str], List[RDFNode]] = {}
            self.query_results_map: Dict[str, List[Dict[str, RDFNode]]] = {}
            self.ask_results_map: Dict[str, bool] = {}
            kce_logger.info("MockStoreManager for WorkflowExecutor test initialized.")
        def _get_key(self, s, p): return (str(s), str(p))
        def add_triples(self, triples_iter, perform_reasoning=True):
            for s, p, o in triples_iter:
                key = self._get_key(s,p)
                if key not in self.graph_data: self.graph_data[key] = []
                if o not in self.graph_data[key]: self.graph_data[key].append(o)
        def query(self, sparql_query_str):
            kce_logger.debug(f"MockStore Executing Query: {sparql_query_str[:100]}...")
            for q_key, results in self.query_results_map.items():
                if q_key in sparql_query_str: return results
            # Check for specific node type queries if general key not found
            if "FILTER(?type = <http://kce.com/ontology/core#AtomicNode> || ?type = <http://kce.com/ontology/core#CompositeNode>)" in sparql_query_str:
                if EX.NodeA_type_key in sparql_query_str: return [{"type": KCE.AtomicNode}]
                if EX.CompositeNodeC_type_key in sparql_query_str: return [{"type": KCE.CompositeNode}]
                if EX.NodeX_type_key in sparql_query_str: return [{"type": KCE.AtomicNode}]

            kce_logger.warning(f"MockStore: No result for query: {sparql_query_str[:100]}")
            return []
        def ask(self, sparql_ask_query: str) -> bool:
            kce_logger.debug(f"MockStore: Received ASK query:\n{sparql_ask_query}")
            for q_key, result in self.ask_results_map.items():
                if q_key in sparql_ask_query:
                    kce_logger.debug(f"MockStore: Matched ASK key '{q_key}', returning {result}.")
                    return result
            kce_logger.warning(f"MockStore: No mock ASK result for query: {sparql_ask_query}")
            return False # Default if not found
        def get_single_property_value(self, s, p, default=None):
            key = self._get_key(s,p)
            vals = self.graph_data.get(key)
            if vals: return vals[0]
            # Special handling for labels in test
            if p == RDFS.label:
                if s == EX.TestWorkflow1: return Literal("Test Workflow 1")
                if s == EX.InternalWorkflowForC: return Literal("Internal WF for C")
                if s == EX.CompositeNodeC: return Literal("Comp C")
            return default


    class MockNodeExecutor:
        def __init__(self):
            self.execution_outcomes: Dict[URIRef, bool] = {}
            self.executed_nodes_with_context: List[Tuple[URIRef, URIRef]] = []
            kce_logger.info("MockNodeExecutor for WorkflowExecutor test initialized.")
        def execute_node(self, node_uri, run_id_uri, workflow_instance_context):
            self.executed_nodes_with_context.append((node_uri, workflow_instance_context))
            kce_logger.info(f"MockNodeExecutor: Executing node <{node_uri}> with context <{workflow_instance_context}>")
            return self.execution_outcomes.get(node_uri, True)

    class MockRuleEvaluator:
        def __init__(self):
            self.rules_triggered_nodes_map: Dict[str, List[URIRef]] = {}
            self.eval_count = 0
            kce_logger.info("MockRuleEvaluator for WorkflowExecutor test initialized.")
        def evaluate_rules(self, current_run_id_uri=None):
            self.eval_count += 1
            kce_logger.info(f"MockRuleEvaluator: Evaluating rules (call #{self.eval_count})")
            return self.rules_triggered_nodes_map.get("after_any_node", [])


    class MockProvenanceLogger: # Simplified version
        def __init__(self): self.log: List[str] = []; self.run_counter = 0
        def start_workflow_execution(self, wu, ip=None, tb="sys"): self.run_counter +=1; ru = KCE[f"run/{self.run_counter}"]; self.log.append(f"START_WF: <{wu}> (<{ru}>)"); return ru
        def end_workflow_execution(self, ru, st, fo=None): self.log.append(f"END_WF: <{ru}> Status: {st}")
        def start_node_execution(self, ru, nu, nl=None): nru = KCE[f"noderun/{len(self.log)}"]; self.log.append(f"START_NODE: <{nu}> in <{ru}> (<{nru}>)"); return nru
        def end_node_execution(self, nru, st, iu=None, og=None, em=None): self.log.append(f"END_NODE: <{nru}> Status: {st}" + (f" Err: {em}" if em else ""))
        def log_generic_event(self, ru, et, msg, re=None, sev="INFO"): self.log.append(f"EVENT ({sev}): {msg} for <{ru}>")

    mock_store = MockStoreManager()
    mock_node_exec = MockNodeExecutor()
    mock_rule_eval = MockRuleEvaluator()
    mock_prov = MockProvenanceLogger()
    workflow_executor = WorkflowExecutor(mock_store, mock_node_exec, mock_rule_eval, mock_prov)

    wf1_uri = EX.TestWorkflow1
    nodeA_uri = EX.NodeA
    nodeB_uri = EX.NodeB
    compC_uri = EX.CompositeNodeC
    wf_internal_uri = EX.InternalWorkflowForC
    nodeX_uri = EX.NodeX

    # Define query keys for mock_store
    EX.NodeA_type_key = f"<{nodeA_uri}> <{RDF.type}> ?type"
    EX.CompositeNodeC_type_key = f"<{compC_uri}> <{RDF.type}> ?type"
    EX.NodeX_type_key = f"<{nodeX_uri}> <{RDF.type}> ?type"


    mock_store.query_results_map[str(wf1_uri)] = [{"label": Literal("Test Workflow 1")}]
    mock_store.query_results_map[f"{str(wf1_uri)}_steps"] = [
        {"executes_node_uri": nodeA_uri, "order": Literal(1)},
        {"executes_node_uri": compC_uri, "order": Literal(2)},
    ]
    
    mock_store.query_results_map[EX.NodeA_type_key] = [{"type": KCE.AtomicNode}]
    mock_store.query_results_map[EX.CompositeNodeC_type_key] = [{"type": KCE.CompositeNode}]
    mock_store.query_results_map[EX.NodeX_type_key] = [{"type": KCE.AtomicNode}]

    mock_store.query_results_map[f"{str(compC_uri)}_nodedef"] = [
        {"label": Literal("Comp C"), "internal_workflow_uri": wf_internal_uri}
    ]
    mock_store.query_results_map[str(wf_internal_uri)] = [{"label": Literal("Internal WF for C")}]
    mock_store.query_results_map[f"{str(wf_internal_uri)}_steps"] = [
        {"executes_node_uri": nodeX_uri, "order": Literal(1)},
    ]

    mock_node_exec.execution_outcomes = {nodeA_uri: True, nodeX_uri: True}
    mock_rule_eval.rules_triggered_nodes_map = {"after_any_node": [nodeB_uri]}

    kce_logger.info("\n--- Testing Workflow Execution ---")
    initial_params_json_test = '{"ex:initialInput": "start_value", "ex:user": "tester"}'
    success = workflow_executor.execute_workflow(wf1_uri, initial_parameters_json_test)

    assert success is True
    kce_logger.info(f"Workflow execution log: {mock_prov.log}")

    executed_node_uris_in_order = [n_uri for n_uri, ctx in mock_node_exec.executed_nodes_with_context]
    kce_logger.info(f"Executed nodes in order: {executed_node_uris_in_order}")
    
    assert nodeA_uri in executed_node_uris_in_order
    assert nodeB_uri in executed_node_uris_in_order
    assert nodeX_uri in executed_node_uris_in_order # This is executed by the composite node part

    # Check context creation and parameter loading
    top_level_run_uri = KCE["run/1"] # First call to start_workflow_execution in this test
    expected_context_uri_str_part = str(top_level_run_uri).split('/')[-1]
    expected_context_uri = KCE[f"instance_data/{expected_context_uri_str_part}"]
        
    assert (str(expected_context_uri), str(EX.initialInput)) in mock_store.graph_data
    assert mock_store.graph_data[(str(expected_context_uri), str(EX.initialInput))] == [Literal("start_value")]
    
    # Check context passed to nodes
    assert mock_node_exec.executed_nodes_with_context[0] == (nodeA_uri, expected_context_uri)
    # NodeB is triggered by rule, should use same top-level context
    # Find NodeB execution context
    nodeB_exec_details = next(item for item in mock_node_exec.executed_nodes_with_context if item[0] == nodeB_uri)
    assert nodeB_exec_details[1] == expected_context_uri

    # NodeX is inside CompositeNodeC. For MVP, it uses the parent context.
    nodeX_exec_details = next(item for item in mock_node_exec.executed_nodes_with_context if item[0] == nodeX_uri)
    assert nodeX_exec_details[1] == expected_context_uri


    assert mock_rule_eval.eval_count >= 3 # After NodeA, NodeB, NodeX

    kce_logger.info("WorkflowExecutor tests completed.")