import pytest
from pathlib import Path
import json
import os
from unittest.mock import MagicMock, call, ANY # Ensure ANY is imported

# KCE Core component imports
from kce_core.execution_layer.node_executor import NodeExecutor
from kce_core.interfaces import IKnowledgeLayer, IRuntimeStateLogger, RDFGraph
from kce_core.knowledge_layer.rdf_store.store_manager import RdfStoreManager
from kce_core.execution_layer.runtime_state_logger import RuntimeStateLogger as ConcreteRuntimeStateLogger

# RDFLib imports
from rdflib import URIRef, Literal, Namespace, XSD, RDF, RDFS, Graph

# Define Namespaces
EX_NS = Namespace("http://example.com/ns#")
KCE_NS = Namespace("http://kce.com/ontology/core#")

# Fixtures
@pytest.fixture
def mock_knowledge_layer_for_node_exec():
    mock_kl = MagicMock(spec=IKnowledgeLayer)
    mock_kl.graph = MagicMock(spec=Graph)
    return mock_kl

@pytest.fixture
def mock_runtime_logger_for_node_exec(): # Although NodeExecutor.__init__ takes no args, other methods might use it if it were passed differently
    return MagicMock(spec=IRuntimeStateLogger)

@pytest.fixture
def node_executor():
    return NodeExecutor()

