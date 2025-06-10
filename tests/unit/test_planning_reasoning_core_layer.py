import pytest
from pathlib import Path
import yaml
from unittest.mock import MagicMock, call, ANY # Added ANY

# KCE Core component imports
from kce_core.planning_reasoning_core_layer.rule_engine import RuleEngine
from kce_core.planning_reasoning_core_layer.planner import Planner
from kce_core.knowledge_layer.rdf_store.store_manager import RdfStoreManager
from kce_core.execution_layer.runtime_state_logger import RuntimeStateLogger
from kce_core.definition_transformation_layer.loader import DefinitionLoader
from kce_core.interfaces import (
    IKnowledgeLayer, IPlanExecutor, IRuleEngine, IRuntimeStateLogger,
    ExecutionResult, TargetDescription, RDFGraph, ExecutionPlan
)


# RDFLib imports
from rdflib import URIRef, Literal, Namespace, XSD, RDF, RDFS, Graph

# Define Namespaces
EX_NS = Namespace("http://example.com/ns#")
KCE_NS = Namespace("http://kce.com/ontology/core#")

# --- Fixtures for RuleEngine Tests ---
@pytest.fixture
def mock_knowledge_layer_for_rules():
    kl = RdfStoreManager(db_path=':memory:')
    kl.graph.bind("ex", EX_NS)
    kl.graph.bind("kce", KCE_NS)
    kl.graph.bind("rdf", RDF)
    kl.graph.bind("rdfs", RDFS)
    yield kl
    kl.close()

@pytest.fixture
def mock_runtime_logger_for_rules():
    return RuntimeStateLogger()

@pytest.fixture
def rule_engine(mock_runtime_logger_for_rules):
    return RuleEngine(runtime_state_logger=mock_runtime_logger_for_rules)

@pytest.fixture
def definition_loader_for_rules(mock_knowledge_layer_for_rules):
    return DefinitionLoader(knowledge_layer=mock_knowledge_layer_for_rules)

# Helper to create YAML rule files
def create_rule_yaml_file(tmp_path: Path, filename: str, rules_content: list):
    definitions_dir = tmp_path / "rule_definitions"
    definitions_dir.mkdir(exist_ok=True)
    rule_file = definitions_dir / filename
    with open(rule_file, 'w') as f:
        yaml.dump_all(rules_content, f)
    return rule_file

# --- RuleEngine Test Cases ---
def test_apply_simple_rule(rule_engine: RuleEngine,
                           mock_knowledge_layer_for_rules: RdfStoreManager,
                           definition_loader_for_rules: DefinitionLoader,
                           tmp_path: Path):
    rule_id_str, rule_label = "ex:SimpleRule_001", "Simple Test Rule"
    rule_yaml_content = {"kind": "Rule", "uri": rule_id_str, "name": rule_label, "priority": 1,
                         "antecedent": "ASK { ex:dataInstance ex:status \"pending\" . }",
                         "consequent": f"PREFIX ex: <{EX_NS}> DELETE DATA {{ ex:dataInstance ex:status \"pending\" . }}; INSERT DATA {{ ex:dataInstance ex:status \"processed\" . }}"}

    rule_file = create_rule_yaml_file(tmp_path, "simple_rule.yaml", [rule_yaml_content])
    load_status = definition_loader_for_rules.load_definitions_from_path(str(rule_file.parent))
    assert load_status["loaded_definitions_count"] == 1 and not load_status["errors"]

    data_instance_uri, status_property = EX_NS["dataInstance"], EX_NS["status"]
    mock_knowledge_layer_for_rules.add_triples([(data_instance_uri, status_property, Literal("pending"))])

    ask_pending_query = "ASK { ex:dataInstance ex:status 'pending' . }"
    assert mock_knowledge_layer_for_rules.execute_sparql_query(ask_pending_query) is True

    changed_any = rule_engine.apply_rules(knowledge_layer=mock_knowledge_layer_for_rules, run_id="test_run_001")
    assert changed_any is True

    assert mock_knowledge_layer_for_rules.execute_sparql_query(ask_pending_query) is False
    ask_processed_query = "ASK { ex:dataInstance ex:status 'processed' . }"
    assert mock_knowledge_layer_for_rules.execute_sparql_query(ask_processed_query) is True
    assert (data_instance_uri, status_property, Literal("processed")) in mock_knowledge_layer_for_rules.graph
    assert (data_instance_uri, status_property, Literal("pending")) not in mock_knowledge_layer_for_rules.graph


