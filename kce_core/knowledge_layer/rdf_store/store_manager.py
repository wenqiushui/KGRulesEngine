import rdflib # Ensure rdflib is imported at the top level
from rdflib import Graph, URIRef, Literal, Namespace # Ensure all are imported
# Attempting alternative import path for Memory store plugin
try:
    from rdflib.plugins.memory import Memory as MemoryStorePlugin
except ImportError:
    from rdflib.plugins.stores.memory import Memory as MemoryStorePlugin # Alternative path
from rdflib.plugins.sparql import prepareQuery, prepareUpdate
# SQLAlchemyStore removed
# from sqlalchemy import create_engine # Ensure this is removed if present
import owlrl
from typing import List, Dict, Any, Optional, Union, Tuple
import os
import logging
from pathlib import Path

from ...interfaces import IKnowledgeLayer, RDFGraph, SPARQLQuery, SPARQLUpdate, LogLocation

kce_logger = logging.getLogger(__name__)
if not kce_logger.handlers:
    kce_logger.addHandler(logging.NullHandler())

DEFAULT_DB_FILENAME = "kce_knowledge_base.sqlite" # This might be misleading now, as we default to .ttl
DEFAULT_DATA_DIR = Path("data")
DEFAULT_LOG_DIR = DEFAULT_DATA_DIR / "logs"
KCE_GRAPH_IDENTIFIER = URIRef("http://kce.com/graph")

