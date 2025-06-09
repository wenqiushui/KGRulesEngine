import rdflib
import subprocess
import json
import os
import tempfile
from typing import Dict, Any, List, Union # Added List, Union for type hints

# Assuming interfaces.py is two levels up
from ..interfaces import INodeExecutor, IKnowledgeLayer, RDFGraph
# Assuming common.utils will be created. For now, define placeholders if not present.
try:
    from ..common.utils import get_value_from_graph, create_rdf_graph_from_json_ld_dict
except ImportError:
    print("Warning: common.utils not found. Using placeholder functions for NodeExecutor.")
    # Placeholder implementations for utils if not found (e.g. during isolated testing)
    def get_value_from_graph(graph: RDFGraph, subject: Any, predicate: Any) -> Any:
        # Simplified placeholder
        for s, p, o_literal in graph.triples((subject, predicate, None)):
            return o_literal # Returns rdflib.Literal or URIRef
        return None

    def create_rdf_graph_from_json_ld_dict(data: Dict[str, Any], base_ns: rdflib.Namespace) -> RDFGraph:
        # Simplified placeholder
        g = rdflib.Graph()
        # This would require a proper JSON-LD parsing logic
        print(f"Placeholder: Would convert JSON-LD dict to graph. Data: {data}")
        return g


# Define KCE namespace (ideally from a central place)
KCE = rdflib.Namespace("http://kce.com/ontology/core#")
EX = rdflib.Namespace("http://example.com/ns#")


