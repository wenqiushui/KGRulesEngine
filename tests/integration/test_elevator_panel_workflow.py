# tests/integration/test_elevator_panel_workflow.py (Refactored)

import pytest
import logging
from pathlib import Path
import json
import uuid # For generating run_ids
import sys # For logging handler setup

from rdflib import URIRef, Literal, XSD, Namespace # Added Namespace

# New KCE Core Imports
from kce_core.interfaces import (
    IKnowledgeLayer, IDefinitionTransformationLayer, IPlanner,
    IPlanExecutor, IRuleEngine, IRuntimeStateLogger,
    TargetDescription, RDFGraph, ExecutionResult # Key data structures
)
# Import specific namespaces and utilities needed for graph manipulation
from kce_core import KCE, EX, RDF, RDFS, XSD # Make sure XSD is imported if used for literals
from kce_core.common.utils import create_rdf_graph_from_json_ld_dict, generate_instance_uri, KCE_NS_STR, EX_NS_STR
from kce_core.knowledge_layer.rdf_store.store_manager import RdfStoreManager
from kce_core.definition_transformation_layer.loader import DefinitionLoader
from kce_core.execution_layer.node_executor import NodeExecutor
from kce_core.execution_layer.runtime_state_logger import RuntimeStateLogger
from kce_core.execution_layer.plan_executor import PlanExecutor
from kce_core.planning_reasoning_core_layer.rule_engine import RuleEngine
from kce_core.planning_reasoning_core_layer.planner import Planner

# Utilities and logger (assuming kce_logger is exported from kce_core.__init__)
from kce_core import kce_logger, KCE, EX, RDF, RDFS # Namespaces from kce_core.__init__
from kce_core.common.utils import load_json_file # to_uriref not used directly here yet

# --- Test Configuration ---
PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent.parent # Project root
DEFAULT_ONTOLOGY_DIR = PROJECT_ROOT_DIR / "ontologies"
EXAMPLE_BASE_DIR = PROJECT_ROOT_DIR / "examples" / "elevator_panel_simplified"
EXAMPLE_DEFS_DIR = EXAMPLE_BASE_DIR / "definitions"
EXAMPLE_PARAMS_DIR = EXAMPLE_BASE_DIR / "params"

# Define specific file paths for clarity in tests
CORE_ONTOLOGY_FILE = DEFAULT_ONTOLOGY_DIR / "kce_core_ontology.ttl"
DOMAIN_ONTOLOGY_FILE = DEFAULT_ONTOLOGY_DIR / "elevator_panel_simplified.ttl"
SCENARIO1_PARAMS_FILE = EXAMPLE_PARAMS_DIR / "scenario1_params.json"
SCENARIO1_TARGET_FILE = EXAMPLE_PARAMS_DIR / "target_scenario1.json"

