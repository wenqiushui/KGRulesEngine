from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
import rdflib

# Define placeholder types for complex data structures for clarity
# These might be further refined or replaced with actual classes/dataclasses later
RDFGraph = rdflib.Graph
SPARQLQuery = str
SPARQLUpdate = str
FilePath = str
DirectoryPath = str
LoadStatus = Dict[str, Any] # e.g., {"loaded_files": [], "errors": []}
InitialStateGraph = RDFGraph
ExecutionPlan = List[Dict[str, str]] # e.g., [{"operation_type": "node", "operation_uri": "uri"}]
ExecutionResult = Dict[str, Any] # e.g., {"status": "success/failure", "message": "", "run_id": ""}
TargetDescription = Dict[str, Any] # Placeholder for structured target
LogLocation = str # Placeholder for log location identifier
StateEvent = Dict[str, Any] # Placeholder for state event structure

class IDefinitionTransformationLayer(ABC):
    @abstractmethod
    def load_definitions_from_path(self, path: DirectoryPath) -> LoadStatus:
        '''Loads all definition files (e.g., YAML) from a given directory path,
           transforms them to RDF, and loads them into the KnowledgeLayer.'''
        pass

    @abstractmethod
    def load_initial_state_from_json(self, json_data: str, base_uri: str) -> InitialStateGraph:
        '''Parses problem instance JSON and converts it to an initial RDF graph.'''
        pass

class IKnowledgeLayer(ABC):
    @abstractmethod
    def execute_sparql_query(self, query: SPARQLQuery) -> Union[List[Dict], bool, RDFGraph]:
        '''Executes a SPARQL query (SELECT, ASK, CONSTRUCT, DESCRIBE) against the RDF store.'''
        pass

    @abstractmethod
    def execute_sparql_update(self, update_statement: SPARQLUpdate) -> None:
        '''Executes a SPARQL UPDATE (INSERT, DELETE) against the RDF store.'''
        pass

    @abstractmethod
    def trigger_reasoning(self) -> None:
        '''Triggers OWL RL reasoning on the RDF store.'''
        pass

    @abstractmethod
    def add_graph(self, graph: RDFGraph, context_uri: Optional[str] = None) -> None:
        '''Adds an RDF graph to the store, optionally in a specific named context.'''
        pass

    @abstractmethod
    def get_graph(self, context_uri: Optional[str] = None) -> RDFGraph:
        '''Retrieves an RDF graph, optionally from a specific named context.'''
        pass

    @abstractmethod
    def store_human_readable_log(self, run_id: str, event_id: str, log_content: str) -> LogLocation:
        '''Stores human-readable log content and returns its location/identifier.'''
        pass

    @abstractmethod
    def get_human_readable_log(self, log_location: LogLocation) -> Optional[str]:
        '''Retrieves human-readable log content given its location/identifier.'''
        pass

class IPlanExecutor(ABC):
    @abstractmethod
    def execute_plan(self, plan: ExecutionPlan, run_id: str, knowledge_layer: IKnowledgeLayer, initial_graph: Optional[RDFGraph] = None) -> ExecutionResult:
        '''Executes a given plan (sequence of operations), interacting with the KnowledgeLayer.
           The initial_graph is provided if this is the start of an execution run.'''
        pass

class INodeExecutor(ABC): # Added as it's a clear component in ExecutionLayer
    @abstractmethod
    def execute_node(self, node_uri: str, run_id: str, knowledge_layer: IKnowledgeLayer, current_input_graph: RDFGraph) -> RDFGraph:
        '''Executes a single node, fetching its definition, preparing inputs,
           invoking it, and returning its output as an RDF graph to be merged.'''
        pass

class IRuntimeStateLogger(ABC): # Added as it's a clear component in ExecutionLayer
    @abstractmethod
    def log_event(self, run_id: str, event_type: str, operation_uri: str, status: str, inputs: Any, outputs: Any, message: Optional[str] = None, knowledge_layer: Optional[IKnowledgeLayer] = None) -> None:
        '''Logs a runtime event (e.g., node start, node end, rule application)
           to both human-readable logs and RDF provenance store via KnowledgeLayer.'''
        pass


class IRuleEngine(ABC): # Added as it's a clear component in P&R Layer
    @abstractmethod
    def apply_rules(self, knowledge_layer: IKnowledgeLayer, run_id: Optional[str] = None) -> bool:
        '''Applies all applicable rules based on the current state in the KnowledgeLayer.
           Returns True if any rule was successfully applied, False otherwise.'''
        pass

class IPlanner(ABC):
    @abstractmethod
    def solve(self, target_description: TargetDescription, initial_state_graph: RDFGraph, knowledge_layer: IKnowledgeLayer, plan_executor: IPlanExecutor, rule_engine: IRuleEngine, run_id: str, mode: str) -> ExecutionResult:
        '''Solves a given problem by planning and orchestrating execution.
           Interacts with KnowledgeLayer for data, RuleEngine for rule applications,
           and PlanExecutor to run parts of the plan.'''
        pass

# It might also be useful to define an interface for the CLI handler,
# but given it's the top-level entry point, its methods are more directly invoked.
# class ICliHandler(ABC):
#     @abstractmethod
#     def load_definitions(self, path: DirectoryPath) -> None:
#         pass
#
#     @abstractmethod
#     def solve_problem(self, target_file: FilePath, initial_state_file: FilePath, mode: str, run_id: Optional[str]) -> None:
#         pass
#
#     # ... other CLI commands
