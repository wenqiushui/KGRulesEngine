import rdflib
from typing import Optional, Any, Union, List, Dict, Mapping # Added Mapping
import uuid
import json
import logging # Added for kce_logger
import sys # Added for kce_logger handler (if used)
from pathlib import Path # Added for load_json_file and path operations

# --- Logger Setup ---
kce_logger = logging.getLogger("kce_core") # Use a common root logger for the library
if not kce_logger.handlers:
    # Add a NullHandler if no handlers are configured by the application.
    # This prevents 'No handler found' warnings and allows the application to control logging.
    kce_logger.addHandler(logging.NullHandler())
    # Application (e.g., CLI) can then add specific handlers and set levels:
    # Example (in CLI or application entry point):
    # import logging
    # from kce_core.common.utils import kce_logger
    # console_handler = logging.StreamHandler()
    # console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    # kce_logger.addHandler(console_handler)
    # kce_logger.setLevel(logging.INFO) # Or DEBUG based on verbosity

# --- Namespace Definitions ---
KCE_NS_STR = "http://kce.com/ontology/core#" # Use _STR suffix for string version
EX_NS_STR = "http://example.com/ns#"
DOMAIN_NS_STR = "http://kce.com/example/elevator_panel#" # For example domain

KCE = rdflib.Namespace(KCE_NS_STR)
EX = rdflib.Namespace(EX_NS_STR)
DOMAIN = rdflib.Namespace(DOMAIN_NS_STR)
RDF = rdflib.RDF
RDFS = rdflib.RDFS
OWL = rdflib.OWL
XSD = rdflib.XSD
DCTERMS = rdflib.DCTERMS
PROV = rdflib.PROV

# Default prefix map for to_uriref and potentially other functions
DEFAULT_PREFIX_MAP: Mapping[str, Union[rdflib.Namespace, str]] = {
    "kce": KCE, "ex": EX, "domain": DOMAIN, # Use Namespace objects
    "rdf": RDF, "rdfs": RDFS, "xsd": XSD, "owl": OWL,
    "dcterms": DCTERMS, "prov": PROV
}

# --- Utility Functions ---
def generate_instance_uri(base_uri: str, prefix: str, local_name: Optional[str] = None) -> rdflib.URIRef:
    if not base_uri.endswith(("/", "#")):
        base_uri += "/" # Default to slash if not specified
    safe_local_name = local_name.replace(' ', '_').replace('#', '_').replace('?', '_') if local_name else None
    if safe_local_name:
        return rdflib.URIRef(f"{base_uri}{prefix}/{safe_local_name}")
    return rdflib.URIRef(f"{base_uri}{prefix}/{uuid.uuid4()}")

def get_value_from_graph(graph: rdflib.Graph,
                         subject_uri: Optional[rdflib.URIRef],
                         predicate_uri: rdflib.URIRef,
                         preferred_lang: str = "en") -> Optional[Any]:
    objects = list(graph.objects(subject_uri, predicate_uri))
    if not objects: return None
    for obj in objects: # Check preferred language first
        if isinstance(obj, rdflib.Literal) and obj.language == preferred_lang: return obj.toPython()
    for obj in objects: # Then non-language-tagged
        if isinstance(obj, rdflib.Literal) and not obj.language: return obj.toPython()
    for obj in objects: # Then any other language
        if isinstance(obj, rdflib.Literal): return obj.toPython()
    for obj in objects: # Then URIRefs/BNodes
        if not isinstance(obj, rdflib.Literal): return obj
    return None