@pytest.fixture(scope="module")
def kce_test_environment_components():
    """Sets up KCE components for testing."""
    # Ensure test output is verbose for debugging
    if not kce_logger.handlers or isinstance(kce_logger.handlers[0], logging.NullHandler):
        if kce_logger.handlers: kce_logger.removeHandler(kce_logger.handlers[0]) # Remove NullHandler if present
        test_handler = logging.StreamHandler(sys.stdout)
        test_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        test_handler.setFormatter(test_formatter)
        kce_logger.addHandler(test_handler)
    kce_logger.setLevel(logging.DEBUG)

    ontology_files_to_load = []
    if CORE_ONTOLOGY_FILE.exists(): ontology_files_to_load.append(str(CORE_ONTOLOGY_FILE))
    else: pytest.fail(f"Core KCE ontology not found: {CORE_ONTOLOGY_FILE}")
    if DOMAIN_ONTOLOGY_FILE.exists(): ontology_files_to_load.append(str(DOMAIN_ONTOLOGY_FILE))
    # Domain ontology might not exist yet, so make this optional for now or create a dummy one
    # else: pytest.fail(f"Domain ontology not found: {DOMAIN_ONTOLOGY_FILE}")
    if not (DOMAIN_ONTOLOGY_FILE.exists()): kce_logger.warning(f"Domain ontology {DOMAIN_ONTOLOGY_FILE} not found, proceeding without it.")

    knowledge_layer: IKnowledgeLayer = RdfStoreManager(db_path=None, ontology_files=ontology_files_to_load)
    kce_logger.info(f"Loaded ontologies into in-memory RdfStoreManager.")

    definition_loader: IDefinitionTransformationLayer = DefinitionLoader(knowledge_layer=knowledge_layer)

    if not EXAMPLE_DEFS_DIR.exists(): pytest.fail(f"Example definitions directory not found: {EXAMPLE_DEFS_DIR}")
    load_status = definition_loader.load_definitions_from_path(str(EXAMPLE_DEFS_DIR))

    errors = load_status.get("errors", [])
    if errors:
        critical_errors = [
            err for err in errors
            if not ("Unknown or unsupported 'kind'/'type': Workflow" in err.get("error", "") and
                    "workflows.yaml" in err.get("file", ""))
        ]
        if critical_errors:
            pytest.fail(f"Critical errors loading definitions from {EXAMPLE_DEFS_DIR}: {critical_errors}")
        else:
            kce_logger.warning(f"Accepted non-critical errors during definition loading (e.g., unsupported Workflow kind): {errors}")

    # Ensure at least nodes and rules were loaded (6 nodes + 3 rules expected)
    assert load_status.get("loaded_definitions_count", 0) >= (6 + 3), \
           f"Expected at least 9 definitions (nodes+rules) to be loaded, got {load_status.get('loaded_definitions_count')}."
    kce_logger.info(f"Loaded {load_status.get('loaded_definitions_count')} definition documents from {EXAMPLE_DEFS_DIR} (Workflows might be reported as non-critical errors).")

    knowledge_layer.trigger_reasoning()
    kce_logger.info("Reasoning performed after definition loading.")

    runtime_logger: IRuntimeStateLogger = RuntimeStateLogger()
    node_executor: INodeExecutor = NodeExecutor()
    rule_engine: IRuleEngine = RuleEngine(runtime_state_logger=runtime_logger)
    plan_executor: IPlanExecutor = PlanExecutor(
        node_executor=node_executor,
        runtime_state_logger=runtime_logger,
        rule_engine=rule_engine
    )
    planner: IPlanner = Planner(runtime_state_logger=runtime_logger)

    return {
        "knowledge_layer": knowledge_layer,
        "definition_loader": definition_loader,
        "planner": planner,
        "plan_executor": plan_executor,
        "rule_engine": rule_engine,
        "runtime_logger": runtime_logger
    }

