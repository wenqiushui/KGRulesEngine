# kce_core/execution/node_executor.py

import logging
import subprocess
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union, List, Tuple

from rdflib import URIRef, Literal, BNode # Removed RDFNode from here
from rdflib.term import Node as RDFNode # Correct way to import the base Node class for type hinting

from kce_core.common.utils import (
    kce_logger,
    ExecutionError,
    DefinitionError,
    to_uriref,
    to_literal,
    get_xsd_uriref,
    KCE, RDF, RDFS, XSD, EX, # Namespaces
    resolve_path
)
from kce_core.rdf_store.store_manager import StoreManager
from kce_core.provenance.logger import ProvenanceLogger
from kce_core.rdf_store import sparql_queries # For querying node definitions


class NodeExecutor:
    """
    Executes kce:AtomicNode instances, particularly those involving Python scripts.
    Handles input/output parameter mapping and script invocation.
    """

    def __init__(self, store_manager: StoreManager, provenance_logger: ProvenanceLogger):
        """
        Initializes the NodeExecutor.

        Args:
            store_manager: An instance of StoreManager.
            provenance_logger: An instance of ProvenanceLogger.
        """
        self.store = store_manager
        self.prov_logger = provenance_logger
        kce_logger.info("NodeExecutor initialized.")

    def execute_node(self, node_uri: URIRef,
                     run_id_uri: URIRef,
                     workflow_instance_context: Optional[URIRef] = None) -> bool:
        """
        Executes a given kce:AtomicNode.

        Args:
            node_uri: The URI of the kce:AtomicNode to execute.
            run_id_uri: The URI of the current kce:ExecutionLog (workflow run).
            workflow_instance_context: (Optional) A URI representing the current specific
                                       context or instance within the workflow.

        Returns:
            True if execution was successful, False otherwise.
        """
        node_label = self._get_node_label(node_uri)
        node_exec_uri = self.prov_logger.start_node_execution(run_id_uri, node_uri, node_label)
        
        inputs_used_for_prov: Dict[str, URIRef] = {}
        outputs_generated_for_prov: Dict[str, URIRef] = {}

        try:
            node_def_query = sparql_queries.format_query(
                sparql_queries.GET_NODE_DEFINITION,
                node_uri=str(node_uri)
            )
            node_def_results = self.store.query(node_def_query)
            if not node_def_results:
                raise DefinitionError(f"Node definition not found for URI: {node_uri}")
            node_details = node_def_results[0]

            invocation_spec_uri = node_details.get('invocation_spec_uri')
            if not invocation_spec_uri:
                raise DefinitionError(f"Node {node_uri} is not an AtomicNode or is missing invocation_spec_uri.")

            invocation_spec_query = sparql_queries.format_query(
                sparql_queries.GET_PYTHON_SCRIPT_INVOCATION_SPEC,
                invocation_spec_uri=str(invocation_spec_uri)
            )
            invocation_spec_results = self.store.query(invocation_spec_query)
            if not invocation_spec_results:
                raise DefinitionError(f"PythonScriptInvocation specification not found for URI: {invocation_spec_uri}")
            invocation_details = invocation_spec_results[0]

            script_path_str = str(invocation_details.get('script_path'))
            if not script_path_str:
                raise DefinitionError(f"Script path not defined for invocation spec: {invocation_spec_uri}")
            
            script_path = Path(script_path_str)
            if not script_path.is_file():
                raise ExecutionError(f"Python script not found at resolved path: {script_path} (defined for {node_uri})")

            # arg_passing_style = str(invocation_details.get('arg_passing_style', 'commandline')) # Currently unused in execution logic below

            input_params_defs = self._get_node_parameters(node_uri, KCE.hasInputParameter)
            script_args, inputs_used_for_prov = self._prepare_script_inputs(
                input_params_defs,
                workflow_instance_context
            )

            kce_logger.info(f"Executing script for node {node_uri} ({node_label}): {script_path} with args: {script_args}")
            
            cmd = ["python", str(script_path)] + [str(arg_val) for arg_val in script_args.values()]

            process = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if process.returncode != 0:
                error_msg = f"Script {script_path} failed with exit code {process.returncode}.\nStderr: {process.stderr.strip()}"
                kce_logger.error(error_msg)
                raise ExecutionError(error_msg)
            
            stdout_data = process.stdout.strip()
            kce_logger.debug(f"Script {script_path} stdout:\n{stdout_data}")

            try:
                script_outputs = json.loads(stdout_data) if stdout_data else {}
                if not isinstance(script_outputs, dict):
                    kce_logger.warning(f"Script {script_path} output was not a JSON object. Received: {type(script_outputs)}")
                    script_outputs = {} 
            except json.JSONDecodeError:
                kce_logger.warning(f"Script {script_path} output was not valid JSON. Stdout: {stdout_data}")
                script_outputs = {"raw_stdout": stdout_data}

            output_params_defs = self._get_node_parameters(node_uri, KCE.hasOutputParameter)
            outputs_generated_for_prov = self._process_script_outputs(
                output_params_defs,
                script_outputs,
                workflow_instance_context,
                node_exec_uri
            )

            self.prov_logger.end_node_execution(
                node_exec_uri, "CompletedSuccess",
                inputs_used=inputs_used_for_prov,
                outputs_generated=outputs_generated_for_prov
            )
            kce_logger.info(f"Node {node_uri} ({node_label}) executed successfully.")
            return True

        except DefinitionError as e:
            err_msg = f"Definition error during execution of node {node_uri} ({node_label}): {e}"
            kce_logger.error(err_msg)
            self.prov_logger.end_node_execution(node_exec_uri, "Failed", error_message=err_msg)
            return False
        except ExecutionError as e:
            err_msg = f"Execution error for node {node_uri} ({node_label}): {e}"
            kce_logger.error(err_msg)
            self.prov_logger.end_node_execution(node_exec_uri, "Failed", error_message=err_msg)
            return False
        except Exception as e: 
            err_msg = f"Unexpected error during execution of node {node_uri} ({node_label}): {e}"
            kce_logger.exception(err_msg)
            self.prov_logger.end_node_execution(node_exec_uri, "Failed", error_message=err_msg)
            return False

    def _get_node_label(self, node_uri: URIRef) -> str:
        label_val = self.store.get_single_property_value(node_uri, RDFS.label)
        return str(label_val) if label_val else node_uri.split('/')[-1].split('#')[-1]


    def _get_node_parameters(self, node_uri: URIRef, param_direction_prop: URIRef) -> List[Dict[str, Any]]:
        query_str = sparql_queries.format_query(
            sparql_queries.GET_NODE_PARAMETERS,
            node_uri=str(node_uri),
            param_direction_prop=str(param_direction_prop)
        )
        param_results = self.store.query(query_str)
        
        params_list = []
        for row in param_results:
            params_list.append({
                "uri": row['param_uri'],
                "name": str(row['param_name']),
                "maps_to_rdf_property": row['maps_to_rdf_prop'],
                "data_type": row.get('data_type'),
                "is_required": bool(row['is_required'].value) if 'is_required' in row and row['is_required'] is not None else False
            })
        return params_list

    def _prepare_script_inputs(self,
                               input_params_defs: List[Dict[str, Any]],
                               context_uri: Optional[URIRef]) -> Tuple[Dict[str, Any], Dict[str, URIRef]]:
        script_args: Dict[str, Any] = {}
        inputs_used_for_prov: Dict[str, URIRef] = {}

        if not context_uri and any(param['maps_to_rdf_property'] for param in input_params_defs):
            kce_logger.warning("Preparing script inputs that map to RDF properties, but no context_uri provided.")

        for param_def in input_params_defs:
            param_name = param_def['name']
            rdf_prop_uri = param_def['maps_to_rdf_property']
            is_required = param_def['is_required']
            
            value_node: Optional[RDFNode] = None
            if context_uri:
                value_node = self.store.get_single_property_value(context_uri, rdf_prop_uri)
            else:
                  kce_logger.debug(f"No context URI for input '{param_name}', cannot fetch from RDF property '{rdf_prop_uri}'.")

            if value_node is None:
                if is_required:
                    raise ExecutionError(f"Required input parameter '{param_name}' (property <{rdf_prop_uri}>) "
                                         f"not found for context <{context_uri}>.")
                else:
                    kce_logger.debug(f"Optional input parameter '{param_name}' not found, skipping.")
                    script_args[param_name] = None 
                    continue

            if isinstance(value_node, Literal):
                script_args[param_name] = value_node.value 
            elif isinstance(value_node, URIRef):
                script_args[param_name] = str(value_node)
                inputs_used_for_prov[param_name] = value_node
            else: 
                script_args[param_name] = str(value_node)

            kce_logger.debug(f"Prepared input '{param_name}': {script_args.get(param_name)}")
        return script_args, inputs_used_for_prov


    def _process_script_outputs(self,
                                output_params_defs: List[Dict[str, Any]],
                                script_outputs: Dict[str, Any],
                                context_uri: Optional[URIRef],
                                node_exec_uri: URIRef
                                ) -> Dict[str, URIRef]:
        outputs_generated_for_prov: Dict[str, URIRef] = {}
        triples_to_add: List[Tuple[URIRef, URIRef, RDFNode]] = []

        if not context_uri and any(param['maps_to_rdf_property'] for param in output_params_defs):
            kce_logger.warning("Processing script outputs that map to RDF properties, but no context_uri provided.")

        # --- Start: Enhanced output processing for _rdf_instructions ---
        if "_rdf_instructions" in script_outputs and isinstance(script_outputs["_rdf_instructions"], dict):
            instructions = script_outputs["_rdf_instructions"]
            kce_logger.debug(f"Processing _rdf_instructions: {instructions}")

            # 1. Create new entities
            for entity_to_create in instructions.get("create_entities", []):
                uri_str = entity_to_create.get("uri")
                type_str = entity_to_create.get("type")
                props_to_set = entity_to_create.get("properties", {})
                if uri_str and type_str:
                    entity_uri = to_uriref(uri_str) # Allow prefixed names from script output
                    entity_type_uri = to_uriref(type_str)
                    triples_to_add.append((entity_uri, RDF.type, entity_type_uri))
                    for prop_str, val in props_to_set.items():
                        prop_uri = to_uriref(prop_str)
                        triples_to_add.append((entity_uri, prop_uri, to_literal(val)))
                    outputs_generated_for_prov[uri_str] = entity_uri # Track created entity

            # 2. Update existing entities (can also be used by scripts that modify multiple entities)
            for entity_to_update in instructions.get("update_entities", []):
                uri_str = entity_to_update.get("uri")
                props_to_set = entity_to_update.get("properties_to_set", {})
                if uri_str:
                    entity_uri = to_uriref(uri_str)
                    for prop_str, val in props_to_set.items():
                        prop_uri = to_uriref(prop_str)
                        # Simple update: remove old, add new. More robust: check cardinality.
                        # For MVP, let's assume we might want to remove existing single values first
                        # This requires a StoreManager method or direct SPARQL UPDATE.
                        # For now, just add. If property is multi-valued, this is fine.
                        # If single-valued, it might lead to multiple values.
                        # A pre-emptive DELETE could be:
                        # self.store.update(f"DELETE WHERE {{ <{entity_uri}> <{prop_uri}> ?any . }}")
                        triples_to_add.append((entity_uri, prop_uri, to_literal(val)))
                    # outputs_generated_for_prov[uri_str] = entity_uri # If updates are considered "generation"

            # 3. Add new links
            for link_to_add in instructions.get("add_links", []):
                s_str = link_to_add.get("subject")
                p_str = link_to_add.get("predicate")
                o_str = link_to_add.get("object") # Assuming object is also a URI string
                if s_str and p_str and o_str:
                    s_uri = to_uriref(s_str)
                    p_uri = to_uriref(p_str)
                    o_uri = to_uriref(o_str) # Assuming object of link is a resource
                    triples_to_add.append((s_uri, p_uri, o_uri))
            
            if triples_to_add:
                self.store.add_triples(iter(triples_to_add), perform_reasoning=False)
                kce_logger.debug(f"Applied {len(triples_to_add)} RDF updates from _rdf_instructions.")
            
            # After processing _rdf_instructions, decide if we also process standard output params.
            # For now, let's assume if _rdf_instructions exists, it's the primary way of updating.
            # Or, standard output params could still be processed if they target the main context_uri.
            # Let's process standard outputs targeting context_uri as well, for flexibility.
        # --- End: Enhanced output processing ---


        for param_def in output_params_defs:
            param_name = param_def['name']
            # Skip if this param_name was just a way to pass "_rdf_instructions"
            if param_name == "_rdf_instructions": # Or if we map a specific output param to it
                continue

            rdf_prop_uri = param_def['maps_to_rdf_property']
            param_data_type_uri = param_def.get('data_type')

            if param_name not in script_outputs:
                kce_logger.debug(f"Output parameter '{param_name}' defined for node but not found in script output (or already handled by _rdf_instructions).")
                continue

            output_value = script_outputs[param_name]
            
            rdf_output_value: RDFNode
            if isinstance(output_value, URIRef):
                rdf_output_value = output_value
                outputs_generated_for_prov[param_name] = output_value
            elif isinstance(output_value, str) and (output_value.startswith("http://") or output_value.startswith("https://") or ":" in output_value):
                try:
                    rdf_output_value = to_uriref(output_value)
                    outputs_generated_for_prov[param_name] = rdf_output_value
                except ValueError: 
                    rdf_output_value = to_literal(output_value, datatype=param_data_type_uri)
            else:
                rdf_output_value = to_literal(output_value, datatype=param_data_type_uri)

            if context_uri: # Standard outputs are typically applied to the main context_uri
                # For MVP, just add. If property should be single-valued, previous values need deletion.
                self.store.add_triple(context_uri, rdf_prop_uri, rdf_output_value, perform_reasoning=False)
                kce_logger.debug(f"Storing standard output '{param_name}' ({rdf_output_value}) "
                                 f"to <{context_uri}> <{rdf_prop_uri}>.")
            else:
                kce_logger.warning(f"No context_uri to store standard output '{param_name}' ({rdf_output_value}) for property <{rdf_prop_uri}>.")

        return outputs_generated_for_prov


