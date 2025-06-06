import rdflib
import datetime
import json # Make sure json is imported at the top level
from typing import Any, Optional, Dict, Union, List # Added Union, List for type hints

# Assuming interfaces.py is two levels up
from ..interfaces import IRuntimeStateLogger, IKnowledgeLayer, RDFGraph # Added RDFGraph

# Placeholder for common.utils.generate_instance_uri
# This will be properly imported if kce_core.common.utils exists when this module is loaded.
try:
    from ..common.utils import generate_instance_uri
except ImportError:
    print("Warning: kce_core.common.utils.generate_instance_uri not found. Using placeholder for RuntimeStateLogger.")
    def generate_instance_uri(base_uri: str, prefix: str, local_name: Optional[str] = None) -> rdflib.URIRef:
        import uuid
        if local_name:
            return rdflib.URIRef(f"{base_uri}{prefix}/{local_name}")
        return rdflib.URIRef(f"{base_uri}{prefix}/{uuid.uuid4()}")


# Define KCE namespace (ideally from a central place)
KCE = rdflib.Namespace("http://kce.com/ontology/core#")
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#") # For PROV-O
XSD = rdflib.namespace.XSD
RDF = rdflib.namespace.RDF
RDFS = rdflib.namespace.RDFS


class RuntimeStateLogger(IRuntimeStateLogger):
    def __init__(self):
        # Configuration for logging, e.g., base URI for execution state nodes
        self.base_execution_uri = "http://kce.com/executions/"

    def _generate_event_id(self, run_id: str, operation_uri: str, status: str) -> str:
        '''Generates a unique-ish ID for the event.'''
        timestamp_short = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        # Sanitize operation_uri for use in event_id to avoid invalid characters if it's a full URI
        op_name_sanitized = operation_uri.split('#')[-1].split('/')[-1] if operation_uri else "system"
        op_name_sanitized = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in op_name_sanitized) # Basic sanitize

        return f"{run_id}_{op_name_sanitized}_{status}_{timestamp_short}"

    def _create_rdf_provenance(self, run_id: str, event_id: str, event_type: str, operation_uri: Optional[str], status: str, inputs: Any, outputs: Any, message: Optional[str], knowledge_layer: IKnowledgeLayer) -> tuple[rdflib.Graph, rdflib.URIRef]:
        '''
        Creates an RDF graph representing the provenance of this execution event.
        '''
        prov_graph = rdflib.Graph()

        exec_state_node_uri_str = f"{self.base_execution_uri}{run_id}/state/{event_id}"
        exec_state_node_uri = rdflib.URIRef(exec_state_node_uri_str)

        prov_graph.add((exec_state_node_uri, RDF.type, KCE.ExecutionStateNode))
        prov_graph.add((exec_state_node_uri, KCE.belongsToRun, rdflib.URIRef(f"{self.base_execution_uri}{run_id}")))
        prov_graph.add((exec_state_node_uri, KCE.timestamp, rdflib.Literal(datetime.datetime.utcnow().isoformat(), datatype=XSD.dateTime)))

        event_type_uri = KCE[event_type.replace(" ", "")]
        prov_graph.add((exec_state_node_uri, KCE.eventType, event_type_uri))

        if operation_uri:
            prov_graph.add((exec_state_node_uri, KCE.triggeredByOperation, rdflib.URIRef(operation_uri)))

        status_uri = KCE[status.capitalize()]
        prov_graph.add((exec_state_node_uri, KCE.status, status_uri))

        if message:
            prov_graph.add((exec_state_node_uri, RDFS.comment, rdflib.Literal(message)))

        prov_graph.bind("kce", KCE)
        prov_graph.bind("prov", PROV)
        prov_graph.bind("xsd", XSD)
        prov_graph.bind("rdfs", RDFS)

        return prov_graph, exec_state_node_uri

    def log_event(self,
                  run_id: str,
                  event_type: str,
                  operation_uri: Optional[str],
                  status: str,
                  inputs: Any,
                  outputs: Any,
                  message: Optional[str] = None,
                  knowledge_layer: Optional[IKnowledgeLayer] = None) -> None:
        if not knowledge_layer:
            print(f"Warning ({datetime.datetime.utcnow().isoformat()}): KnowledgeLayer not provided to RuntimeStateLogger.log_event. "
                  f"Cannot log RDF or human-readable logs for event: type='{event_type}', op='{operation_uri}', status='{status}'.")
            return

        event_id_op_uri = operation_uri if operation_uri else "system_event"
        event_id = self._generate_event_id(run_id, event_id_op_uri, status)

        hr_log_content = {
            "event_id": event_id,
            "run_id": run_id,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "event_type": event_type,
            "operation_uri": operation_uri,
            "status": status,
            "inputs": inputs,
            "outputs": outputs,
            "message": message
        }
        try:
            hr_log_json = json.dumps(hr_log_content, indent=2, default=str)
        except Exception as e:
            hr_log_json = f"Error serializing log content: {e}\nContent: {str(hr_log_content)}"

        log_location = knowledge_layer.store_human_readable_log(run_id, event_id, hr_log_json)

        rdf_prov_graph, exec_state_node_uri = self._create_rdf_provenance(
            run_id, event_id, event_type, operation_uri, status, inputs, outputs, message, knowledge_layer
        )

        if log_location: # log_location can be empty string if store_human_readable_log failed
            rdf_prov_graph.add((exec_state_node_uri, KCE.humanReadableLogLocation, rdflib.Literal(log_location)))

        if rdf_prov_graph and len(rdf_prov_graph) > 0:
            # Define a context URI for provenance data, e.g., based on the run_id
            prov_context_uri = rdflib.URIRef(f"{self.base_execution_uri}{run_id}/provenance")
            knowledge_layer.add_graph(rdf_prov_graph, context_uri=str(prov_context_uri))

        print(f"Logged event: {event_id} (type: {event_type}, status: {status}, op: {operation_uri}) HumanLog: {log_location}, RDFStateNode: <{exec_state_node_uri}>")


