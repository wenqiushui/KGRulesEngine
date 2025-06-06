# kce_core/definitions/loader.py

import logging
from pathlib import Path
from typing import Any, Dict, List, Union, Optional

from rdflib import URIRef, Literal, BNode # BNode might be used for complex structures

from kce_core.common.utils import (
    kce_logger,
    DefinitionError,
    load_yaml_file,
    resolve_path,
    to_uriref,
    to_literal,
    get_xsd_uriref,
    KCE, RDF, RDFS, OWL, DCTERMS, EX, # Namespaces
)
from kce_core.rdf_store.store_manager import StoreManager


class DefinitionLoader:
    """
    Loads KCE definitions (Nodes, Rules, Workflows) from YAML configuration
    files and converts them into RDF triples in the knowledge base.
    """

    def __init__(self, store_manager: StoreManager, base_path_for_relative_scripts: Optional[Path] = None):
        """
        Initializes the DefinitionLoader.

        Args:
            store_manager: An instance of StoreManager to interact with the RDF graph.
            base_path_for_relative_scripts: The base path from which relative script paths
                                            in node definitions should be resolved. If None,
                                            the YAML file's directory will be used.
        """
        self.store = store_manager
        # base_path_for_relative_scripts allows to set a project root for scripts
        # If not set, script paths are relative to the YAML definition file itself.
        self.base_path_for_scripts = base_path_for_relative_scripts
        kce_logger.info("DefinitionLoader initialized.")

    def load_definitions_from_yaml(self, yaml_file_path: Union[str, Path], perform_reasoning_after_load: bool = True):
        """
        Loads all types of definitions (nodes, rules, workflows) from a single YAML file.
        The YAML file is expected to have top-level keys like 'nodes', 'rules', 'workflows'.

        Args:
            yaml_file_path: Path to the YAML definition file.
            perform_reasoning_after_load: Whether to trigger reasoning after loading definitions.
        """
        path = Path(yaml_file_path)
        kce_logger.info(f"Loading definitions from YAML file: {path}")
        yaml_data = load_yaml_file(path) # Raises DefinitionError on failure

        # Determine the base path for resolving relative script paths
        # If a global base_path_for_scripts is set, use it. Otherwise, use the YAML file's dir.
        current_script_base_path = self.base_path_for_scripts if self.base_path_for_scripts else path.parent

        triples_to_add = []

        if 'nodes' in yaml_data and isinstance(yaml_data['nodes'], list):
            for node_def in yaml_data['nodes']:
                triples_to_add.extend(self._parse_node_definition(node_def, current_script_base_path))
        else:
            kce_logger.debug(f"No 'nodes' section found or not a list in {path}")

        if 'rules' in yaml_data and isinstance(yaml_data['rules'], list):
            for rule_def in yaml_data['rules']:
                triples_to_add.extend(self._parse_rule_definition(rule_def))
        else:
            kce_logger.debug(f"No 'rules' section found or not a list in {path}")

        if 'workflows' in yaml_data and isinstance(yaml_data['workflows'], list):
            for workflow_def in yaml_data['workflows']:
                triples_to_add.extend(self._parse_workflow_definition(workflow_def))
        else:
            kce_logger.debug(f"No 'workflows' section found or not a list in {path}")
        
        if not triples_to_add:
            kce_logger.warning(f"No valid definitions found in {path}. Nothing loaded.")
            return

        try:
            self.store.add_triples(iter(triples_to_add), perform_reasoning=perform_reasoning_after_load)
            kce_logger.info(f"Successfully loaded {len(triples_to_add)} triples from definitions in {path}.")
        except Exception as e:
            raise DefinitionError(f"Error adding definition triples from {path} to store: {e}")


    def _parse_node_definition(self, node_def: Dict[str, Any], script_base_path: Path) -> List[tuple]:
        """Parses a single node definition from YAML data into RDF triples."""
        triples = []
        node_id = node_def.get('id')
        if not node_id:
            raise DefinitionError("Node definition missing 'id'.")
        
        node_uri = to_uriref(node_id) # Assumes id is a URI or prefixed name
        node_type_str = node_def.get('type', 'AtomicNode') # Default to AtomicNode

        if node_type_str == 'AtomicNode':
            triples.append((node_uri, RDF.type, KCE.AtomicNode))
        elif node_type_str == 'CompositeNode':
            triples.append((node_uri, RDF.type, KCE.CompositeNode))
        else:
            raise DefinitionError(f"Unknown node type '{node_type_str}' for node '{node_id}'. Must be 'AtomicNode' or 'CompositeNode'.")
        
        triples.append((node_uri, RDF.type, KCE.Node)) # Also assert it's a generic KCE Node

        if 'label' in node_def:
            triples.append((node_uri, RDFS.label, Literal(node_def['label'])))
        if 'description' in node_def:
            triples.append((node_uri, DCTERMS.description, Literal(node_def['description'])))

        # Input Parameters
        for param_def in node_def.get('inputs', []):
            param_uri, param_triples = self._parse_parameter(param_def, node_uri, KCE.InputParameter)
            triples.append((node_uri, KCE.hasInputParameter, param_uri))
            triples.extend(param_triples)

        # Output Parameters
        for param_def in node_def.get('outputs', []):
            param_uri, param_triples = self._parse_parameter(param_def, node_uri, KCE.OutputParameter)
            triples.append((node_uri, KCE.hasOutputParameter, param_uri))
            triples.extend(param_triples)

        # Invocation Spec (for AtomicNode)
        if node_type_str == 'AtomicNode':
            invocation_spec = node_def.get('invocation')
            if not invocation_spec or not isinstance(invocation_spec, dict):
                raise DefinitionError(f"AtomicNode '{node_id}' missing 'invocation' specification or it's not a dict.")
            
            # Create a BNode or named URI for the invocation spec
            spec_uri = BNode() # Or generate a URI: node_uri + "/invocationSpec"
            triples.append((node_uri, KCE.hasInvocationSpec, spec_uri))
            
            invocation_type = invocation_spec.get('type')
            if invocation_type == 'PythonScript':
                triples.append((spec_uri, RDF.type, KCE.PythonScriptInvocation))
                script_path_str = invocation_spec.get('script_path')
                if not script_path_str:
                    raise DefinitionError(f"PythonScriptInvocation for '{node_id}' missing 'script_path'.")
                
                # Resolve script path
                resolved_script_path = resolve_path(script_base_path, script_path_str)
                triples.append((spec_uri, KCE.scriptPath, Literal(str(resolved_script_path))))
                
                if 'argument_passing_style' in invocation_spec:
                    triples.append((spec_uri, KCE.argumentPassingStyle, Literal(invocation_spec['argument_passing_style'])))
            else:
                raise DefinitionError(f"Unsupported invocation type '{invocation_type}' for node '{node_id}'. MVP supports 'PythonScript'.")

        # Internal Workflow (for CompositeNode)
        if node_type_str == 'CompositeNode':
            internal_workflow_id = node_def.get('internal_workflow_uri')
            if not internal_workflow_id:
                raise DefinitionError(f"CompositeNode '{node_id}' missing 'internal_workflow_uri'.")
            triples.append((node_uri, KCE.hasInternalWorkflow, to_uriref(internal_workflow_id)))

            # I/O Mappings for CompositeNode (Simplified for MVP)
            # Example YAML:
            # mappings:
            #   inputs:
            #     - external_param_name: "compInputX"
            #       internal_workflow_input_name: "wfInputA" # or mapsToInternalPropertyURI
            #   outputs:
            #     - internal_workflow_output_name: "wfOutputZ"
            #       external_param_name: "compOutputY"
            mappings = node_def.get('mappings', {})
            for map_type, map_list in mappings.items(): # 'inputs', 'outputs'
                if map_type == 'inputs':
                    map_predicate = KCE.mapsInputToInternal
                elif map_type == 'outputs':
                    map_predicate = KCE.mapsInternalToOutput
                else:
                    continue

                for mapping_item in map_list:
                    mapping_bnode = BNode()
                    triples.append((node_uri, map_predicate, mapping_bnode))
                    if 'external_param_name' in mapping_item:
                        triples.append((mapping_bnode, KCE.externalParameterName, Literal(mapping_item['external_param_name'])))
                    if 'internal_workflow_input_name' in mapping_item: # For input mapping
                        triples.append((mapping_bnode, KCE.internalParameterName, Literal(mapping_item['internal_workflow_input_name'])))
                    if 'internal_workflow_output_name' in mapping_item: # For output mapping
                         triples.append((mapping_bnode, KCE.internalParameterName, Literal(mapping_item['internal_workflow_output_name']))) # Re-use for simplicity
                    # Could also add kce:mapsToInternalPropertyURI if mapping directly to a property

        return triples

    def _parse_parameter(self, param_def: Dict[str, Any], parent_node_uri: URIRef, param_rdf_type: URIRef) -> tuple[URIRef, List[tuple]]:
        """Parses a single input or output parameter definition."""
        triples = []
        param_name = param_def.get('name')
        if not param_name:
            raise DefinitionError(f"Parameter for node '{parent_node_uri}' missing 'name'.")

        # Create a BNode or named URI for the parameter instance
        # Using BNode is simpler for MVP, less URI management.
        param_uri = BNode() # Or generate a URI: parent_node_uri + f"/param/{param_name}"
        
        triples.append((param_uri, RDF.type, param_rdf_type))
        triples.append((param_uri, KCE.parameterName, Literal(param_name)))

        maps_to_prop_str = param_def.get('maps_to_rdf_property')
        if not maps_to_prop_str:
            raise DefinitionError(f"Parameter '{param_name}' for node '{parent_node_uri}' missing 'maps_to_rdf_property'.")
        triples.append((param_uri, KCE.mapsToRdfProperty, to_uriref(maps_to_prop_str))) # Assumes prefixed name or full URI

        if 'data_type' in param_def:
            xsd_type_uri = get_xsd_uriref(param_def['data_type'])
            if xsd_type_uri:
                triples.append((param_uri, KCE.dataType, xsd_type_uri))
            else:
                kce_logger.warning(f"Unknown XSD data_type '{param_def['data_type']}' for parameter '{param_name}'. Defaulting to xsd:string or none.")
        
        if param_rdf_type == KCE.InputParameter and 'is_required' in param_def:
            triples.append((param_uri, KCE.isRequired, to_literal(param_def['is_required']))) # Handles bool to xsd:boolean

        return param_uri, triples

    def _parse_rule_definition(self, rule_def: Dict[str, Any]) -> List[tuple]:
        """Parses a single rule definition from YAML data into RDF triples."""
        triples = []
        rule_id = rule_def.get('id')
        if not rule_id:
            raise DefinitionError("Rule definition missing 'id'.")
        
        rule_uri = to_uriref(rule_id)
        triples.append((rule_uri, RDF.type, KCE.Rule))

        if 'label' in rule_def:
            triples.append((rule_uri, RDFS.label, Literal(rule_def['label'])))
        if 'description' in rule_def:
            triples.append((rule_uri, DCTERMS.description, Literal(rule_def['description'])))

        condition_sparql = rule_def.get('condition_sparql')
        if not condition_sparql:
            raise DefinitionError(f"Rule '{rule_id}' missing 'condition_sparql'.")
        triples.append((rule_uri, KCE.hasConditionSPARQL, Literal(condition_sparql)))

        action_node_id = rule_def.get('action_node_uri')
        if not action_node_id:
            raise DefinitionError(f"Rule '{rule_id}' missing 'action_node_uri'.")
        triples.append((rule_uri, KCE.hasActionNodeURI, to_uriref(action_node_id)))

        if 'priority' in rule_def:
            triples.append((rule_uri, KCE.priority, to_literal(rule_def['priority']))) # Handles int to xsd:integer

        return triples

    def _parse_workflow_definition(self, workflow_def: Dict[str, Any]) -> List[tuple]:
        """Parses a single workflow definition from YAML data into RDF triples."""
        triples = []
        workflow_id = workflow_def.get('id')
        if not workflow_id:
            raise DefinitionError("Workflow definition missing 'id'.")

        workflow_uri = to_uriref(workflow_id)
        triples.append((workflow_uri, RDF.type, KCE.Workflow))

        if 'label' in workflow_def:
            triples.append((workflow_uri, RDFS.label, Literal(workflow_def['label'])))
        if 'description' in workflow_def:
            triples.append((workflow_uri, DCTERMS.description, Literal(workflow_def['description'])))

        steps = workflow_def.get('steps', [])
        if not steps or not isinstance(steps, list):
            raise DefinitionError(f"Workflow '{workflow_id}' has no 'steps' or it's not a list.")

        previous_step_uri = None # For linking linear steps in MVP
        for i, step_def in enumerate(steps):
            step_bnode = BNode() # Each step is a blank node related to the workflow
            triples.append((workflow_uri, KCE.hasStep, step_bnode))
            triples.append((step_bnode, RDF.type, KCE.WorkflowStep))

            executes_node_id = step_def.get('executes_node_uri')
            if not executes_node_id:
                raise DefinitionError(f"Step {i+1} in workflow '{workflow_id}' missing 'executes_node_uri'.")
            triples.append((step_bnode, KCE.executesNode, to_uriref(executes_node_id)))

            # Order for MVP (can also be used for sorting if steps are not explicitly linked)
            order = step_def.get('order', i + 1) # Default to list order
            triples.append((step_bnode, KCE.order, to_literal(order)))

            # For MVP linear flow, link steps explicitly (optional, order might be enough)
            # If kce:nextStep is used, the WorkflowExecutor will follow these links.
            # If only kce:order is used, WorkflowExecutor sorts by order.
            # Let's assume for MVP kce:order is primary for simplicity.
            # If you want to enforce strict linear linking:
            # if previous_step_uri:
            #    triples.append((previous_step_uri, KCE.nextStep, step_bnode))
            # previous_step_uri = step_bnode
        return triples


