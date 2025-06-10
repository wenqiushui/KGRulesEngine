import pytest
from pathlib import Path
import json
import os
import sys
from unittest.mock import MagicMock, call, ANY

# KCE Core component imports
from kce_core.execution_layer.node_executor import NodeExecutor
from kce_core.execution_layer.plan_executor import PlanExecutor
from kce_core.interfaces import (
    IKnowledgeLayer, IRuntimeStateLogger, RDFGraph,
    IPlanExecutor, INodeExecutor, IRuleEngine,
    ExecutionResult, TargetDescription, ExecutionPlan
)
from kce_core.knowledge_layer.rdf_store.store_manager import RdfStoreManager
from kce_core.execution_layer.runtime_state_logger import RuntimeStateLogger as ConcreteRuntimeStateLogger
from kce_core.planning_reasoning_core_layer.rule_engine import RuleEngine

# RDFLib imports
from rdflib import URIRef, Literal, Namespace, XSD, RDF, RDFS, Graph

# Define Namespaces
EX_NS = Namespace("http://example.com/ns#")
KCE_NS = Namespace("http://kce.com/ontology/core#") # Used in NodeExecutor

# KCE terms for argument passing (matching those in NodeExecutor.py)
ARG_PASSING_STYLE_PROP = KCE_NS.argumentPassingStyle
CMD_LINE_ARGS_STYLE = KCE_NS.CommandLineArguments
STDIN_JSON_STYLE = KCE_NS.StdInJSON
PARAM_ORDER_PROP = KCE_NS.parameterOrder
MAPS_TO_RDF_PROPERTY_PROP = KCE_NS.mapsToRdfProperty
HAS_DATATYPE_PROP = KCE_NS.hasDatatype


# --- Fixtures ---
@pytest.fixture
def mock_knowledge_layer():
    mock_kl = MagicMock(spec=IKnowledgeLayer)
    mock_kl.graph = MagicMock(spec=Graph)
    mock_kl.execute_sparql_update.return_value = None
    mock_kl.get_graph.return_value = mock_kl.graph
    return mock_kl

@pytest.fixture
def mock_runtime_logger():
    return MagicMock(spec=IRuntimeStateLogger)

@pytest.fixture
def node_executor():
    return NodeExecutor()

@pytest.fixture
def mock_node_executor():
    return MagicMock(spec=INodeExecutor)

@pytest.fixture
def mock_rule_engine():
    mock_re = MagicMock(spec=IRuleEngine)
    mock_re.apply_rules.return_value = False
    return mock_re

@pytest.fixture
def plan_executor(mock_node_executor: MagicMock, mock_runtime_logger: MagicMock, mock_rule_engine: MagicMock):
    return PlanExecutor(
        node_executor=mock_node_executor,
        runtime_state_logger=mock_runtime_logger,
        rule_engine=mock_rule_engine
    )