class RdfStoreManager(IKnowledgeLayer):
    def __init__(self, db_path: Optional[str] = None, ontology_files: Optional[List[str]] = None, log_dir: Optional[str] = None):
        self.db_path = db_path
        self.graph_identifier = KCE_GRAPH_IDENTIFIER
        # self.store = None # Removed, Graph manages its own store
        # self.db_uri = None # Removed, not needed for file or memory stores in this simplified model
        self._is_in_memory = False

        self.log_dir = Path(log_dir if log_dir else DEFAULT_LOG_DIR).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        if self.db_path is None or self.db_path == ':memory:':
            kce_logger.info("RdfStoreManager initializing with in-memory RDFLib Graph.")
            self._is_in_memory = True
            self.graph = Graph(identifier=self.graph_identifier)
        else:  # File-based persistent store
            self._is_in_memory = False
            resolved_db_path = Path(self.db_path).resolve()
            kce_logger.info(f"RdfStoreManager initializing with file-based storage: {resolved_db_path}")
            self.graph = Graph(identifier=self.graph_identifier)
            if resolved_db_path.exists() and resolved_db_path.is_file():
                try:
                    # Guess format based on extension, fallback to turtle
                    file_format = rdflib.util.guess_format(str(resolved_db_path)) or "turtle"
                    self.graph.parse(str(resolved_db_path), format=file_format)
                    kce_logger.info(f"Loaded graph from existing file: {resolved_db_path} with format {file_format}")
                except Exception as e:
                    kce_logger.error(f"Failed to parse existing graph file {resolved_db_path}: {e}. Initializing empty graph.", exc_info=True)
                    # Initialize an empty graph if parsing fails
                    self.graph = Graph(identifier=self.graph_identifier)
            else:
                kce_logger.info(f"Graph file not found at {resolved_db_path}. Initializing an empty graph. It will be saved on close.")
                # Ensure parent directory exists for when we save later
                resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
                self.graph = Graph(identifier=self.graph_identifier) # Ensure graph is initialized

        if ontology_files and self.graph is not None: # Ensure self.graph is checked here
            for ont_file in ontology_files:
                try:
                    ont_path = Path(ont_file).resolve()
                    if ont_path.exists() and ont_path.is_file():
                        self.graph.parse(str(ont_path), format=rdflib.util.guess_format(str(ont_path)))
                        kce_logger.info(f"Successfully loaded ontology: {ont_path}")
                    else:
                        kce_logger.warning(f"Ontology file not found: {ont_path}. Skipping.")
                except Exception as e:
                    kce_logger.error(f"Error loading ontology {ont_path}: {e}", exc_info=True)
            if hasattr(self.graph, 'commit') and callable(self.graph.commit):
                 self.graph.commit()

    def add_triples(self, triples_list: List[Tuple[URIRef, URIRef, Any]]):
        if self.graph is None:
            kce_logger.error("Graph not initialized. Cannot add triples.")
            return
        for s, p, o in triples_list:
            self.graph.add((s, p, o))
        if hasattr(self.graph, 'commit') and callable(self.graph.commit):
             self.graph.commit()

    def execute_sparql_query(self, query: SPARQLQuery) -> Union[List[Dict[str, Any]], bool, RDFGraph]:
        if self.graph is None:
            kce_logger.error("Graph not initialized. Cannot execute SPARQL query.")
            return []

        init_ns = {pfx: str(ns) for pfx, ns in self.graph.namespaces()}
        prepared_query = prepareQuery(query, initNs=init_ns)
        q_result = self.graph.query(prepared_query)

        if q_result.type == 'ASK':
            return q_result.askAnswer
        elif q_result.type == 'SELECT':
            return [row.asdict() for row in q_result]
        elif q_result.type in ['CONSTRUCT', 'DESCRIBE']:
            return q_result.graph

        kce_logger.warning(f"Unknown or unhandled SPARQL query result type: {q_result.type}")
        if isinstance(q_result, (list, bool, Graph)):
            return q_result
        return []

    def execute_sparql_update(self, update_statement: SPARQLUpdate) -> None:
        if self.graph is None:
            kce_logger.error("Graph not initialized. Cannot execute SPARQL update.")
            return
        init_ns = {pfx: str(ns) for pfx, ns in self.graph.namespaces()}
        prepared_update = prepareUpdate(update_statement, initNs=init_ns)
        self.graph.update(prepared_update)
        if hasattr(self.graph, 'commit') and callable(self.graph.commit):
            self.graph.commit()

    def trigger_reasoning(self) -> None:
        if self.graph is None:
            kce_logger.error("Graph not initialized. Cannot trigger reasoning.")
            return
        kce_logger.info("Starting OWL RL Reasoning with owlrl...")
        try:
            closure = owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, rdfs_closure=False, axiomatic_triples=True, datatype_axioms=True)
            closure.expand(self.graph)
            if hasattr(self.graph, 'commit') and callable(self.graph.commit):
                self.graph.commit()
            kce_logger.info("OWL RL Reasoning complete.")
        except Exception as e:
            kce_logger.error(f"Error during OWL RL reasoning: {e}", exc_info=True)

    def add_graph(self, graph_to_add: RDFGraph, context_uri: Optional[str] = None) -> None:
        if self.graph is None:
            kce_logger.error("Main graph not initialized. Cannot add graph.")
            return

        if context_uri:
            kce_logger.warning(f"Context URI '{context_uri}' provided. File-based and simple in-memory stores operate on a single default graph. Context URI will be ignored.")

        # All operations target self.graph directly
        for s, p, o in graph_to_add:
            self.graph.add((s,p,o))
        if hasattr(self.graph, 'commit') and callable(self.graph.commit):
            self.graph.commit() # This commit is for rdflib's internal store if it supports it.
        kce_logger.debug(f"Added {len(graph_to_add)} triples to the graph.")

    def get_graph(self, context_uri: Optional[str] = None) -> RDFGraph:
        if self.graph is None:
            kce_logger.error("Graph not initialized. Cannot get graph.")
            return Graph()

        if context_uri:
            kce_logger.warning(f"Context URI '{context_uri}' requested. File-based and simple in-memory stores operate on a single default graph. Returning the default graph.")
        return self.graph

    def store_human_readable_log(self, run_id: str, event_id: str, log_content: str) -> LogLocation:
        if not self.log_dir:
            kce_logger.error("Log directory not configured.")
            return ""
        run_log_dir = self.log_dir / run_id
        run_log_dir.mkdir(parents=True, exist_ok=True)
        safe_event_id = event_id.replace(':', '_').replace('/', '_').replace('\\', '_')
        log_file_path = run_log_dir / f"{safe_event_id}.json"
        try:
            with open(log_file_path, "w", encoding='utf-8') as f: f.write(log_content)
            return str(log_file_path.resolve())
        except IOError as e:
            kce_logger.error(f"Error writing human-readable log to {log_file_path}: {e}", exc_info=True)
            return ""

    def get_human_readable_log(self, log_location: LogLocation) -> Optional[str]:
        log_file = Path(log_location)
        try:
            if log_file.is_file():
                with open(log_file, "r", encoding='utf-8') as f: return f.read()
            else: kce_logger.warning(f"Human-readable log file not found or is not a file: {log_location}"); return None
        except IOError as e:
            kce_logger.error(f"Error reading human-readable log {log_location}: {e}", exc_info=True)
            return None

    def close(self):
        db_identity = self.db_path if self.db_path and not self._is_in_memory else "in-memory store"
        if self.graph is not None:
            if not self._is_in_memory and self.db_path and self.db_path != ':memory:':
                resolved_db_path = Path(self.db_path).resolve()
                try:
                    # Determine format, default to turtle.
                    # If db_path has a common RDF extension, use that, otherwise turtle.
                    file_format = rdflib.util.guess_format(str(resolved_db_path))
                    if file_format is None:
                        # If filename is e.g. "knowledge_base.db" and we want to save as turtle:
                        # We should ensure self.db_path implies a .ttl or similar, or save with a fixed extension.
                        # For now, we'll try to use turtle if format is unknown or not typical RDF.
                        # A more robust solution might involve checking the db_path extension or having a dedicated save format.
                        kce_logger.info(f"Output format for {resolved_db_path} not guessed, defaulting to turtle. Consider using .ttl extension.")
                        file_format = "turtle"
                        # To ensure it saves with a .ttl extension if not already present:
                        # if not str(resolved_db_path).endswith(f".{file_format}"):
                        #    resolved_db_path = resolved_db_path.with_suffix(f".{file_format}")
                        #    kce_logger.info(f"Saving to {resolved_db_path} to ensure turtle format.")

                    # Ensure parent directory exists
                    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)

                    self.graph.serialize(destination=str(resolved_db_path), format=file_format)
                    kce_logger.info(f"Graph serialized to {resolved_db_path} in {file_format} format.")
                except Exception as e:
                    kce_logger.error(f"Failed to serialize graph to {resolved_db_path}: {e}", exc_info=True)

            self.graph.close() # Close the rdflib graph itself

        # self.store is removed, so no store.close() needed.
        kce_logger.info(f"RdfStoreManager for {db_identity} closed.")

    def clear_store(self):
        if self.graph is None: # Should not happen if __init__ is correct
            kce_logger.error("Graph not initialized. Cannot clear store.")
            return

        kce_logger.info(f"Clearing store. Is in-memory: {self._is_in_memory}. Re-initializing graph.")
        # For both in-memory and file-based, clearing means creating a new empty graph.
        # For file-based, the old file content is not wiped until .close() is called.
        self.graph = Graph(identifier=self.graph_identifier)
        # If there were ontology files, they should ideally be reloaded here if clear means "reset to initial state"
        # For now, "clear" means an empty graph. This can be revisited.
        kce_logger.info("Graph re-initialized. Previous content (if any) will be overwritten on close for file-based stores.")

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()