# Test Cases
def test_node_executor_python_script(
    node_executor: NodeExecutor,
    mock_knowledge_layer_for_node_exec: MagicMock,
    # mock_runtime_logger_for_node_exec: MagicMock, # Not directly used by execute_node signature
    tmp_path: Path
):
    """Tests successful execution of a Python script node using stdin/stdout."""

    # 1. Create the Python script (adapted for stdin/stdout)
    script_content = """
import json
import sys

try:
    inputs = json.load(sys.stdin)

    a = inputs.get("param_a", 0)
    b = inputs.get("param_b", 0)
    result_sum = a + b

    outputs = {"sum_result": result_sum, "message": "Calculation successful"}

    json.dump(outputs, sys.stdout)

except Exception as e:
    # For testing error propagation, script should indicate error clearly
    # NodeExecutor's current _execute_python_script catches stderr and non-zero exit codes.
    # Printing to stderr is a good way to signal error details.
    sys.stderr.write(f"Script error: {{'error': str(e), 'script_failed': True}}\\n")
    sys.exit(1) # Signal failure with non-zero exit code
"""
    # Script needs to be in a directory NodeExecutor can find it.
    # NodeExecutor._execute_python_script tries various paths.
    # For testing, we'll ensure it's discoverable by placing it in tmp_path directly
    # and mocking the KG to return its absolute path.
    script_file_path = tmp_path / "simple_script.py"
    script_file_path.write_text(script_content)
    # Make it executable
    os.chmod(script_file_path, 0o755)


    node_uri_str = "ex:TestScriptNode_001" # String form for queries
    node_uri = EX_NS["TestScriptNode_001"] # URIRef form for graph operations

    input_param_a_uri = EX_NS["inputParamA"]
    input_param_a_name = Literal("param_a")
    input_param_a_maps_to = EX_NS["hasInputA"]

    input_param_b_uri = EX_NS["inputParamB"]
    input_param_b_name = Literal("param_b")
    input_param_b_maps_to = EX_NS["hasInputB"]

    output_param_sum_uri = EX_NS["outputParamSum"]
    output_param_sum_name = Literal("sum_result")
    output_param_sum_maps_to = EX_NS["hasSum"]

    # 2. Configure mock_knowledge_layer_for_node_exec
    mock_knowledge_layer_for_node_exec.execute_sparql_query.side_effect = [
        # Call 1: _get_node_implementation_details (script path and type)
        [{
            'type': KCE_NS.PythonScriptInvocation,
            'scriptPath': Literal(str(script_file_path.resolve()))
        }],
        # Call 2: _prepare_node_inputs (get input param definitions)
        [
            {'paramName': input_param_a_name, 'rdfProp': input_param_a_maps_to, 'datatype': XSD.integer},
            {'paramName': input_param_b_name, 'rdfProp': input_param_b_maps_to, 'datatype': XSD.integer}
        ],
        # Call 3: _convert_outputs_to_rdf (get output param definitions)
        [{
            'paramName': output_param_sum_name,
            'rdfProp': output_param_sum_maps_to,
            'datatype': XSD.integer,
            'nodeContextUri': node_uri # Simulate this being bound, or NodeExecutor defaults to node_uri
        }]
    ]

    # 3. Input data for the Node (as an RDFGraph)
    # This graph will be queried by _prepare_node_inputs
    input_rdf_graph = Graph()
    input_entity_uri = EX_NS["inputEntity"] # An example entity holding the input values
    input_rdf_graph.add((input_entity_uri, input_param_a_maps_to, Literal(10, datatype=XSD.integer)))
    input_rdf_graph.add((input_entity_uri, input_param_b_maps_to, Literal(5, datatype=XSD.integer)))

    # 4. Call node_executor.execute_node
    run_id = "test_run_script_node_001"

    # NodeExecutor.execute_node signature is (self, node_uri, run_id, knowledge_layer, current_input_graph)
    output_graph = node_executor.execute_node(
        node_uri=node_uri_str, # Passed as string
        run_id=run_id,
        knowledge_layer=mock_knowledge_layer_for_node_exec,
        current_input_graph=input_rdf_graph
    )

    # 5. Verify Outcome
    assert isinstance(output_graph, Graph)

    expected_sum = 10 + 5
    # Check for the output triple in the output_graph
    # _convert_outputs_to_rdf uses node_uri as subject for output triples by default if not specified otherwise
    # The mock for output param defs includes 'nodeContextUri': node_uri
    assert (node_uri, output_param_sum_maps_to, Literal(expected_sum, datatype=XSD.integer)) in output_graph, \
           f"Output graph does not contain expected sum. Graph: {list(output_graph.triples((None,None,None)))}"

    # Verify mock calls
    expected_script_path_query = f"""
        PREFIX kce: <{KCE_NS}>
        SELECT ?type ?scriptPath
        WHERE {{
            <{node_uri_str}> kce:hasImplementationDetail ?impl .
            ?impl kce:invocationType ?type .
            OPTIONAL {{ ?impl kce:scriptPath ?scriptPath . }}
        }}
        LIMIT 1
        """
    expected_input_params_query = f"""
        PREFIX kce: <{KCE_NS}>
        PREFIX rdfs: <{RDFS}>
        SELECT ?paramName ?rdfProp ?datatype
        WHERE {{
            <{node_uri_str}> kce:hasInputParameter ?param .
            ?param rdfs:label ?paramName .
            ?param kce:mapsToRdfProperty ?rdfProp .
            OPTIONAL {{ ?param kce:hasDatatype ?datatype . }}
        }}
        """
    expected_output_params_query = f"""
        PREFIX kce: <{KCE_NS}>
        PREFIX rdfs: <{RDFS}>
        SELECT ?paramName ?rdfProp ?datatype ?nodeContextUri
        WHERE {{
            <{node_uri_str}> kce:hasOutputParameter ?param .
            ?param rdfs:label ?paramName .
            ?param kce:mapsToRdfProperty ?rdfProp .
            OPTIONAL {{ ?param kce:hasDatatype ?datatype . }}
            # The subject for output triples needs robust definition.
            # Using node_uri as a placeholder if no specific context is defined.
            BIND(IRI(COALESCE(STR(?param_nodeContextUri), STR(<{node_uri_str}>))) AS ?nodeContextUri) # TODO: Define ?param_nodeContextUri properly
        }}
        """

    # Check calls to execute_sparql_query
    calls = mock_knowledge_layer_for_node_exec.execute_sparql_query.call_args_list
    assert len(calls) == 3
    # Comparing multiline SPARQL queries can be tricky due to whitespace.
    # A robust way is to parse them or compare canonical forms, but for mocks, direct string compare is often used.
    # We'll check for key parts of the query.
    assert "kce:hasImplementationDetail" in str(calls[0].args[0])
    assert "kce:hasInputParameter" in str(calls[1].args[0])
    assert "kce:hasOutputParameter" in str(calls[2].args[0])

    # Note: RuntimeStateLogger is not passed to execute_node, so cannot directly test calls on mock_runtime_logger_for_node_exec via this method.
    # If NodeExecutor used a self.logger initialized in __init__, then we could test that.
    # The current NodeExecutor.py does not show logger usage in execute_node path.
    # The test specification included mock_runtime_logger_for_node_exec in call, which was incorrect.
    # If NodeExecutor had its own logger attribute initialized from constructor, this would be different.
    # For now, no logger assertions related to execute_node as it doesn't take one.
