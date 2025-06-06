from typing import List, Dict, Any, Optional
import rdflib

# Assuming interfaces.py is two levels up
from ..interfaces import IPlanExecutor, IKnowledgeLayer, INodeExecutor, IRuntimeStateLogger, IRuleEngine, ExecutionPlan, ExecutionResult, RDFGraph

# Define KCE namespace (ideally from a central place)
KCE = rdflib.Namespace("http://kce.com/ontology/core#")
# Define RDF and RDFS if not imported through other means in test mocks
RDF = rdflib.namespace.RDF
RDFS = rdflib.namespace.RDFS


class PlanExecutor(IPlanExecutor):
    def __init__(self,
                 node_executor: INodeExecutor,
                 runtime_state_logger: IRuntimeStateLogger,
                 rule_engine: Optional[IRuleEngine] = None): # RuleEngine might be optional for PlanExecutor if Planner handles rule ops directly
        self.node_executor = node_executor
        self.logger = runtime_state_logger
        self.rule_engine = rule_engine # RuleEngine is needed if plan steps include 'apply_rules'

    def execute_plan(self,
                     plan: ExecutionPlan,
                     run_id: str,
                     knowledge_layer: IKnowledgeLayer,
                     initial_graph: Optional[RDFGraph] = None) -> ExecutionResult:
        '''
        Executes a given plan (sequence of operations), interacting with the KnowledgeLayer.
        The plan is a list of dictionaries, each specifying 'operation_type' ('node' or 'rule')
        and 'operation_uri' (URI of the node or rule).
        '''
        print(f"Executing plan for run_id: {run_id}. Plan has {len(plan)} steps.")

        if initial_graph is not None and len(initial_graph) > 0:
            knowledge_layer.add_graph(initial_graph, context_uri=rdflib.URIRef(f"urn:kce:run:{run_id}:initial_plan_data"))
            self.logger.log_event(
                run_id=run_id,
                event_type="PlanSegmentStart",
                operation_uri=None,
                status="Started",
                inputs={"plan_step_count": len(plan), "initial_graph_size": len(initial_graph)},
                outputs=None,
                knowledge_layer=knowledge_layer
            )
        else:
             self.logger.log_event(
                run_id=run_id,
                event_type="PlanSegmentStart",
                operation_uri=None,
                status="Started",
                inputs={"plan_step_count": len(plan)},
                outputs=None,
                knowledge_layer=knowledge_layer
            )


        for i, step in enumerate(plan):
            operation_type = step.get("operation_type")
            # Ensure operation_uri is a string, as it's often used to build URIs or log messages
            operation_uri_any = step.get("operation_uri")
            operation_uri = str(operation_uri_any) if operation_uri_any is not None else None


            if not operation_type or not operation_uri:
                message = f"Invalid plan step {i+1}/{len(plan)}: missing operation_type or operation_uri."
                print(message)
                self.logger.log_event(run_id=run_id, event_type="PlanStepExecution", operation_uri="InvalidStep", status="Failed", inputs={"step_details": step}, outputs=None, message=message, knowledge_layer=knowledge_layer)
                return {"status": "failure", "message": message, "run_id": run_id, "failed_step_index": i}

            print(f"Executing plan step {i+1}/{len(plan)}: Type='{operation_type}', URI='{operation_uri}'")

            step_inputs = {"operation_type": operation_type, "operation_uri": operation_uri}

            self.logger.log_event(
                run_id=run_id,
                event_type=f"{operation_type.capitalize()}ExecutionStart",
                operation_uri=operation_uri,
                status="Started",
                inputs=step_inputs,
                outputs=None,
                knowledge_layer=knowledge_layer
            )

            try:
                if operation_type == "node":
                    node_input_context_graph = rdflib.Graph()

                    output_rdf_graph = self.node_executor.execute_node(
                        node_uri=operation_uri,
                        run_id=run_id,
                        knowledge_layer=knowledge_layer,
                        current_input_graph=node_input_context_graph
                    )

                    if output_rdf_graph and len(output_rdf_graph) > 0:
                        knowledge_layer.add_graph(output_rdf_graph)

                    self.logger.log_event(
                        run_id=run_id,
                        event_type=f"{operation_type.capitalize()}ExecutionEnd",
                        operation_uri=operation_uri,
                        status="Succeeded",
                        inputs=step_inputs,
                        outputs={"generated_triples_count": len(output_rdf_graph) if output_rdf_graph else 0},
                        knowledge_layer=knowledge_layer
                    )

                elif operation_type == "rule":
                    if not self.rule_engine:
                        # Log this specific error before raising, so it's captured by RuntimeStateLogger
                        err_msg_no_re = "Rule execution requested but no RuleEngine provided to PlanExecutor."
                        self.logger.log_event(run_id=run_id, event_type=f"{operation_type.capitalize()}ExecutionEnd", operation_uri=operation_uri,status="Failed", inputs=step_inputs, outputs=None, message=err_msg_no_re, knowledge_layer=knowledge_layer)
                        raise NotImplementedError(err_msg_no_re)

                    rules_applied_flag = self.rule_engine.apply_rules(knowledge_layer, run_id=run_id)

                    self.logger.log_event(
                        run_id=run_id,
                        event_type=f"{operation_type.capitalize()}ApplicationEnd",
                        operation_uri=operation_uri,
                        status="Succeeded",
                        inputs={"trigger_condition": "plan_step"},
                        outputs={"rules_were_applied": rules_applied_flag},
                        knowledge_layer=knowledge_layer
                    )
                else:
                    err_msg_unsupported_op = f"Unsupported operation type: {operation_type} for URI {operation_uri}"
                    self.logger.log_event(run_id=run_id, event_type="PlanStepExecution", operation_uri=operation_uri,status="Failed",inputs=step_inputs, outputs=None,message=err_msg_unsupported_op,knowledge_layer=knowledge_layer)
                    raise NotImplementedError(err_msg_unsupported_op)

            except Exception as e:
                import traceback
                error_msg = f"Error executing plan step {i+1} ({operation_type} <{operation_uri}>): {e}\n{traceback.format_exc()}"
                print(error_msg)
                self.logger.log_event(
                    run_id=run_id,
                    event_type=f"{operation_type.capitalize()}ExecutionEnd",
                    operation_uri=operation_uri,
                    status="Failed",
                    inputs=step_inputs,
                    outputs=None,
                    message=error_msg,
                    knowledge_layer=knowledge_layer
                )
                return {"status": "failure", "message": error_msg, "run_id": run_id, "failed_step_index": i}

        final_message = f"Plan execution completed successfully for run_id: {run_id}"
        self.logger.log_event(run_id=run_id, event_type="PlanSegmentEnd", operation_uri=None, status="Succeeded", inputs={"total_steps": len(plan)}, outputs=None, message=final_message, knowledge_layer=knowledge_layer)
        return {"status": "success", "message": final_message, "run_id": run_id}


