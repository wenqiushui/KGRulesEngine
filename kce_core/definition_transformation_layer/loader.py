import yaml
import json
import os
from pathlib import Path # Added Path
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD
from typing import Any, Dict # Added Any and Dict for type hinting
import uuid # For fallback URI generation
import logging # For kce_logger
from rdflib.collection import Collection # Added for RDF List
from rdflib import BNode # Added for RDF List

# Assuming interfaces.py is two levels up from definition_transformation_layer directory
from ..interfaces import IDefinitionTransformationLayer, IKnowledgeLayer, LoadStatus, InitialStateGraph, DirectoryPath
from ..common.exceptions import KCEError, DefinitionError # Assuming exceptions are in common
from ..common.utils import create_rdf_graph_from_json_ld_dict # For initial state

# Setup logger for this module - typically it would inherit from a root kce_core logger
kce_logger = logging.getLogger(__name__)
if not kce_logger.handlers:
    kce_logger.addHandler(logging.NullHandler()) # Avoid 'No handler found' if not configured by app

# Define KCE and other relevant namespaces (should ideally come from a central ontology definitions file)
KCE = Namespace("http://kce.com/ontology/core#")
EX = Namespace("http://example.com/ns#") # Example namespace for instance data
DOMAIN = Namespace("http://kce.com/example/elevator_panel#") # For example

