import pytest
from rdflib import Graph, URIRef, Literal, Namespace, XSD, RDF, RDFS # Ensure RDF, RDFS are imported
from kce_core.knowledge_layer.rdf_store.store_manager import RdfStoreManager
from pathlib import Path
import os # For persistent store cleanup, though tmp_path fixture handles it better

# Define namespaces for testing
EX = Namespace("http://example.org/")
ONT = Namespace("http://example.org/ontology#")
KCE = Namespace("http://kce.com/ontology/core#") # From RdfStoreManager

# Fixture for existing in-memory tests (renamed for clarity)
@pytest.fixture
def memory_store_manager():
    manager = RdfStoreManager(db_path=':memory:')
    yield manager
    manager.close()

# Fixture for creating a dummy ontology file
@pytest.fixture
def dummy_ontology_file(tmp_path):
    ontology_content = f"""
    @prefix rdf: <{RDF}> .
    @prefix rdfs: <{RDFS}> .
    @prefix ont: <{ONT}> .
    @prefix xsd: <{XSD}> .

    ont:MyClass rdfs:subClassOf rdfs:Resource .
    ont:myProperty rdf:type rdf:Property ;
                   rdfs:domain ont:MyClass ;
                   rdfs:range xsd:string .
    ont:myInstance rdf:type ont:MyClass ;
                  ont:myProperty "instance value" .
    """
    d = tmp_path / "ontologies"
    d.mkdir()
    p = d / "dummy_ontology.ttl"
    p.write_text(ontology_content)
    return p

# Fixture for a second dummy ontology file
@pytest.fixture
def dummy_ontology_file_two(tmp_path):
    ontology_content = f"""
    @prefix rdf: <{RDF}> .
    @prefix rdfs: <{RDFS}> .
    @prefix ont: <{ONT}> .
    @prefix ex: <{EX}> .

    ex:AnotherClass rdfs:subClassOf rdfs:Resource .
    ex:anotherInstance rdf:type ex:AnotherClass .
    """
    d = tmp_path / "ontologies2" # Ensure different sub-directory or name
    d.mkdir()
    p = d / "dummy_ontology_two.ttl"
    p.write_text(ontology_content)
    return p

# Fixture for persistent store tests
@pytest.fixture
def persistent_store_manager(tmp_path):
    db_file = tmp_path / "persistent_store.ttl"  # Changed extension
    manager = RdfStoreManager(db_path=str(db_file))
    yield manager
    manager.close()
    # tmp_path fixture handles cleanup of the directory and file

# --- Existing Tests (slightly adapted for new fixture name) ---
def test_add_and_select_triples(memory_store_manager):
    subject = EX.subject1
    predicate = EX.predicate1
    obj_literal = Literal("Test Object", lang="en")

    triples_to_add = [(subject, predicate, obj_literal)]
    memory_store_manager.add_triples(triples_to_add)

    query_string = "SELECT ?s ?p ?o WHERE { ?s ?p ?o . }"
    results = memory_store_manager.execute_sparql_query(query_string)

    assert results is not None
    assert len(results) == 1
    row = results[0]
    assert row['s'] == subject
    assert row['p'] == predicate
    assert row['o'] == obj_literal

def test_ask_query(memory_store_manager):
    subject = EX.known_subject
    predicate = EX.known_predicate
    obj_val = Literal(123, datatype=XSD.integer)
    memory_store_manager.add_triples([(subject, predicate, obj_val)])

    ask_query_true_string = f"ASK WHERE {{ {subject.n3()} {predicate.n3()} {obj_val.n3()} . }}"
    assert memory_store_manager.execute_sparql_query(ask_query_true_string) is True

    non_existent_subject = EX.non_existent_subject
    ask_query_false_string = f"ASK WHERE {{ {non_existent_subject.n3()} {predicate.n3()} {obj_val.n3()} . }}"
    assert memory_store_manager.execute_sparql_query(ask_query_false_string) is False

def test_clear_store(memory_store_manager):
    subject = EX.data_to_clear
    predicate = EX.has_value
    obj = Literal("some value")
    memory_store_manager.add_triples([(subject, predicate, obj)])

    ask_query_exists = f"ASK WHERE {{ {subject.n3()} {predicate.n3()} {obj.n3()} . }}"
    assert memory_store_manager.execute_sparql_query(ask_query_exists) is True

    memory_store_manager.clear_store()
    assert memory_store_manager.execute_sparql_query(ask_query_exists) is False
    select_results = memory_store_manager.execute_sparql_query(f"SELECT ?s WHERE {{ {subject.n3()} {predicate.n3()} {obj.n3()} . }}")
    assert isinstance(select_results, list) and len(select_results) == 0

    new_subject = EX.new_data
    memory_store_manager.add_triples([(new_subject, predicate, obj)])
    assert memory_store_manager.execute_sparql_query(f"ASK WHERE {{ {new_subject.n3()} {predicate.n3()} {obj.n3()} . }}") is True
    assert len(list(memory_store_manager.graph)) == 1

# --- New Ontology Loading Tests ---
def test_load_ontology_from_file(dummy_ontology_file):
    # Ontology loading happens in __init__, so create a new manager
    manager = RdfStoreManager(db_path=':memory:', ontology_files=[str(dummy_ontology_file)])
    try:
        # Verify triples from the dummy ontology
        assert (ONT.myInstance, RDF.type, ONT.MyClass) in manager.graph
        assert (ONT.myInstance, ONT.myProperty, Literal("instance value")) in manager.graph
        assert (ONT.MyClass, RDFS.subClassOf, RDFS.Resource) in manager.graph
        # Check if a triple that is not in the ontology is not present
        assert (EX.nonExistentSubject, RDF.type, ONT.MyClass) not in manager.graph
    finally:
        manager.close()

