import rdflib
from rdflib import Graph, URIRef, Literal, Namespace # Ensure all are imported
# Attempting alternative import path for Memory store plugin
try:
    from rdflib.plugins.memory import Memory as MemoryStorePlugin
except ImportError:
    from rdflib.plugins.stores.memory import Memory as MemoryStorePlugin # Alternative path
from rdflib.plugins.sparql import prepareQuery, prepareUpdate
from rdflib_sqlalchemy.store import Store as SQLAlchemyStore
# from sqlalchemy import create_engine
import owlrl
from typing import List, Dict, Any, Optional, Union, Tuple
import os
import logging
from pathlib import Path

from ...interfaces import IKnowledgeLayer, RDFGraph, SPARQLQuery, SPARQLUpdate, LogLocation

kce_logger = logging.getLogger(__name__)
if not kce_logger.handlers:
    kce_logger.addHandler(logging.NullHandler())

DEFAULT_DB_FILENAME = "kce_knowledge_base.sqlite"
DEFAULT_DATA_DIR = Path("data")
DEFAULT_LOG_DIR = DEFAULT_DATA_DIR / "logs"
KCE_GRAPH_IDENTIFIER = URIRef("http://kce.com/graph")

class RdfStoreManager(IKnowledgeLayer):
    def __init__(self, db_path: Optional[str] = None, ontology_files: Optional[List[str]] = None, log_dir: Optional[str] = None):
        self.db_path = db_path
        self.graph_identifier = KCE_GRAPH_IDENTIFIER
        self.store = None
        self.db_uri = None
        self._is_in_memory = False

        self.log_dir = Path(log_dir if log_dir else DEFAULT_LOG_DIR).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        if self.db_path is None or self.db_path == ':memory:':
            kce_logger.info("RdfStoreManager initializing with explicit RDFLib MemoryStorePlugin.")
            self._is_in_memory = True
            self.store = MemoryStorePlugin() # Instantiate the memory store plugin
            self.graph = Graph(store=self.store, identifier=self.graph_identifier)
            # No graph.open() needed for MemoryStorePlugin
        else:  # Persistent store using SQLAlchemy
            self._is_in_memory = False
            kce_logger.info(f"RdfStoreManager initializing with SQLAlchemyStore for persistent storage: {self.db_path}")

            if "://" not in self.db_path:
                resolved_db_path = Path(self.db_path).resolve()
                resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
                self.db_uri = f"sqlite:///{resolved_db_path}"
            else:
                self.db_uri = self.db_path

            self.store = SQLAlchemyStore(identifier=self.graph_identifier, configuration=self.db_uri)
            try:
                # Explicitly open the store. For SQLAlchemyStore, this should handle table creation.
                self.store.open(configuration=self.db_uri, create=True)
                kce_logger.info(f"SQLAlchemyStore opened successfully for URI: {self.db_uri}")
            except Exception as e:
                kce_logger.error(f"Failed to open SQLAlchemyStore with URI {self.db_uri}: {e}", exc_info=True)
                # This might be critical, consider re-raising or alternative handling
                # For now, let's see if graph init works or also fails

            self.graph = Graph(store=self.store, identifier=self.graph_identifier)
            # Depending on the store plugin, graph.open() might be redundant if store.open() did everything,
            # or it might be necessary. For safety and to follow rdflib patterns:
            try:
                self.graph.open(self.db_uri, create=True) # create=True might be ignored if store already created tables
                kce_logger.info(f"Persistent graph (using SQLAlchemyStore) opened successfully for URI: {self.db_uri}")
            except Exception as e:
                kce_logger.error(f"Failed to open graph (using SQLAlchemyStore) with URI {self.db_uri}: {e}", exc_info=True)
                raise

        if ontology_files and self.graph is not None:
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

        target_graph = self.graph
        log_msg_context = "default graph"

        if context_uri:
            # Note: self.store is None for in-memory MemoryStorePlugin.
            # It is an SQLAlchemyStore instance for persistent dbs.
            if self.store and not self._is_in_memory :
                target_graph_identifier = URIRef(context_uri)
                target_graph = Graph(store=self.store, identifier=target_graph_identifier)
                try:
                    target_graph.open(self.db_uri, create=False)
                except Exception as e:
                    kce_logger.error(f"Failed to open named graph context {context_uri}: {e}. Triples will likely be added to default graph or fail.", exc_info=True)
                    target_graph = self.graph
                    log_msg_context = "default graph (fallback from named)"
            else:
                kce_logger.warning(f"Context URI '{context_uri}' provided for in-memory store. Operations will target default graph as MemoryStorePlugin does not inherently support named contexts in this setup.")

        for s, p, o in graph_to_add:
            target_graph.add((s,p,o))
        if hasattr(target_graph, 'commit') and callable(target_graph.commit):
            target_graph.commit()
        kce_logger.debug(f"Added {len(graph_to_add)} triples to {log_msg_context}.")

    def get_graph(self, context_uri: Optional[str] = None) -> RDFGraph:
        if self.graph is None:
            kce_logger.error("Graph not initialized. Cannot get graph.")
            return Graph()

        if context_uri:
            if self.store and not self._is_in_memory:
                named_graph_identifier = URIRef(context_uri)
                named_g = Graph(store=self.store, identifier=named_graph_identifier)
                try:
                    named_g.open(self.db_uri, create=False)
                    return named_g
                except Exception as e:
                    kce_logger.error(f"Failed to open named graph {context_uri} for get: {e}", exc_info=True)
                    return Graph()
            else:
                kce_logger.warning(f"Context URI '{context_uri}' requested for in-memory store. Returning default graph.")
                return self.graph
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
            self.graph.close()

        # Defensive check for the store closing logic
        if self._is_in_memory is False: # Explicitly check boolean state
            if self.store and hasattr(self.store, 'close') and callable(self.store.close):
                self.store.close()
        kce_logger.info(f"RdfStoreManager for {db_identity} closed.")

    def clear_store(self):
        if self.graph is None:
            kce_logger.error("Graph not initialized. Cannot clear store.")
            return

        kce_logger.info(f"Clearing store. Is in-memory: {self._is_in_memory}")
        if self._is_in_memory:
            kce_logger.info("Re-initializing in-memory graph by creating new MemoryStorePlugin and Graph.")
            self.store = MemoryStorePlugin() # Create a new store instance
            self.graph = Graph(store=self.store, identifier=self.graph_identifier)
        elif self.store: # Persistent SQLAlchemyStore
            kce_logger.info("Removing all triples from persistent graph.")
            self.graph.remove((None, None, None))
            if hasattr(self.graph, 'commit') and callable(self.graph.commit):
                self.graph.commit()
        else:
            kce_logger.warning("Store type unclear or not properly initialized. Cannot effectively clear.")

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()