def test_no_rule_fires_condition_not_met(rule_engine: RuleEngine,
                                          mock_knowledge_layer_for_rules: RdfStoreManager,
                                          definition_loader_for_rules: DefinitionLoader,
                                          tmp_path: Path):
    rule_yaml_content = {"kind": "Rule", "uri": "ex:NoFireRule_001", "name": "No Fire Rule", "priority": 1,
                         "antecedent": "ASK { ex:dataInstance ex:status \"pending\" . }",
                         "consequent": f"PREFIX ex: <{EX_NS}> INSERT DATA {{ ex:dataInstance ex:status \"should_not_happen\" . }}"}
    rule_file = create_rule_yaml_file(tmp_path, "no_fire_rule.yaml", [rule_yaml_content])
    load_status = definition_loader_for_rules.load_definitions_from_path(str(rule_file.parent))
    assert load_status["loaded_definitions_count"] == 1 and not load_status["errors"]

    data_instance_uri, status_property = EX_NS["dataInstance"], EX_NS["status"]
    mock_knowledge_layer_for_rules.add_triples([(data_instance_uri, status_property, Literal("initial"))])

    ask_initial_query = "ASK { ex:dataInstance ex:status 'initial' . }"
    assert mock_knowledge_layer_for_rules.execute_sparql_query(ask_initial_query) is True

    changed_any = rule_engine.apply_rules(knowledge_layer=mock_knowledge_layer_for_rules, run_id="test_run_002")
    assert changed_any is False
    assert mock_knowledge_layer_for_rules.execute_sparql_query(ask_initial_query) is True
    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:dataInstance ex:status 'should_not_happen' . }") is False


def test_multiple_rules_fire_sequential_by_repeated_calls(rule_engine: RuleEngine,
                                                            mock_knowledge_layer_for_rules: RdfStoreManager,
                                                            definition_loader_for_rules: DefinitionLoader,
                                                            tmp_path: Path):
    definitions_dir = tmp_path / "multi_rules_seq"
    definitions_dir.mkdir(exist_ok=True)

    rule1_content = {"kind": "Rule", "uri": "ex:Rule_A_to_B", "name": "Rule A to B", "priority": 2,
                     "antecedent": "ASK { ex:multiTest ex:status 'A' . }",
                     "consequent": f"PREFIX ex: <{EX_NS}> DELETE DATA {{ ex:multiTest ex:status 'A' . }}; INSERT DATA {{ ex:multiTest ex:status 'B' . }}"}
    with open(definitions_dir / "rule1.yaml", 'w') as f: yaml.dump(rule1_content, f)

    rule2_content = {"kind": "Rule", "uri": "ex:Rule_B_to_C", "name": "Rule B to C", "priority": 1,
                     "antecedent": "ASK { ex:multiTest ex:status 'B' . }",
                     "consequent": f"PREFIX ex: <{EX_NS}> DELETE DATA {{ ex:multiTest ex:status 'B' . }}; INSERT DATA {{ ex:multiTest ex:status 'C' . }}"}
    with open(definitions_dir / "rule2.yaml", 'w') as f: yaml.dump(rule2_content, f)

    load_status = definition_loader_for_rules.load_definitions_from_path(str(definitions_dir))
    assert load_status["loaded_definitions_count"] == 2 and not load_status["errors"]

    data_uri, status_prop = EX_NS["multiTest"], EX_NS["status"]
    mock_knowledge_layer_for_rules.add_triples([(data_uri, status_prop, Literal("A"))])

    changed_any_pass1 = rule_engine.apply_rules(knowledge_layer=mock_knowledge_layer_for_rules, run_id="test_run_003_pass1")
    assert changed_any_pass1 is True

    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:multiTest ex:status 'C' . }") is True
    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:multiTest ex:status 'A' . }") is False
    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:multiTest ex:status 'B' . }") is False

    changed_any_pass2 = rule_engine.apply_rules(knowledge_layer=mock_knowledge_layer_for_rules, run_id="test_run_003_pass2")
    assert changed_any_pass2 is False
    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:multiTest ex:status 'C' . }") is True


