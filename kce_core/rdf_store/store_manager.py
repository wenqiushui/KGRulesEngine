# kce_core/rdf_store/store_manager.py

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Iterator, Type

from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, OWL, XSD # For convenience
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore # If connecting to external SPARQL endpoint
from rdflib.term import Node as RDFNode # Type hint for rdflib nodes

# For SQLite backend (ensure rdflib-sqlite is installed)
try:
    from rdflib_sqlite import SQLExternalStorePLSQL # This might vary with plugin versions
except ImportError:
    SQLExternalStorePLSQL = None # Fallback or raise error if SQLite is mandatory

# Import owlrl components based on v7.x API
# Import the specific semantics classes directly from owlrl
from owlrl import DeductiveClosure, OWLRL_Semantics, RDFS_Semantics # Add other semantics if needed

from kce_core.common.utils import (
    kce_logger,
    KCEError,
    RDFStoreError,
    KCE, PROV, DCTERMS, EX, # Import common namespaces
    to_uriref,
    to_literal
)
from . import sparql_queries # Import predefined query templates

# Default store identifier for rdflib-sqlite
DEFAULT_SQLITE_IDENTIFIER = URIRef("kce-knowledge-base")

# Define a type alias for the semantics classes for cleaner type hints
# This allows reasoning_level to be typed as expecting one of these classes.
OwlrlSemanticsClassType = Type[Union[OWLRL_Semantics, RDFS_Semantics]] # Add more if KCE uses them