# --- NodeExecutor Test Cases ---
def test_node_executor_python_script(node_executor: NodeExecutor, mock_knowledge_layer: MagicMock, tmp_path: Path):
    script_content = """
import json, sys
try:
    inputs = json.load(sys.stdin)
    a = inputs.get("param_a", 0); b = inputs.get("param_b", 0)
    outputs = {"sum_result": a + b, "message": "Calculation successful"}
    json.dump(outputs, sys.stdout)
except Exception as e:
    sys.stderr.write(f"Script error: {{'error': str(e), 'script_failed': True}}\\n")
    sys.exit(1)
"""
    script_file_path = tmp_path / "simple_script.py"; script_file_path.write_text(script_content); os.chmod(script_file_path, 0o755)
    node_uri_str, node_uri = str(EX_NS["TestScriptNode_001"]), EX_NS["TestScriptNode_001"]
    in_a_uri, in_a_name, in_a_map = EX_NS["inA"], Literal("param_a"), EX_NS["mapA"]
    in_b_uri, in_b_name, in_b_map = EX_NS["inB"], Literal("param_b"), EX_NS["mapB"]
    out_sum_uri, out_sum_name, out_sum_map = EX_NS["outSum"], Literal("sum_result"), EX_NS["mapSum"]

    mock_knowledge_layer.execute_sparql_query.side_effect = [
        [{'type': KCE_NS.PythonScriptInvocation, 'scriptPath': Literal(str(script_file_path.resolve())),
          'command': None, 'target_uri': None, 'target_sparql_ask_query': None, 'arg_style_uri': None}], # arg_style is None for STDIN
        [{'paramName': in_a_name, 'rdfProp': in_a_map, 'datatype': XSD.integer, 'order': Literal(1, datatype=XSD.integer)},
         {'paramName': in_b_name, 'rdfProp': in_b_map, 'datatype': XSD.integer, 'order': Literal(2, datatype=XSD.integer)}],
        [{'paramName': out_sum_name, 'rdfProp': out_sum_map, 'datatype': XSD.integer, 'nodeContextUri': node_uri, 'order': Literal(1, datatype=XSD.integer)}]
    ]
    input_rdf_graph = Graph(); input_entity = EX_NS["inEntity"]
    input_rdf_graph.add((input_entity, in_a_map, Literal(10, datatype=XSD.integer)))
    input_rdf_graph.add((input_entity, in_b_map, Literal(5, datatype=XSD.integer)))

    output_graph = node_executor.execute_node(node_uri_str, "run1", mock_knowledge_layer, input_rdf_graph)
    assert isinstance(output_graph, Graph)

    expected_triple = (node_uri, out_sum_map, Literal(15, datatype=XSD.integer))
    assert len(output_graph) == 1, f"Output graph should contain one triple, got {len(output_graph)}. Graph: {list(output_graph)}"
    s_out, p_out, o_out = list(output_graph)[0]
    assert s_out == expected_triple[0], f"Subject mismatch: Got {s_out.n3()} vs Expected {expected_triple[0].n3()}"
    assert p_out == expected_triple[1], f"Predicate mismatch: Got {p_out.n3()} vs Expected {expected_triple[1].n3()}"
    assert o_out == expected_triple[2], f"Object mismatch: Got {o_out.n3()} vs Expected {expected_triple[2].n3()}"
    assert mock_knowledge_layer.execute_sparql_query.call_count == 3

def test_node_executor_sparql_update(node_executor: NodeExecutor, mock_knowledge_layer: MagicMock):
    node_uri_str, query = str(EX_NS["UpdateNode"]), "INSERT DATA { ex:s ex:p ex:o . }"
    mock_knowledge_layer.execute_sparql_query.side_effect = [[{'type': KCE_NS.SparqlUpdateInvocation, 'command': Literal(query), 'scriptPath':None, 'target_uri':None, 'target_sparql_ask_query':None, 'arg_style_uri': None}], [], []]
    # Current NodeExecutor handles SparqlUpdateInvocation and returns empty graph
    output_graph = node_executor.execute_node(node_uri_str, "run_sparql", mock_knowledge_layer, Graph())
    assert isinstance(output_graph, Graph) and len(output_graph) == 0
    mock_knowledge_layer.execute_sparql_update.assert_called_once_with(query)
    assert mock_knowledge_layer.execute_sparql_query.call_count == 1

def test_node_executor_python_script_runtime_error(node_executor: NodeExecutor, mock_knowledge_layer: MagicMock, tmp_path: Path):
    s_path = tmp_path / "error.py"; s_path.write_text("import sys; raise ValueError('Deliberate runtime error'); sys.exit(1)"); os.chmod(s_path, 0o755)
    mock_knowledge_layer.execute_sparql_query.side_effect = [[{'type': KCE_NS.PythonScriptInvocation, 'scriptPath': Literal(str(s_path.resolve())), 'command':None, 'target_uri':None, 'target_sparql_ask_query':None, 'arg_style_uri': None}], [], []]
    with pytest.raises(RuntimeError, match="failed with exit code 1"):
        node_executor.execute_node(str(EX_NS["ErrNode"]), "run_err", mock_knowledge_layer, Graph())