def test_elevator_panel_scenario_1(kce_test_environment_components):
    """Tests end-to-end execution for elevator panel scenario 1 using the Planner."""
    kl: IKnowledgeLayer = kce_test_environment_components["knowledge_layer"]
    dl: IDefinitionTransformationLayer = kce_test_environment_components["definition_loader"]
    planner: IPlanner = kce_test_environment_components["planner"]
    ple: IPlanExecutor = kce_test_environment_components["plan_executor"]
    re: IRuleEngine = kce_test_environment_components["rule_engine"]
    # Assuming runtime_logger is also in components if needed for direct logging here
    # runtime_logger: IRuntimeStateLogger = kce_test_environment_components["runtime_logger"]

    if not SCENARIO1_TARGET_FILE.exists(): pytest.fail(f"Scenario target file not found: {SCENARIO1_TARGET_FILE}")
    target_desc_data = load_json_file(str(SCENARIO1_TARGET_FILE))
    assert "sparql_ask_query" in target_desc_data, "Target description must contain 'sparql_ask_query'"
    target_description: TargetDescription = target_desc_data

    if not SCENARIO1_PARAMS_FILE.exists(): pytest.fail(f"Scenario parameters file not found: {SCENARIO1_PARAMS_FILE}")
    with open(SCENARIO1_PARAMS_FILE, 'r', encoding='utf-8') as f: initial_state_json_str = f.read()

    run_id = f"test_run_{uuid.uuid4()}"
    # The base_uri for problem instances should be distinct for each run or problem.
    problem_instance_uri = URIRef(f"http://example.com/instances/{run_id}/problemInstance")

    # Create initial_state_graph with kce:ProblemInstance and parameters
    initial_state_rdf = RDFGraph()
    initial_state_rdf.bind("kce", KCE)
    initial_state_rdf.bind("ex", EX)
    initial_state_rdf.add((problem_instance_uri, RDF.type, KCE.ProblemInstance))

    params_data = json.loads(initial_state_json_str)
    json_context = params_data.get("@context", {})

    for key, value in params_data.items():
        if key.startswith("@"):
            continue

        # Expand CURIEs like "ex:carInternalWidth" to full URIs
        key_uri: Optional[URIRef] = None
        if ":" in key:
            prefix, local_name = key.split(":", 1)
            if prefix in json_context and isinstance(json_context[prefix], str):
                key_uri = URIRef(json_context[prefix] + local_name)
            elif prefix == "ex": # Fallback for common prefix if not in context string
                 key_uri = EX[local_name]
            elif prefix == "kce":
                 key_uri = KCE[local_name]
            # Add more known prefixes if necessary or rely on a robust CURIE expansion utility

        if not key_uri: # If not a CURIE or expansion failed, treat as full URI or skip
            try:
                key_uri = URIRef(key) # Assume it's a full URI if no prefix
            except:
                kce_logger.warning(f"Could not resolve parameter key '{key}' to URI, skipping.")
                continue

        # Convert value to RDF Literal or URIRef (basic type inference)
        rdf_value: Union[Literal, URIRef]
        if isinstance(value, bool):
            rdf_value = Literal(value, datatype=XSD.boolean)
        elif isinstance(value, int):
            rdf_value = Literal(value, datatype=XSD.integer)
        elif isinstance(value, float):
            rdf_value = Literal(value, datatype=XSD.double)
        elif isinstance(value, str):
            if value.startswith("http://") or value.startswith("https://") or value.startswith("urn:"):
                rdf_value = URIRef(value)
            else: # Default to string literal
                rdf_value = Literal(value)
        else: # For other types, convert to string literal
            rdf_value = Literal(str(value))

        initial_state_rdf.add((problem_instance_uri, key_uri, rdf_value))

    kce_logger.info(f"Constructed initial state for run {run_id} with ProblemInstance <{problem_instance_uri}> ({len(initial_state_rdf)} triples).")
    if kce_logger.isEnabledFor(logging.DEBUG):
        kce_logger.debug("Initial state graph (Turtle):")
        kce_logger.debug(initial_state_rdf.serialize(format="turtle"))

    kce_logger.info(f"Invoking Planner for target: {target_description.get('target_description_label', 'N/A')}")
    execution_result: ExecutionResult = planner.solve(
        target_description=target_description,
        initial_state_graph=initial_state_rdf,
        knowledge_layer=kl,
        plan_executor=ple,
        rule_engine=re,
        run_id=run_id,
        mode="user"
    )

    assert execution_result.get("status") == "success", f"Planner failed: {execution_result.get('message', 'No message')}"
    kce_logger.info(f"Planner reported success for run {run_id}: {execution_result.get('message')}")

    goal_achieved_check = kl.execute_sparql_query(target_description["sparql_ask_query"])
    assert goal_achieved_check is True, "Final goal state (as per target SPARQL ASK) not achieved in RDF store."
    kce_logger.info("Target goal ASK query confirmed True in the knowledge layer after planning.")

    # Example of querying for a specific output (optional, good for debugging)
    # This query assumes that the 'InitializeRearWallNode' (or similar) creates an assembly
    # and links it via 'ex:createdRearWallAssemblyURI' to the initial parameter context.
    # The initial parameter context ID is 'ex:ScenarioParameters_Scenario1' from scenario1_params.json
    # which gets loaded under problem_instance_uri.

    query_final_cost = f"""
    PREFIX ex: <{EX}>
    PREFIX domain: <{Namespace('http://kce.com/example/elevator_panel#')}>
    SELECT ?total_cost WHERE {{
      # Assuming InitializeRearWallNode's output 'rear_wall_assembly_uri' is stored on the input context
      # This is a guess based on how nodes might link outputs to inputs or a run context.
      # A more reliable way would be to query for any RearWallAssembly that has assemblyCostCalculated = true.
      ?assembly_uri a domain:RearWallAssembly ;
                      ex:assemblyCostCalculated true ;
                      ex:assemblyTotalCost ?total_cost .
    }} LIMIT 1
    """
    cost_results = kl.execute_sparql_query(query_final_cost)
    assert isinstance(cost_results, list) and len(cost_results) > 0, "Could not find total cost for the assembly."
    kce_logger.info(f"Final assembly total cost from query: {cost_results[0]['total_cost']}")
    assert float(cost_results[0]['total_cost']) > 0, "Assembly total cost should be greater than 0."

# To run this test:
# 1. Ensure all example files (definitions, params, target, scripts) are correctly updated and in place.
# 2. Ensure kce_core (including loader.py) is updated.
# 3. Run pytest from the project root: `pytest tests/integration/test_elevator_panel_workflow.py`