class StoreManager:
    """
    Manages interactions with the RDF knowledge base (Graph).
    Handles data loading, querying, updates, and OWL RL reasoning.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = "kce_store.sqlite",
                 identifier: URIRef = DEFAULT_SQLITE_IDENTIFIER,
                 reasoning_level: Optional[OwlrlSemanticsClassType] = OWLRL_Semantics, # Default to OWLRL_Semantics class
                 auto_reason: bool = True):
        """
        Initializes the StoreManager.

        Args:
            db_path: Path to the SQLite database file. If None, an in-memory store is used.
            identifier: The identifier for the rdflib store (used by some backends like SQLite).
            reasoning_level: The semantics class from the owlrl module to use for reasoning
                             (e.g., OWLRL_Semantics, RDFS_Semantics from owlrl module).
                             Set to None to disable reasoning initially.
            auto_reason: If True, automatically performs reasoning after data modifications.
        """
        self.db_path = Path(db_path) if db_path else None
        self.identifier = identifier
        self.reasoning_level_class: Optional[OwlrlSemanticsClassType] = reasoning_level # Store the class
        self.auto_reason = auto_reason
        self.graph: Graph
        self._init_graph()
        self._bind_common_namespaces()

        reasoning_name = self.reasoning_level_class.__name__ if self.reasoning_level_class else 'Disabled'
        kce_logger.info(f"StoreManager initialized. DB: {self.db_path or 'In-memory'}. Reasoning: {reasoning_name}.")

    def _init_graph(self):
        """Initializes the RDFLib Graph with the specified backend."""
        if self.db_path:
            if SQLExternalStorePLSQL is None and self.db_path.name != ":memory:":
                kce_logger.warning("rdflib-sqlite plugin not found. Attempting default SQLite store if supported by rdflib, or consider installing rdflib-sqlite.")

            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.graph = Graph(store='SQLite', identifier=self.identifier)
                self.graph.open(str(self.db_path), create=True)
                kce_logger.debug(f"Using SQLite store at: {self.db_path}")
            except Exception as e:
                raise RDFStoreError(f"Failed to open SQLite store at {self.db_path} (is rdflib-sqlite installed and configured?): {e}")
        else:
            self.graph = Graph(identifier=self.identifier)
            kce_logger.debug("Using in-memory RDF store.")

    def _bind_common_namespaces(self):
        """Binds common namespaces to the graph for more readable RDF serialization."""
        self.graph.bind("kce", KCE)
        self.graph.bind("prov", PROV)
        self.graph.bind("rdf", RDF)
        self.graph.bind("rdfs", RDFS)
        self.graph.bind("owl", OWL)
        self.graph.bind("xsd", XSD)
        self.graph.bind("dcterms", DCTERMS)
        self.graph.bind("ex", EX)

    def close(self):
        """Closes the graph store connection."""
        if self.graph:
            self.graph.close()
            kce_logger.info(f"RDF store closed ({self.db_path or 'In-memory'}).")

    def clear_graph(self, auto_rebind_ns: bool = True): # auto_rebind_ns is effectively always True due to re-init
        """Removes all triples from the graph. Re-initializes for persistent stores."""
        current_db_path = self.db_path
        current_identifier = self.identifier
        current_reasoning_level = self.reasoning_level_class
        current_auto_reason = self.auto_reason
        
        if hasattr(self.graph, 'destroy') and self.db_path and self.db_path.name != ":memory:":
             try:
                 self.graph.destroy(configuration=str(self.db_path)) # Some stores need configuration string
             except Exception as e_destroy:
                 kce_logger.warning(f"Could not explicitly destroy store {self.db_path}, attempting unlink: {e_destroy}")
                 if self.db_path.exists():
                     self.close()
                     self.db_path.unlink()
        elif self.db_path and self.db_path.exists() and self.db_path.name != ":memory:":
            self.close()
            self.db_path.unlink()

        # Re-initialize the graph object using saved parameters
        self.__init__(db_path=current_db_path, 
                      identifier=current_identifier,
                      reasoning_level=current_reasoning_level,
                      auto_reason=current_auto_reason)
        
        kce_logger.info("RDF graph cleared and re-initialized.")


    def load_rdf_file(self, file_path: Union[str, Path], rdf_format: Optional[str] = None,
                      perform_reasoning: Optional[bool] = None):
        path = Path(file_path)
        if not path.is_file():
            raise RDFStoreError(f"RDF file not found: {file_path}")
        try:
            self.graph.parse(source=str(path), format=rdf_format)
            kce_logger.info(f"Loaded RDF data from: {file_path}")
            should_reason = perform_reasoning if perform_reasoning is not None else self.auto_reason
            if should_reason:
                self.perform_reasoning()
        except Exception as e:
            raise RDFStoreError(f"Error parsing RDF file {file_path}: {e}")

    def add_triples(self, triples: Iterator[tuple[RDFNode, RDFNode, RDFNode]],
                    perform_reasoning: Optional[bool] = None):
        try:
            # If triples is an iterator, list(triples) will consume it.
            # For counting, convert to list first if it's not already huge.
            # If it could be huge, iterate once for adding, then don't log precise count or find another way.
            # For MVP, assuming it's manageable to convert to list for logging.
            triples_list = list(triples) # Consume iterator here for count
            count = len(triples_list)
            for s, p, o in triples_list:
                self.graph.add((s, p, o))
            kce_logger.debug(f"Added {count} triples.")
            should_reason = perform_reasoning if perform_reasoning is not None else self.auto_reason
            if should_reason:
                self.perform_reasoning()
        except Exception as e:
            raise RDFStoreError(f"Error adding triples: {e}")

    def add_triple(self, s: RDFNode, p: RDFNode, o: RDFNode, perform_reasoning: Optional[bool] = None):
        self.add_triples(iter([(s,p,o)]), perform_reasoning=perform_reasoning)


    def remove_triples(self, triples: Iterator[tuple[RDFNode, RDFNode, RDFNode]],
                       perform_reasoning: Optional[bool] = None):
        try:
            triples_list = list(triples) # Consume for count
            count = len(triples_list)
            for s, p, o in triples_list:
                self.graph.remove((s, p, o))
            kce_logger.debug(f"Removed {count} triples.")
            should_reason = perform_reasoning if perform_reasoning is not None else self.auto_reason
            if should_reason:
                self.perform_reasoning()
        except Exception as e:
            raise RDFStoreError(f"Error removing triples: {e}")

    def perform_reasoning(self):
        if not self.reasoning_level_class:
            kce_logger.debug("Reasoning is disabled (no reasoning_level_class). Skipping.")
            return

        reasoning_name = self.reasoning_level_class.__name__
        kce_logger.info(f"Performing {reasoning_name} reasoning...")
        try:
            closure = DeductiveClosure(
                self.reasoning_level_class, # Pass the class e.g. owlrl.OWLRL_Semantics
                axiomatic_triples=False,
                datatype_axioms=False
            )
            closure.expand(self.graph)
            kce_logger.info(f"Reasoning complete. Graph size: {len(self.graph)} triples.")
        except Exception as e:
            raise RDFStoreError(f"Error during {reasoning_name} reasoning with class {self.reasoning_level_class}: {e}")

    def query(self, sparql_query: str) -> List[Dict[str, RDFNode]]:
        kce_logger.debug(f"Executing SPARQL query:\n{sparql_query.strip()}")
        try:
            qres = self.graph.query(sparql_query)
            results = []
            select_vars = [str(var) for var in qres.vars] if qres.vars else []
            for row_tuple in qres:
                if not select_vars and row_tuple: # Handle cases like CONSTRUCT/DESCRIBE that return graph-like results
                    # For MVP, query is primarily for SELECT. If other types return rows, handle generically.
                     results.append({f"_{i}": item for i, item in enumerate(row_tuple)})
                elif select_vars:
                    results.append(dict(zip(select_vars, row_tuple)))
            kce_logger.debug(f"Query returned {len(results)} results.")
            return results
        except Exception as e:
            raise RDFStoreError(f"Error executing SPARQL SELECT query: {e}\nQuery:\n{sparql_query}")

    def update(self, sparql_update: str, perform_reasoning: Optional[bool] = None):
        kce_logger.debug(f"Executing SPARQL UPDATE:\n{sparql_update.strip()}")
        try:
            self.graph.update(sparql_update)
            kce_logger.debug("SPARQL UPDATE executed successfully.")
            should_reason = perform_reasoning if perform_reasoning is not None else self.auto_reason
            if should_reason:
                self.perform_reasoning()
        except Exception as e:
            raise RDFStoreError(f"Error executing SPARQL UPDATE query: {e}\nQuery:\n{sparql_update}")

    def ask(self, sparql_ask_query: str) -> bool:
        kce_logger.debug(f"Executing SPARQL ASK query:\n{sparql_ask_query.strip()}")
        try:
            qres = self.graph.query(sparql_ask_query)
            if qres.askAnswer is None:
                 kce_logger.warning("ASK query returned None for askAnswer. Treating as False.")
                 return False
            return bool(qres.askAnswer)
        except Exception as e:
            raise RDFStoreError(f"Error executing SPARQL ASK query: {e}\nQuery:\n{sparql_ask_query}")

    def get_instance_properties(self, instance_uri: Union[str, URIRef]) -> List[Dict[str, RDFNode]]:
        uri = to_uriref(instance_uri) if isinstance(instance_uri, str) else instance_uri
        query_str = sparql_queries.format_query(
            sparql_queries.GET_ALL_TRIPLES_FOR_SUBJECT,
            subject_uri=str(uri)
        )
        return self.query(query_str)

    def get_property_values(self, subject_uri: Union[str, URIRef],
                             property_uri: Union[str, URIRef]) -> List[RDFNode]:
        s_uri = to_uriref(subject_uri) if isinstance(subject_uri, str) else subject_uri
        p_uri = to_uriref(property_uri) if isinstance(property_uri, str) else property_uri

        query_str = sparql_queries.format_query(
            sparql_queries.GET_PROPERTIES_FOR_SUBJECT,
            subject_uri=str(s_uri),
            property_uri=str(p_uri)
        )
        results = self.query(query_str)
        return [row['value'] for row in results if 'value' in row]
    
    def get_single_property_value(self, subject_uri: Union[str, URIRef],
                                   property_uri: Union[str, URIRef],
                                   default: Optional[Any] = None) -> Optional[RDFNode]:
        values = self.get_property_values(subject_uri, property_uri)
        if len(values) == 1:
            return values[0]
        elif not values:
            if default is not None:
                 return default
            return None
        else:
            kce_logger.warning(f"Multiple values found for <{subject_uri}> <{property_uri}> when one was expected. Returning first.")
            return values[0]

    def serialize_graph(self, destination: Optional[Union[str, Path]] = None, rdf_format: str = "turtle") -> Optional[str]:
        try:
            return self.graph.serialize(destination=str(destination) if destination else None, format=rdf_format, encoding="utf-8")
        except Exception as e:
            raise RDFStoreError(f"Error serializing graph to {destination or 'string'} in {rdf_format} format: {e}")


if __name__ == '__main__':
    kce_logger.setLevel(logging.DEBUG) 

    print("\n--- Testing In-Memory Store with owlrl.OWLRL_Semantics (class) ---")
    mem_store_manager = StoreManager(db_path=None, auto_reason=False, reasoning_level=OWLRL_Semantics) # Directly use imported class
    
    s = KCE.TestSubject
    p1 = KCE.hasName
    o1 = Literal("Test Name", lang="en")
    mem_store_manager.add_triple(s, p1, o1)
    mem_store_manager.add_triple(KCE.MyClass, RDFS.subClassOf, KCE.BaseClass)
    mem_store_manager.add_triple(s, RDF.type, KCE.MyClass)

    print(f"Graph size before reasoning: {len(mem_store_manager.graph)}")
    print("Performing reasoning...")
    mem_store_manager.perform_reasoning()
    print(f"Graph size after reasoning: {len(mem_store_manager.graph)}")
    
    inferred_type_query = sparql_queries.format_query(
        "SELECT ?type WHERE {{ <{subject_uri}> <{rdf_ns}type> ?type . }}",
        subject_uri=str(s)
    )
    types_after_reasoning = mem_store_manager.query(inferred_type_query)
    print(f"Types of {s} after reasoning:")
    found_base_class = False
    for row in types_after_reasoning:
        print(f"  {row['type']}")
        if row['type'] == KCE.BaseClass: 
            found_base_class = True
    assert found_base_class, f"Expected <{KCE.BaseClass}> to be inferred for <{s}>. Found types: {[r['type'] for r in types_after_reasoning]}"
    
    mem_store_manager.close()
    print("StoreManager test with owlrl.OWLRL_Semantics (class) completed.")

    print("\n--- Testing In-Memory Store with owlrl.RDFS_Semantics (class) ---")
    mem_store_manager_rdfs = StoreManager(db_path=None, auto_reason=False, reasoning_level=RDFS_Semantics) # Directly use imported class
    mem_store_manager_rdfs.add_triple(KCE.MySpecificClass, RDFS.subClassOf, KCE.MyGeneralClass)
    mem_store_manager_rdfs.add_triple(KCE.MyGeneralClass, RDFS.subClassOf, KCE.MyRootClass)
    mem_store_manager_rdfs.add_triple(KCE.myInstance, RDF.type, KCE.MySpecificClass)
    
    print("Performing RDFS reasoning...")
    mem_store_manager_rdfs.perform_reasoning()
    
    inferred_rdfs_type_query = sparql_queries.format_query(
        "SELECT ?type WHERE {{ <{instance_uri}> <{rdf_ns}type> ?type . }}",
        instance_uri=str(KCE.myInstance)
    )
    types_after_rdfs_reasoning = mem_store_manager_rdfs.query(inferred_rdfs_type_query)
    print(f"Types of {KCE.myInstance} after RDFS reasoning:")
    inferred_types_set = set()
    for row in types_after_rdfs_reasoning:
        print(f"  {row['type']}")
        inferred_types_set.add(row['type'])
    
    assert KCE.MySpecificClass in inferred_types_set
    assert KCE.MyGeneralClass in inferred_types_set
    assert KCE.MyRootClass in inferred_types_set
    
    mem_store_manager_rdfs.close()
    print("StoreManager test with owlrl.RDFS_Semantics (class) completed.")

    if SQLExternalStorePLSQL: # Or just try: if True:
        print("\n--- Testing clear_graph with SQLite Store ---")
        sqlite_db_file_clear = Path("test_kce_store_clear.sqlite")
        if sqlite_db_file_clear.exists():
            sqlite_db_file_clear.unlink()

        sql_store_clear = StoreManager(db_path=sqlite_db_file_clear)
        sql_store_clear.add_triple(EX.DataPointClear, DCTERMS.title, Literal("To be cleared"))
        assert len(sql_store_clear.graph) > 0 # After add, should be > 0
        print(f"Graph size before clear: {len(sql_store_clear.graph)}")
        
        sql_store_clear.clear_graph() # This re-initializes the StoreManager instance
        print(f"Graph size after clear: {len(sql_store_clear.graph)}") # Length of the new empty graph
        assert len(sql_store_clear.graph) == 0

        sql_store_clear.add_triple(EX.DataPointClear2, DCTERMS.title, Literal("After clear"))
        assert len(sql_store_clear.graph) > 0
        print(f"Graph size after adding post-clear: {len(sql_store_clear.graph)}")
        
        sql_store_clear.close()
        if sqlite_db_file_clear.exists():
            sqlite_db_file_clear.unlink()
        print("clear_graph test completed.")
    else:
        print("\n--- Skipping SQLite clear_graph test (rdflib-sqlite issues or not primary focus) ---")