def test_rule_priority_conflict(rule_engine: RuleEngine,
                                mock_knowledge_layer_for_rules: RdfStoreManager,
                                definition_loader_for_rules: DefinitionLoader,
                                tmp_path: Path):
    definitions_dir = tmp_path / "priority_rules"
    definitions_dir.mkdir(exist_ok=True)

    rule_Y_content = {"kind": "Rule", "uri": "ex:Rule_Y_Low_Pri", "name": "Rule Y Low", "priority": 1,
                      "antecedent": "ASK { ex:priTest ex:status 'start' . }",
                      "consequent": f"PREFIX ex: <{EX_NS}> DELETE DATA {{ ex:priTest ex:status 'start' . }}; INSERT DATA {{ ex:priTest ex:status 'Y-priority-loses' . }}"}
    with open(definitions_dir / "rule_y.yaml", 'w') as f: yaml.dump(rule_Y_content, f)

    rule_X_content = {"kind": "Rule", "uri": "ex:Rule_X_High_Pri", "name": "Rule X High", "priority": 10,
                      "antecedent": "ASK { ex:priTest ex:status 'start' . }",
                      "consequent": f"PREFIX ex: <{EX_NS}> DELETE DATA {{ ex:priTest ex:status 'start' . }}; INSERT DATA {{ ex:priTest ex:status 'X-priority-wins' . }}"}
    with open(definitions_dir / "rule_x.yaml", 'w') as f: yaml.dump(rule_X_content, f)

    load_status = definition_loader_for_rules.load_definitions_from_path(str(definitions_dir))
    assert load_status["loaded_definitions_count"] == 2 and not load_status["errors"]

    data_uri, status_prop = EX_NS["priTest"], EX_NS["status"]
    mock_knowledge_layer_for_rules.add_triples([(data_uri, status_prop, Literal("start"))])

    changed_any = rule_engine.apply_rules(knowledge_layer=mock_knowledge_layer_for_rules, run_id="test_run_004")
    assert changed_any is True

    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:priTest ex:status 'X-priority-wins' . }") is True
    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:priTest ex:status 'Y-priority-loses' . }") is False
    assert mock_knowledge_layer_for_rules.execute_sparql_query("ASK { ex:priTest ex:status 'start' . }") is False

# --- Fixtures for Planner Tests ---
@pytest.fixture
def mock_knowledge_layer_for_planner():
    mock_kl = MagicMock(spec=IKnowledgeLayer)
    mock_kl.graph = MagicMock(spec=Graph)
    mock_kl.add_graph.return_value = None
    mock_kl.trigger_reasoning.return_value = None
    return mock_kl

@pytest.fixture
def mock_plan_executor_for_planner():
    return MagicMock(spec=IPlanExecutor)

@pytest.fixture
def mock_rule_engine_for_planner():
    mock_re = MagicMock(spec=IRuleEngine)
    mock_re.apply_rules.return_value = False
    return mock_re

@pytest.fixture
def mock_runtime_logger_for_planner():
    return MagicMock(spec=IRuntimeStateLogger)

@pytest.fixture
def planner_under_test(mock_runtime_logger_for_planner):
    return Planner(runtime_state_logger=mock_runtime_logger_for_planner)

