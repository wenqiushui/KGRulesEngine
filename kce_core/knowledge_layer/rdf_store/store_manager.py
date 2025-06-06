import sqlite3
import rdflib
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from rdflib_sqlite import SQLiteStore
import owlrl
from typing import List, Dict, Any, Optional, Union

# Assuming interfaces.py is one level up from rdf_store directory
from ..interfaces import IKnowledgeLayer, RDFGraph, SPARQLQuery, SPARQLUpdate, LogLocation

# Assuming log_manager.py is in the same directory or path is adjusted
# For now, let's assume it will be used internally or its functionality integrated.
# from ..log_manager import LogManager # This might be instantiated or its methods called

# Default path for the SQLite database if not provided
DEFAULT_DB_PATH = "data/kce_knowledge_base.sqlite"
DEFAULT_LOG_DIR = "data/logs/" # For human-readable logs

class RdfStoreManager(IKnowledgeLayer):
    def __init__(self, db_path: Optional[str] = None, ontology_files: Optional[List[str]] = None, log_dir: Optional[str] = None):
        self.db_path = db_path if db_path else DEFAULT_DB_PATH
        self.log_dir = log_dir if log_dir else DEFAULT_LOG_DIR

        # Ensure data directory exists
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        # Configure the store
        identifier = rdflib.URIRef("kce-graph")
        self.store = SQLiteStore(database=self.db_path, autocommit=True)
        self.graph = rdflib.Graph(store=self.store, identifier=identifier)
        self.graph.open(self.db_path, create=True)

        # Load ontologies if provided
        if ontology_files:
            for ont_file in ontology_files:
                try:
                    self.graph.parse(ont_file, format=rdflib.util.guess_format(ont_file))
                    print(f"Successfully loaded ontology: {ont_file}")
                except Exception as e:
                    print(f"Error loading ontology {ont_file}: {e}")

        # Initialize LogManager (example of integration)
        # self.log_manager = LogManager(log_dir=self.log_dir, rdf_graph=self.graph) # If LogManager handles RDF logging too

    def execute_sparql_query(self, query: SPARQLQuery) -> Union[List[Dict], bool, RDFGraph]:
        '''Executes a SPARQL query (SELECT, ASK, CONSTRUCT, DESCRIBE) against the RDF store.'''
        prepared_query = rdflib.plugins.sparql.prepareQuery(query)
        q_result = self.graph.query(prepared_query)

        if prepared_query.query_type == 'ASK':
            return q_result.askAnswer
        elif prepared_query.query_type == 'SELECT':
            return [dict(row) for row in q_result] # Convert to list of dicts
        elif prepared_query.query_type in ['CONSTRUCT', 'DESCRIBE']:
            return q_result.graph # Returns an rdflib.Graph
        return q_result # Should not happen for valid query types

    def execute_sparql_update(self, update_statement: SPARQLUpdate) -> None:
        '''Executes a SPARQL UPDATE (INSERT, DELETE) against the RDF store.'''
        prepared_update = rdflib.plugins.sparql.prepareUpdate(update_statement)
        self.graph.update(prepared_update)
        # self.graph.commit() # For SQLiteStore, autocommit might be on, or commit explicitly

    def trigger_reasoning(self) -> None:
        '''Triggers OWL RL reasoning on the RDF store.'''
        print("Starting OWL RL Reasoning...")
        try:
            owlrl.CombinedClosure.RDFS_OWLRL_Semantics(self.graph, axioms=True, daxioms=True).closure()
            # owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(self.graph) # Alternative way
            self.graph.commit() # Commit changes after reasoning
            print("OWL RL Reasoning complete.")
        except Exception as e:
            print(f"Error during OWL RL reasoning: {e}")


    def add_graph(self, graph_to_add: RDFGraph, context_uri: Optional[str] = None) -> None:
        '''Adds an RDF graph to the store, optionally in a specific named context.'''
        # If context_uri is provided, we might want to use a Dataset or a different graph identifier
        # For a single graph setup with SQLiteStore, adding to the main graph.
        if context_uri:
            # This needs a more complex setup for named graphs with rdflib-sqlite if not inherently supported by graph.addN
            # For now, merging into the default graph.
            # Consider using rdflib.Dataset if multiple named graphs are a strong requirement.
            print(f"Warning: context_uri ('{context_uri}') provided but current setup merges into default graph.")

        for triple in graph_to_add:
            self.graph.add(triple)
        # self.graph.commit()

    def get_graph(self, context_uri: Optional[str] = None) -> RDFGraph:
        '''Retrieves an RDF graph, optionally from a specific named context.'''
        if context_uri:
            # This would require fetching a specific named graph.
            # For now, returning the default graph.
            print(f"Warning: context_uri ('{context_uri}') provided but current setup returns default graph.")
            # named_graph = self.graph.get_context(context_uri) # This is for rdflib.Dataset
            # return named_graph
        return self.graph # Returns the main graph

    def store_human_readable_log(self, run_id: str, event_id: str, log_content: str) -> LogLocation:
        '''Stores human-readable log content and returns its location/identifier.'''
        import os
        run_log_dir = os.path.join(self.log_dir, run_id)
        os.makedirs(run_log_dir, exist_ok=True)
        log_file_path = os.path.join(run_log_dir, f"{event_id.replace(':', '_')}.log")
        try:
            with open(log_file_path, "w") as f:
                f.write(log_content)
            return log_file_path
        except IOError as e:
            print(f"Error writing human-readable log: {e}")
            return "" # Return empty string or raise error

    def get_human_readable_log(self, log_location: LogLocation) -> Optional[str]:
        '''Retrieves human-readable log content given its location/identifier.'''
        try:
            import os
            if os.path.exists(log_location):
                with open(log_location, "r") as f:
                    return f.read()
            else:
                print(f"Log file not found at: {log_location}")
                return None
        except IOError as e:
            print(f"Error reading human-readable log {log_location}: {e}")
            return None

    def close(self):
        '''Closes the graph store connection.'''
        self.graph.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    # Create a dummy ontology file
    with open("dummy_ontology.ttl", "w") as f:
        f.write("<urn:ex:subject> <urn:ex:predicate> <urn:ex:object> .")

    # Test with a persistent DB
    manager = RdfStoreManager(db_path="test_kce_db.sqlite", ontology_files=["dummy_ontology.ttl"])

    print(f"Default graph has {len(manager.get_graph())} triples after loading.")

    # Test add_graph
    g_add = rdflib.Graph()
    g_add.add((rdflib.URIRef("urn:test:entity1"), rdflib.RDF.type, rdflib.RDFS.Class))
    manager.add_graph(g_add)
    print(f"Graph has {len(manager.get_graph())} triples after adding a graph.")

    # Test SPARQL Update
    update_q = "INSERT DATA { <urn:test:entity2> a <urn:ex:MyType> . }"
    manager.execute_sparql_update(update_q)
    print(f"Graph has {len(manager.get_graph())} triples after SPARQL update.")

    # Test SPARQL Query
    select_q = "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5"
    results = manager.execute_sparql_query(select_q)
    print("Query results (first 5):", results)

    ask_q = "ASK { <urn:test:entity1> a <http://www.w3.org/2000/01/rdf-schema#Class> . }"
    ask_result = manager.execute_sparql_query(ask_q)
    print("ASK result:", ask_result)

    # Test Reasoning (simple RDFS example)
    manager.execute_sparql_update("INSERT DATA { <urn:test:sub> rdfs:subClassOf <urn:test:super>. <urn:test:ind> a <urn:test:sub>. }")
    print(f"Graph has {len(manager.get_graph())} triples before reasoning on subclass.")
    manager.trigger_reasoning()
    print(f"Graph has {len(manager.get_graph())} triples after reasoning.")

    reasoning_q = "SELECT ?ind WHERE { ?ind a <urn:test:super> . }"
    reasoning_results = manager.execute_sparql_query(reasoning_q)
    print("Individuals of type urn:test:super (after reasoning):", reasoning_results)

    # Test Human Readable Logs
    run1_event1_loc = manager.store_human_readable_log("run001", "event001_init", "System initialized with params X.")
    print(f"Stored log for run001/event001 at: {run1_event1_loc}")
    retrieved_log = manager.get_human_readable_log(run1_event1_loc)
    print(f"Retrieved log: {retrieved_log}")

    run1_event2_loc = manager.store_human_readable_log("run001", "event002_node_A_output", "{'output_value': 123}")
    print(f"Stored log for run001/event002 at: {run1_event2_loc}")


    # Clean up dummy files
    import os
    os.remove("dummy_ontology.ttl")
    # os.remove("test_kce_db.sqlite") # Keep it to see persistence or remove

    manager.close()
    print("Store manager operations test complete.")