def test_node_executor_python_script_malformed_json_output(node_executor: NodeExecutor, mock_knowledge_layer: MagicMock, tmp_path: Path):
    s_path = tmp_path / "badjson.py"; s_path.write_text("import sys; sys.stdout.write('{badjson')"); os.chmod(s_path, 0o755)
    mock_knowledge_layer.execute_sparql_query.side_effect = [[{'type': KCE_NS.PythonScriptInvocation, 'scriptPath': Literal(str(s_path.resolve())), 'command':None, 'target_uri':None, 'target_sparql_ask_query':None, 'arg_style_uri': None}], [], []]
    with pytest.raises(RuntimeError, match="Failed to decode JSON output"):
        node_executor.execute_node(str(EX_NS["BadJsonNode"]), "run_badjson", mock_knowledge_layer, Graph())

def test_node_executor_script_path_not_found(node_executor: NodeExecutor, mock_knowledge_layer: MagicMock):
    mock_knowledge_layer.execute_sparql_query.side_effect = [[{'type': KCE_NS.PythonScriptInvocation, 'scriptPath': Literal("/no/such/script.py"), 'command':None, 'target_uri':None, 'target_sparql_ask_query':None, 'arg_style_uri': None}], [], []]
    with pytest.raises(FileNotFoundError, match="Script not found"):
        node_executor.execute_node(str(EX_NS["NoScriptNode"]), "run_noscript", mock_knowledge_layer, Graph())

# --- New Test for Command-Line Args ---
def test_node_executor_python_script_cmd_line_args(
    node_executor: NodeExecutor,
    mock_knowledge_layer: MagicMock,
    tmp_path: Path
):
    script_content = """
import json, sys
arg_string = "-".join(sys.argv[1:]) # Skip script name, join others
outputs = {"combined_result": arg_string, "arg_count": len(sys.argv) -1}
sys.stdout.write(json.dumps(outputs))
sys.stdout.flush()
"""
    script_file_path = tmp_path / "cmd_line_script.py"; script_file_path.write_text(script_content); os.chmod(script_file_path, 0o755)
    node_uri_str = str(EX_NS["TestCmdLineNode_001"])
    node_uri = EX_NS["TestCmdLineNode_001"]

    # Parameter definitions for command line
    param_str_uri = EX_NS.inputStrParam; param_str_name = Literal("param_str1"); param_str_map = EX_NS.hasStringValue
    param_num_uri = EX_NS.inputNumParam; param_num_name = Literal("param_num1"); param_num_map = EX_NS.hasNumValue
    output_comb_uri = EX_NS.outputCombined; output_comb_name = Literal("combined_result"); output_comb_map = EX_NS.hasCombinedOutput

    mock_knowledge_layer.execute_sparql_query.side_effect = [
        [{ # Call 1: _get_node_implementation_details
            'type': KCE_NS.PythonScriptInvocation,
            'scriptPath': Literal(str(script_file_path.resolve())),
            'command': None, 'target_uri': None, 'target_sparql_ask_query': None,
            'arg_style_uri': CMD_LINE_ARGS_STYLE # Specify command line style
        }],
        [ # Call 2: _get_node_parameter_definitions (inputs)
            {'paramName': param_str_name, 'rdfProp': param_str_map, 'datatype': XSD.string, 'order': Literal(1, datatype=XSD.integer), 'param_uri': param_str_uri},
            {'paramName': param_num_name, 'rdfProp': param_num_map, 'datatype': XSD.integer, 'order': Literal(2, datatype=XSD.integer), 'param_uri': param_num_uri}
        ],
        [ # Call 3: _get_node_parameter_definitions (outputs)
            {'paramName': output_comb_name, 'rdfProp': output_comb_map, 'datatype': XSD.string, 'nodeContextUri': node_uri, 'order': Literal(1, datatype=XSD.integer), 'param_uri': output_comb_uri}
        ]
    ]

    input_rdf_graph = Graph(); current_entity_uri = EX_NS["cmdLineInputEntity"]
    input_rdf_graph.add((current_entity_uri, param_str_map, Literal("hello")))
    input_rdf_graph.add((current_entity_uri, param_num_map, Literal(42, datatype=XSD.integer)))

    output_graph = node_executor.execute_node(node_uri_str, "run_cmdline", mock_knowledge_layer, input_rdf_graph)

    assert isinstance(output_graph, Graph)
    expected_combined_value = "hello-42" # Script concatenates with '-'
    assert (node_uri, output_comb_map, Literal(expected_combined_value, datatype=XSD.string)) in output_graph, \
        f"Output graph does not contain expected combined string. Actual: {list(output_graph.triples((None,None,None)))}"
    assert mock_knowledge_layer.execute_sparql_query.call_count == 3


