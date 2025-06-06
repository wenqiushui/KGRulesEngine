# kce_core/provenance/logger.py

import datetime
import logging
from typing import Union, Optional, List, Any, Dict # <--- 已添加 Dict

from rdflib import URIRef, Literal, BNode, RDF

from kce_core.common.utils import (
    kce_logger,
    KCEError,
    generate_unique_id,
    to_uriref,
    to_literal,
    KCE, PROV, DCTERMS, XSD, RDFS, # Added RDFS here if used for labels
)
from kce_core.rdf_store.store_manager import StoreManager


class ProvenanceLogger:
    """
    Logs execution events and basic data provenance information
    as RDF triples into the knowledge base.
    """

    def __init__(self, store_manager: StoreManager,
                 run_id_prefix: str = str(KCE["run/"]), # Base for run IDs
                 node_exec_id_prefix: str = str(KCE["node-exec/"]) # Base for node exec IDs
                 ):
        """
        Initializes the ProvenanceLogger.

        Args:
            store_manager: An instance of StoreManager.
            run_id_prefix: Prefix for generating workflow run instance URIs.
            node_exec_id_prefix: Prefix for generating node execution instance URIs.
        """
        self.store = store_manager
        self.run_id_prefix = run_id_prefix
        self.node_exec_id_prefix = node_exec_id_prefix
        kce_logger.info("ProvenanceLogger initialized.")

    def _now_iso_literal(self) -> Literal:
        """Returns the current time as an XSD.dateTime Literal."""
        # Ensure timezone aware datetime for ISO format consistency
        return Literal(datetime.datetime.now(datetime.timezone.utc).isoformat(), datatype=XSD.dateTime)

    def start_workflow_execution(self, workflow_uri: URIRef,
                                 initial_params: Optional[Dict[str, Any]] = None, # Type hint uses Dict
                                 triggered_by: Optional[str] = "system") -> URIRef:
        """
        Logs the start of a workflow execution.

        Args:
            workflow_uri: The URI of the workflow being executed.
            initial_params: A dictionary of initial parameters (for logging, not direct storage here).
            triggered_by: Identifier for what triggered the execution.

        Returns:
            The URI of the created kce:ExecutionLog instance (run_id_uri).
        """
        run_id = generate_unique_id(prefix="") # Just the UUID part
        run_id_uri = URIRef(self.run_id_prefix + run_id)
        
        triples = [
            (run_id_uri, RDF.type, KCE.ExecutionLog),
            (run_id_uri, KCE.executesWorkflow, workflow_uri),
            (run_id_uri, PROV.startedAtTime, self._now_iso_literal()),
            (run_id_uri, KCE.executionStatus, Literal("Running")),
            (run_id_uri, DCTERMS.creator, Literal(triggered_by))
        ]
        # Example: if you wanted to log initial_params as a JSON string
        # if initial_params:
        #     import json # Ensure json is imported
        #     triples.append((run_id_uri, KCE.hasInitialParameters, Literal(json.dumps(initial_params), datatype=XSD.string)))

        try:
            self.store.add_triples(iter(triples), perform_reasoning=False)
            kce_logger.info(f"Workflow execution started: {run_id_uri} for workflow {workflow_uri}")
            return run_id_uri
        except Exception as e:
            kce_logger.error(f"Failed to log workflow start for {workflow_uri}: {e}")
            raise KCEError(f"Failed to log workflow start: {e}")


    def end_workflow_execution(self, run_id_uri: URIRef, status: str,
                               final_outputs_map: Optional[Dict[str, Any]] = None): # Type hint uses Dict
        """
        Logs the end of a workflow execution.

        Args:
            run_id_uri: The URI of the kce:ExecutionLog instance.
            status: The final status (e.g., "CompletedSuccess", "Failed", "Cancelled").
            final_outputs_map: A dictionary mapping output parameter names to their URIs or Literal values.
        """
        triples = [
            (run_id_uri, PROV.endedAtTime, self._now_iso_literal()),
            (run_id_uri, KCE.executionStatus, Literal(status))
        ]
        
        # MVP: Linking overall workflow outputs directly to ExecutionLog is complex.
        # This can be expanded if KCE.workflowOutput property and its structure are defined.
        # if final_outputs_map:
        #     for param_name, data_value in final_outputs_map.items():
        #         output_bnode = BNode()
        #         triples.append((run_id_uri, KCE.workflowOutput, output_bnode)) # Define KCE.workflowOutput
        #         triples.append((output_bnode, KCE.parameterName, Literal(param_name))) # Define KCE.parameterName on output structure
        #         if isinstance(data_value, RDFNode):
        #             triples.append((output_bnode, RDF.value, data_value)) # Define KCE.hasValue or use rdf:value
        #         else:
        #             triples.append((output_bnode, RDF.value, to_literal(data_value)))


        try:
            self.store.add_triples(iter(triples), perform_reasoning=False)
            kce_logger.info(f"Workflow execution ended: {run_id_uri}, Status: {status}")
        except Exception as e:
            kce_logger.error(f"Failed to log workflow end for {run_id_uri}: {e}")

    def start_node_execution(self, run_id_uri: URIRef, node_uri: URIRef,
                             node_label: Optional[str] = None) -> URIRef:
        """
        Logs the start of a node execution within a workflow run.
        """
        node_exec_id = generate_unique_id(prefix="")
        node_exec_uri = URIRef(self.node_exec_id_prefix + node_exec_id)

        triples = [
            (node_exec_uri, RDF.type, KCE.NodeExecutionLog),
            (node_exec_uri, PROV.wasAssociatedWith, run_id_uri),
            (node_exec_uri, KCE.executesNodeInstance, node_uri),
            (node_exec_uri, PROV.startedAtTime, self._now_iso_literal()),
            (node_exec_uri, KCE.executionStatus, Literal("Running"))
        ]
        if node_label: # Ensure RDFS is imported in utils if not already
            triples.append((node_exec_uri, RDFS.label, Literal(f"Execution of {node_label} ({node_uri.split('/')[-1].split('#')[-1]})")))

        try:
            self.store.add_triples(iter(triples), perform_reasoning=False)
            kce_logger.debug(f"Node execution started: {node_exec_uri} for node {node_uri} in run {run_id_uri}")
            return node_exec_uri
        except Exception as e:
            kce_logger.error(f"Failed to log node start for {node_uri} in run {run_id_uri}: {e}")
            raise KCEError(f"Failed to log node start: {e}")

    def end_node_execution(self, node_exec_uri: URIRef, status: str,
                           inputs_used: Optional[Dict[str, URIRef]] = None, # Type hint uses Dict
                           outputs_generated: Optional[Dict[str, URIRef]] = None, # Type hint uses Dict
                           error_message: Optional[str] = None):
        """
        Logs the end of a node execution, including basic provenance.
        """
        triples = [
            (node_exec_uri, PROV.endedAtTime, self._now_iso_literal()),
            (node_exec_uri, KCE.executionStatus, Literal(status))
        ]

        if error_message:
            triples.append((node_exec_uri, KCE.hasErrorMessage, Literal(error_message)))

        if inputs_used:
            for _param_name, data_uri in inputs_used.items(): # param_name currently unused in this simple logging
                if isinstance(data_uri, URIRef):
                    triples.append((node_exec_uri, PROV.used, data_uri))

        if outputs_generated:
            for _param_name, data_uri in outputs_generated.items(): # param_name currently unused
                if isinstance(data_uri, URIRef):
                    triples.append((data_uri, PROV.wasGeneratedBy, node_exec_uri))

        try:
            self.store.add_triples(iter(triples), perform_reasoning=False)
            kce_logger.debug(f"Node execution ended: {node_exec_uri}, Status: {status}")
        except Exception as e:
            kce_logger.error(f"Failed to log node end for {node_exec_uri}: {e}")

    def log_generic_event(self, run_id_uri: URIRef,
                          event_type: URIRef,
                          message: str,
                          related_entity_uri: Optional[URIRef] = None,
                          severity: str = "INFO"):
        """
        Logs a generic event related to a workflow execution.
        """
        event_id = generate_unique_id(prefix="")
        # Ensure KCE namespace has a suitable base for events if not already defined
        event_uri = URIRef(str(KCE["event/"]) + event_id if "event/" in str(KCE) else str(KCE) + "event/" + event_id)


        triples = [
            (event_uri, RDF.type, KCE.AuditEvent),
            (event_uri, RDF.type, event_type), # Specific event type
            (event_uri, PROV.wasAssociatedWith, run_id_uri),
            (event_uri, RDFS.comment, Literal(message)), # Using rdfs:comment for the message
            (event_uri, KCE.eventSeverity, Literal(severity)),
            (event_uri, PROV.atTime, self._now_iso_literal())
        ]
        if related_entity_uri:
            triples.append((event_uri, KCE.relatedEntity, related_entity_uri))

        try:
            self.store.add_triples(iter(triples), perform_reasoning=False)
            kce_logger.debug(f"Logged generic event: {event_uri} ('{message[:50]}...') for run {run_id_uri}")
        except Exception as e:
            kce_logger.error(f"Failed to log generic event for run {run_id_uri}: {e}")


