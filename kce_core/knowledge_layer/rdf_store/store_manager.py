import rdflib
from rdflib.plugins.sparql import prepareQuery, prepareUpdate
from rdflib_sqlalchemy.store import SQLAlchemyStore
# from sqlalchemy import create_engine # Not strictly needed if only dburi is used by SQLAlchemyStore
import owlrl
from typing import List, Dict, Any, Optional, Union
import os
import logging
from pathlib import Path # Ensure Path is imported

from ...interfaces import IKnowledgeLayer, RDFGraph, SPARQLQuery, SPARQLUpdate, LogLocation

kce_logger = logging.getLogger(__name__) # Use module-specific logger
if not kce_logger.handlers:
    kce_logger.addHandler(logging.NullHandler()) # Library default

DEFAULT_DB_FILENAME = "kce_knowledge_base.sqlite"
DEFAULT_DATA_DIR = Path("data") # Use Path object
DEFAULT_LOG_DIR = DEFAULT_DATA_DIR / "logs"

class RdfStoreManager(IKnowledgeLayer):
    def __init__(self, db_path: Optional[str] = None, ontology_files: Optional[List[str]] = None, log_dir: Optional[str] = None):
        self.db_uri: str
        if db_path is None or db_path == ':memory:': # Handle explicit in-memory
            self.db_uri = "sqlite:///:memory:"
            kce_logger.info("RdfStoreManager initialized with in-memory SQLite store using rdflib-sqlalchemy.")
        else: # Persistent store
            db_file_path = Path(db_path).resolve()
            db_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_uri = f"sqlite:///{db_file_path}"
            kce_logger.info(f"RdfStoreManager initialized with persistent SQLite store at: {self.db_uri} using rdflib-sqlalchemy.")

        self.log_dir = Path(log_dir if log_dir else DEFAULT_LOG_DIR).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.graph_identifier = rdflib.URIRef("kce_default_graph")
        self.store = SQLAlchemyStore(identifier=self.graph_identifier, dburi=self.db_uri, string_diff_patch=True)
        self.graph = rdflib.Graph(store=self.store, identifier=self.graph_identifier)

        if ontology_files:
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
            self.graph.commit() # Commit after loading ontologies

    def execute_sparql_query(self, query: SPARQLQuery) -> Union[List[Dict[str, Any]], bool, RDFGraph]:
        init_ns = {pfx: str(ns) for pfx, ns in self.graph.namespaces()}
        prepared_query = prepareQuery(query, initNs=init_ns)
        q_result = self.graph.query(prepared_query)

        if prepared_query.query_type == 'ASK': return q_result.askAnswer # type: ignore [attr-defined]
        elif prepared_query.query_type == 'SELECT':
            # Correctly convert ResultRow objects to dictionaries
            return [row.asdict() for row in q_result]
        elif prepared_query.query_type in ['CONSTRUCT', 'DESCRIBE']: return q_result.graph # type: ignore [attr-defined]
        kce_logger.warning(f"Unknown or unhandled SPARQL query type: {prepared_query.query_type}")
        if isinstance(q_result, list): return q_result
        return [] # Default empty list for unknown results

    def execute_sparql_update(self, update_statement: SPARQLUpdate) -> None:
        init_ns = {pfx: str(ns) for pfx, ns in self.graph.namespaces()}
        prepared_update = prepareUpdate(update_statement, initNs=init_ns)
        self.graph.update(prepared_update)
        self.graph.commit()

    def trigger_reasoning(self) -> None:
        kce_logger.info("Starting OWL RL Reasoning with owlrl...")
        try:
            closure = owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, rdfs_closure=False, axiomatic_triples=True, datatype_axioms=True)
            closure.expand(self.graph)
            self.graph.commit()
            kce_logger.info("OWL RL Reasoning complete.")
        except Exception as e:
            kce_logger.error(f"Error during OWL RL reasoning: {e}", exc_info=True)

    def add_graph(self, graph_to_add: RDFGraph, context_uri: Optional[str] = None) -> None:
        target_graph = self.graph
        log_msg_context = "default graph"
        if context_uri:
            target_graph = rdflib.Graph(store=self.store, identifier=rdflib.URIRef(context_uri))
            log_msg_context = f"named graph: {context_uri}"

        for triple in graph_to_add:
            target_graph.add(triple)
        target_graph.commit()
        kce_logger.debug(f"Added {len(graph_to_add)} triples to {log_msg_context}.")

    def get_graph(self, context_uri: Optional[str] = None) -> RDFGraph:
        if context_uri:
            return rdflib.Graph(store=self.store, identifier=rdflib.URIRef(context_uri))
        return self.graph

    def store_human_readable_log(self, run_id: str, event_id: str, log_content: str) -> LogLocation:
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
            if log_file.is_file(): # Check if it's a file specifically
                with open(log_file, "r", encoding='utf-8') as f: return f.read()
            else: kce_logger.warning(f"Human-readable log file not found or is not a file: {log_location}"); return None
        except IOError as e:
            kce_logger.error(f"Error reading human-readable log {log_location}: {e}", exc_info=True)
            return None

    def close(self):
        if self.graph is not None: self.graph.close()
        kce_logger.info(f"RdfStoreManager for {self.db_uri} closed.")

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()