# --- PlanExecutor Test Cases ---
# (PlanExecutor tests remain unchanged from last successful run)
def test_plan_executor_one_node_success(
    plan_executor: PlanExecutor, mock_node_executor: MagicMock,
    mock_rule_engine: MagicMock, mock_knowledge_layer: MagicMock,
    mock_runtime_logger: MagicMock
):
    node1_uri_str = str(EX_NS["Node1"])
    plan: ExecutionPlan = [{"operation_type": "node", "operation_uri": node1_uri_str}]
    initial_graph_arg = Graph(); initial_graph_arg.add((EX_NS["initialData"], RDF.type, EX_NS["SomeType"]))
    output_node1_graph = Graph(); output_node1_graph.add((EX_NS["Node1Output"], RDF.type, EX_NS["OutputType1"]))

    mock_node_executor.execute_node.return_value = output_node1_graph

    run_id = "test_run_simple_plan"
    result = plan_executor.execute_plan(plan, run_id, mock_knowledge_layer, initial_graph_arg)

    assert result["status"] == "success"
    mock_knowledge_layer.add_graph.assert_any_call(initial_graph_arg, context_uri=URIRef(f"urn:kce:run:{run_id}:initial_plan_data"))
    mock_knowledge_layer.add_graph.assert_any_call(output_node1_graph)

    mock_node_executor.execute_node.assert_called_once_with(
        node_uri=node1_uri_str, run_id=run_id,
        knowledge_layer=mock_knowledge_layer, current_input_graph=ANY
    )
    assert len(mock_node_executor.execute_node.call_args.kwargs['current_input_graph']) == 0

    mock_rule_engine.apply_rules.assert_not_called()

    expected_start_inputs = {"plan_step_count": len(plan), "initial_graph_size": len(initial_graph_arg)}
    if not initial_graph_arg: expected_start_inputs = {"plan_step_count": len(plan)}

    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="PlanSegmentStart", operation_uri=None, status="Started",
        inputs=expected_start_inputs, outputs=None, # message omitted
        knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionStart", operation_uri=node1_uri_str, status="Started",
        inputs={"operation_type": "node", "operation_uri": node1_uri_str}, outputs=None, # message omitted
        knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionEnd", operation_uri=node1_uri_str, status="Succeeded",
        inputs={"operation_type": "node", "operation_uri": node1_uri_str},
        outputs={"generated_triples_count": len(output_node1_graph)}, # message omitted
        knowledge_layer=mock_knowledge_layer
    )
    expected_end_inputs = {"total_steps": len(plan)}
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="PlanSegmentEnd", operation_uri=None, status="Succeeded",
        inputs=expected_end_inputs, outputs=None, message=ANY,
        knowledge_layer=mock_knowledge_layer
    )

