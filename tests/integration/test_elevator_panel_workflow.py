# tests/integration/test_elevator_panel_workflow.py (Refactored)

import pytest
import logging
import sys # Import sys
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
from kce_core.common.utils import load_json_file, create_rdf_graph_from_json_ld_dict

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

# @pytest.fixture(scope="module") # Removed duplicate fixture decorator
@pytest.fixture(scope="function")
def kce_test_environment_components():
    # Configure logging for kce_core to DEBUG level
    logging.basicConfig(level=logging.DEBUG) # Set root logger to DEBUG
    kce_core_logger = logging.getLogger('kce_core')
    kce_core_logger.setLevel(logging.DEBUG)
    # Ensure handlers are set up to output to console
    if not kce_core_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(levelname)s:%(name)s:%(filename)s:%(lineno)d:%(message)s')
        handler.setFormatter(formatter)
        kce_core_logger.addHandler(handler)

    # Initialize RDF store manager
    kl = RdfStoreManager(db_path=None, ontology_files=[str(CORE_ONTOLOGY_FILE), str(DOMAIN_ONTOLOGY_FILE)]) # Use in-memory for testing
    # kl.load_ontology(CORE_ONTOLOGY_PATH) # Removed as ontologies are loaded in constructor
    # kl.load_ontology(DOMAIN_ONTOLOGY_PATH) # Removed as ontologies are loaded in constructor

    """Sets up KCE components for testing."""
    # Ensure test output is verbose for debugging
    # This is handled by the logging configuration above

    definition_loader = DefinitionLoader(kl)
    # Load example definitions
    definition_loader.load_definitions_from_path(EXAMPLE_DEFS_DIR)
    kl.trigger_reasoning() # Trigger reasoning after loading definitions

    # Initialize Planner, PlanExecutor, RuleEngine
    runtime_logger = RuntimeStateLogger()
    node_executor = NodeExecutor(knowledge_layer=kl) # Initialize NodeExecutor
    planner = Planner(runtime_state_logger=runtime_logger)
    plan_executor = PlanExecutor(node_executor=node_executor, runtime_state_logger=runtime_logger)
    rule_engine = RuleEngine(runtime_state_logger=runtime_logger)

    yield {
        "knowledge_layer": kl,
        "definition_loader": definition_loader,
        "planner": planner,
        "plan_executor": plan_executor,
        "rule_engine": rule_engine,
        "runtime_logger": runtime_logger
    }

    # Teardown: Clean up the in-memory store after each test function
    kl.clear_store()


def test_elevator_panel_scenario_1(kce_test_environment_components):
    kl = kce_test_environment_components["knowledge_layer"]
    planner = kce_test_environment_components["planner"]
    ple = kce_test_environment_components["plan_executor"]
    re = kce_test_environment_components["rule_engine"]
    runtime_logger = kce_test_environment_components["runtime_logger"]

    # Generate a unique run ID for this test execution
    run_id = f"test_run_{uuid.uuid4().hex}"

    # Load target description and initial parameters
    target_description_path = EXAMPLE_PARAMS_DIR / "target_scenario1.json"
    initial_params_path = EXAMPLE_PARAMS_DIR / "scenario1_params.json"

    with open(target_description_path, 'r', encoding='utf-8') as f:
        target_description = json.load(f)


    with open(initial_params_path, 'r', encoding='utf-8') as f:
        initial_params_json = json.load(f)

    # Convert initial parameters to RDF graph
    instance_base_uri = "http://kce.com/instances/"
    initial_state_rdf = create_rdf_graph_from_json_ld_dict(initial_params_json, instance_base_uri)
    kce_logger.info(f"Initial state RDF graph loaded with {len(initial_state_rdf)} triples.")

    initial_params_instance_uri = URIRef(instance_base_uri + "ScenarioParameters_Scenario1")

    # Remove the redundant initial_state_graph loading and the try-except block
    # initial_state_graph = kl.load_initial_state_from_json_ld(initial_state_json_str, initial_params_instance_uri)
    # kce_logger.info(f"Initial state graph loaded with {len(initial_state_graph)} triples.")

    # Add debug print to check loaded AtomicNodes
    node_count_query = f"""PREFIX kce: <http://kce.com/ontology/core#> SELECT (COUNT(?node) AS ?count) WHERE {{ ?node a kce:AtomicNode . }}"""
    node_count_results = kl.execute_sparql_query(node_count_query)
    if isinstance(node_count_results, list) and node_count_results and 'count' in node_count_results[0]:
        kce_logger.info(f"Knowledge Layer contains {node_count_results[0]['count']} AtomicNodes before planner.solve.")
    else:
        kce_logger.warning("Could not query AtomicNode count.")

    # Original planner.solve call
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

    # Further assertions based on the final state of the knowledge layer
    # For scenario 1, we expect the assembly cost to be calculated.
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

# Helper function to load definitions from YAML files
# def load_yaml_definitions(file_path):
#     with open(file_path, 'r') as f:
#         return yaml.safe_load_all(f)

# 3. Run pytest from the project root: `pytest tests/integration/test_elevator_panel_workflow.py`

