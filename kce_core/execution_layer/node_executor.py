import rdflib
import subprocess
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Union, Optional, Tuple
from rdflib import URIRef, Literal, Graph, BNode
from rdflib.namespace import RDF, RDFS, XSD # Ensure these are directly available if used
import logging # Added for logging

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

# Setup logger for this module
node_executor_logger = logging.getLogger(__name__)
if not node_executor_logger.handlers: # Ensure a handler is present, e.g. NullHandler
    node_executor_logger.addHandler(logging.NullHandler())


class NodeExecutor(INodeExecutor):
    def __init__(self):
        pass # No runtime_state_logger instance variable as per current class structure

    def _python_to_rdf_literal(self, value: Any, datatype_uri_str: Optional[str] = None) -> Union[Literal, URIRef]:
        """Converts a Python value to an RDFLib Literal, inferring datatype if possible, or URIRef if value is a URI string."""
        if isinstance(value, str):
            if value.startswith("http://") or value.startswith("https://") or value.startswith("urn:"):
                try:
                    return URIRef(value) # Value is a URI
                except: # Fallback if URIRef creation fails
                    pass # Continue to treat as Literal
            if datatype_uri_str:
                return Literal(value, datatype=URIRef(datatype_uri_str))
            return Literal(value) # Default to xsd:string or lang-tagged if appropriate in future
        elif isinstance(value, bool):
            return Literal(value, datatype=XSD.boolean)
        elif isinstance(value, int):
            return Literal(value, datatype=XSD.integer)
        elif isinstance(value, float):
            return Literal(value, datatype=XSD.double)
        # Add more type conversions as needed (e.g., date, datetime)
        elif datatype_uri_str: # If other types but datatype is specified
            return Literal(str(value), datatype=URIRef(datatype_uri_str))
        return Literal(str(value)) # Fallback for other types

    def _process_rdf_instructions(self, instructions: Dict[str, Any], node_uri: str) -> RDFGraph:
        """Processes '_rdf_instructions' from script output to create an RDF graph."""
        instruction_graph = Graph()
        node_executor_logger.debug(f"Node <{node_uri}>: Processing _rdf_instructions.")

        # Process 'create_entities'
        created_entities_count = 0
        if "create_entities" in instructions and isinstance(instructions["create_entities"], list):
            for entity_spec in instructions["create_entities"]:
                if not isinstance(entity_spec, dict) or "uri" not in entity_spec or "type" not in entity_spec:
                    node_executor_logger.warning(f"Node <{node_uri}>: Invalid entity_spec in _rdf_instructions: {entity_spec}")
                    continue

                entity_uri_str = entity_spec["uri"]
                entity_uri = URIRef(entity_uri_str if ":" in entity_uri_str or entity_uri_str.startswith("http") else BNode(entity_uri_str)) # Allow BNode IDs from script using "bnode_id" convention

                entity_type_uri = URIRef(entity_spec["type"])
                instruction_graph.add((entity_uri, RDF.type, entity_type_uri))
                created_entities_count +=1
                node_executor_logger.debug(f"Node <{node_uri}>: Instruction to create entity <{entity_uri}> of type <{entity_type_uri}>.")

                if "properties" in entity_spec and isinstance(entity_spec["properties"], dict):
                    for prop_uri_str, prop_value in entity_spec["properties"].items():
                        prop_uri = URIRef(prop_uri_str)
                        # Datatype might be part of prop_value if it's a dict like {'value': '10', 'datatype': 'xsd:integer'}
                        # For now, assume direct value and use _python_to_rdf_literal's inference
                        rdf_value = self._python_to_rdf_literal(prop_value)
                        instruction_graph.add((entity_uri, prop_uri, rdf_value))
                        node_executor_logger.debug(f"Node <{node_uri}>:   - Adding property <{prop_uri}> with value '{rdf_value}'.")

        if created_entities_count > 0:
            node_executor_logger.info(f"Node <{node_uri}>: Processed {created_entities_count} 'create_entities' instructions.")

        # Process 'add_links'
        added_links_count = 0
        if "add_links" in instructions and isinstance(instructions["add_links"], list):
            for link_spec in instructions["add_links"]:
                if not isinstance(link_spec, dict) or not all(k in link_spec for k in ["subject", "predicate", "object"]):
                    node_executor_logger.warning(f"Node <{node_uri}>: Invalid link_spec in _rdf_instructions: {link_spec}")
                    continue

                subj_uri = URIRef(link_spec["subject"] if ":" in link_spec["subject"] or link_spec["subject"].startswith("http") else BNode(link_spec["subject"]))
                pred_uri = URIRef(link_spec["predicate"])
                obj_uri = URIRef(link_spec["object"] if ":" in link_spec["object"] or link_spec["object"].startswith("http") else BNode(link_spec["object"]))

                instruction_graph.add((subj_uri, pred_uri, obj_uri))
                added_links_count +=1
                node_executor_logger.debug(f"Node <{node_uri}>: Instruction to add link: <{subj_uri}> <{pred_uri}> <{obj_uri}>.")

        if added_links_count > 0:
            node_executor_logger.info(f"Node <{node_uri}>: Processed {added_links_count} 'add_links' instructions.")

        return instruction_graph

    def _get_node_implementation_details(self, node_uri: str, knowledge_layer: IKnowledgeLayer) -> Dict[str, Any]:
        # Added ?arg_style_uri to the query
        query = f"""
        PREFIX kce: <{KCE}>
        SELECT ?type ?scriptPath ?command ?target_uri ?target_sparql_ask_query ?arg_style_uri
        WHERE {{
            <{node_uri}> kce:hasImplementationDetail ?impl .
            ?impl kce:invocationType ?type .
            OPTIONAL {{ ?impl kce:scriptPath ?scriptPath . }}
            OPTIONAL {{ ?impl kce:hasSparqlUpdateCommand ?command . }}
            OPTIONAL {{ ?impl kce:targetUri ?target_uri . }}
            OPTIONAL {{ ?impl kce:targetSparqlAskQuery ?target_sparql_ask_query . }}
            OPTIONAL {{ ?impl <{ARG_PASSING_STYLE_PROP}> ?arg_style_uri . }}
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
        raise ValueError(f"Node implementation details not found for <{node_uri}>")

    def _get_node_parameter_definitions(self, node_uri: str, direction: str, knowledge_layer: IKnowledgeLayer) -> List[Dict[str, Any]]:
        if direction not in ["Input", "Output"]:
            raise ValueError("Direction must be 'Input' or 'Output'")

        has_param_prop = KCE[f"has{direction}Parameter"]

        # Added ?order to the query
        query = f"""
        PREFIX kce: <{KCE}>
        PREFIX rdfs: <{RDFS}>
        SELECT ?param_uri ?paramName ?rdfProp ?datatype ?order
        WHERE {{
            <{node_uri}> <{has_param_prop}> ?param_uri .
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
                        print(f"Warning: Could not parse parameterOrder '{order_literal.value}' as int for param <{row.get('param_uri')}> on node <{node_uri}>.")

                params.append({
                    "uri": row.get('param_uri'),
                    "name": str(row.get('paramName')),
                    "maps_to_prop": row.get('rdfProp'),
                    "datatype": row.get('datatype'),
                    "order": order_val
                })
        params.sort(key=lambda p: (p["order"], p["name"])) # Sort by order, then by name
        return params

    def _prepare_inputs_for_script_stdin(self, input_param_definitions: List[Dict[str, Any]], current_input_graph: RDFGraph, node_uri: str) -> Dict[str, Any]:
        inputs_for_script = {}
        if not input_param_definitions: return inputs_for_script

        for p_def in input_param_definitions:
            param_name = p_def['name']
            rdf_prop_uri = p_def.get('maps_to_prop')

            if not rdf_prop_uri:
                print(f"Warning: Input parameter '{param_name}' for node <{node_uri}> has no kce:mapsToRdfProperty. Cannot fetch value for stdin/JSON.")
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
                print(f"Warning: Input for parameter '{param_name}' (property <{rdf_prop_uri}>) for node <{node_uri}> not found in current_input_graph for stdin/JSON.")
        return inputs_for_script

    def _execute_python_script(
        self,
        script_path_str: str,
        node_uri: str,
        arg_style_uri: Optional[URIRef],
        input_param_definitions: List[Dict[str, Any]],
        current_input_graph: RDFGraph
    ) -> Dict[str, Any]:

        actual_script_path = Path(script_path_str)
        if not actual_script_path.is_file():
            # This check might be redundant if DefinitionLoader already provides resolved, checked paths.
            # However, NodeExecutor._get_node_implementation_details doesn't guarantee this check was done by loader.
            raise FileNotFoundError(f"Script not found for node <{node_uri}>. Path: '{actual_script_path}'")

        cmd_args_list = []
        stdin_payload_str = None

        if arg_style_uri == CMD_LINE_ARGS_STYLE:
            print(f"Preparing command-line arguments for node <{node_uri}>.")
            print(f"Raw input_param_definitions for <{node_uri}>: {input_param_definitions}") # DEBUG LOG
            args_for_sorting = []
            for p_def in input_param_definitions:
                param_name = p_def['name']
                rdf_prop_uri = p_def.get('maps_to_prop')
                param_order_from_def = p_def.get('order', float('inf')) # Corrected to param_order_from_def

                print(f"Processing param: {param_name}, order: {param_order_from_def}, maps_to_prop: {rdf_prop_uri}") # DEBUG LOG

                value_for_arg_str = ""
                value_found = False
                if rdf_prop_uri:
                    # Ensure rdf_prop_uri is a URIRef for the query
                    if not isinstance(rdf_prop_uri, URIRef): rdf_prop_uri = URIRef(str(rdf_prop_uri))

                    found_triples_debug = list(current_input_graph.triples((None, rdf_prop_uri, None)))
                    print(f"  Searching for triples with P=<{(rdf_prop_uri if rdf_prop_uri else 'None')}>. Found {len(found_triples_debug)}: {found_triples_debug[:3]}") # DEBUG LOG

                    for s, p, o_val in found_triples_debug: # Use the fetched list
                        if isinstance(o_val, Literal):
                            value_for_arg_str = str(o_val.toPython())
                        else:
                            value_for_arg_str = str(o_val)
                        value_found = True
                        print(f"  Found value for {param_name}: '{value_for_arg_str}'") # DEBUG LOG
                        break

                if not value_found:
                     print(f"  Value for {param_name} (prop: {rdf_prop_uri}) not found in current_input_graph.") # DEBUG LOG


                if value_found:
                    args_for_sorting.append({'order': param_order_from_def, 'name': param_name, 'value': value_for_arg_str})
                else:
                    print(f"Warning: Value for command-line argument '{param_name}' for node <{node_uri}> (prop: {rdf_prop_uri}) not found in input graph. It will be omitted or empty.")
                    args_for_sorting.append({'order': param_order_from_def, 'name': param_name, 'value': ""})

            # input_param_definitions should already be sorted by 'order', then 'name'.
            # So, iterating through it should build args_for_sorting in the correct order.
            # The list `args_for_sorting` itself is not re-sorted before creating `cmd_args_list`.
            # This relies on `input_param_definitions` being correctly sorted by `_get_node_parameter_definitions`.

            cmd_args_list = [item['value'] for item in args_for_sorting] # This uses the order from input_param_definitions
            cmd = [sys.executable, str(actual_script_path)] + cmd_args_list
            print(f"Executing command: {cmd}")

        elif arg_style_uri == STDIN_JSON_STYLE or arg_style_uri is None: # Default to STDIN JSON
            inputs_for_stdin = self._prepare_inputs_for_script_stdin(input_param_definitions, current_input_graph, node_uri)
            stdin_payload_str = json.dumps(inputs_for_stdin)
            cmd = [sys.executable, str(actual_script_path)]
            print(f"Executing command with stdin JSON: {cmd}, input: {stdin_payload_str[:200]}...")
        else:
            raise NotImplementedError(f"Argument passing style {arg_style_uri} not supported for Python script node <{node_uri}>.")

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
                error_message = (f"Script {actual_script_path} for node <{node_uri}> failed with exit code {process.returncode}. "
                                 f"Stderr: {stderr_val}")
                print(error_message)
                raise RuntimeError(error_message)

            return json.loads(stdout_val) if stdout_val else {}
        except FileNotFoundError:
            raise
        except subprocess.TimeoutExpired:
            error_message = f"Script {actual_script_path} for node <{node_uri}> timed out. Stderr: {stderr_val}"
            print(error_message)
            raise RuntimeError(error_message) from None
        except json.JSONDecodeError as e:
            error_message = f"Failed to decode JSON output from script {actual_script_path} for node <{node_uri}>. Output: '{stdout_val}'. Error: {e}"
            print(error_message)
            raise RuntimeError(error_message) from e
        except Exception as e:
            error_message = f"Error executing script {actual_script_path} for node <{node_uri}>: {e}. Stderr: {stderr_val}"
            print(error_message)
            raise RuntimeError(error_message) from e

    def _convert_outputs_to_rdf(self, node_uri: str, script_outputs: Dict[str, Any], output_param_definitions: List[Dict[str, Any]]) -> RDFGraph:
        output_graph = Graph()
        # Ensure node_uri for adding to graph is a URIRef. If node_uri is already a full URI, URIRef() is idempotent.
        # If node_uri is like "ex:Node1", this will create a relative URIRef if "ex" is not globally known to rdflib's default parsing.
        # However, the subject_uri will usually come from nodeContextUri from the definition, which should be absolute.
        node_uri_as_uriref = URIRef(node_uri)

        if not output_param_definitions: return output_graph

        for p_def in output_param_definitions:
            param_name = p_def['name']
            rdf_prop_uri = p_def.get('maps_to_prop')
            subject_uri = p_def.get('nodeContextUri', node_uri_as_uriref) # Default to node_uri_as_uriref
            if not isinstance(subject_uri, URIRef): # Ensure subject is URIRef
                subject_uri = URIRef(str(subject_uri))

            datatype_uri = p_def.get('datatype')

            if not rdf_prop_uri:
                print(f"Warning: Output parameter '{param_name}' for node <{node_uri}> has no kce:mapsToRdfProperty. Cannot create output triple.")
                continue

            fixed_value_data = p_def.get('kce:hasFixedValue') # Check for fixed value

            if fixed_value_data is not None: # Note: kce:hasFixedValue could be boolean false, so check for None
                # If there's a fixed value, use it directly.
                # The value from YAML (True/False) should be converted to Python bool by YAML loader.
                # Then _python_to_rdf_literal handles it.
                rdf_value = self._python_to_rdf_literal(fixed_value_data, datatype_uri_str=str(datatype_uri) if datatype_uri else None)
                output_graph.add((subject_uri, rdf_prop_uri, rdf_value))
                node_executor_logger.info(f"Node <{node_uri}>: Added fixed output for param '{param_name}' with value '{rdf_value}'.")

            elif param_name in script_outputs:
                value = script_outputs[param_name]
                # Basic check if value looks like a URI to be turned into URIRef, otherwise Literal
                if isinstance(value, str) and (value.startswith("http://") or value.startswith("https://") or value.startswith("urn:") or value.count(":") == 1):
                    try: # Attempt to see if it's a CURIE that can be expanded or is a valid relative/absolute URI part
                        rdf_value = URIRef(value) # This might need prefix expansion if it's like "ex:item"
                    except: # If URIRef creation fails with it, treat as Literal
                        rdf_value = Literal(value, datatype=datatype_uri if datatype_uri else XSD.string if isinstance(value, str) else None)
                else:
                    rdf_value = Literal(value, datatype=datatype_uri if datatype_uri else None) # Infer datatype if not specified
                output_graph.add((subject_uri, rdf_prop_uri, rdf_value))
            else:
                # Only print warning if it's not a fixed value and also not in script output
                print(f"Warning: Output parameter '{param_name}' defined for node <{node_uri}> but not found in script output: {list(script_outputs.keys())} and no kce:hasFixedValue provided.")

        return output_graph

    def _execute_sparql_update(self, command: str, knowledge_layer: IKnowledgeLayer) -> RDFGraph:
        knowledge_layer.execute_sparql_update(command)
        return Graph()

    def execute_node(self, node_uri: str, run_id: str, knowledge_layer: IKnowledgeLayer, current_input_graph: RDFGraph) -> RDFGraph:
        node_executor_logger.info(f"Executing node <{node_uri}> for run_id: {run_id}")

        # Log triples with kce:instanceURI from current_input_graph
        instance_uri_triples_found = []
        for s, p, o in current_input_graph.triples((None, KCE.instanceURI, None)):
            instance_uri_triples_found.append((s, p, o))
            node_executor_logger.info(f"Node <{node_uri}> received kce:instanceURI triple in current_input_graph: Subject={s}, Predicate={p}, Object={o}")

        if not instance_uri_triples_found:
            node_executor_logger.info(f"Node <{node_uri}>: No kce:instanceURI triples found in current_input_graph (size: {len(current_input_graph)}).")

        # For more detailed debugging of the input graph if needed:
        # if len(current_input_graph) < 20: # Log small graphs
        #    node_executor_logger.debug(f"Node <{node_uri}> current_input_graph dump (first few triples):")
        #    for i, (s_debug, p_debug, o_debug) in enumerate(current_input_graph):
        #        if i >= 5: break # Log max 5 triples
        #        node_executor_logger.debug(f"  - {s_debug.n3()} {p_debug.n3()} {o_debug.n3()}")
        # else:
        #    node_executor_logger.debug(f"Node <{node_uri}> current_input_graph is large (size: {len(current_input_graph)}), selective logging for KCE.instanceURI done above.")


        impl_details = self._get_node_implementation_details(node_uri, knowledge_layer)

        invocation_type = impl_details.get('type')
        if invocation_type and not isinstance(invocation_type, URIRef):
            invocation_type = URIRef(str(invocation_type))

        arg_style_uri = impl_details.get('arg_style_uri')
        if arg_style_uri and not isinstance(arg_style_uri, URIRef):
             arg_style_uri = URIRef(str(arg_style_uri))

        if invocation_type == KCE.PythonScriptInvocation:
            script_path_literal = impl_details.get('scriptPath')
            if not script_path_literal:
                raise ValueError(f"Script path (kce:scriptPath or kce:hasAbsoluteScriptPath) not defined for Python node <{node_uri}>.")
            script_path = str(script_path_literal)

            input_param_defs = self._get_node_parameter_definitions(node_uri, "Input", knowledge_layer)
            output_param_defs = self._get_node_parameter_definitions(node_uri, "Output", knowledge_layer)

            script_outputs = self._execute_python_script(script_path, node_uri, arg_style_uri, input_param_defs, current_input_graph)
            node_executor_logger.info(f"Node <{node_uri}> script outputs: {script_outputs}")

            # Process explicitly defined outputs
            output_rdf_graph = self._convert_outputs_to_rdf(node_uri, script_outputs, output_param_defs)
            node_executor_logger.info(f"Node <{node_uri}> generated {len(output_rdf_graph)} triples from explicit output parameters.")

            # Process _rdf_instructions if present
            if isinstance(script_outputs, dict) and "_rdf_instructions" in script_outputs:
                rdf_instructions = script_outputs["_rdf_instructions"]
                if isinstance(rdf_instructions, dict):
                    instruction_graph = self._process_rdf_instructions(rdf_instructions, node_uri)
                    if len(instruction_graph) > 0:
                        node_executor_logger.info(f"Node <{node_uri}> generated {len(instruction_graph)} triples from _rdf_instructions.")
                        output_rdf_graph += instruction_graph # Combine with explicit outputs
                    else:
                        node_executor_logger.info(f"Node <{node_uri}>: _rdf_instructions were present but generated no triples.")
                else:
                    node_executor_logger.warning(f"Node <{node_uri}>: _rdf_instructions key found in script output, but its value is not a dictionary. Skipping. Value: {rdf_instructions}")

            return output_rdf_graph

        elif invocation_type == KCE.SparqlUpdateInvocation:
            command_literal = impl_details.get('command')
            if not command_literal:
                 raise ValueError(f"SPARQL update command (kce:hasSparqlUpdateCommand) not defined for node <{node_uri}>.")
            command_str = str(command_literal)
            return self._execute_sparql_update(command_str, knowledge_layer)

        else:
            raise NotImplementedError(f"Node invocation type {invocation_type} not supported yet for <{node_uri}>.")

# Main block for isolated testing (needs update for new arg passing)
if __name__ == '__main__':
    print("NodeExecutor main test block needs update for new argument passing styles.")