def test_plan_executor_two_nodes_data_flow(
    plan_executor: PlanExecutor, mock_node_executor: MagicMock,
    mock_rule_engine: MagicMock, mock_knowledge_layer: MagicMock,
    mock_runtime_logger: MagicMock
):
    node1_uri_str, node2_uri_str = str(EX_NS["Node1"]), str(EX_NS["Node2"])
    plan: ExecutionPlan = [
        {"operation_type": "node", "operation_uri": node1_uri_str},
        {"operation_type": "node", "operation_uri": node2_uri_str}
    ]
    initial_graph_arg = Graph(); initial_graph_arg.add((EX_NS["initialData"], RDF.type, EX_NS["SomeType"]))
    output_node1_graph = Graph(); output_node1_graph.add((EX_NS["Node1Output"], EX_NS["isOutputOf"], EX_NS["Node1"]))
    output_node2_graph = Graph(); output_node2_graph.add((EX_NS["Node2Output"], EX_NS["isOutputOf"], EX_NS["Node2"]))

    mock_node_executor.execute_node.side_effect = [output_node1_graph, output_node2_graph]
    mock_rule_engine.apply_rules.return_value = False

    run_id = "test_run_two_nodes"
    result = plan_executor.execute_plan(plan, run_id, mock_knowledge_layer, initial_graph_arg)

    assert result["status"] == "success"
    mock_knowledge_layer.add_graph.assert_any_call(initial_graph_arg, context_uri=ANY)
    mock_knowledge_layer.add_graph.assert_any_call(output_node1_graph)
    mock_knowledge_layer.add_graph.assert_any_call(output_node2_graph)

    assert mock_node_executor.execute_node.call_count == 2

    call_node1_args = mock_node_executor.execute_node.call_args_list[0]
    assert call_node1_args.kwargs['node_uri'] == node1_uri_str
    assert len(call_node1_args.kwargs['current_input_graph']) == 0

    call_node2_args = mock_node_executor.execute_node.call_args_list[1]
    assert call_node2_args.kwargs['node_uri'] == node2_uri_str
    assert len(call_node2_args.kwargs['current_input_graph']) == 0

    mock_rule_engine.apply_rules.assert_not_called()

    expected_start_inputs = {"plan_step_count": len(plan), "initial_graph_size": len(initial_graph_arg)}
    if not initial_graph_arg: expected_start_inputs = {"plan_step_count": len(plan)}
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="PlanSegmentStart", operation_uri=None, status="Started",
        inputs=expected_start_inputs, outputs=None, # message omitted
        knowledge_layer=mock_knowledge_layer
    )

    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionStart", operation_uri=node1_uri_str, status="Started",
        inputs={"operation_type": "node", "operation_uri": node1_uri_str}, outputs=None, # message omitted
        knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionEnd", operation_uri=node1_uri_str, status="Succeeded",
        inputs={"operation_type": "node", "operation_uri": node1_uri_str},
        outputs={"generated_triples_count": len(output_node1_graph)}, # message omitted
        knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionStart", operation_uri=node2_uri_str, status="Started",
        inputs={"operation_type": "node", "operation_uri": node2_uri_str}, outputs=None, # message omitted
        knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionEnd", operation_uri=node2_uri_str, status="Succeeded",
        inputs={"operation_type": "node", "operation_uri": node2_uri_str},
        outputs={"generated_triples_count": len(output_node2_graph)}, # message omitted
        knowledge_layer=mock_knowledge_layer
    )

    expected_end_inputs = {"total_steps": len(plan)}
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="PlanSegmentEnd", operation_uri=None, status="Succeeded",
        inputs=expected_end_inputs, outputs=None, message=ANY,
        knowledge_layer=mock_knowledge_layer
    )