if __name__ == '__main__':
    # --- Example Usage and Basic Test ---
    kce_logger.setLevel(logging.DEBUG)
    
    # Mock StoreManager for testing loader independently
    class MockStoreManager:
        def __init__(self):
            self.triples_added = []
            kce_logger.info("MockStoreManager initialized for loader test.")
        def add_triples(self, triples_iter, perform_reasoning=True):
            added = list(triples_iter)
            self.triples_added.extend(added)
            kce_logger.info(f"MockStoreManager: Added {len(added)} triples. Reasoning: {perform_reasoning}")
        def get_graph(self): # Dummy method if needed by other parts (not by loader directly)
            return None

    mock_store = MockStoreManager()
    
    # Create a dummy base path for script resolution (e.g., project root)
    # In a real scenario, this might be determined by where the KCE CLI is run from
    # or a configuration setting. For testing, we can set it to current dir.
    test_project_root = Path(__file__).parent.parent.parent / "examples" # Point to where 'scripts' might be
    
    loader = DefinitionLoader(mock_store, base_path_for_relative_scripts=test_project_root)

    # Create a dummy YAML file for testing
    dummy_yaml_content = f"""
nodes:
  - id: ex:NodeA
    type: AtomicNode
    label: "First Test Node"
    description: "This is node A."
    inputs:
      - name: "input1"
        maps_to_rdf_property: "ex:inputValue"
        data_type: "integer"
        is_required: true
    outputs:
      - name: "output1"
        maps_to_rdf_property: "ex:outputValue"
        data_type: "string"
    invocation:
      type: "PythonScript"
      script_path: "elevator_panel_simplified/scripts/calculate_thickness.py" # Relative path
      argument_passing_style: "commandline"

  - id: ex:CompNodeB
    type: CompositeNode
    label: "Composite Node B"
    internal_workflow_uri: "ex:InternalWorkflow1"
    mappings:
      inputs:
        - external_param_name: "compIn"
          internal_workflow_input_name: "wfIn"
      outputs:
        - internal_workflow_output_name: "wfOut"
          external_param_name: "compOut"

rules:
  - id: ex:Rule1
    label: "A simple rule"
    condition_sparql: "ASK {{ ?s ex:someProp ?o . }}"
    action_node_uri: "ex:NodeA"
    priority: 1

workflows:
  - id: ex:MainWorkflow
    label: "Main Test Workflow"
    steps:
      - executes_node_uri: "ex:NodeA"
        order: 1
      - executes_node_uri: "ex:CompNodeB" # Assuming CompNodeB is defined elsewhere or self-contained
        order: 2
  - id: ex:InternalWorkflow1 # Referenced by CompNodeB
    label: "Internal Workflow for Composite Node"
    steps:
      - executes_node_uri: "ex:InternalNodeX" # Assume ex:InternalNodeX is defined
        order: 1
"""
    test_yaml_path = Path("test_definitions_temp.yaml")
    with open(test_yaml_path, "w", encoding="utf-8") as f:
        f.write(dummy_yaml_content)

    try:
        loader.load_definitions_from_yaml(test_yaml_path)
        kce_logger.info(f"Total triples generated by loader: {len(mock_store.triples_added)}")
        
        # Basic checks
        assert len(mock_store.triples_added) > 10 # Expect a decent number of triples
        
        # Check if a known triple exists (example)
        node_a_uri = EX.NodeA
        found_node_a_type = any(
            s == node_a_uri and p == RDF.type and o == KCE.AtomicNode
            for s, p, o in mock_store.triples_added
        )
        assert found_node_a_type, "ex:NodeA type triple not found."

        found_script_path = False
        for s,p,o in mock_store.triples_added:
            if p == KCE.scriptPath:
                kce_logger.debug(f"Script path triple: {s} {p} {o}")
                # Check if the path was resolved correctly (this depends on your test_project_root)
                # For this example, just check if it contains the original relative part
                if "elevator_panel_simplified/scripts/calculate_thickness.py" in str(o):
                    assert Path(str(o)).is_absolute(), "Script path should be absolute after resolution."
                    found_script_path = True
        assert found_script_path, "Script path for NodeA not found or not resolved as expected."


        kce_logger.info("DefinitionLoader test with dummy YAML seemed to work.")

    except DefinitionError as e:
        kce_logger.error(f"DefinitionLoader test failed: {e}")
    finally:
        if test_yaml_path.exists():
            test_yaml_path.unlink() # Clean up

    kce_logger.info("DefinitionLoader tests completed.")