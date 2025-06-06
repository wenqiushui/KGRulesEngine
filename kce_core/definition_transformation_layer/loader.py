import yaml
import json
import os
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD

# Assuming interfaces.py is two levels up from definition_transformation_layer directory
from ..interfaces import IDefinitionTransformationLayer, IKnowledgeLayer, LoadStatus, InitialStateGraph, DirectoryPath

# Define KCE and other relevant namespaces (should ideally come from a central ontology definitions file)
KCE = Namespace("http://kce.com/ontology/core#")
EX = Namespace("http://example.com/ns#") # Example namespace for instance data

class DefinitionLoader(IDefinitionTransformationLayer):
    def __init__(self, knowledge_layer: IKnowledgeLayer):
        self.kl = knowledge_layer
        # You might want to define expected namespaces or load them from the KCE core ontology
        self.kce_ns_map = {
            "kce": KCE,
            "rdf": RDF,
            "rdfs": RDFS,
            "xsd": XSD,
            "ex": EX, # For example data
        }

    def _prefix_uri(self, value: str) -> URIRef:
        '''Converts a prefixed string (e.g., "kce:Node") to a URIRef if a prefix is found,
           otherwise assumes it's a full URI or creates one with a default namespace.'''
        if ":" in value:
            prefix, local_name = value.split(":", 1)
            if prefix in self.kce_ns_map:
                return self.kce_ns_map[prefix][local_name]
        # Fallback or error if no recognized prefix and not a full URI
        if value.startswith("http://") or value.startswith("https://") or value.startswith("urn:"):
            return URIRef(value)
        # Default to EX namespace if it's a simple string without recognized prefix
        print(f"Warning: No prefix found for '{value}', defaulting to example namespace or treating as full URI.")
        return EX[value] # Or raise an error, or use a default base URI from config

    def _parse_node_definition(self, data: Dict, file_path: str) -> Graph:
        g = Graph()
        node_uri = self._prefix_uri(data.get("uri", f"urn:uuid:{os.urandom(16).hex()}")) # Generate URI if missing
        g.add((node_uri, RDF.type, KCE.AtomicNode)) # Or kce:Node from FR-KM-002

        if "name" in data:
            g.add((node_uri, RDFS.label, Literal(data["name"])))
        if "description" in data:
            g.add((node_uri, RDFS.comment, Literal(data["description"]))) # Or kce:description

        # FR-DEF-001: Preconditions, Inputs, Effects, Outputs, Implementation, Capability
        if "precondition" in data: # SPARQL ASK
            g.add((node_uri, KCE.hasPrecondition, Literal(data["precondition"], datatype=KCE.SparqlQuery)))

        for param_type, kce_predicate in [("inputs", KCE.hasInputParameter), ("outputs", KCE.hasOutputParameter)]:
            if param_type in data:
                for p_data in data[param_type]:
                    param_uri = self._prefix_uri(p_data.get("uri", f"{node_uri}/param/{p_data['name']}"))
                    g.add((param_uri, RDF.type, KCE.Parameter)) # KCE.InputParameter / KCE.OutputParameter
                    g.add((param_uri, RDFS.label, Literal(p_data["name"])))
                    if "mapsToRdfProperty" in p_data:
                        g.add((param_uri, KCE.mapsToRdfProperty, self._prefix_uri(p_data["mapsToRdfProperty"])))
                    if "datatype" in p_data:
                        g.add((param_uri, KCE.hasDatatype, self._prefix_uri(p_data["datatype"])))
                    g.add((node_uri, kce_predicate, param_uri))

        if "effect" in data: # SPARQL UPDATE template or similar
             g.add((node_uri, KCE.hasEffect, Literal(data["effect"], datatype=KCE.SparqlUpdateTemplate))) # Or structured node

        if "implementation" in data:
            impl_uri = URIRef(f"{node_uri}/implementation")
            g.add((impl_uri, RDF.type, KCE.ImplementationDetail))
            if "type" in data["implementation"] and data["implementation"]["type"] == "python_script":
                g.add((impl_uri, KCE.invocationType, KCE.PythonScriptInvocation))
                if "scriptPath" in data["implementation"]:
                    g.add((impl_uri, KCE.scriptPath, Literal(data["implementation"]["scriptPath"])))
            g.add((node_uri, KCE.hasImplementationDetail, impl_uri))

        if "capability" in data: # FR-DEF-001 AC7
            # Assuming data["capability"] is a URI of a CapabilityTemplate
            g.add((node_uri, KCE.implementsCapability, self._prefix_uri(data["capability"])))
            # Mappings would be more complex, perhaps as separate triples or structured literals

        # Bind namespaces for cleaner RDF output if serialized
        for prefix, namespace in self.kce_ns_map.items():
            g.bind(prefix, namespace)
        return g

    def _parse_rule_definition(self, data: Dict, file_path: str) -> Graph:
        g = Graph()
        rule_uri = self._prefix_uri(data.get("uri", f"urn:uuid:{os.urandom(16).hex()}"))
        g.add((rule_uri, RDF.type, KCE.Rule))
        # ... (similar parsing for name, description, antecedent, consequent, priority) ...
        if "name" in data:
            g.add((rule_uri, RDFS.label, Literal(data["name"])))
        if "description" in data:
            g.add((rule_uri, RDFS.comment, Literal(data["description"])))
        if "priority" in data:
            g.add((rule_uri, KCE.hasPriority, Literal(data["priority"], datatype=XSD.integer)))

        if "antecedent" in data: # SPARQL WHERE part
            g.add((rule_uri, KCE.hasAntecedent, Literal(data["antecedent"], datatype=KCE.SparqlQuery)))
        if "consequent" in data: # SPARQL CONSTRUCT/INSERT/UPDATE
            g.add((rule_uri, KCE.hasConsequent, Literal(data["consequent"], datatype=KCE.SparqlUpdate))) # Or KCE.SparqlConstruct

        for prefix, namespace in self.kce_ns_map.items():
            g.bind(prefix, namespace)
        return g

    def _parse_capability_template_definition(self, data: Dict, file_path: str) -> Graph:
        g = Graph()
        cap_uri = self._prefix_uri(data.get("uri", f"urn:uuid:{os.urandom(16).hex()}"))
        g.add((cap_uri, RDF.type, KCE.CapabilityTemplate))
        # ... (similar parsing for name, description, inputInterface, outputInterface) ...
        if "name" in data:
            g.add((cap_uri, RDFS.label, Literal(data["name"])))
        if "description" in data:
            g.add((cap_uri, RDFS.comment, Literal(data["description"])))

        for if_type, kce_predicate in [("inputInterface", KCE.hasInputInterface), ("outputInterface", KCE.hasOutputInterface)]:
            if if_type in data:
                for p_data in data[if_type]:
                    param_uri = self._prefix_uri(p_data.get("uri", f"{cap_uri}/interface/{p_data['name']}"))
                    g.add((param_uri, RDF.type, KCE.InterfaceParameter)) # Or more specific type
                    g.add((param_uri, RDFS.label, Literal(p_data["name"])))
                    if "type" in p_data: # Abstract type description
                         g.add((param_uri, KCE.hasAbstractType, Literal(p_data["type"])))
                    g.add((cap_uri, kce_predicate, param_uri))

        for prefix, namespace in self.kce_ns_map.items():
            g.bind(prefix, namespace)
        return g

    def load_definitions_from_path(self, path: DirectoryPath) -> LoadStatus:
        loaded_files_count = 0
        errors = []

        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith((".yaml", ".yml")):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r') as f:
                            yaml_data_list = list(yaml.safe_load_all(f)) # Support multi-document YAML

                        for yaml_data in yaml_data_list:
                            if not yaml_data or not isinstance(yaml_data, dict): # Skip empty or non-dict documents
                                continue

                            doc_type = yaml_data.get("kind", None) # Assuming a 'kind' field to distinguish definition types
                            rdf_graph = None

                            if doc_type == "AtomicNode" or ("implementation" in yaml_data and "precondition" in yaml_data): # Fallback heuristic
                                rdf_graph = self._parse_node_definition(yaml_data, file_path)
                            elif doc_type == "Rule" or ("antecedent" in yaml_data and "consequent" in yaml_data):
                                rdf_graph = self._parse_rule_definition(yaml_data, file_path)
                            elif doc_type == "CapabilityTemplate" or ("inputInterface" in yaml_data and "outputInterface" in yaml_data):
                                rdf_graph = self._parse_capability_template_definition(yaml_data, file_path)
                            # Add more types as needed (e.g., CompositeNode, Ontology, InstanceData)
                            else:
                                errors.append({"file": file_path, "error": f"Unknown or unspecified 'kind' in YAML document: {list(yaml_data.keys())}"})
                                continue # Skip this document

                            if rdf_graph and len(rdf_graph) > 0:
                                self.kl.add_graph(rdf_graph) # Use the KnowledgeLayer to add the graph
                                loaded_files_count +=1 # Or count documents
                            elif rdf_graph is None: # Error already logged if kind was unknown
                                pass
                            else: # Graph was created but is empty, maybe a warning?
                                print(f"Warning: Generated empty RDF graph for a document in {file_path}")

                    except yaml.YAMLError as ye:
                        errors.append({"file": file_path, "error": f"YAML parsing error: {ye}"})
                    except Exception as e:
                        errors.append({"file": file_path, "error": f"General error processing file: {e}"})

        # Optionally, trigger reasoning after loading all definitions
        # self.kl.trigger_reasoning()

        return {"loaded_definitions_count": loaded_files_count, "errors": errors}

    def load_initial_state_from_json(self, json_data_str: str, base_uri_str: str) -> InitialStateGraph:
        '''Parses problem instance JSON and converts it to an initial RDF graph.
           This is a simplified example; a more robust converter would be needed.
        '''
        g = Graph()
        base_uri = Namespace(base_uri_str)
        try:
            data = json.loads(json_data_str)

            # Simple conversion: Assumes top-level keys are entities, and their dicts are properties
            # This needs to be much more robust based on actual JSON structure and mapping rules.
            for entity_name, properties in data.items():
                entity_uri = base_uri[entity_name]
                g.add((entity_uri, RDF.type, KCE.ProblemInstanceEntity)) # Example type
                if isinstance(properties, dict):
                    for prop_name, value in properties.items():
                        prop_uri = base_uri[prop_name] # This is too simple, properties should have proper URIs
                        if isinstance(value, list):
                            for item in value:
                                g.add((entity_uri, prop_uri, Literal(item)))
                        else:
                            g.add((entity_uri, prop_uri, Literal(value)))
            return g
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for initial state: {e}")
            raise # Or return an empty graph / handle error appropriately
        except Exception as e:
            print(f"Error converting initial state JSON to RDF: {e}")
            raise