class NodeExecutor(INodeExecutor):
    def __init__(self, knowledge_layer: IKnowledgeLayer):
        self.knowledge_layer = knowledge_layer

    def _get_node_implementation_details(self, node_uri: str, knowledge_layer: IKnowledgeLayer) -> Dict[str, Any]:
        '''Retrieve node implementation details (e.g., script path, invocation type) from the KnowledgeLayer.'''
        query = f"""
        PREFIX kce: <{KCE}>
        SELECT ?type ?scriptPath
        WHERE {{
            <{node_uri}> kce:hasImplementationDetail ?impl .
            ?impl kce:invocationType ?type .
            OPTIONAL {{ ?impl kce:scriptPath ?scriptPath . }}
        }}
        LIMIT 1
        """
        results = knowledge_layer.execute_sparql_query(query)
        if isinstance(results, list) and results:
            return results[0] # Returns a dict like {'type': URIRef(...), 'scriptPath': Literal(...)}
        raise ValueError(f"Node implementation details not found for {node_uri}")

    def _prepare_node_inputs(self, node_uri: str, knowledge_layer: IKnowledgeLayer, current_input_graph: RDFGraph) -> Dict[str, Any]:
        '''
        Prepares a dictionary of inputs for the node based on its input parameter definitions
        and the current state of the knowledge graph (current_input_graph).
        '''
        inputs = {}
        input_params_query = f"""
        PREFIX kce: <{KCE}>
        PREFIX rdfs: <{rdflib.RDFS}>
        SELECT ?paramName ?rdfProp ?datatype
        WHERE {{
            <{node_uri}> kce:hasInputParameter ?param .
            ?param rdfs:label ?paramName .
            ?param kce:mapsToRdfProperty ?rdfProp .
            OPTIONAL {{ ?param kce:hasDatatype ?datatype . }}
        }}
        """
        param_defs = knowledge_layer.execute_sparql_query(input_params_query)
        if isinstance(param_defs, list):
            for p_def in param_defs:
                param_name = str(p_def['paramName']) # Literal to string
                rdf_prop_uri = p_def['rdfProp']    # URIRef

                # Find a subject in current_input_graph that has this rdf_prop_uri
                # This assumes current_input_graph contains entities that are inputs to the node.
                # A more robust way might involve knowing the target entity URI for this node execution.
                value_found = False
                for s, p, o in current_input_graph.triples((None, rdf_prop_uri, None)):
                    # Convert rdflib Literal/URIRef to Python native type for the script
                    if isinstance(o, rdflib.Literal):
                        inputs[param_name] = o.toPython()
                    else: # URIRef
                        inputs[param_name] = str(o)
                    value_found = True
                    break # Take first one found for this property

                if not value_found:
                    print(f"Warning: Input for parameter '{param_name}' (property <{rdf_prop_uri}>) "
                          f"for node <{node_uri}> not found in current_input_graph.")
        return inputs


    def _execute_python_script(self, script_path: str, inputs: Dict[str, Any], node_uri: str) -> Dict[str, Any]:
        '''Executes a Python script, passing inputs as JSON via stdin or temp file,
           and captures its JSON output from stdout.'''

        potential_paths = [
            script_path, # Absolute or relative to CWD
            os.path.join("examples", script_path),
            # Path relative to this node_executor.py file: kce_core/execution_layer/node_executor.py
            # So, to get to repo root, it's three levels up.
            os.path.join(os.path.dirname(__file__), "..", "..", script_path)
        ]

        actual_script_path = None
        for p_path in potential_paths:
            abs_path = os.path.abspath(p_path)
            if os.path.exists(abs_path) and os.path.isfile(abs_path):
                actual_script_path = abs_path
                break

        if not actual_script_path:
            checked_paths_str = ", ".join([os.path.abspath(p) for p in potential_paths])
            raise FileNotFoundError(f"Script not found for node <{node_uri}>. Original path: '{script_path}'. Checked absolute paths: [{checked_paths_str}]")

        input_json_str = json.dumps(inputs)
        stdout_val, stderr_val = "", "" # Ensure these are defined for the final exception message

        try:
            process = subprocess.Popen(
                ['python', actual_script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(actual_script_path) # Execute script in its own directory
            )
            stdout_val, stderr_val = process.communicate(input=input_json_str, timeout=30) # Added timeout

            if process.returncode != 0:
                error_message = f"Script {actual_script_path} for node <{node_uri}> failed with exit code {process.returncode}. Stderr: {stderr_val}"
                print(error_message)
                raise RuntimeError(error_message)

            return json.loads(stdout_val)
        except FileNotFoundError: # Should be caught by the check above, but as a safeguard
            raise
        except subprocess.TimeoutExpired:
            error_message = f"Script {actual_script_path} for node <{node_uri}> timed out. Stderr: {stderr_val}"
            print(error_message)
            process.kill() # Ensure process is killed
            raise RuntimeError(error_message) from None
        except json.JSONDecodeError as e:
            error_message = f"Failed to decode JSON output from script {actual_script_path} for node <{node_uri}>. Output: {stdout_val}. Error: {e}"
            print(error_message)
            raise RuntimeError(error_message) from e
        except Exception as e: # Catch other potential errors like permission issues
            error_message = f"Error executing script {actual_script_path} for node <{node_uri}>: {e}. Stderr: {stderr_val}"
            print(error_message)
            raise RuntimeError(error_message) from e


    def _convert_outputs_to_rdf(self, node_uri: str, outputs: Dict[str, Any], knowledge_layer: IKnowledgeLayer) -> RDFGraph:
        '''
        Converts the Python dictionary output from a script to an RDF graph
        based on the node's kce:OutputParameter definitions.
        '''
        output_graph = rdflib.Graph()

        output_params_query = f"""
        PREFIX kce: <{KCE}>
        PREFIX rdfs: <{rdflib.RDFS}>
        SELECT ?paramName ?rdfProp ?datatype ?nodeContextUri
        WHERE {{
            <{node_uri}> kce:hasOutputParameter ?param .
            ?param rdfs:label ?paramName .
            ?param kce:mapsToRdfProperty ?rdfProp .
            OPTIONAL {{ ?param kce:hasDatatype ?datatype . }}
            # The subject for output triples needs robust definition.
            # Using node_uri as a placeholder if no specific context is defined.
            BIND(IRI(COALESCE(STR(?param_nodeContextUri), STR(<{node_uri}>))) AS ?nodeContextUri) # TODO: Define ?param_nodeContextUri properly
        }}
        """
        param_defs = knowledge_layer.execute_sparql_query(output_params_query)

        if isinstance(param_defs, list):
            for p_def in param_defs:
                param_name = str(p_def['paramName'])
                rdf_prop_uri = p_def['rdfProp'] # URIRef
                subject_uri = p_def['nodeContextUri'] # URIRef, defaults to node_uri

                if param_name in outputs:
                    value = outputs[param_name]
                    # TODO: Handle datatypes from p_def['datatype'] (e.g. XSD.integer, XSD.string)
                    # For now, all are Literals. If value is a URI string, convert to URIRef.
                    if isinstance(value, str) and (value.startswith("http://") or value.startswith("urn:")) :
                         output_graph.add((subject_uri, rdf_prop_uri, rdflib.URIRef(value)))
                    else:
                         output_graph.add((subject_uri, rdf_prop_uri, rdflib.Literal(value)))
                else:
                    print(f"Warning: Output parameter '{param_name}' defined for node <{node_uri}> but not found in script output: {outputs.keys()}")

        return output_graph


    def execute_node(self, node_uri: str, run_id: str, knowledge_layer: IKnowledgeLayer, current_input_graph: RDFGraph) -> RDFGraph:
        print(f"Executing node <{node_uri}> for run_id: {run_id}")

        impl_details = self._get_node_implementation_details(node_uri, knowledge_layer)

        # Ensure type is URIRef for comparison
        invocation_type = impl_details.get('type')
        if not isinstance(invocation_type, rdflib.URIRef):
            invocation_type = rdflib.URIRef(str(invocation_type)) # Convert if it's a Literal from mock or bad data

        if invocation_type != KCE.PythonScriptInvocation:
            raise NotImplementedError(f"Node invocation type {invocation_type} not supported yet for <{node_uri}>.")

        script_path_literal = impl_details.get('scriptPath')
        if not script_path_literal:
            raise ValueError(f"Script path not defined for Python node <{node_uri}>.")
        script_path = str(script_path_literal)

        inputs = self._prepare_node_inputs(node_uri, knowledge_layer, current_input_graph)
        print(f"Node <{node_uri}> inputs: {inputs}")

        script_outputs = self._execute_python_script(script_path, inputs, node_uri)
        print(f"Node <{node_uri}> script outputs: {script_outputs}")

        output_rdf_graph = self._convert_outputs_to_rdf(node_uri, script_outputs, knowledge_layer)
        print(f"Node <{node_uri}> generated {len(output_rdf_graph)} output triples.")
        return output_rdf_graph

if __name__ == '__main__':
    # Mock IKnowledgeLayer for testing
    class MockKnowledgeLayer(IKnowledgeLayer):
        def __init__(self):
            self.graph = rdflib.Graph()
            self.node_uri_str = "http://example.com/ns/TestScriptNode" # Full URI string
            self.node_uri = EX.TestScriptNode # URIRef
            self.script_rel_path = "dummy_script_for_node_executor.py"

            self.graph.add((self.node_uri, KCE.hasImplementationDetail, EX.TestScriptNodeImpl))
            self.graph.add((EX.TestScriptNodeImpl, KCE.invocationType, KCE.PythonScriptInvocation))
            self.graph.add((EX.TestScriptNodeImpl, KCE.scriptPath, rdflib.Literal(self.script_rel_path)))

            self.graph.add((self.node_uri, KCE.hasInputParameter, EX.InputP1))
            self.graph.add((EX.InputP1, rdflib.RDFS.label, rdflib.Literal("message")))
            self.graph.add((EX.InputP1, KCE.mapsToRdfProperty, EX.hasMessage))

            self.graph.add((self.node_uri, KCE.hasOutputParameter, EX.OutputP1))
            self.graph.add((EX.OutputP1, rdflib.RDFS.label, rdflib.Literal("response")))
            self.graph.add((EX.OutputP1, KCE.mapsToRdfProperty, EX.hasResponse))
            # For _convert_outputs_to_rdf, the ?nodeContextUri needs to be bound.
            # Let's assume for this test the output is a property of the node itself.
            # The query in _convert_outputs_to_rdf has a COALESCE to default to node_uri.

        def execute_sparql_query(self, query: str) -> Union[List[Dict[str, Any]], bool, RDFGraph]:
            # This mock is very basic. It should ideally parse the SPARQL and return results from self.graph
            # For now, it's hardcoded for specific queries made by NodeExecutor.
            if "kce:hasImplementationDetail" in query and self.node_uri_str in query:
                return [{'type': KCE.PythonScriptInvocation, 'scriptPath': rdflib.Literal(self.script_rel_path)}]
            if "kce:hasInputParameter" in query and self.node_uri_str in query:
                return [{'paramName': rdflib.Literal("message"), 'rdfProp': EX.hasMessage, 'datatype': None}]
            if "kce:hasOutputParameter" in query and self.node_uri_str in query:
                 return [{'paramName': rdflib.Literal("response"), 'rdfProp': EX.hasResponse, 'datatype': None, 'nodeContextUri': self.node_uri}]
            print(f"MockKL: Unhandled SPARQL Query: {query}")
            return []

        def execute_sparql_update(self, update_statement): pass
        def trigger_reasoning(self): pass
        def add_graph(self, graph_to_add, context_uri=None): self.graph += graph_to_add
        def get_graph(self, context_uri=None): return self.graph
        def store_human_readable_log(self, run_id, event_id, log_content): return ""
        def get_human_readable_log(self, log_location): return None

    dummy_script_content = """
import json, sys
try:
    input_data = json.load(sys.stdin)
    msg = input_data.get("message", "No message provided")
    response_message = f"Script processed: {msg}"
    output_data = {"response": response_message, "status_code": 200}
    json.dump(output_data, sys.stdout)
except Exception as e:
    sys.stderr.write(f"Script error: {e}\\n")
    sys.exit(1)
"""
    # Script path needs to be findable by _execute_python_script
    # It tries CWD, examples/, and relative to node_executor.py
    # For testing, placing it in CWD is simplest.
    script_file_name = "dummy_script_for_node_executor.py"
    with open(script_file_name, "w") as f:
        f.write(dummy_script_content)

    mock_kl_instance = MockKnowledgeLayer()
    executor = NodeExecutor()

    test_input_graph = rdflib.Graph()
    test_input_graph.add((EX.SomeInputEntity, EX.hasMessage, rdflib.Literal("Hello Node Executor")))

    try:
        print(f"--- Testing NodeExecutor with node <{mock_kl_instance.node_uri_str}> and script '{script_file_name}' ---")
        output_graph = executor.execute_node(
            node_uri=mock_kl_instance.node_uri_str, # Pass as string
            run_id="test_run_ne_001",
            knowledge_layer=mock_kl_instance,
            current_input_graph=test_input_graph
        )
        print(f"--- Execution successful. Output graph ({len(output_graph)} triples): ---")
        # print(output_graph.serialize(format="turtle")) # Requires rdflib to be fully available

        # Basic verification
        expected_subject = mock_kl_instance.node_uri
        expected_predicate = EX.hasResponse
        expected_object_literal_part = "Script processed: Hello Node Executor"

        found_triple = False
        for s, p, o in output_graph:
            if s == expected_subject and p == expected_predicate and expected_object_literal_part in str(o):
                found_triple = True
                break
        assert found_triple, f"Expected triple ({expected_subject}, {expected_predicate}, '{expected_object_literal_part}...') not found in output graph."
        print("--- Output triple verified. ---")

    except Exception as e:
        print(f"--- NodeExecutor test failed: {e} ---")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(script_file_name):
            os.remove(script_file_name)
        print("--- NodeExecutor test complete. ---")