def test_plan_executor_rule_operation(
    plan_executor: PlanExecutor, mock_node_executor: MagicMock,
    mock_rule_engine: MagicMock, mock_knowledge_layer: MagicMock,
    mock_runtime_logger: MagicMock
):
    rule_op_uri = str(EX_NS["RuleSetToApply"])
    plan: ExecutionPlan = [{"operation_type": "rule", "operation_uri": rule_op_uri}]
    initial_graph_arg = Graph()
    run_id = "test_run_rule_op_plan"

    mock_rule_engine.apply_rules.return_value = True

    result = plan_executor.execute_plan(plan, run_id, mock_knowledge_layer, initial_graph_arg)

    assert result["status"] == "success"
    mock_rule_engine.apply_rules.assert_called_once_with(mock_knowledge_layer, run_id=run_id)
    mock_node_executor.execute_node.assert_not_called()

    expected_start_inputs = {"plan_step_count": len(plan), "initial_graph_size": len(initial_graph_arg)}
    if not initial_graph_arg: expected_start_inputs = {"plan_step_count": len(plan)}
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="PlanSegmentStart", operation_uri=None, status="Started",
        inputs=expected_start_inputs, outputs=None, knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="RuleExecutionStart", operation_uri=rule_op_uri, status="Started",
        inputs={"operation_type": "rule", "operation_uri": rule_op_uri}, outputs=None,
        knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="RuleApplicationEnd", operation_uri=rule_op_uri, status="Succeeded",
        inputs={"trigger_condition": "plan_step"}, outputs={"rules_were_applied": True},
        knowledge_layer=mock_knowledge_layer
    )
    expected_end_inputs = {"total_steps": len(plan)}
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="PlanSegmentEnd", operation_uri=None, status="Succeeded",
        inputs=expected_end_inputs, outputs=None, message=ANY,
        knowledge_layer=mock_knowledge_layer
    )

def test_plan_executor_node_failure(
    plan_executor: PlanExecutor, mock_node_executor: MagicMock,
    mock_rule_engine: MagicMock, mock_knowledge_layer: MagicMock,
    mock_runtime_logger: MagicMock
):
    node_uri_str = str(EX_NS["FailingNode"])
    plan: ExecutionPlan = [{"operation_type": "node", "operation_uri": node_uri_str}]
    initial_graph_arg = Graph()
    run_id = "test_run_node_failure_plan"
    error_message_from_node = "Node failed to execute due to internal error"

    mock_node_executor.execute_node.side_effect = RuntimeError(error_message_from_node)

    result = plan_executor.execute_plan(plan, run_id, mock_knowledge_layer, initial_graph_arg)

    assert result["status"] == "failure"
    assert "error executing plan step" in result["message"].lower()
    assert error_message_from_node in result["message"]
    assert result.get("failed_step_index") == 0

    mock_node_executor.execute_node.assert_called_once()
    mock_rule_engine.apply_rules.assert_not_called()

    expected_start_inputs = {"plan_step_count": len(plan), "initial_graph_size": len(initial_graph_arg)}
    if not initial_graph_arg: expected_start_inputs = {"plan_step_count": len(plan)}
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="PlanSegmentStart", operation_uri=None, status="Started",
        inputs=expected_start_inputs, outputs=None, knowledge_layer=mock_knowledge_layer
    )
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionStart", operation_uri=node_uri_str, status="Started",
        inputs={"operation_type": "node", "operation_uri": node_uri_str}, outputs=None,
        knowledge_layer=mock_knowledge_layer
    )
    # In PlanExecutor, the message for NodeExecutionEnd (Failed) includes the traceback.
    mock_runtime_logger.log_event.assert_any_call(
        run_id=run_id, event_type="NodeExecutionEnd", operation_uri=node_uri_str, status="Failed",
        inputs={"operation_type": "node", "operation_uri": node_uri_str}, outputs=None, message=ANY,
        knowledge_layer=mock_knowledge_layer
    )

    # PlanSegmentEnd should not be logged with "Succeeded" status on failure
    for actual_call in mock_runtime_logger.log_event.call_args_list:
        if actual_call.kwargs.get('event_type') == "PlanSegmentEnd":
            assert actual_call.kwargs.get('status') != "Succeeded"
    assert not any(c.kwargs.get('event_type') == "PlanSegmentEnd" and c.kwargs.get('status') == "Succeeded" for c in mock_runtime_logger.log_event.call_args_list)