def create_rdf_graph_from_json_ld_dict(json_ld_dict: Dict, default_base_ns_str: Optional[str]=None) -> rdflib.Graph:
    g = rdflib.Graph()
    effective_base_ns_str = default_base_ns_str if default_base_ns_str else EX_NS_STR
    if not effective_base_ns_str.endswith(('#', '/')): effective_base_ns_str += "#"
    base_ns = rdflib.Namespace(effective_base_ns_str)
    context = json_ld_dict.get("@context", {})
    prefixes = DEFAULT_PREFIX_MAP.copy() # Start with defaults
    if isinstance(context, dict):
        for k, v_ns_str in context.items():
            if isinstance(v_ns_str, str) and not k.startswith("@"): prefixes[k] = rdflib.Namespace(v_ns_str)
    for pfx_label, ns_obj in prefixes.items(): g.bind(pfx_label, ns_obj)
    def expand_uri(value_str: str) -> rdflib.URIRef:
        if value_str.startswith(("http://", "https://", "urn:")): return rdflib.URIRef(value_str)
        if ":" in value_str:
            pfx, l_name = value_str.split(":", 1)
            if pfx in prefixes: return prefixes[pfx][l_name] # type: ignore
        return base_ns[value_str]
    entities_to_process = []
    if "@graph" in json_ld_dict and isinstance(json_ld_dict["@graph"], list): entities_to_process.extend(json_ld_dict["@graph"])
    elif isinstance(json_ld_dict, list): entities_to_process.extend(json_ld_dict)
    elif isinstance(json_ld_dict, dict) and ("@id" in json_ld_dict or any(not k.startswith("@") for k in json_ld_dict.keys())): entities_to_process.append(json_ld_dict)
    for entity_data in entities_to_process:
        if not isinstance(entity_data, dict): continue
        subject_uri_str = entity_data.get('@id')
        subject_uri = expand_uri(subject_uri_str) if subject_uri_str else rdflib.BNode()
        type_values = entity_data.get("@type", []); type_values = type_values if isinstance(type_values, list) else [type_values]
        for type_val_str in type_values: g.add((subject_uri, RDF.type, expand_uri(type_val_str)))
        for key, value_obj in entity_data.items():
            if key.startswith('@'): continue
            prop_uri = expand_uri(key)
            values_to_add = value_obj if isinstance(value_obj, list) else [value_obj]
            for v_item in values_to_add:
                if isinstance(v_item, dict):
                    if '@id' in v_item: g.add((subject_uri, prop_uri, expand_uri(v_item['@id'])))
                    elif '@value' in v_item:
                        lit_val,l_lang,l_type_str = v_item['@value'],v_item.get('@language'),v_item.get('@type')
                        dt_uri = expand_uri(l_type_str) if l_type_str else None
                        g.add((subject_uri, prop_uri, rdflib.Literal(lit_val, lang=l_lang or None, datatype=dt_uri)))
                elif isinstance(v_item, str) and (v_item.startswith(("http:","https:","urn:")) or (":" in v_item and v_item.split(":",1)[0] in prefixes)):
                    g.add((subject_uri, prop_uri, expand_uri(v_item)))
                else: g.add((subject_uri, prop_uri, rdflib.Literal(v_item)))
    return g

def graph_to_json_ld_string(graph: rdflib.Graph, context: Optional[Dict] = None, base_uri: Optional[str] = None) -> str:
    try:
        ctx = {pfx: str(ns) for pfx, ns in graph.namespaces()}
        if context: ctx.update(context)
        for p, u_ns in DEFAULT_PREFIX_MAP.items(): # Ensure defaults are there
            if p not in ctx: ctx[p] = str(u_ns) # Use string form of namespace for context
        return graph.serialize(format='json-ld', context=ctx, indent=2, auto_compact=True)
    except Exception as e:
        kce_logger.warning(f"Advanced JSON-LD serialization failed: {e}. Using basic dict list.")
        output_list = []
        for s, p, o in graph:
            s_val, p_val = str(s), str(p)
            o_val_dict: Dict[str, Any] = {}
            if isinstance(o, rdflib.URIRef): o_val_dict = {"@id": str(o)}
            elif isinstance(o, rdflib.Literal): o_val_dict = {"@value": o.toPython()}; if o.language: o_val_dict["@language"] = o.language; if o.datatype: o_val_dict["@type"] = str(o.datatype)
            else: o_val_dict = {"@id": str(o)} # BNode as @id (or str(o) directly)
            found = False
            for item in output_list:
                if item["@id"] == s_val: item.setdefault(p_val, []).append(o_val_dict); found = True; break
            if not found: output_list.append({"@id": s_val, p_val: [o_val_dict]})
        return json.dumps({"@context": ctx, "@graph": output_list}, indent=2)

def load_json_file(file_path: Union[str, Path]) -> Any:
    file_p = Path(file_path)
    try:
        with file_p.open('r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError: kce_logger.error(f"JSON file not found: {file_p}"); raise
    except json.JSONDecodeError as e: kce_logger.error(f"Error decoding JSON from {file_p}: {e}"); raise

def to_uriref(term_str: Optional[str], base_ns: Optional[Union[rdflib.Namespace, str]] = None, known_prefixes: Optional[Mapping[str, Union[rdflib.Namespace, str]]] = None) -> Optional[rdflib.URIRef]:
    if not term_str: return None
    if isinstance(term_str, rdflib.URIRef): return term_str
    if not isinstance(term_str, str): term_str = str(term_str)
    if term_str.startswith(('<', 'http://', 'https://', 'urn:')):
        return rdflib.URIRef(term_str[1:-1] if term_str.startswith('<') else term_str)
    current_prefixes = DEFAULT_PREFIX_MAP.copy()
    if known_prefixes: current_prefixes.update(known_prefixes)
    if ":" in term_str:
        prefix, local_name = term_str.split(":", 1)
        if prefix in current_prefixes:
            ns_val = current_prefixes[prefix]
            return ns_val[local_name] if isinstance(ns_val, rdflib.Namespace) else rdflib.URIRef(str(ns_val) + local_name)
    if base_ns: return base_ns[term_str] if isinstance(base_ns, rdflib.Namespace) else rdflib.URIRef(str(base_ns) + term_str)
    try: return rdflib.URIRef(term_str) # Last attempt, might be invalid relative URI
    except Exception as e: kce_logger.error(f"Failed to convert '{term_str}' to URIRef: {e}"); return None

