import rdflib
from typing import Optional, Any, Union, List, Dict
import uuid
import json

# Define KCE and other relevant namespaces (should ideally come from a central ontology definitions file)
KCE_NS = "http://kce.com/ontology/core#"
EX_NS = "http://example.com/ns#"

KCE = rdflib.Namespace(KCE_NS)
EX = rdflib.Namespace(EX_NS)
RDF = rdflib.RDF
RDFS = rdflib.RDFS
XSD = rdflib.XSD # rdflib.namespace.XSD is correct

def generate_instance_uri(base_uri: str, prefix: str, local_name: Optional[str] = None) -> rdflib.URIRef:
    if not base_uri.endswith("/"):
        base_uri += "/"
    # Sanitize local_name if provided, e.g., replace spaces
    safe_local_name = local_name.replace(' ', '_').replace('#', '_').replace('?', '_') if local_name else None

    if safe_local_name:
        return rdflib.URIRef(f"{base_uri}{prefix}/{safe_local_name}")
    return rdflib.URIRef(f"{base_uri}{prefix}/{uuid.uuid4()}")

def get_value_from_graph(graph: rdflib.Graph,
                         subject_uri: Optional[rdflib.URIRef],
                         predicate_uri: rdflib.URIRef,
                         preferred_lang: str = "en") -> Optional[Any]:
    '''
    Retrieves a single value for a given subject and predicate from the graph.
    Handles literals (with language preference), URI resources.
    Returns Python native type for literals, or rdflib.URIRef/BNode for resources.
    Returns None if no value is found.
    '''
    # Store objects to avoid multiple graph traversals if possible
    objects = list(graph.objects(subject_uri, predicate_uri))
    if not objects:
        return None

    # 1. Try preferred language literal
    for obj in objects:
        if isinstance(obj, rdflib.Literal) and obj.language == preferred_lang:
            return obj.toPython() # Converts to Python native type

    # 2. Try non-language-tagged literal
    for obj in objects:
        if isinstance(obj, rdflib.Literal) and not obj.language:
            return obj.toPython()

    # 3. Try any other language literal if preferred and non-tagged not found
    for obj in objects:
        if isinstance(obj, rdflib.Literal):
            return obj.toPython()

    # 4. If it's not a Literal, it might be a URIRef or BNode
    for obj in objects: # Should be only one if we got here and it's not a literal list
        if not isinstance(obj, rdflib.Literal):
            return obj # Return the rdflib term itself (URIRef or BNode)

    return None # Should not be reached if objects list was not empty

