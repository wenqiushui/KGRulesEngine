# tests/integration/test_elevator_panel_workflow.py

import pytest
import logging
from pathlib import Path
import json

from rdflib import URIRef, Literal, XSD
from owlrl import OWLRL_Semantics # Import OWLRL_Semantics

# Import KCE core components (assuming they are installable or PYTHONPATH is set)
from kce_core import (
    StoreManager,
    DefinitionLoader,
    WorkflowExecutor,
    NodeExecutor,
    RuleEvaluator,
    ProvenanceLogger,
    kce_logger,
    sparql_queries, # For direct queries if needed for assertions
    KCE, EX, RDF, RDFS # Namespaces
)
from kce_core.common.utils import load_json_file # For loading expected results

# --- Test Configuration ---
BASE_DIR = Path(__file__).parent.parent.parent # Project root
ONTOLOGY_DIR = BASE_DIR / "ontologies"
EXAMPLE_DEFS_DIR = BASE_DIR / "examples" / "elevator_panel_simplified" / "definitions"
EXAMPLE_PARAMS_FILE = BASE_DIR / "examples" / "elevator_panel_simplified" / "params" / "scenario1_params.json"
# You might want to create an "expected_results.json" for comparison
EXPECTED_RESULTS_FILE = BASE_DIR / "tests" / "test_data" / "elevator_panel_expected_results.json"


@pytest.fixture(scope="module") # Run once per test module for setup
def kce_test_environment():
    """
    Sets up a KCE environment for testing the elevator panel workflow.
    Initializes StoreManager, loads ontologies and definitions.
    """
    kce_logger.setLevel(logging.DEBUG) # Enable debug logging for tests

    # Use an in-memory store for isolated testing
    store_manager = StoreManager(db_path=None, auto_reason=True) # Enable auto-reasoning

    # 1. Load Core Ontology
    core_ontology_path = ONTOLOGY_DIR / "kce_core_ontology.ttl"
    if core_ontology_path.exists():
        store_manager.load_rdf_file(core_ontology_path, perform_reasoning=False) # Reason after all loads
        kce_logger.info(f"Loaded core ontology: {core_ontology_path}")
    else:
        pytest.fail(f"Core ontology not found: {core_ontology_path}")

    # 2. Load Domain Ontology
    domain_ontology_path = ONTOLOGY_DIR / "elevator_panel_simplified.ttl"
    if domain_ontology_path.exists():
        store_manager.load_rdf_file(domain_ontology_path, perform_reasoning=False)
        kce_logger.info(f"Loaded domain ontology: {domain_ontology_path}")
    else:
        pytest.fail(f"Domain ontology not found: {domain_ontology_path}")
    
    # Perform reasoning after all ontologies are loaded
    store_manager.perform_reasoning()


    # 3. Initialize other KCE components
    prov_logger = ProvenanceLogger(store_manager)
    node_exec = NodeExecutor(store_manager, prov_logger)
    rule_eval = RuleEvaluator(store_manager, prov_logger)
    
    # For DefinitionLoader, script paths are relative to YAMLs or a base path.
    # If YAMLs use "../scripts/", and YAMLs are in EXAMPLE_DEFS_DIR, then base is EXAMPLE_DEFS_DIR.parent
    script_base_path = EXAMPLE_DEFS_DIR.parent 
    definition_loader = DefinitionLoader(store_manager, base_path_for_relative_scripts=script_base_path)
    
    workflow_executor = WorkflowExecutor(store_manager, node_exec, rule_eval, prov_logger)

    # 4. Load Workflow Definitions (nodes, rules, workflows YAMLs)
    yaml_files = [
        EXAMPLE_DEFS_DIR / "nodes.yaml",
        EXAMPLE_DEFS_DIR / "rules.yaml", # May be empty or have conceptual rules
        EXAMPLE_DEFS_DIR / "workflows.yaml"
    ]
    for yaml_file in yaml_files:
        if yaml_file.exists():
            definition_loader.load_definitions_from_yaml(yaml_file, perform_reasoning_after_load=True) # Reason after each def file
            kce_logger.info(f"Loaded definitions from: {yaml_file}")
        else:
            # Fail if core definition files are missing; rules might be optional
            if "rules.yaml" not in str(yaml_file):
                 pytest.fail(f"Definition YAML not found: {yaml_file}")
            else:
                kce_logger.warning(f"Optional rules definition YAML not found: {yaml_file}")
    
    return store_manager, workflow_executor, definition_loader # Return what's needed for tests