if __name__ == '__main__':
    # Mock IKnowledgeLayer for testing
    class MockKnowledgeLayer(IKnowledgeLayer):
        def __init__(self):
            self.rdf_store = rdflib.Graph() # Default graph
            self.named_graphs: Dict[str, rdflib.Graph] = {} # For contexts
            self.human_logs: Dict[str, str] = {}
        def execute_sparql_query(self, query: str) -> Union[List[Dict[str, Any]], bool, RDFGraph]: return []
        def execute_sparql_update(self, update_statement: str) -> None: pass
        def trigger_reasoning(self) -> None: pass
        def add_graph(self, graph_to_add: RDFGraph, context_uri: Optional[str] = None) -> None:
            if context_uri:
                if context_uri not in self.named_graphs:
                    self.named_graphs[context_uri] = rdflib.Graph(identifier=rdflib.URIRef(context_uri))
                self.named_graphs[context_uri] += graph_to_add
            else:
                self.rdf_store += graph_to_add
        def get_graph(self, context_uri: Optional[str] = None) -> RDFGraph:
            return self.named_graphs.get(context_uri) if context_uri else self.rdf_store
        def store_human_readable_log(self, run_id: str, event_id: str, log_content: str) -> str:
            location = f"data/logs/{run_id}/{event_id}.json" # More realistic path
             # Ensure directory exists (os.makedirs would be here in real KL)
            print(f"MockKL: Storing human log at {location}")
            self.human_logs[location] = log_content
            return location
        def get_human_readable_log(self, log_location: str) -> Optional[str]: return self.human_logs.get(log_location)

    # Make sure EX namespace is available for test URIs
    EX = rdflib.Namespace("http://example.com/ns#")

    mock_kl = MockKnowledgeLayer()
    logger = RuntimeStateLogger()

    # Test generate_instance_uri (it's imported, so this assumes it works or is mocked)
    # If common.utils is not actually present, the placeholder will be used.
    try:
        from kce_core.common.utils import generate_instance_uri
        print("Actual generate_instance_uri from common.utils would be used if available.")
    except ImportError:
        print("Using placeholder generate_instance_uri for test.")
        # The placeholder is already defined at the module level if import fails.
        pass


    test_run_id = "test_run_rstl_002"
    test_node_uri = str(EX.MyProcessingNode)

    print(f"--- Testing RuntimeStateLogger (run_id: {test_run_id}) ---")

    logger.log_event(
        run_id=test_run_id, event_type="NodeExecutionStart", operation_uri=test_node_uri, status="Started",
        inputs={"param1": 200, "param2": "world"}, outputs=None, knowledge_layer=mock_kl
    )
    logger.log_event(
        run_id=test_run_id, event_type="NodeExecutionEnd", operation_uri=test_node_uri, status="Succeeded",
        inputs={"param1": 200, "param2": "world"}, outputs={"result": "processed_world_200", "value": 400},
        message="Node completed successfully.", knowledge_layer=mock_kl
    )

    test_node_uri_fail = str(EX.MyFailingNode)
    logger.log_event(
        run_id=test_run_id, event_type="NodeExecutionEnd", operation_uri=test_node_uri_fail, status="Failed",
        inputs={"data": [4,5,6]}, outputs=None, message="Exception: Division by zero.", knowledge_layer=mock_kl
    )

    test_rule_uri = str(EX.MyValidationRule)
    logger.log_event(
        run_id=test_run_id, event_type="RuleApplication", operation_uri=test_rule_uri, status="Applied",
        inputs={"validated_entity": str(EX.EntityX), "isValid": True}, outputs={"actions_taken": 0},
        message=f"Rule <{test_rule_uri}> applied, no actions needed.", knowledge_layer=mock_kl
    )

    print(f"--- Total RDF triples in MockKL default graph: {len(mock_kl.rdf_store)} ---")
    prov_context_uri = f"{logger.base_execution_uri}{test_run_id}/provenance"
    if prov_context_uri in mock_kl.named_graphs:
        print(f"--- Total RDF triples in MockKL provenance graph <{prov_context_uri}>: {len(mock_kl.named_graphs[prov_context_uri])} ---")
        # print(mock_kl.named_graphs[prov_context_uri].serialize(format="turtle"))
    else:
        print(f"--- Provenance graph <{prov_context_uri}> not found in MockKL. ---")


    print("--- Human-readable logs created: ---")
    for location, content_json_str in mock_kl.human_logs.items():
        print(f"--- Log at {location} ---")
        try:
            content_dict = json.loads(content_json_str)
            print(json.dumps(content_dict, indent=2))
        except json.JSONDecodeError:
            print(content_json_str)
        print("--- End Log ---")

    print("--- RuntimeStateLogger test complete. ---")