if __name__ == '__main__':
    # Mock dependencies
    class MockKnowledgeLayer(IKnowledgeLayer):
        def __init__(self): self.graph = rdflib.Graph(); self.log_count = 0
        def execute_sparql_query(self, q): print(f"KL Query: {q[:30]}..."); return []
        def execute_sparql_update(self, u): print(f"KL Update: {u[:30]}...")
        def trigger_reasoning(self): print("KL Trigger Reasoning")
        def add_graph(self, g, context_uri=None): print(f"KL Add Graph: {len(g)} triples to context {context_uri if context_uri else 'default'}"); self.graph += g
        def get_graph(self, context_uri=None): return self.graph
        def store_human_readable_log(self, rid, eid, content): self.log_count +=1; print(f"KL StoreLog: Run='{rid}', Event='{eid}'"); return f"logs/{rid}/{eid}.log"
        def get_human_readable_log(self, loc): return "log content"

    class MockNodeExecutor(INodeExecutor):
        def execute_node(self, node_uri, run_id, kl, current_input_graph):
            print(f"NodeExecutor: Executing node <{node_uri}> for run <{run_id}>")
            if node_uri == "ex:FailingNode":
                raise ValueError("This node is designed to fail.")
            out_g = rdflib.Graph()
            out_g.add((rdflib.URIRef(node_uri), KCE.hasOutputValue, rdflib.Literal("MockOutput")))
            return out_g

    class MockRuntimeStateLogger(IRuntimeStateLogger):
        def log_event(self, run_id, event_type, operation_uri, status, inputs, outputs, message=None, knowledge_layer=None):
            print(f"Logger: Event='{event_type}', Op='{operation_uri}', Status='{status}', Run='{run_id}'")
            if message: print(f"  Msg: {message[:100]}...")
            if inputs: print(f"  Inputs: {inputs}")
            if outputs: print(f"  Outputs: {outputs}")


    class MockRuleEngine(IRuleEngine):
        def apply_rules(self, knowledge_layer, run_id=None):
            print(f"RuleEngine: Applying rules for run <{run_id}>")
            rule_effect_g = rdflib.Graph()
            rule_effect_g.add((KCE.RuleEffectInstance, RDF.type, KCE.SomeRuleDerivedData)) # Ensure RDF is defined
            knowledge_layer.add_graph(rule_effect_g)
            return True

    # Setup
    EX = rdflib.Namespace("http://example.com/ns#") # Define EX for test URIs
    mock_kl_instance = MockKnowledgeLayer()
    mock_ne_instance = MockNodeExecutor()
    mock_rsl_instance = MockRuntimeStateLogger()
    mock_re_instance = MockRuleEngine()

    plan_executor = PlanExecutor(node_executor=mock_ne_instance, runtime_state_logger=mock_rsl_instance, rule_engine=mock_re_instance)

    test_run_id_main = "test_plan_run_main_001"

    sample_plan_success: ExecutionPlan = [
        {"operation_type": "node", "operation_uri": str(EX.NodeA)},
        {"operation_type": "rule", "operation_uri": str(EX.RuleSet1Trigger)},
        {"operation_type": "node", "operation_uri": str(EX.NodeB)}
    ]
    print("\n--- Test Plan 1: Successful Execution ---")
    result1 = plan_executor.execute_plan(sample_plan_success, test_run_id_main, mock_kl_instance)
    print(f"Plan 1 Result: {result1['status']} - {result1['message']}")
    assert result1['status'] == 'success'

    sample_plan_fail: ExecutionPlan = [
        {"operation_type": "node", "operation_uri": str(EX.NodeC)},
        {"operation_type": "node", "operation_uri": "ex:FailingNode"}, # This will fail
        {"operation_type": "node", "operation_uri": str(EX.NodeD)}
    ]
    print("\n--- Test Plan 2: Execution with Failing Node ---")
    result2 = plan_executor.execute_plan(sample_plan_fail, test_run_id_main + "_fail", mock_kl_instance)
    print(f"Plan 2 Result: {result2['status']} - {result2['message']}")
    assert result2['status'] == 'failure'
    assert result2.get('failed_step_index') == 1

    sample_plan_invalid: ExecutionPlan = [
        {"operation_type": "node", "operation_uri": str(EX.NodeE)},
        {"operation_uri": str(EX.InvalidStepMissingType)},
    ]
    print("\n--- Test Plan 3: Execution with Invalid Step ---")
    result3 = plan_executor.execute_plan(sample_plan_invalid, test_run_id_main + "_invalid", mock_kl_instance)
    print(f"Plan 3 Result: {result3['status']} - {result3['message']}")
    assert result3['status'] == 'failure'
    assert result3.get('failed_step_index') == 1

    plan_executor_no_re = PlanExecutor(node_executor=mock_ne_instance, runtime_state_logger=mock_rsl_instance, rule_engine=None)
    sample_plan_rule_no_re: ExecutionPlan = [
        {"operation_type": "rule", "operation_uri": str(EX.SomeRule)}
    ]
    print("\n--- Test Plan 4: Rule Execution with No RuleEngine ---")
    result4 = plan_executor_no_re.execute_plan(sample_plan_rule_no_re, test_run_id_main + "_no_re", mock_kl_instance)
    print(f"Plan 4 Result: {result4['status']} - {result4['message']}")
    assert result4['status'] == 'failure'
    assert "RuleEngine provided" in result4['message']

    print("\nPlanExecutor test complete.")