# --- Planner Test Cases ---
def test_planner_goal_already_achieved(planner_under_test: Planner,
                                     mock_knowledge_layer_for_planner: MagicMock,
                                     mock_plan_executor_for_planner: MagicMock,
                                     mock_rule_engine_for_planner: MagicMock):
    target_description: TargetDescription = {
        "target_description_label": "Test Goal Already Met",
        "sparql_ask_query": "PREFIX ex: <http://example.com/ns#> ASK { ex:goalState ex:isAchieved true . }"
    }
    mock_knowledge_layer_for_planner.execute_sparql_query.return_value = True
    initial_state_graph_mock = MagicMock(spec=Graph)
    initial_state_graph_mock.__len__.return_value = 1

    result: ExecutionResult = planner_under_test.solve(
        target_description=target_description, initial_state_graph=initial_state_graph_mock,
        knowledge_layer=mock_knowledge_layer_for_planner, plan_executor=mock_plan_executor_for_planner,
        rule_engine=mock_rule_engine_for_planner, run_id="test_run_goal_met", mode="user"
    )

    assert result["status"] == "success"
    assert "goal achieved" in result["message"].lower()
    mock_knowledge_layer_for_planner.execute_sparql_query.assert_called_once_with(target_description["sparql_ask_query"])
    mock_rule_engine_for_planner.apply_rules.assert_called_once_with(mock_knowledge_layer_for_planner, "test_run_goal_met")
    mock_plan_executor_for_planner.execute_plan.assert_not_called()
    mock_knowledge_layer_for_planner.add_graph.assert_called_once_with(
        initial_state_graph_mock, context_uri=URIRef(f"urn:kce:run:test_run_goal_met:initial_problem_state")
    )
    mock_knowledge_layer_for_planner.trigger_reasoning.assert_called()


def test_planner_finds_and_executes_one_node( # Renamed for clarity based on current Planner
    planner_under_test: Planner,
    mock_knowledge_layer_for_planner: MagicMock,
    mock_plan_executor_for_planner: MagicMock,
    mock_rule_engine_for_planner: MagicMock,
    mock_runtime_logger_for_planner: MagicMock
    ):
    target_description: TargetDescription = {
        "target_description_label": "Test Goal Achieved by One Atomic Node",
        "sparql_ask_query": "ASK { ex:finalState ex:isAchieved true . }"
    }
    atomic_node_uri = EX_NS["TestAtomicNode_001"]

    mock_knowledge_layer_for_planner.execute_sparql_query.side_effect = [
        False,  # 1. Initial _check_goal_achieved in solve(): Goal NOT met
        [{'node_uri': atomic_node_uri}],  # 2. _find_relevant_nodes(): Finds one AtomicNode URI
        [{'precondition_query': Literal("ASK { ex:precondMet true . }")}], # 3. _check_node_preconditions(): Gets kce:hasPrecondition
        True,  # 4. _check_node_preconditions(): Executes precondition query: Precondition IS met
        True    # 5. Final _check_goal_achieved: Goal MET after plan execution
    ]
    mock_plan_executor_for_planner.execute_plan.return_value = {"status": "success", "message": "Plan executed."}

    initial_state_graph_mock = MagicMock(spec=Graph); initial_state_graph_mock.__len__.return_value = 1

    result: ExecutionResult = planner_under_test.solve(
        target_description=target_description, initial_state_graph=initial_state_graph_mock,
        knowledge_layer=mock_knowledge_layer_for_planner, plan_executor=mock_plan_executor_for_planner,
        rule_engine=mock_rule_engine_for_planner, run_id="test_run_one_node", mode="auto"
    )

    assert result["status"] == "success"
    assert "goal achieved" in result["message"].lower()
    assert mock_knowledge_layer_for_planner.execute_sparql_query.call_count == 5
    expected_plan_step: ExecutionPlan = [{"operation_type": "node", "operation_uri": str(atomic_node_uri)}]
    mock_plan_executor_for_planner.execute_plan.assert_called_once_with(
        expected_plan_step, "test_run_one_node", mock_knowledge_layer_for_planner, initial_graph=None
    )
    assert mock_rule_engine_for_planner.apply_rules.call_count >= 1 # Initial + after node execution
    mock_runtime_logger_for_planner.log_event.assert_any_call("test_run_one_node", "NodeSelectedForExecution", str(atomic_node_uri), "Selected", ANY, ANY, ANY, ANY)
    mock_runtime_logger_for_planner.log_event.assert_any_call("test_run_one_node", "GoalAchieved", ANY, "Succeeded", ANY, ANY, "Goal achieved.", ANY)