if __name__ == '__main__':
    # --- Example Usage and Basic Test (remains the same as previous version) ---
    kce_logger.setLevel(logging.DEBUG)

    class MockStoreManager:
        def __init__(self):
            self.triples_added = []
            self.graph = [] 
            kce_logger.info("MockStoreManager initialized for ProvenanceLogger test.")

        def add_triples(self, triples_iter, perform_reasoning=True):
            added = list(triples_iter)
            self.triples_added.extend(added)
            self.graph.extend(added)
            # kce_logger.info(f"MockStoreManager: Added {len(added)} triples. Reasoning: {perform_reasoning}") # Too verbose for many calls

    mock_store = MockStoreManager()
    provenance_logger = ProvenanceLogger(mock_store)

    workflow_uri_test = KCE.TestWorkflow1
    run_id_uri_test = provenance_logger.start_workflow_execution(workflow_uri_test)
    assert run_id_uri_test is not None
    kce_logger.info(f"Test run URI: {run_id_uri_test}")

    node_uri_test = KCE.TestNodeA
    node_exec_uri_test = provenance_logger.start_node_execution(run_id_uri_test, node_uri_test, "Node A")
    assert node_exec_uri_test is not None
    kce_logger.info(f"Test node exec URI: {node_exec_uri_test}")

    input_data_uri = EX.InputData1
    output_data_uri = EX.OutputData1
    provenance_logger.end_node_execution(
        node_exec_uri_test,
        "CompletedSuccess",
        inputs_used={"input_param": input_data_uri},
        outputs_generated={"output_param": output_data_uri}
    )

    provenance_logger.end_workflow_execution(run_id_uri_test, "CompletedSuccess")

    provenance_logger.log_generic_event(
        run_id_uri_test,
        KCE.RuleFiredEvent, 
        "Rule 'HighValueRule' fired.",
        related_entity_uri=KCE.HighValueRule, 
        severity="INFO"
    )

    kce_logger.info(f"Total triples logged by ProvenanceLogger: {len(mock_store.triples_added)}")
    assert len(mock_store.triples_added) > 10

    found_prov_used = any(
        s == node_exec_uri_test and p == PROV.used and o == input_data_uri
        for s, p, o in mock_store.triples_added
    )
    assert found_prov_used, f"PROV.used triple not found for {node_exec_uri_test} and {input_data_uri}"

    found_prov_generated = any(
        s == output_data_uri and p == PROV.wasGeneratedBy and o == node_exec_uri_test
        for s, p, o in mock_store.triples_added
    )
    assert found_prov_generated, f"PROV.wasGeneratedBy triple not found for {output_data_uri} and {node_exec_uri_test}"

    kce_logger.info("ProvenanceLogger tests completed.")