class DefinitionLoader(IDefinitionTransformationLayer):
    def __init__(self, knowledge_layer: IKnowledgeLayer):
        self.kl = knowledge_layer
        self.kce_ns_map = {
            "kce": KCE,
            "rdf": RDF,
            "rdfs": RDFS,
            "xsd": XSD,
            "ex": EX,
            "domain": DOMAIN
        }

    def _prefix_uri(self, value: Any) -> URIRef:
        if not isinstance(value, str):
            try: value = str(value)
            except Exception as e: raise ValueError(f"URI value must be a string or convertible, got {type(value)}: {e}")
        if ":" in value:
            prefix, local_name = value.split(":", 1)
            if prefix in self.kce_ns_map:
                return self.kce_ns_map[prefix][local_name]
        if value.startswith("http://") or value.startswith("https://") or value.startswith("urn:"):
            return URIRef(value)
        kce_logger.debug(f"No prefix found for '{value}', defaulting to EX namespace: {EX[value]}")
        return EX[value] # Fallback

    def _parse_node_definition(self, data: Dict, file_path_str: str) -> Graph:
        g = Graph()
        node_uri_str = data.get("uri")
        if not node_uri_str:
            node_uri_str = f"urn:uuid:{uuid.uuid4()}"
            kce_logger.warning(f"Node definition in {file_path_str} missing 'uri'. Generated: {node_uri_str}")
        node_uri = self._prefix_uri(node_uri_str)
        g.add((node_uri, RDF.type, KCE.AtomicNode))
        if "name" in data: g.add((node_uri, RDFS.label, Literal(data["name"])))
        if "description" in data: g.add((node_uri, RDFS.comment, Literal(data["description"])))
        if "precondition" in data: g.add((node_uri, KCE.hasPrecondition, Literal(data["precondition"], datatype=KCE.SparqlQuery)))
        if "effect" in data: g.add((node_uri, KCE.hasEffect, Literal(data["effect"], datatype=KCE.SparqlUpdateTemplate)))

        param_name_to_uri_map = {} # To store input param names to URIs for ordering

        for param_type_key, kce_predicate, param_rdf_type in [("inputs", KCE.hasInputParameter, KCE.InputParameter),
                                                       ("outputs", KCE.hasOutputParameter, KCE.OutputParameter)]:
            if param_type_key in data:
                for p_data in data[param_type_key]:
                    param_name = p_data.get("name")
                    if not param_name: continue
                    param_uri_str = p_data.get("uri", f"{node_uri_str}/param/{param_name}") # Default URI construction
                    param_uri = self._prefix_uri(param_uri_str)
                    g.add((param_uri, RDF.type, param_rdf_type))
                    g.add((param_uri, RDFS.label, Literal(param_name)))
                    if "maps_to_rdf_property" in p_data: # Corrected key
                        g.add((param_uri, KCE.mapsToRdfProperty, self._prefix_uri(p_data["maps_to_rdf_property"])))
                    if "datatype" in p_data: g.add((param_uri, KCE.hasDatatype, self._prefix_uri(p_data["datatype"])))
                    if "isRequired" in p_data and param_type_key == "inputs":
                        g.add((param_uri, KCE.isRequired, Literal(bool(p_data["isRequired"]), datatype=XSD.boolean)))
                    g.add((node_uri, kce_predicate, param_uri))
                    if param_type_key == "inputs":
                        param_name_to_uri_map[param_name] = param_uri


        # Use "invocation" from YAML, mapping to "implementation" conceptually for some parts
        if "invocation" in data:
            impl_data = data["invocation"]

            # Create the ImplementationDetail node (impl_uri)
            # This URI should be unique for each node's implementation details.
            impl_uri_str = f"{node_uri_str}/implementation_detail"
            impl_uri = self._prefix_uri(impl_uri_str)
            g.add((node_uri, KCE.hasImplementationDetail, impl_uri))
            g.add((impl_uri, RDF.type, KCE.ImplementationDetail))

            # 1. Store kce:argumentPassingStyle on impl_uri
            arg_style_yaml_key = "kce:argumentPassingStyle" # Key as in YAML
            arg_style_value = impl_data.get(arg_style_yaml_key)
            if arg_style_value:
                # Assuming KCE.argumentPassingStyle is defined, otherwise use self._prefix_uri
                g.add((impl_uri, self._prefix_uri("kce:argumentPassingStyle"), self._prefix_uri(arg_style_value)))

            # 2. Store kce:parameterOrder on impl_uri as an RDF List
            param_order_yaml_key = "kce:parameterOrder" # Key as in YAML
            ordered_param_names = impl_data.get(param_order_yaml_key)
            if ordered_param_names and isinstance(ordered_param_names, list):
                if ordered_param_names: # Ensure list is not empty before creating collection
                    order_collection = Collection(g, BNode()) # Create a new BNode for the list head
                    for name_str in ordered_param_names:
                        order_collection.append(Literal(name_str))
                    # Assuming KCE.parameterOrder is defined for the predicate, otherwise use self._prefix_uri
                    g.add((impl_uri, self._prefix_uri("kce:parameterOrder"), order_collection.uri))
                else:
                    # Optionally handle empty list e.g. by adding rdf:nil or omitting the triple
                    g.add((impl_uri, self._prefix_uri("kce:parameterOrder"), RDF.nil))


            # Store invocationType (e.g., PythonScript) on impl_uri
            impl_type_str = impl_data.get("type")
            if impl_type_str:
                if impl_type_str == "PythonScript": invocation_type_uri = KCE.PythonScriptInvocation
                elif impl_type_str == "SparqlUpdate": invocation_type_uri = KCE.SparqlUpdateInvocation
                else: invocation_type_uri = self._prefix_uri(impl_type_str)
                g.add((impl_uri, KCE.invocationType, invocation_type_uri))

            # Store scriptPath on impl_uri
            original_script_path = impl_data.get("script_path")
            if original_script_path:
                yaml_file_path_obj = Path(file_path_str)
                yaml_dir = yaml_file_path_obj.parent
                resolved_script_path = (yaml_dir / original_script_path).resolve()
                g.add((impl_uri, KCE.scriptPath, Literal(str(resolved_script_path))))
                if not resolved_script_path.is_file():
                    kce_logger.warning(f"Script at resolved path {resolved_script_path} (from '{original_script_path}' in {file_path_str}) was not found. NodeExecutor will verify at runtime.")

            # The triple (node_uri, KCE.hasImplementationDetail, impl_uri) is added at the beginning of this block.
            # No need to add it again. The previous duplicate g.add((node_uri, KCE.hasImplementationDetail, impl_uri)) is removed.

        for prefix, namespace_obj in self.kce_ns_map.items(): g.bind(prefix, namespace_obj)
        return g

    def _parse_rule_definition(self, data: Dict, file_path_str: str) -> Graph:
        g = Graph()
        rule_uri_str = data.get("uri")
        if not rule_uri_str: rule_uri_str = f"urn:uuid:{uuid.uuid4()}"
        rule_uri = self._prefix_uri(rule_uri_str)
        g.add((rule_uri, RDF.type, KCE.Rule))
        if "name" in data: g.add((rule_uri, RDFS.label, Literal(data["name"])))
        if "description" in data: g.add((rule_uri, RDFS.comment, Literal(data["description"])))
        if "priority" in data: g.add((rule_uri, KCE.hasPriority, Literal(int(data["priority"]), datatype=XSD.integer)))
        if "antecedent" in data: g.add((rule_uri, KCE.hasAntecedent, Literal(data["antecedent"], datatype=KCE.SparqlQuery)))
        if "consequent" in data: g.add((rule_uri, KCE.hasConsequent, Literal(data["consequent"], datatype=KCE.SparqlUpdateTemplate)))
        for prefix, namespace_obj in self.kce_ns_map.items(): g.bind(prefix, namespace_obj)
        return g

    def _parse_capability_template_definition(self, data: Dict, file_path_str: str) -> Graph:
        g = Graph()
        kce_logger.warning(f"CapabilityTemplate parsing not fully implemented. Skipping item in {file_path_str}")
        return g

    def load_definitions_from_path(self, definitions_dir_path: DirectoryPath) -> LoadStatus:
        loaded_docs_count = 0
        errors = []
        abs_definitions_dir_path = Path(definitions_dir_path).resolve()
        kce_logger.info(f"Loading definitions from directory: {abs_definitions_dir_path}")

        for root, _, files in os.walk(abs_definitions_dir_path):
            for file_name in files:
                if file_name.endswith(('.yaml', '.yml')):
                    abs_file_path_str = str(Path(root) / file_name)
                    kce_logger.debug(f"Processing definition file: {abs_file_path_str}")
                    try:
                        with open(abs_file_path_str, 'r', encoding='utf-8') as f:
                            yaml_documents = list(yaml.safe_load_all(f))
                        for i, doc_data_or_collection in enumerate(yaml_documents):
                            if not doc_data_or_collection or not isinstance(doc_data_or_collection, dict):
                                continue

                            definitions_to_process = []
                            found_collection = False
                            # Check for common top-level collection keys like 'nodes', 'rules', etc.
                            for key in ["nodes", "rules", "workflows", "definitions"]:
                                if key in doc_data_or_collection and isinstance(doc_data_or_collection[key], list):
                                    definitions_to_process.extend(doc_data_or_collection[key])
                                    found_collection = True
                                    kce_logger.debug(f"Found collection key '{key}' in document {i+1} from {abs_file_path_str}")
                                    break

                            if not found_collection:
                                # Assume the document itself is a single definition
                                definitions_to_process.append(doc_data_or_collection)

                            for j, def_data in enumerate(definitions_to_process):
                                if not def_data or not isinstance(def_data, dict):
                                    kce_logger.warning(f"Skipping item {j} in document {i} from file {abs_file_path_str} as it's not a dictionary.")
                                    continue

                                kce_logger.debug(f"Processing definition item {j} (doc {i+1}) from {abs_file_path_str} (keys: {list(def_data.keys())})")

                                # Map 'id' to 'uri' and 'label' to 'name' if 'uri'/'name' are not present
                                if "id" in def_data and "uri" not in def_data:
                                     def_data["uri"] = def_data["id"]
                                if "label" in def_data and "name" not in def_data:
                                     def_data["name"] = def_data["label"]

                                doc_kind = def_data.get("kind")
                                # Fallback to 'type' if 'kind' is not present, for compatibility with some YAML structures
                                if not doc_kind:
                                    doc_kind = def_data.get("type")

                                rdf_graph = None
                                if doc_kind == "AtomicNode":
                                    rdf_graph = self._parse_node_definition(def_data, abs_file_path_str)
                                elif doc_kind == "Rule":
                                    rdf_graph = self._parse_rule_definition(def_data, abs_file_path_str)
                                elif doc_kind == "CapabilityTemplate":
                                    rdf_graph = self._parse_capability_template_definition(def_data, abs_file_path_str)
                                # Add elif for "Workflow" kind here if _parse_workflow_definition is implemented
                                # elif doc_kind == "Workflow":
                                #     rdf_graph = self._parse_workflow_definition(def_data, abs_file_path_str)
                                else:
                                    errors.append({"file": abs_file_path_str, "document_index": i, "item_index":j, "error": f"Unknown or unsupported 'kind'/'type': {doc_kind} for item: {str(def_data)[:100]}"})
                                    continue

                                if rdf_graph and len(rdf_graph) > 0:
                                    self.kl.add_graph(rdf_graph)
                                    loaded_docs_count += 1
                                elif rdf_graph is None: # Parsing method itself had an issue
                                     errors.append({"file": abs_file_path_str, "document_index": i, "item_index":j, "error": f"Parsing for kind '{doc_kind}' returned None for item: {str(def_data)[:100]}"})
                                # If rdf_graph is an empty graph, it means parsing happened but produced no triples (e.g. CapabilityTemplate)
                                # No explicit error here, but count doesn't increment.

                    except yaml.YAMLError as ye:
                        errors.append({"file": abs_file_path_str, "error": f"YAML parsing error: {ye}"})
                    except Exception as e:
                        errors.append({"file": abs_file_path_str, "error": f"General error processing file: {e}"})
                        kce_logger.error(f"Unhandled error processing {abs_file_path_str}: {e}", exc_info=True)
        kce_logger.info(f"Definition loading complete. Processed: {loaded_docs_count} documents. Errors: {len(errors)}.")
        return {"loaded_definitions_count": loaded_docs_count, "errors": errors}

    def load_initial_state_from_json(self, json_data_str: str, base_uri: str) -> InitialStateGraph:
        try:
            data = json.loads(json_data_str)
            return create_rdf_graph_from_json_ld_dict(data, default_base_ns_str=base_uri)
        except json.JSONDecodeError as e:
            kce_logger.error(f"Error decoding JSON for initial state: {e}", exc_info=True)
            raise DefinitionError(f"Invalid JSON for initial state: {e}") from e
        except Exception as e:
            kce_logger.error(f"Error converting initial state JSON to RDF: {e}", exc_info=True)
            raise KCEError(f"Could not convert JSON to RDF: {e}") from e