if __name__ == '__main__':
    # Example Usage (requires a mock IKnowledgeLayer)
    class MockKnowledgeLayer(IKnowledgeLayer):
        def __init__(self): self.graph = Graph()
        def execute_sparql_query(self, query): print(f"MockKL Query: {query}"); return []
        def execute_sparql_update(self, update_statement): print(f"MockKL Update: {update_statement}")
        def trigger_reasoning(self): print("MockKL Trigger Reasoning")
        def add_graph(self, graph_to_add, context_uri=None):
            print(f"MockKL Add Graph (context: {context_uri}): {len(graph_to_add)} triples");
            self.graph += graph_to_add
        def get_graph(self, context_uri=None): return self.graph
        def store_human_readable_log(self, run_id, event_id, log_content): return f"logs/{run_id}/{event_id}.log"
        def get_human_readable_log(self, log_location): return "log content"

    mock_kl = MockKnowledgeLayer()
    loader = DefinitionLoader(knowledge_layer=mock_kl)

    # Create dummy YAML files for testing
    os.makedirs("temp_defs/nodes", exist_ok=True)
    os.makedirs("temp_defs/rules", exist_ok=True)

    with open("temp_defs/nodes/node1.yaml", "w") as f:
        f.write("""
kind: AtomicNode
uri: ex:MyTestNode
name: My Test Node
description: A node for testing.
precondition: ASK { ?s ?p ?o . }
inputs:
  - name: input1
    mapsToRdfProperty: ex:hasInputData
    datatype: xsd:string
outputs:
  - name: output1
    mapsToRdfProperty: ex:hasOutputData
    datatype: xsd:integer
implementation:
  type: python_script
  scriptPath: scripts/my_script.py
""")

    with open("temp_defs/rules/rule1.yaml", "w") as f:
        f.write("""
kind: Rule
uri: ex:MyTestRule
name: My Test Rule
antecedent: WHERE { ?s kce:someCondition true . }
consequent: INSERT DATA { ex:newState kce:generatedByRule ex:MyTestRule . }
""")

    status = loader.load_definitions_from_path("temp_defs")
    print("Load Status:", status)
    print(f"Total triples in MockKL: {len(mock_kl.get_graph())}")
    # print(mock_kl.get_graph().serialize(format="turtle"))


    # Test initial state loading
    json_state = '{ "myCar": { "width": 1500, "height": 2400 }, "environment": { "temperature": 25 } }'
    initial_graph = loader.load_initial_state_from_json(json_state, "http://example.com/problemInstance/")
    print(f"Initial state graph has {len(initial_graph)} triples.")
    # print(initial_graph.serialize(format="turtle"))
    mock_kl.add_graph(initial_graph, context_uri="urn:problem:initial_state")


    # Clean up dummy files
    import shutil
    shutil.rmtree("temp_defs")
    print("DefinitionLoader test complete.")
