import rdflib
import subprocess
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Union, Optional, Tuple
from rdflib import URIRef, Literal, Graph
from rdflib.namespace import RDF, RDFS, XSD # Ensure these are directly available if used

from ..interfaces import INodeExecutor, IKnowledgeLayer, RDFGraph

# Define KCE namespace (ideally from a central place)
KCE = rdflib.Namespace("http://kce.com/ontology/core#")
EX = rdflib.Namespace("http://example.com/ns#") # Fallback, not used much here

# KCE terms for argument passing and parameters
ARG_PASSING_STYLE_PROP = KCE.argumentPassingStyle
CMD_LINE_ARGS_STYLE = KCE.CommandLineArguments
STDIN_JSON_STYLE = KCE.StdInJSON # Used for explicit stdin preference or as fallback
PARAM_ORDER_PROP = KCE.parameterOrder
MAPS_TO_RDF_PROPERTY_PROP = KCE.mapsToRdfProperty
HAS_DATATYPE_PROP = KCE.hasDatatype


class NodeExecutor(INodeExecutor):
    def __init__(self):
        pass # No runtime_state_logger instance variable as per current class structure

    def _get_node_implementation_details(self, node_uri_str: str, knowledge_layer: IKnowledgeLayer) -> Dict[str, Any]:
        # Added ?arg_style_uri to the query
        query = f"""
        PREFIX kce: <{KCE}>
        SELECT ?type ?scriptPath ?command ?target_uri ?target_sparql_ask_query ?arg_style_uri
        WHERE {{
            <{node_uri_str}> kce:hasImplementationDetail ?impl .
            ?impl kce:invocationType ?type .
            OPTIONAL {{ ?impl kce:scriptPath ?scriptPath . }}
            OPTIONAL {{ ?impl kce:hasSparqlUpdateCommand ?command . }}
            OPTIONAL {{ ?impl kce:targetUri ?target_uri . }}
            OPTIONAL {{ ?impl kce:targetSparqlAskQuery ?target_sparql_ask_query . }}
            OPTIONAL {{ <{node_uri_str}> <{ARG_PASSING_STYLE_PROP}> ?arg_style_uri . }}
        }}
        LIMIT 1
        """
        results = knowledge_layer.execute_sparql_query(query)
        if isinstance(results, list) and results:
            # Ensure all expected keys are present, defaulting to None if OPTIONAL and not found
            details = results[0]
            return {
                'type': details.get('type'),
                'scriptPath': details.get('scriptPath'),
                'command': details.get('command'),
                'target_uri': details.get('target_uri'),
                'target_sparql_ask_query': details.get('target_sparql_ask_query'),
                'arg_style_uri': details.get('arg_style_uri')
            }
        raise ValueError(f"Node implementation details not found for <{node_uri_str}>")

    def _get_node_parameter_definitions(self, node_uri_str: str, direction: str, knowledge_layer: IKnowledgeLayer) -> List[Dict[str, Any]]:
        if direction not in ["Input", "Output"]:
            raise ValueError("Direction must be 'Input' or 'Output'")

        has_param_prop = KCE[f"has{direction}Parameter"]

        # Added ?order to the query
        query = f"""
        PREFIX kce: <{KCE}>
        PREFIX rdfs: <{RDFS}>
        SELECT ?param_uri ?paramName ?rdfProp ?datatype ?order
        WHERE {{
            <{node_uri_str}> <{has_param_prop}> ?param_uri .
            ?param_uri rdfs:label ?paramName .
            OPTIONAL {{ ?param_uri <{MAPS_TO_RDF_PROPERTY_PROP}> ?rdfProp . }}
            OPTIONAL {{ ?param_uri <{HAS_DATATYPE_PROP}> ?datatype . }}
            OPTIONAL {{ ?param_uri <{PARAM_ORDER_PROP}> ?order . }}
        }}
        """
        results = knowledge_layer.execute_sparql_query(query)
        params = []
        if isinstance(results, list):
            for row in results:
                order_val = float('inf')
                order_literal = row.get('order')
                if order_literal and isinstance(order_literal, Literal) and order_literal.value is not None:
                    try:
                        order_val = int(order_literal.value)
                    except ValueError:
                        print(f"Warning: Could not parse parameterOrder '{order_literal.value}' as int for param <{row.get('param_uri')}> on node <{node_uri_str}>.")

                params.append({
                    "uri": row.get('param_uri'),
                    "name": str(row.get('paramName')),
                    "maps_to_prop": row.get('rdfProp'),
                    "datatype": row.get('datatype'),
                    "order": order_val
                })
        params.sort(key=lambda p: (p["order"], p["name"])) # Sort by order, then by name
        return params

    def _prepare_inputs_for_script_stdin(self, input_param_definitions: List[Dict[str, Any]], current_input_graph: RDFGraph, node_uri_str: str) -> Dict[str, Any]:
        inputs_for_script = {}
        if not input_param_definitions: return inputs_for_script

        for p_def in input_param_definitions:
            param_name = p_def['name']
            rdf_prop_uri = p_def.get('maps_to_prop')

            if not rdf_prop_uri:
                print(f"Warning: Input parameter '{param_name}' for node <{node_uri_str}> has no kce:mapsToRdfProperty. Cannot fetch value for stdin/JSON.")
                continue

            value_found = False
            for s, p, o_val in current_input_graph.triples((None, rdf_prop_uri, None)):
                if isinstance(o_val, Literal):
                    inputs_for_script[param_name] = o_val.toPython()
                else:
                    inputs_for_script[param_name] = str(o_val)
                value_found = True
                break

            if not value_found:
                print(f"Warning: Input for parameter '{param_name}' (property <{rdf_prop_uri}>) for node <{node_uri_str}> not found in current_input_graph for stdin/JSON.")
        return inputs_for_script

    def _execute_python_script(
        self,
        script_path_str: str,
        node_uri_str: str,
        arg_style_uri: Optional[URIRef],
        input_param_definitions: List[Dict[str, Any]],
        current_input_graph: RDFGraph
    ) -> Dict[str, Any]:

        actual_script_path = Path(script_path_str)
        if not actual_script_path.is_file():
            # This check might be redundant if DefinitionLoader already provides resolved, checked paths.
            # However, NodeExecutor._get_node_implementation_details doesn't guarantee this check was done by loader.
            raise FileNotFoundError(f"Script not found for node <{node_uri_str}>. Path: '{actual_script_path}'")

        cmd_args_list = []
        stdin_payload_str = None

        if arg_style_uri == CMD_LINE_ARGS_STYLE:
            print(f"Preparing command-line arguments for node <{node_uri_str}>.")
            args_for_sorting = []
            for p_def in input_param_definitions:
                param_name = p_def['name']
                rdf_prop_uri = p_def.get('maps_to_prop')
                param_order = p_def.get('order', float('inf'))

                value_for_arg_str = "" # Default to empty string if not found? Or error?
                value_found = False
                if rdf_prop_uri:
                    for s, p, o_val in current_input_graph.triples((None, rdf_prop_uri, None)):
                        if isinstance(o_val, Literal):
                            value_for_arg_str = str(o_val.toPython())
                        else:
                            value_for_arg_str = str(o_val)
                        value_found = True
                        break

                if value_found:
                    args_for_sorting.append({'order': param_order, 'name': param_name, 'value': value_for_arg_str})
                else:
                    # This behavior might need refinement: error if required, or pass empty string, or skip.
                    print(f"Warning: Value for command-line argument '{param_name}' for node <{node_uri_str}> not found in input graph. It will be omitted or empty.")
                    # For now, let's add an empty string if not found, to maintain argument positions if order is critical.
                    # Scripts need to be robust to this. Or, add an 'isRequired' check from definition.
                    args_for_sorting.append({'order': param_order, 'name': param_name, 'value': ""})


            # Parameters are already sorted by _get_node_parameter_definitions
            cmd_args_list = [item['value'] for item in args_for_sorting]
            cmd = [sys.executable, str(actual_script_path)] + cmd_args_list
            print(f"Executing command: {cmd}")

        elif arg_style_uri == STDIN_JSON_STYLE or arg_style_uri is None: # Default to STDIN JSON
            inputs_for_stdin = self._prepare_inputs_for_script_stdin(input_param_definitions, current_input_graph, node_uri_str)
            stdin_payload_str = json.dumps(inputs_for_stdin)
            cmd = [sys.executable, str(actual_script_path)]
            print(f"Executing command with stdin JSON: {cmd}, input: {stdin_payload_str[:200]}...")
        else:
            raise NotImplementedError(f"Argument passing style {arg_style_uri} not supported for Python script node <{node_uri_str}>.")

        stdout_val, stderr_val = "", ""
        try:
            process = subprocess.run(
                cmd,
                input=stdin_payload_str,
                capture_output=True,
                text=True,
                cwd=actual_script_path.parent,
                timeout=30,
                check=False,
                encoding='utf-8'
            )
            stdout_val = process.stdout.strip() if process.stdout else ""
            stderr_val = process.stderr.strip() if process.stderr else ""

            if process.returncode != 0:
                error_message = (f"Script {actual_script_path} for node <{node_uri_str}> failed with exit code {process.returncode}. "
                                 f"Stderr: {stderr_val}")
                print(error_message)
                raise RuntimeError(error_message)

            return json.loads(stdout_val) if stdout_val else {}
        except FileNotFoundError:
            raise
        except subprocess.TimeoutExpired:
            error_message = f"Script {actual_script_path} for node <{node_uri_str}> timed out. Stderr: {stderr_val}"
            print(error_message)
            raise RuntimeError(error_message) from None
        except json.JSONDecodeError as e:
            error_message = f"Failed to decode JSON output from script {actual_script_path} for node <{node_uri_str}>. Output: '{stdout_val}'. Error: {e}"
            print(error_message)
            raise RuntimeError(error_message) from e
        except Exception as e:
            error_message = f"Error executing script {actual_script_path} for node <{node_uri_str}>: {e}. Stderr: {stderr_val}"
            print(error_message)
            raise RuntimeError(error_message) from e

    def _convert_outputs_to_rdf(self, node_uri_str: str, script_outputs: Dict[str, Any], output_param_definitions: List[Dict[str, Any]]) -> RDFGraph:
        output_graph = Graph()
        # Ensure node_uri for adding to graph is a URIRef. If node_uri_str is already a full URI, URIRef() is idempotent.
        # If node_uri_str is like "ex:Node1", this will create a relative URIRef if "ex" is not globally known to rdflib's default parsing.
        # However, the subject_uri will usually come from nodeContextUri from the definition, which should be absolute.
        node_uri_as_uriref = URIRef(node_uri_str)

        if not output_param_definitions: return output_graph

        for p_def in output_param_definitions:
            param_name = p_def['name']
            rdf_prop_uri = p_def.get('maps_to_prop')
            subject_uri = p_def.get('nodeContextUri', node_uri_as_uriref) # Default to node_uri_as_uriref
            if not isinstance(subject_uri, URIRef): # Ensure subject is URIRef
                subject_uri = URIRef(str(subject_uri))

            datatype_uri = p_def.get('datatype')

            if not rdf_prop_uri:
                print(f"Warning: Output parameter '{param_name}' for node <{node_uri_str}> has no kce:mapsToRdfProperty. Cannot create output triple.")
                continue

            if param_name in script_outputs:
                value = script_outputs[param_name]
                rdf_value: Union[Literal, URIRef]
                # Basic check if value looks like a URI to be turned into URIRef, otherwise Literal
                if isinstance(value, str) and (value.startswith("http://") or value.startswith("https://") or value.startswith("urn:") or value.count(":") == 1):
                    try: # Attempt to see if it's a CURIE that can be expanded or is a valid relative/absolute URI part
                        rdf_value = URIRef(value) # This might need prefix expansion if it's like "ex:item"
                    except: # If URIRef creation fails with it, treat as Literal
                        rdf_value = Literal(value, datatype=datatype_uri if datatype_uri else XSD.string if isinstance(value, str) else None)
                else:
                    rdf_value = Literal(value, datatype=datatype_uri if datatype_uri else None)
                output_graph.add((subject_uri, rdf_prop_uri, rdf_value))
            else:
                print(f"Warning: Output parameter '{param_name}' defined for node <{node_uri_str}> but not found in script output: {list(script_outputs.keys())}")
        return output_graph

    def _execute_sparql_update(self, command: str, knowledge_layer: IKnowledgeLayer) -> RDFGraph:
        knowledge_layer.execute_sparql_update(command)
        return Graph()

    def execute_node(self, node_uri_str: str, run_id: str, knowledge_layer: IKnowledgeLayer, current_input_graph: RDFGraph) -> RDFGraph:
        print(f"Executing node <{node_uri_str}> for run_id: {run_id}")

        impl_details = self._get_node_implementation_details(node_uri_str, knowledge_layer)

        invocation_type = impl_details.get('type')
        if invocation_type and not isinstance(invocation_type, URIRef):
            invocation_type = URIRef(str(invocation_type))

        arg_style_uri = impl_details.get('arg_style_uri')
        if arg_style_uri and not isinstance(arg_style_uri, URIRef):
             arg_style_uri = URIRef(str(arg_style_uri))

        if invocation_type == KCE.PythonScriptInvocation:
            script_path_literal = impl_details.get('scriptPath')
            if not script_path_literal:
                raise ValueError(f"Script path (kce:scriptPath or kce:hasAbsoluteScriptPath) not defined for Python node <{node_uri_str}>.")
            script_path = str(script_path_literal)

            input_param_defs = self._get_node_parameter_definitions(node_uri_str, "Input", knowledge_layer)
            output_param_defs = self._get_node_parameter_definitions(node_uri_str, "Output", knowledge_layer)

            script_outputs = self._execute_python_script(script_path, node_uri_str, arg_style_uri, input_param_defs, current_input_graph)
            print(f"Node <{node_uri_str}> script outputs: {script_outputs}")

            output_rdf_graph = self._convert_outputs_to_rdf(node_uri_str, script_outputs, output_param_defs)
            print(f"Node <{node_uri_str}> generated {len(output_rdf_graph)} output triples.")
            return output_rdf_graph

        elif invocation_type == KCE.SparqlUpdateInvocation:
            command_literal = impl_details.get('command')
            if not command_literal:
                 raise ValueError(f"SPARQL update command (kce:hasSparqlUpdateCommand) not defined for node <{node_uri_str}>.")
            command_str = str(command_literal)
            return self._execute_sparql_update(command_str, knowledge_layer)

        else:
            raise NotImplementedError(f"Node invocation type {invocation_type} not supported yet for <{node_uri_str}>.")

# Main block for isolated testing (needs update for new arg passing)
if __name__ == '__main__':
    print("NodeExecutor main test block needs update for new argument passing styles.")
