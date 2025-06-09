import yaml
import json
import os
from pathlib import Path
import logging
from typing import Any, Dict, List, Optional, Union
import yaml

from rdflib import Graph, URIRef, Literal, Namespace
import uuid # For fallback URI generation
from rdflib.namespace import RDF, RDFS, XSD

from kce_core.interfaces import IDefinitionTransformationLayer, RDFGraph, LoadStatus, InitialStateGraph, DirectoryPath, IKnowledgeLayer
from kce_core.common.exceptions import KCEError, DefinitionError
from kce_core.common.utils import create_rdf_graph_from_json_ld_dict

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
        # If no prefix and not a full URI, default to KCE namespace
        kce_logger.debug(f"No prefix found for '{value}', defaulting to KCE namespace: {KCE[value]}")
        return KCE[value] # Fallback

    def _parse_node_definition(self, data: Dict, file_path_str: str) -> Graph:
        g = Graph()
        node_uri_str = data.get("id") or data.get("uri")
        if not node_uri_str:
            node_uri_str = f"urn:uuid:{uuid.uuid4()}"
            kce_logger.warning(f"Node definition in {file_path_str} missing 'uri'. Generated: {node_uri_str}")
        node_uri = self._prefix_uri(node_uri_str)
        g.add((node_uri, RDF.type, KCE.AtomicNode))
        if "name" in data: g.add((node_uri, RDFS.label, Literal(data["name"])))
        if "description" in data: g.add((node_uri, RDFS.comment, Literal(data["description"])))
        if "precondition" in data: g.add((node_uri, KCE.hasPrecondition, Literal(data["precondition"], datatype=KCE.SparqlQuery)))
        if "effect" in data: g.add((node_uri, KCE.hasEffect, Literal(data["effect"], datatype=KCE.SparqlUpdateTemplate)))

        for param_type_key, kce_predicate, param_rdf_type in [("inputs", KCE.hasInputParameter, KCE.InputParameter),
                                                       ("outputs", KCE.hasOutputParameter, KCE.OutputParameter)]:
            if param_type_key in data:
                for p_data in data[param_type_key]:
                    param_name = p_data.get("name")
                    if not param_name: continue
                    param_uri_str = p_data.get("uri", f"{node_uri_str}/param/{param_name}")
                    param_uri = self._prefix_uri(param_uri_str)
                    g.add((param_uri, RDF.type, param_rdf_type))
                    g.add((param_uri, RDFS.label, Literal(param_name)))
                    if p_data.get("mapsToRdfProperty") or p_data.get("maps_to_rdf_property"): g.add((param_uri, KCE.mapsToRdfProperty, self._prefix_uri(p_data.get("mapsToRdfProperty") or p_data.get("maps_to_rdf_property"))))
                    if "datatype" in p_data: g.add((param_uri, KCE.hasDatatype, self._prefix_uri(p_data["datatype"])))
                    if p_data.get("is_required") is not None and param_type_key == "inputs":
                        g.add((param_uri, KCE.isRequired, Literal(bool(p_data["is_required"]), datatype=XSD.boolean)))
                    g.add((node_uri, kce_predicate, param_uri))

        if "implementation" in data:
            impl_data = data["implementation"]
            impl_uri_str = f"{node_uri_str}/implementation"
            impl_uri = self._prefix_uri(impl_uri_str)
            g.add((impl_uri, RDF.type, KCE.ImplementationDetail))
            impl_type_str = impl_data.get("type")
            if impl_type_str: g.add((impl_uri, KCE.invocationType, self._prefix_uri(impl_type_str)))
            if "scriptPath" in impl_data:
                original_script_path = impl_data["scriptPath"]
                yaml_file_path_obj = Path(file_path_str)
                yaml_dir = yaml_file_path_obj.parent
                resolved_script_path = (yaml_dir / original_script_path).resolve()
                g.add((impl_uri, KCE.scriptPath, Literal(str(resolved_script_path))))
                if not resolved_script_path.is_file():
                    kce_logger.warning(f"Script at resolved path {resolved_script_path} (from '{original_script_path}' in {file_path_str}) was not found. NodeExecutor will verify at runtime.")
            g.add((node_uri, KCE.hasImplementationDetail, impl_uri))

        for prefix, namespace_obj in self.kce_ns_map.items(): g.bind(prefix, namespace_obj)
        return g

    def _parse_rule_definition(self, data: Dict, file_path_str: str) -> Graph:
        g = Graph()
        rule_uri_str = data.get("id") or data.get("uri")
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

    def _parse_workflow_definition(self, data: Dict, file_path_str: str) -> Graph:
        g = Graph()
        workflow_uri_str = data.get("id") or data.get("uri")
        if not workflow_uri_str:
            workflow_uri_str = f"urn:uuid:{uuid.uuid4()}"
            kce_logger.warning(f"Workflow definition in {file_path_str} missing 'id' or 'uri'. Generated: {workflow_uri_str}")
        workflow_uri = self._prefix_uri(workflow_uri_str)
        g.add((workflow_uri, RDF.type, KCE.Workflow))
        if "label" in data: g.add((workflow_uri, RDFS.label, Literal(data["label"])))
        if "description" in data: g.add((workflow_uri, RDFS.comment, Literal(data["description"])))

        if "steps" in data and isinstance(data["steps"], list):
            for step_data in data["steps"]:
                if not isinstance(step_data, dict): continue
                executes_node_uri_str = step_data.get("executes_node_uri")
                order = step_data.get("order")
                if executes_node_uri_str and order is not None:
                    step_uri_str = f"{workflow_uri_str}/step/{order}"
                    step_uri = self._prefix_uri(step_uri_str)
                    g.add((step_uri, RDF.type, KCE.WorkflowStep))
                    g.add((step_uri, KCE.executesNode, self._prefix_uri(executes_node_uri_str)))
                    g.add((step_uri, KCE.hasOrder, Literal(int(order), datatype=XSD.integer)))
                    g.add((workflow_uri, KCE.hasStep, step_uri))
                else:
                    kce_logger.warning(f"Workflow step in {file_path_str} missing 'executes_node_uri' or 'order'. Skipping step.")

        for prefix, namespace_obj in self.kce_ns_map.items(): g.bind(prefix, namespace_obj)
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
                        for i, doc_data in enumerate(yaml_documents):
                            if not doc_data or not isinstance(doc_data, dict): continue
                            kce_logger.debug(f"Processing document {i+1} in {abs_file_path_str} (keys: {list(doc_data.keys())})")

                            # Handle top-level 'nodes' key for lists of definitions
                            if "nodes" in doc_data and isinstance(doc_data["nodes"], list):
                                for j, node_data in enumerate(doc_data["nodes"]):
                                    if not isinstance(node_data, dict): continue
                                    rdf_graph = self._parse_node_definition(node_data, abs_file_path_str)
                                    if rdf_graph and len(rdf_graph) > 0:
                                        self.kl.add_graph(rdf_graph)
                                        loaded_docs_count += 1
                                continue # Skip further processing for this top-level document

                            # Handle top-level 'rules' key for lists of definitions
                            if "rules" in doc_data and isinstance(doc_data["rules"], list):
                                for j, rule_data in enumerate(doc_data["rules"]):
                                    if not isinstance(rule_data, dict): continue
                                    rdf_graph = self._parse_rule_definition(rule_data, abs_file_path_str)
                                    if rdf_graph and len(rdf_graph) > 0:
                                        self.kl.add_graph(rdf_graph)
                                        loaded_docs_count += 1
                                continue # Skip further processing for this top-level document

                            # Handle top-level 'workflows' key for lists of definitions
                            if "workflows" in doc_data and isinstance(doc_data["workflows"], list):
                                for j, workflow_data in enumerate(doc_data["workflows"]):
                                    if not isinstance(workflow_data, dict): continue
                                    rdf_graph = self._parse_workflow_definition(workflow_data, abs_file_path_str)
                                    if rdf_graph and len(rdf_graph) > 0:
                                        self.kl.add_graph(rdf_graph)
                                        loaded_docs_count += 1
                                continue # Skip further processing for this top-level document

                            # Original handling for single definitions per document
                            doc_kind = doc_data.get("kind") or doc_data.get("type")
                            rdf_graph = None
                            if doc_kind == "AtomicNode":
                                rdf_graph = self._parse_node_definition(doc_data, abs_file_path_str)
                            elif doc_kind == "Rule":
                                rdf_graph = self._parse_rule_definition(doc_data, abs_file_path_str)
                            elif doc_kind == "CapabilityTemplate":
                                rdf_graph = self._parse_capability_template_definition(doc_data, abs_file_path_str)
                            elif doc_kind == "Workflow":
                                rdf_graph = self._parse_workflow_definition(doc_data, abs_file_path_str)
                            else:
                                errors.append({"file": abs_file_path_str, "document_index": i, "error": f"Unknown 'kind' or 'type': {doc_kind}"})
                                continue
                            if rdf_graph and len(rdf_graph) > 0:
                                self.kl.add_graph(rdf_graph)
                                loaded_docs_count += 1
                    except yaml.YAMLError as ye:
                        error_msg = f"YAML parsing error in {abs_file_path_str}: {ye}"
                        errors.append({"file": abs_file_path_str, "error": error_msg})
                        kce_logger.error(error_msg, exc_info=True)
                    except Exception as e:
                        error_msg = f"General error processing file {abs_file_path_str}: {e}"
                        errors.append({"file": abs_file_path_str, "error": error_msg})
                        kce_logger.error(error_msg, exc_info=True)
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