def create_rdf_graph_from_json_ld_dict(json_ld_dict: Dict, default_base_ns_str: Optional[str]=None) -> rdflib.Graph:
    g = rdflib.Graph()
    # Use provided default_base_ns_str or fall back to EX_NS
    effective_base_ns_str = default_base_ns_str if default_base_ns_str else EX_NS
    if not effective_base_ns_str.endswith(('#', '/')): # Ensure namespace ends with # or /
        effective_base_ns_str += "#"
    base_ns = rdflib.Namespace(effective_base_ns_str)

    context = json_ld_dict.get("@context", {})

    prefixes = { # Default common prefixes
        'rdf': RDF, 'rdfs': RDFS, 'xsd': XSD,
        'kce': KCE, 'ex': EX
    }
    if isinstance(context, dict):
        for k, v in context.items():
            if isinstance(v, str) and not k.startswith("@"):
                prefixes[k] = rdflib.Namespace(v)

    # Bind known prefixes to the graph
    for prefix_label, namespace_obj in prefixes.items():
        g.bind(prefix_label, namespace_obj)


    def expand_uri(value_str: str) -> rdflib.URIRef:
        if value_str.startswith("http://") or value_str.startswith("https://") or value_str.startswith("urn:"):
            return rdflib.URIRef(value_str)
        if ":" in value_str:
            prefix, local_name = value_str.split(":", 1)
            if prefix in prefixes:
                return prefixes[prefix][local_name]
        return base_ns[value_str]

    entities_to_process = []
    if "@graph" in json_ld_dict and isinstance(json_ld_dict["@graph"], list):
        entities_to_process.extend(json_ld_dict["@graph"])
    elif isinstance(json_ld_dict, list): # Handle list of entities at top level
        entities_to_process.extend(json_ld_dict)
    elif isinstance(json_ld_dict, dict) and ( "@id" in json_ld_dict or any(not k.startswith("@") for k in json_ld_dict.keys())):
        entities_to_process.append(json_ld_dict)


    for entity_data in entities_to_process:
        if not isinstance(entity_data, dict): continue

        subject_uri_str = entity_data.get('@id')
        if not subject_uri_str:
            subject_uri = rdflib.BNode()
        else:
            subject_uri = expand_uri(subject_uri_str)

        type_values_from_data = entity_data.get("@type", [])
        if not isinstance(type_values_from_data, list): type_values_from_data = [type_values_from_data]
        for type_val_str in type_values_from_data:
                 g.add((subject_uri, RDF.type, expand_uri(type_val_str)))


        for key, value_obj in entity_data.items():
            if key.startswith('@'):
                continue

            prop_uri = expand_uri(key)

            values_to_add = value_obj if isinstance(value_obj, list) else [value_obj]

            for v_item in values_to_add:
                if isinstance(v_item, dict):
                    if '@id' in v_item:
                        g.add((subject_uri, prop_uri, expand_uri(v_item['@id'])))
                    elif '@value' in v_item:
                        lit_val = v_item['@value']
                        lit_lang = v_item.get('@language')
                        lit_type_str = v_item.get('@type')

                        datatype_uri = expand_uri(lit_type_str) if lit_type_str else None
                        g.add((subject_uri, prop_uri, rdflib.Literal(lit_val, lang=lit_lang or None, datatype=datatype_uri)))
                elif isinstance(v_item, str) and (v_item.startswith("http:") or v_item.startswith("https:") or v_item.startswith("urn:") or (":" in v_item and v_item.split(":",1)[0] in prefixes)):
                    g.add((subject_uri, prop_uri, expand_uri(v_item)))
                else:
                    g.add((subject_uri, prop_uri, rdflib.Literal(v_item)))
    return g

def graph_to_json_ld_string(graph: rdflib.Graph, context: Optional[Dict] = None, base_uri: Optional[str] = None) -> str:
    try:
        default_context = {
            "xsd": str(XSD), "rdf": str(RDF), "rdfs": str(RDFS),
            "kce": str(KCE), "ex": str(EX) # Use stringified namespaces for context
        }
        if context: default_context.update(context)

        json_ld_str = graph.serialize(format='json-ld', context=default_context, indent=2, auto_compact=True)
        return json_ld_str
    except Exception as e: # Broad exception for potential serialization issues
        print(f"Error during advanced JSON-LD serialization: {e}. Falling back to basic dictionary list.")
        output_list = []
        for s, p, o in graph:
            s_dict = {"@id": str(s)}
            p_str = str(p)
            o_val: Any
            if isinstance(o, rdflib.URIRef):
                o_val = {"@id": str(o)}
            elif isinstance(o, rdflib.Literal):
                o_val = {"@value": o.toPython()}
                if o.language: o_val["@language"] = o.language
                if o.datatype: o_val["@type"] = str(o.datatype)
            else: # BNode
                o_val = str(o)

            # Try to merge if subject already in list (very basic grouping)
            found = False
            for item in output_list:
                if item["@id"] == s_dict["@id"]:
                    if p_str not in item:
                        item[p_str] = o_val
                    elif isinstance(item[p_str], list):
                        item[p_str].append(o_val)
                    else: # Convert single value to list
                        item[p_str] = [item[p_str], o_val]
                    found = True
                    break
            if not found:
                 s_dict[p_str] = o_val
                 output_list.append(s_dict)
        return json.dumps({"@context": default_context, "@graph": output_list}, indent=2)


