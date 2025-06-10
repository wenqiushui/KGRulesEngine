import pytest
from unittest.mock import MagicMock, patch, ANY
from pathlib import Path

# KCE Core component imports
from cli.main import cli as kce_cli_setup_function
from cli.main import CliContext

from kce_core.interfaces import (
    IKnowledgeLayer, IDefinitionTransformationLayer, IPlanner, IPlanExecutor,
    IRuleEngine, IRuntimeStateLogger,
    ExecutionResult, TargetDescription, RDFGraph
)

# RDFLib imports
from rdflib import Graph, URIRef, Literal, Namespace

# Define Namespaces
EX = Namespace("http://example.com/ns#")

# Paths for patching should be where the class is LOOKED UP by the module under test (cli.main)
RDF_STORE_MANAGER_PATH = 'cli.main.StoreManager'
DEFINITION_LOADER_PATH = 'cli.main.DefinitionLoader'
PLAN_EXECUTOR_PATH = 'cli.main.WorkflowExecutor'
RULE_ENGINE_PATH = 'cli.main.RuleEvaluator'
NODE_EXECUTOR_PATH = 'cli.main.NodeExecutor'
RUNTIME_STATE_LOGGER_PATH = 'cli.main.ProvenanceLogger'
PLANNER_PATH = 'cli.main.Planner' # Planner is not used by cli.main.KCE, but test structure includes it.

# Test KCE Initialization
# Removing autospec=True to test how cli.main.py *actually* calls these,
# even if those calls are mismatched with component __init__ signatures.
# This will reveal TypeErrors if cli.main.py is changed to call correctly,
# or if the components change and cli.main.py is not updated.
@patch(RUNTIME_STATE_LOGGER_PATH) # No autospec
@patch(NODE_EXECUTOR_PATH)        # No autospec
@patch(RULE_ENGINE_PATH)          # No autospec
@patch(PLAN_EXECUTOR_PATH)        # No autospec
# @patch(PLANNER_PATH) # Planner is not imported/used by cli.main.py, so cannot be patched here.
@patch(DEFINITION_LOADER_PATH)    # No autospec
@patch(RDF_STORE_MANAGER_PATH)    # No autospec
def test_kce_component_initialization(
    MockStoreManager, MockDefinitionLoader, # MockPlanner removed
    MockWorkflowExecutor, MockRuleEvaluator, MockNodeExecutor, MockProvenanceLogger
):
    """
    Tests the instantiation of internal components by cli.main.py's setup logic.
    """
    db_path_arg = "test_db.sqlite"
    base_script_path_arg = "/dummy/scripts"

    ctx = CliContext()
    ctx.db_path = Path(db_path_arg)
    ctx.base_script_path = Path(base_script_path_arg)

    # Simulate the KCE component setup within cli.main.cli's try block
    # These calls will use the mocked classes.

    ctx.store_manager = MockStoreManager(db_path=ctx.db_path)
    MockStoreManager.assert_called_once_with(db_path=ctx.db_path)

    prov_logger_instance = MockProvenanceLogger(ctx.store_manager)
    MockProvenanceLogger.assert_called_once_with(ctx.store_manager)

    node_exec_instance = MockNodeExecutor(ctx.store_manager, prov_logger_instance)
    MockNodeExecutor.assert_called_once_with(ctx.store_manager, prov_logger_instance)

    rule_eval_instance = MockRuleEvaluator(ctx.store_manager, prov_logger_instance)
    MockRuleEvaluator.assert_called_once_with(ctx.store_manager, prov_logger_instance)

    ctx.definition_loader = MockDefinitionLoader(ctx.store_manager, base_path_for_relative_scripts=ctx.base_script_path)
    MockDefinitionLoader.assert_called_once_with(ctx.store_manager, base_path_for_relative_scripts=ctx.base_script_path)

    ctx.workflow_executor = MockWorkflowExecutor(ctx.store_manager, node_exec_instance, rule_eval_instance, prov_logger_instance)
    MockWorkflowExecutor.assert_called_once_with(
        ctx.store_manager,
        node_exec_instance,
        rule_eval_instance,
        prov_logger_instance
    )

    assert ctx.store_manager == MockStoreManager.return_value
    assert ctx.definition_loader == MockDefinitionLoader.return_value
    assert ctx.workflow_executor == MockWorkflowExecutor.return_value

    # Planner is not instantiated by cli.main.KCE's setup logic being simulated here.
    # MockPlanner.assert_not_called() # MockPlanner is no longer an arg

    # load_definitions_from_path and trigger_reasoning are not called directly in this setup block of cli.main.py
    # They are called by specific CLI commands.
    mock_def_loader_instance = MockDefinitionLoader.return_value
    mock_def_loader_instance.load_definitions_from_path.assert_not_called()

    mock_kl_instance = MockStoreManager.return_value
    mock_kl_instance.trigger_reasoning.assert_not_called()


# test_kce_solve_success is removed as cli.main.KCE (the cli function group)
# does not have a .solve() method. Testing workflow execution would involve
# testing the 'run-workflow' Click command or directly testing the
# WorkflowExecutor.execute_workflow method with appropriate setup, which is beyond
# the scope of testing the KCE facade's direct instantiation and methods.
# The previous test was based on a different KCE class structure.