def load_expected_results():
    """Loads expected results from a JSON file."""
    if EXPECTED_RESULTS_FILE.exists():
        return load_json_file(EXPECTED_RESULTS_FILE)
    else:
        # For the first run, you might not have this. The test will help generate it.
        kce_logger.warning(f"Expected results file not found: {EXPECTED_RESULTS_FILE}. Test will log actual results.")
        return None

# --- The Test Function ---
def test_elevator_panel_scenario_1(kce_test_environment):
    """
    Tests the end-to-end execution of the simplified elevator panel workflow
    with scenario 1 parameters and validates the outputs.
    """
    store_manager, workflow_executor, _ = kce_test_environment
    expected_results_data = load_expected_results()

    # 1. Load Input Parameters for the scenario
    if not EXAMPLE_PARAMS_FILE.exists():
        pytest.fail(f"Scenario parameters file not found: {EXAMPLE_PARAMS_FILE}")
    
    params_json_str: str
    with open(EXAMPLE_PARAMS_FILE, 'r') as f:
        params_json_str = f.read()

    # 2. Define the Workflow URI to execute
    workflow_uri_to_run = EX.SimplifiedElevatorPanelWorkflow # From workflows.yaml

    # 3. Execute the Workflow
    kce_logger.info(f"Executing workflow: {workflow_uri_to_run} with params from {EXAMPLE_PARAMS_FILE}")
    success = workflow_executor.execute_workflow(
        workflow_uri_to_run,
        initial_parameters_json=params_json_str
    )
    assert success, "Workflow execution reported failure."

    # 4. Query RDF Store for Results
    #    We need to know the URI of the RearWallAssembly instance created by the workflow.
    #    The InitializeRearWallNode is expected to store this URI on the workflow instance context.
    #    The workflow instance context URI is typically kce:instance_data/<run_id_uuid_part>

    #    First, find the latest run_id_uri (not ideal, better if workflow_executor returned it)
    #    For a test, we can assume it's the only/latest one.
    #    A better way: workflow_executor.execute_workflow could return the run_id_uri or context_uri.
    #    For now, let's query for the created RearWallAssembly instance based on some property.
    
    #    Alternative: Get the instance_context_uri from the provenance log for the run.
    #    This is a bit complex for a direct test query without knowing the run_id.
    #    Let's assume InitializeRearWallNode creates exactly one RearWallAssembly for this test.
    
    query_assembly = sparql_queries.format_query("""
        SELECT ?assembly_uri ?total_cost ?total_width ?total_height
        WHERE {{
            ?assembly_uri rdf:type <{ex_ns}RearWallAssembly> .
            OPTIONAL {{ ?assembly_uri <{ex_ns}assemblyTotalCost> ?total_cost . }}
            OPTIONAL {{ ?assembly_uri <{ex_ns}assemblyTotalWidth> ?total_width . }}
            OPTIONAL {{ ?assembly_uri <{ex_ns}assemblyTotalHeight> ?total_height . }}
        }}
    """, ex_ns=str(EX)) # Pass EX namespace to format_query

    assembly_results = store_manager.query(query_assembly)
    assert len(assembly_results) == 1, "Expected exactly one RearWallAssembly instance to be created."
    assembly_data = assembly_results[0]
    assembly_uri = assembly_data['assembly_uri']
    kce_logger.info(f"Found RearWallAssembly: <{assembly_uri}>")
    kce_logger.info(f"  Total Cost: {assembly_data.get('total_cost')}")
    kce_logger.info(f"  Total Width: {assembly_data.get('total_width')}")
    kce_logger.info(f"  Total Height: {assembly_data.get('total_height')}")


    # Query for individual panel details linked to this assembly
    query_panels = sparql_queries.format_query("""
        SELECT ?panel_uri ?name ?width ?height ?thickness ?bending ?bolt_count ?stiffener_count ?panel_cost
        WHERE {{
            <{assembly_uri}> <{ex_ns}hasPanelPart> ?panel_uri .
            ?panel_uri rdf:type <{ex_ns}ElevatorPanel> .
            OPTIONAL {{ ?panel_uri <{ex_ns}panelName> ?name . }}
            OPTIONAL {{ ?panel_uri <{ex_ns}panelWidth> ?width . }}
            OPTIONAL {{ ?panel_uri <{ex_ns}panelHeight> ?height . }}
            OPTIONAL {{ ?panel_uri <{ex_ns}panelThickness> ?thickness . }}
            OPTIONAL {{ ?panel_uri <{ex_ns}bendingHeight> ?bending . }}
            OPTIONAL {{ ?panel_uri <{ex_ns}boltHoleCount> ?bolt_count . }}
            OPTIONAL {{ ?panel_uri <{ex_ns}stiffenerCount> ?stiffener_count . }}
            OPTIONAL {{ ?panel_uri <{ex_ns}panelTotalCost> ?panel_cost . }}
        }}
        ORDER BY ?name
    """, assembly_uri=str(assembly_uri), ex_ns=str(EX))

    panel_results = store_manager.query(query_panels)
    assert len(panel_results) > 0, "Expected at least one ElevatorPanel instance."
    kce_logger.info(f"\n--- Found {len(panel_results)} Elevator Panels ---")

    actual_panel_data_for_comparison = []
    for i, panel in enumerate(panel_results):
        kce_logger.info(f"Panel {i+1}: <{panel['panel_uri']}>")
        panel_details = {
            "panelName": str(panel.get('name', '')),
            "width": panel.get('width').value if panel.get('width') else None,
            "height": panel.get('height').value if panel.get('height') else None,
            "thickness": panel.get('thickness').value if panel.get('thickness') else None,
            "bendingHeight": panel.get('bending').value if panel.get('bending') else None,
            "boltHoleCount": panel.get('bolt_count').value if panel.get('bolt_count') else None,
            "stiffenerCount": panel.get('stiffener_count').value if panel.get('stiffener_count') else None,
            "panelTotalCost": panel.get('panel_cost').value if panel.get('panel_cost') else None,
        }
        for k, v in panel_details.items():
            kce_logger.info(f"  {k}: {v}")
        actual_panel_data_for_comparison.append(panel_details)

    # 5. Compare with Expected Results
    if expected_results_data:
        # Compare Assembly Total Cost
        expected_total_cost = expected_results_data.get("assembly_total_cost")
        actual_total_cost = assembly_data.get('total_cost').value if assembly_data.get('total_cost') else None
        if expected_total_cost is not None:
            assert actual_total_cost == pytest.approx(expected_total_cost), \
                f"Assembly total cost mismatch: Expected {expected_total_cost}, Got {actual_total_cost}"

        # Compare Panel Data (this requires matching panels, e.g., by name or order if consistent)
        expected_panels = sorted(expected_results_data.get("panels", []), key=lambda p: p.get("panelName", ""))
        actual_panels_sorted = sorted(actual_panel_data_for_comparison, key=lambda p: p.get("panelName", ""))
        
        assert len(actual_panels_sorted) == len(expected_panels), \
            f"Mismatch in number of panels: Expected {len(expected_panels)}, Got {len(actual_panels_sorted)}"

        for i, actual_p in enumerate(actual_panels_sorted):
            expected_p = expected_panels[i]
            kce_logger.info(f"\nComparing panel: {actual_p.get('panelName')}")
            for key in expected_p:
                if key in actual_p: # Only compare keys present in expected
                    expected_val = expected_p[key]
                    actual_val = actual_p[key]
                    if isinstance(expected_val, float):
                        assert actual_val == pytest.approx(expected_val), \
                            f"Panel '{actual_p.get('panelName')}' property '{key}' mismatch: Exp {expected_val}, Got {actual_val}"
                    else:
                        assert actual_val == expected_val, \
                            f"Panel '{actual_p.get('panelName')}' property '{key}' mismatch: Exp {expected_val}, Got {actual_val}"
    else:
        kce_logger.warning("No expected results provided. This test run serves to establish baseline actual results.")
        # You can print the actual_assembly_data and actual_panel_data_for_comparison
        # in a JSON format here to help create the expected_results.json file.
        baseline_output = {
            "assembly_total_cost": assembly_data.get('total_cost').value if assembly_data.get('total_cost') else None,
            "assembly_total_width": assembly_data.get('total_width').value if assembly_data.get('total_width') else None,
            "assembly_total_height": assembly_data.get('total_height').value if assembly_data.get('total_height') else None,
            "panels": actual_panel_data_for_comparison
        }
        kce_logger.info("\n--- ACTUAL RESULTS (for baseline) ---")
        kce_logger.info(json.dumps(baseline_output, indent=2))
        # To fail the test if no expected results, uncomment next line:
        # pytest.fail("Expected results file is missing. Cannot validate outputs.")

# To run this test:
# 1. Make sure all Python scripts in examples/elevator_panel_simplified/scripts/ are implemented.
# 2. Create examples/test_data/elevator_panel_expected_results.json with the correct expected values.
#    (You can run the test once without it to get the actual output, then save that as expected if it's correct)
# 3. Run pytest from the project root: `pytest tests/integration/test_elevator_panel_workflow.py`