if __name__ == '__main__':
    print("kce_core.common.utils tests starting.")
    # Test generate_instance_uri
    uri1 = generate_instance_uri("http://example.com/data/", "item", "My Item 1")
    assert str(uri1) == "http://example.com/data/item/My_Item_1"
    uri2 = generate_instance_uri("http://example.com/data", "item") # No local name
    assert "http://example.com/data/item/" in str(uri2) and len(str(uri2)) > len("http://example.com/data/item/") + 30 # UUID
    print("generate_instance_uri tests passed.")

    g_test = rdflib.Graph()
    ts = EX.testSubject
    tp_en = EX.testPredicateEn
    tp_fr = EX.testPredicateFr
    tp_none = EX.testPredicateNoLang

    g_test.add((ts, tp_en, rdflib.Literal("Test Value EN", lang="en")))
    g_test.add((ts, tp_fr, rdflib.Literal("Test Value FR", lang="fr")))
    g_test.add((ts, tp_none, rdflib.Literal("Test Value NoLang")))
    g_test.add((ts, EX.hasNumber, rdflib.Literal(123, datatype=XSD.integer)))
    g_test.add((ts, EX.hasLink, EX.linkedResource))
    g_test.add((ts, EX.multiLang, rdflib.Literal("English", lang="en")))
    g_test.add((ts, EX.multiLang, rdflib.Literal("Deutsch", lang="de")))

    assert get_value_from_graph(g_test, ts, tp_en, preferred_lang="en") == "Test Value EN"
    assert get_value_from_graph(g_test, ts, tp_fr, preferred_lang="en") == "Test Value FR"
    assert get_value_from_graph(g_test, ts, tp_none, preferred_lang="en") == "Test Value NoLang"
    assert get_value_from_graph(g_test, ts, EX.hasNumber) == 123
    assert get_value_from_graph(g_test, ts, EX.hasLink) == EX.linkedResource
    assert get_value_from_graph(g_test, ts, EX.multiLang, preferred_lang="de") == "Deutsch"
    assert get_value_from_graph(g_test, ts, EX.multiLang, preferred_lang="es") == "English" # Falls back to first found if preferred not there
    print(f"get_value_from_graph tests passed.")

    json_ld_str_complex = """
    {
        "@context": {
            "ex": "http://example.com/ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "kce": "http://kce.com/ontology/core#", "foo": "http://foo.com/"
        },
        "@graph": [
            {
                "@id": "ex:MyEntity123", "@type": ["kce:SomeType", "foo:CustomEntity"],
                "rdfs:label": "Test Entity From JSON",
                "ex:hasNumber": {"@value": 456, "@type": "xsd:integer"},
                "ex:hasLink": {"@id": "ex:AnotherLinkedEntity"},
                "ex:stringProp": "A string value",
                "ex:boolProp": {"@value": true, "@type": "xsd:boolean"},
                "ex:dateProp": {"@value": "2023-01-01", "@type": "xsd:date"},
                "ex:listOfNumbers": [{"@value": 1, "@type": "xsd:integer"}, {"@value": 2, "@type": "xsd:integer"}]
            }
        ]
    }
    """
    g_from_json = create_rdf_graph_from_json_ld_dict(json.loads(json_ld_str_complex))
    print(f"Graph from JSON-LD ({len(g_from_json)} triples):")
    # Expected: types (2) + label (1) + hasNumber (1) + hasLink (1) + stringProp (1) + boolProp (1) + dateProp (1) + listOfNumbers (2) = 10
    assert len(g_from_json) == 10, f"Expected 10 triples, got {len(g_from_json)}"
    # print(g_from_json.serialize(format="turtle"))

    json_ld_output = graph_to_json_ld_string(g_from_json)
    # print(f"\nGraph to JSON-LD string:\n{json_ld_output}")
    assert "ex:MyEntity123" in json_ld_output and "kce:SomeType" in json_ld_output
    assert "foo:CustomEntity" in json_ld_output and "456" in json_ld_output
    assert "\"true\"" in json_ld_output or "true," in json_ld_output # Handle boolean serialization
    assert "2023-01-01" in json_ld_output
    print("JSON-LD conversion tests passed.")

    print("kce_core.common.utils tests complete.")