def test_load_multiple_ontologies(dummy_ontology_file, dummy_ontology_file_two):
    manager = RdfStoreManager(db_path=':memory:', ontology_files=[str(dummy_ontology_file), str(dummy_ontology_file_two)])
    try:
        # Verify triples from first ontology
        assert (ONT.myInstance, RDF.type, ONT.MyClass) in manager.graph
        # Verify triples from second ontology
        assert (EX.anotherInstance, RDF.type, EX.AnotherClass) in manager.graph
    finally:
        manager.close()

def test_load_non_existent_ontology(memory_store_manager, caplog):
    # Use the existing memory_store_manager, which is empty initially
    # Attempt to load a non-existent file path using a new manager instance, as loading is in __init__
    non_existent_file = "path/to/non_existent_ontology.ttl"
    manager = RdfStoreManager(db_path=':memory:', ontology_files=[non_existent_file])
    try:
        assert len(manager.graph) == 0 # Should not have loaded anything new
        # Check logs (RdfStoreManager uses kce_logger which should be captured by caplog if configured)
        # This assertion depends on the logger name and level used in RdfStoreManager
        # For this example, we assume RdfStoreManager's logger is 'kce_core.knowledge_layer.rdf_store.store_manager'
        # and it logs a warning.
        # Note: caplog might need setup if kce_logger doesn't propagate to root or if test logger settings are restrictive.
        # For simplicity, check if any warning was logged by the relevant logger.
        found_log = False
        for record in caplog.records:
            if record.levelname == 'WARNING' and non_existent_file in record.message:
                found_log = True
                break
        assert found_log, f"Expected warning log for non-existent ontology file '{non_existent_file}' not found."
    finally:
        manager.close()


# --- New Reasoning Test ---
@pytest.fixture
def reasoning_ontology_file(tmp_path):
    content = f"""
    @prefix rdf: <{RDF}> .
    @prefix rdfs: <{RDFS}> .
    @prefix ont: <{ONT}> .

    ont:SubClass rdfs:subClassOf ont:SuperClass .
    ont:SuperClass rdfs:subClassOf rdfs:Resource . # Optional, for completeness
    """
    p = tmp_path / "reasoning_ontology.ttl"
    p.write_text(content)
    return p

def test_basic_reasoning(reasoning_ontology_file):
    # Reasoning needs a fresh manager with the specific ontology
    manager = RdfStoreManager(db_path=':memory:', ontology_files=[str(reasoning_ontology_file)])
    try:
        instance = EX.myInstance
        sub_class = ONT.SubClass
        super_class = ONT.SuperClass

        # Add an instance of the subclass
        manager.add_triples([(instance, RDF.type, sub_class)])

        # Before reasoning, check instance is not type SuperClass
        ask_is_super_type_query = f"ASK {{ {instance.n3()} rdf:type {super_class.n3()} . }}"
        assert manager.execute_sparql_query(ask_is_super_type_query) is False, "Instance should not be type SuperClass before reasoning"

        # Trigger reasoning
        manager.trigger_reasoning()

        # After reasoning, check instance IS type SuperClass
        assert manager.execute_sparql_query(ask_is_super_type_query) is True, "Instance should be type SuperClass after reasoning"
    finally:
        manager.close()

# --- New Persistent Store Tests ---
# @pytest.mark.skip(reason="Persistent store tests failing due to issues with SQLAlchemyStore v0.5.4 returning None for triples()") # Unskipped
def test_persistent_add_select(tmp_path):
    db_file = tmp_path / "test_persistent_add_select.ttl" # Changed extension and made filename specific
    manager1 = RdfStoreManager(db_path=str(db_file))

    subject = EX.persistentSubject
    predicate = EX.persistentPredicate
    obj = Literal("Persists!", lang="en")

    try:
        manager1.add_triples([(subject, predicate, obj)])
        # Verify in first manager instance
        query = f"ASK {{ {subject.n3()} {predicate.n3()} {obj.n3()} . }}"
        assert manager1.execute_sparql_query(query) is True
    finally:
        manager1.close()

    # Create a new manager instance with the same db_file
    manager2 = RdfStoreManager(db_path=str(db_file))
    try:
        # Verify data persists
        assert manager2.execute_sparql_query(query) is True
        assert (subject, predicate, obj) in manager2.graph
    finally:
        manager2.close()

# @pytest.mark.skip(reason="Persistent store tests failing due to issues with SQLAlchemyStore v0.5.4 returning None for triples()") # Unskipped
def test_persistent_clear(tmp_path):
    db_file = tmp_path / "test_persistent_clear.ttl" # Changed extension and made filename specific
    manager1 = RdfStoreManager(db_path=str(db_file))

    subject = EX.dataToClear
    predicate = EX.valueProperty
    obj = Literal("To be cleared")

    try:
        manager1.add_triples([(subject, predicate, obj)])
        query = f"ASK {{ {subject.n3()} {predicate.n3()} {obj.n3()} . }}"
        assert manager1.execute_sparql_query(query) is True

        manager1.clear_store()
        assert manager1.execute_sparql_query(query) is False
        assert len(list(manager1.graph)) == 0
    finally:
        manager1.close()

    # New manager instance should also see an empty store
    manager2 = RdfStoreManager(db_path=str(db_file))
    try:
        assert manager2.execute_sparql_query(query) is False
        assert len(list(manager2.graph)) == 0
    finally:
        manager2.close()