def test_planner_fails_to_find_node(planner_under_test: Planner,
                                   mock_knowledge_layer_for_planner: MagicMock,
                                   mock_plan_executor_for_planner: MagicMock,
                                   mock_rule_engine_for_planner: MagicMock,
                                   mock_runtime_logger_for_planner: MagicMock):
    target_description: TargetDescription = {
        "target_description_label": "Test Goal Cannot Be Achieved - No Node",
        "sparql_ask_query": "ASK { ex:unattainableState ex:isAchieved true . }"
    }
    mock_knowledge_layer_for_planner.execute_sparql_query.side_effect = [
        False,  # 1. Initial target check: Goal NOT met
        []      # 2. Planner queries for kce:AtomicNode instances, finds none.
    ]
    initial_state_graph_mock = MagicMock(spec=Graph); initial_state_graph_mock.__len__.return_value = 1
    mock_rule_engine_for_planner.apply_rules.return_value = False # No rule changes

    result: ExecutionResult = planner_under_test.solve(
        target_description=target_description, initial_state_graph=initial_state_graph_mock,
        knowledge_layer=mock_knowledge_layer_for_planner, plan_executor=mock_plan_executor_for_planner,
        rule_engine=mock_rule_engine_for_planner, run_id="test_run_no_node_found", mode="user"
    )

    assert result["status"] == "failure"
    assert "no candidate nodes found" in result["message"].lower()
    assert mock_knowledge_layer_for_planner.execute_sparql_query.call_count == 2
    mock_plan_executor_for_planner.execute_plan.assert_not_called()
    mock_rule_engine_for_planner.apply_rules.assert_called_once() # Initial stabilization call
    mock_runtime_logger_for_planner.log_event.assert_any_call("test_run_no_node_found", "NodeSelection", ANY, "Failed", ANY, ANY, ANY, ANY)


def test_planner_finds_node_precondition_fails(planner_under_test: Planner,
                                               mock_knowledge_layer_for_planner: MagicMock,
                                               mock_plan_executor_for_planner: MagicMock,
                                               mock_rule_engine_for_planner: MagicMock,
                                               mock_runtime_logger_for_planner: MagicMock):
    target_description: TargetDescription = {
        "target_description_label": "Test Goal With Failed Precondition",
        "sparql_ask_query": "ASK { ex:anotherState ex:isAchieved true . }"
    }
    node_uri = EX_NS["NodeWithFailedPrecondition"]
    precondition_ask_query = "ASK { ex:myPrecondition ex:isSatisfied true . }"

    mock_knowledge_layer_for_planner.execute_sparql_query.side_effect = [
        False,  # 1. Initial target check: Goal NOT met
        [{'node_uri': node_uri}],  # 2. _find_relevant_nodes(): Finds one AtomicNode URI
        [{'precondition_query': Literal(precondition_ask_query)}], # 3. _check_node_preconditions(): Gets kce:hasPrecondition
        False  # 4. _check_node_preconditions(): Executes precondition query: Precondition FAILS
    ]
    initial_state_graph_mock = MagicMock(spec=Graph); initial_state_graph_mock.__len__.return_value = 1
    mock_rule_engine_for_planner.apply_rules.return_value = False # No rule changes

    result: ExecutionResult = planner_under_test.solve(
        target_description=target_description, initial_state_graph=initial_state_graph_mock,
        knowledge_layer=mock_knowledge_layer_for_planner, plan_executor=mock_plan_executor_for_planner,
        rule_engine=mock_rule_engine_for_planner, run_id="test_run_precond_fail", mode="user"
    )

    assert result["status"] == "failure"
    assert "no executable node found" in result["message"].lower() # Planner.py message
    assert mock_knowledge_layer_for_planner.execute_sparql_query.call_count == 4
    mock_plan_executor_for_planner.execute_plan.assert_not_called()
    mock_rule_engine_for_planner.apply_rules.assert_called_once() # Initial stabilization call
    mock_runtime_logger_for_planner.log_event.assert_any_call("test_run_precond_fail", "NoExecutableNodeFound", ANY, "Failed", ANY, ANY, ANY, ANY)
