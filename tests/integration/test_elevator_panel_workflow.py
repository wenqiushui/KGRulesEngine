# tests/integration/test_elevator_panel_workflow.py (Refactored)

import pytest
import logging
from pathlib import Path
import json
import uuid # For generating run_ids

from rdflib import URIRef, Literal, XSD, Namespace # Added Namespace

# New KCE Core Imports
from kce_core.interfaces import (
    IKnowledgeLayer, IDefinitionTransformationLayer, IPlanner,
    IPlanExecutor, IRuleEngine, IRuntimeStateLogger, # Added IRuntimeStateLogger
    TargetDescription, RDFGraph, ExecutionResult # Key data structures
)
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
    if load_status.get("errors"):
        pytest.fail(f"Errors loading definitions from {EXAMPLE_DEFS_DIR}: {load_status['errors']}")
    kce_logger.info(f"Loaded {load_status.get('loaded_definitions_count')} definition documents from {EXAMPLE_DEFS_DIR}")

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

    if not SCENARIO1_TARGET_FILE.exists(): pytest.fail(f"Scenario target file not found: {SCENARIO1_TARGET_FILE}")
    target_desc_data = load_json_file(str(SCENARIO1_TARGET_FILE))
    assert "sparql_ask_query" in target_desc_data, "Target description must contain 'sparql_ask_query'"
    target_description: TargetDescription = target_desc_data

    if not SCENARIO1_PARAMS_FILE.exists(): pytest.fail(f"Scenario parameters file not found: {SCENARIO1_PARAMS_FILE}")
    with open(SCENARIO1_PARAMS_FILE, 'r', encoding='utf-8') as f: initial_state_json_str = f.read()
    
    run_id = f"test_run_{uuid.uuid4()}"
    # The base_uri for problem instances should be distinct for each run or problem to avoid clashes.
    # Using a UUID in the path or a run-specific segment.
    instance_base_uri = f"http://example.com/instances/{run_id}/problem_data#" # Added '#' for proper URI construction

    initial_state_rdf: RDFGraph = dl.load_initial_state_from_json(initial_state_json_str, base_uri=instance_base_uri)
    kce_logger.info(f"Loaded initial state for run {run_id} ({len(initial_state_rdf)} triples).")

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
    # which gets loaded under instance_base_uri.
    
    # Note: The original test had a fixed context URI. Here, it's dynamic with run_id.
    # For a robust query, the link between initial params and output assembly needs to be clear.
    # If InitializeRearWallNode sets ex:createdRearWallAssemblyURI on the @id from scenario1_params.json, we can query it.
    initial_params_instance_uri = URIRef(instance_base_uri + "ScenarioParameters_Scenario1")

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