if __name__ == '__main__':
    # --- Example Usage and Basic Test (remains largely the same as previous version) ---
    kce_logger.setLevel(logging.DEBUG)

    class MockStoreManager:
        def __init__(self):
            self.graph_data: Dict[Tuple[str, str], List[RDFNode]] = {}
            self.query_results_map: Dict[str, List[Dict[str, RDFNode]]] = {}
            self.added_triples_log: List[Tuple[RDFNode, RDFNode, RDFNode]] = []
            kce_logger.info("MockStoreManager for NodeExecutor test initialized.")

        def _get_key(self, s, p): return (str(s), str(p))

        def add_triples(self, triples_iter, perform_reasoning=True):
            for s, p, o in triples_iter:
                self.added_triples_log.append((s, p, o)) # Log for verification
                key = self._get_key(s,p)
                if key not in self.graph_data: self.graph_data[key] = []
                # Avoid duplicates for simplicity in mock, real store handles this
                if o not in self.graph_data[key]:
                    self.graph_data[key].append(o)
            kce_logger.debug(f"MockStore: Added triples. Current graph state (simplified): {len(self.added_triples_log)} total logged adds.")
        
        def add_triple(self, s,p,o, perform_reasoning=True):
            self.add_triples(iter([(s,p,o)]), perform_reasoning)


        def query(self, sparql_query_str):
            kce_logger.debug(f"MockStore: Received query:\n{sparql_query_str[:200]}...")
            for q_key, results in self.query_results_map.items():
                if q_key in sparql_query_str:
                    kce_logger.debug(f"MockStore: Matched query key '{q_key}', returning {len(results)} results.")
                    return results
            kce_logger.warning(f"MockStore: No mock result found for query containing parts of:\n{sparql_query_str}")
            return []

        def get_single_property_value(self, subject_uri, property_uri, default=None):
            key = self._get_key(subject_uri, property_uri)
            values = self.graph_data.get(key)
            if values: return values[0]
            return default
        
        def get_property_values(self, subject_uri, property_uri):
            key = self._get_key(subject_uri, property_uri)
            return self.graph_data.get(key, [])


    class MockProvenanceLogger:
        def __init__(self):
            self.starts = 0
            self.ends = 0
            self.last_node_exec_uri = None
            self.last_status = None
            self.last_error = None
            self.last_inputs_used = None
            self.last_outputs_generated = None
            kce_logger.info("MockProvenanceLogger for NodeExecutor test initialized.")

        def start_node_execution(self, run_id_uri, node_uri, node_label=None):
            self.starts += 1
            self.last_node_exec_uri = to_uriref(f"urn:mock-node-exec:{self.starts}")
            kce_logger.debug(f"MockProv: Started node exec {self.last_node_exec_uri} for {node_uri}")
            return self.last_node_exec_uri

        def end_node_execution(self, node_exec_uri, status, inputs_used=None, outputs_generated=None, error_message=None):
            self.ends += 1
            self.last_status = status
            self.last_error = error_message
            self.last_inputs_used = inputs_used
            self.last_outputs_generated = outputs_generated
            kce_logger.debug(f"MockProv: Ended node exec {node_exec_uri} with status {status}")

    mock_store = MockStoreManager()
    mock_prov = MockProvenanceLogger()
    node_executor = NodeExecutor(mock_store, mock_prov)

    test_node_uri = KCE.TestNodeScript
    test_run_id_uri = KCE["run/testrun123"]
    test_context_uri = EX.MyPanelInstance1 # This is where standard outputs go

    # Create a dummy Python script that outputs _rdf_instructions
    script_content_rdf_instructions = f"""
import sys
import json

if __name__ == "__main__":
    input_arg = sys.argv[1] if len(sys.argv) > 1 else "default_input"
    
    new_entity_uri = "{EX_NS}NewEntityFromScript_" + input_arg
    new_property_uri = "{EX_NS}hasScriptValue"
    
    output_data = {{
        "main_output_param_name": "some_value_for_context", # Standard output
        "_rdf_instructions": {{
            "create_entities": [
                {{
                    "uri": new_entity_uri,
                    "type": "{EX_NS}GeneratedType",
                    "properties": {{
                        "{EX_NS}scriptInputReceived": input_arg,
                        new_property_uri: "This is a new property value"
                    }}
                }}
            ],
            "update_entities": [
                {{
                    "uri": "{str(test_context_uri)}", # Update the main context URI
                    "properties_to_set": {{
                        "{EX_NS}updatedByScript": True
                    }}
                }}
            ],
            "add_links": [
                {{
                    "subject": "{str(test_context_uri)}",
                    "predicate": "{EX_NS}relatesToGenerated",
                    "object": new_entity_uri
                }}
            ]
        }}
    }}
    print(json.dumps(output_data))
    sys.exit(0)
"""
    test_script_instr_path = Path("temp_test_script_instr.py")
    with open(test_script_instr_path, "w") as f:
        f.write(script_content_rdf_instructions)

    # Mock RDF Data for Node Definition
    mock_store.query_results_map[str(test_node_uri)] = [
        {"label": Literal("Test Script Node"), "invocation_spec_uri": KCE.TestNodeScriptInvocation}
    ]
    mock_store.query_results_map[str(KCE.TestNodeScriptInvocation)] = [
        {"script_path": Literal(str(test_script_instr_path.resolve()))}
    ]
    # Input (optional, script uses default if not passed)
    mock_store.query_results_map[f"{str(test_node_uri)}_{str(KCE.hasInputParameter)}"] = [
         {
            "param_uri": KCE.TestNodeInputParam, "param_name": Literal("script_arg1"),
            "maps_to_rdf_property": EX.scriptInput, "data_type": XSD.string, "is_required": Literal(False)
        }
    ]
    # Output (standard output parameter)
    mock_store.query_results_map[f"{str(test_node_uri)}_{str(KCE.hasOutputParameter)}"] = [
        {
            "param_uri": KCE.TestNodeOutputParam, "param_name": Literal("main_output_param_name"),
            "maps_to_rdf_property": EX.scriptMainOutput, "data_type": XSD.string
        }
    ]
    mock_store.add_triple(test_context_uri, EX.scriptInput, Literal("test_param_val"))


    kce_logger.info("\n--- Testing Node Execution with _rdf_instructions ---")
    success = node_executor.execute_node(test_node_uri, test_run_id_uri, test_context_uri)
    assert success is True
    assert mock_prov.last_status == "CompletedSuccess"

    # Verify standard output was processed
    std_out_key = (str(test_context_uri), str(EX.scriptMainOutput))
    assert std_out_key in mock_store.graph_data
    assert mock_store.graph_data[std_out_key] == [Literal("some_value_for_context")]

    # Verify _rdf_instructions were processed by checking added_triples_log
    created_entity_uri_expected = EX_NS + "NewEntityFromScript_test_param_val"
    
    # Check for creation
    assert (to_uriref(created_entity_uri_expected), RDF.type, to_uriref(EX_NS + "GeneratedType")) in mock_store.added_triples_log
    assert (to_uriref(created_entity_uri_expected), to_uriref(EX_NS+"scriptInputReceived"), Literal("test_param_val")) in mock_store.added_triples_log

    # Check for update on context
    assert (test_context_uri, to_uriref(EX_NS+"updatedByScript"), Literal(True)) in mock_store.added_triples_log
    
    # Check for link
    assert (test_context_uri, to_uriref(EX_NS+"relatesToGenerated"), to_uriref(created_entity_uri_expected)) in mock_store.added_triples_log


    if test_script_instr_path.exists():
        test_script_instr_path.unlink()
    kce_logger.info("\nNodeExecutor _rdf_instructions test completed.")