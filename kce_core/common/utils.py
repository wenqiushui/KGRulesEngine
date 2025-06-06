# kce_core/common/utils.py

import yaml
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Union, Optional
from rdflib import Namespace, URIRef, Literal, XSD

# --- Constants ---

# Define common namespaces used in KCE (adjust URIs as needed)
KCE_NS_STR = "http://kce.com/ontology/core#" # Example, replace with your actual ontology URI base
KCE = Namespace(KCE_NS_STR)
PROV = Namespace("http://www.w3.org/ns/prov#")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")
XSD_NS = Namespace(str(XSD)) # Get the XSD namespace string correctly
DCTERMS = Namespace("http://purl.org/dc/terms/") # For common metadata like description
EX_NS_STR = "http://kce.com/example#" # Example namespace for domain-specific things
EX = Namespace(EX_NS_STR)


# Default YAML encoding
YAML_ENCODING = 'utf-8'

# Default logging format
LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOG_LEVEL = logging.INFO


# --- Custom Exceptions ---

class KCEError(Exception):
    """Base class for KCE specific errors."""
    pass

class DefinitionError(KCEError):
    """Error related to loading or parsing definitions (YAML, etc.)."""
    pass

class RDFStoreError(KCEError):
    """Error related to RDF store operations."""
    pass

class ExecutionError(KCEError):
    """Error occurring during workflow or node execution."""
    pass

class ConfigurationError(KCEError):
    """Error related to KCE configuration itself."""
    pass


# --- Configuration and File Handling ---

def load_yaml_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Loads a YAML file and returns its content as a dictionary.
    Raises DefinitionError if file not found or parsing fails.
    """
    path = Path(file_path)
    if not path.is_file():
        raise DefinitionError(f"YAML file not found: {file_path}")
    try:
        with open(path, 'r', encoding=YAML_ENCODING) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise DefinitionError(f"Error parsing YAML file {file_path}: {e}")
    except Exception as e:
        raise DefinitionError(f"Unexpected error loading YAML file {file_path}: {e}")

def load_json_file(file_path: Union[str, Path]) -> Union[Dict[str, Any], List[Any]]:
    """
    Loads a JSON file and returns its content.
    Raises DefinitionError if file not found or parsing fails.
    """
    path = Path(file_path)
    if not path.is_file():
        raise DefinitionError(f"JSON file not found: {file_path}")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise DefinitionError(f"Error parsing JSON file {file_path}: {e}")
    except Exception as e:
        raise DefinitionError(f"Unexpected error loading JSON file {file_path}: {e}")

def load_json_string(json_string: str) -> Union[Dict[str, Any], List[Any]]:
    """
    Loads a JSON string and returns its content.
    Raises DefinitionError if parsing fails.
    """
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        raise DefinitionError(f"Error parsing JSON string: {e}")
    except Exception as e:
        raise DefinitionError(f"Unexpected error loading JSON string: {e}")

def resolve_path(base_path: Union[str, Path], relative_path: str) -> Path:
    """
    Resolves a relative path against a base path (typically the location of a config file).
    Returns an absolute Path object.
    """
    base = Path(base_path)
    if base.is_file():
        base = base.parent
    return (base / relative_path).resolve()


# --- RDF Utilities ---

def to_uriref(value: str, base_ns: Optional[Namespace] = KCE) -> URIRef:
    """
    Converts a string to a URIRef.
    If it contains ':', it's assumed to be a full URI or a prefixed name that rdflib can handle.
    Otherwise, it prepends the base_ns.
    """
    if ':' in value: # crude check for prefixed name or full URI
        # For prefixed names like 'kce:MyNode', rdflib's Namespace manager handles it
        # if the prefix is bound to the graph. Here, we assume it might be full or
        # will be handled by graph.bind(). If it's a direct URI, URIRef() is fine.
        return URIRef(value)
    elif base_ns:
        return base_ns[value]
    else:
        raise ValueError("Cannot create URIRef without a base namespace for non-prefixed value.")

def to_literal(value: Any, datatype: Optional[URIRef] = None, lang: Optional[str] = None) -> Literal:
    """
    Converts a Python value to an RDFLib Literal with an optional XSD datatype.
    Tries to infer common XSD datatypes if not provided.
    """
    if datatype:
        return Literal(value, datatype=datatype, lang=lang)

    if isinstance(value, bool):
        return Literal(value, datatype=XSD.boolean)
    elif isinstance(value, int):
        return Literal(value, datatype=XSD.integer)
    elif isinstance(value, float):
        return Literal(value, datatype=XSD.double) # or XSD.decimal
    elif isinstance(value, str):
        return Literal(value, datatype=XSD.string, lang=lang)
    # Add more type inference if needed (e.g., datetime.date -> XSD.date)
    else:
        # Default to string if datatype cannot be inferred or is not explicitly given
        return Literal(str(value), datatype=XSD.string, lang=lang)

def get_xsd_uriref(xsd_type_short: str) -> Optional[URIRef]:
    """
    Converts a short XSD type string (e.g., "integer", "string", "boolean")
    to its corresponding rdflib XSD URIRef.
    Returns None if not found.
    """
    mapping = {
        "string": XSD.string,
        "integer": XSD.integer,
        "int": XSD.integer, # alias
        "boolean": XSD.boolean,
        "bool": XSD.boolean, # alias
        "float": XSD.float,
        "double": XSD.double,
        "decimal": XSD.decimal,
        "dateTime": XSD.dateTime,
        "date": XSD.date,
        "time": XSD.time,
        "anyURI": XSD.anyURI,
    }
    return mapping.get(xsd_type_short.lower())


# --- Logging Setup ---

def setup_logger(name: str, level: int = DEFAULT_LOG_LEVEL, log_file: Optional[Union[str, Path]] = None) -> logging.Logger:
    """
    Sets up a logger with a standard format.
    """
    logger = logging.getLogger(name)
    if not logger.handlers: # Avoid adding multiple handlers if called multiple times
        logger.setLevel(level)
        formatter = logging.Formatter(LOGGING_FORMAT)

        # Console Handler
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # File Handler (optional)
        if log_file:
            fh = logging.FileHandler(log_file)
            fh.setLevel(level)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
    return logger

# Example of a global logger for the KCE core, can be configured from CLI later
kce_logger = setup_logger("kce_core")


# --- Other Utilities ---

def generate_unique_id(prefix: str = "urn:uuid:") -> str:
    """Generates a unique ID, e.g., for run instances."""
    import uuid
    return f"{prefix}{uuid.uuid4()}"

def get_from_dict_path(data_dict: Dict, path_keys: List[str], default: Optional[Any] = None) -> Any:
    """
    Safely retrieves a value from a nested dictionary using a list of keys (path).
    Returns default if path is not found or any intermediate key is missing.
    Example: get_from_dict_path({"a": {"b": 1}}, ["a", "b"]) -> 1
             get_from_dict_path({"a": {"b": 1}}, ["a", "c"], "default") -> "default"
    """
    current = data_dict
    for key in path_keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current

if __name__ == '__main__':
    # Simple test cases for utils
    kce_logger.info("Utils module loaded and testing.")

    # Test YAML loading
    test_yaml_content = """
    name: Test KCE
    version: 0.1
    nodes:
      - id: NodeA
        script: scripts/node_a.py
    """
    with open("test_temp.yaml", "w") as f:
        f.write(test_yaml_content)
    try:
        data = load_yaml_file("test_temp.yaml")
        assert data["name"] == "Test KCE"
        kce_logger.info(f"YAML loaded successfully: {data}")
        Path("test_temp.yaml").unlink() # Clean up
    except KCEError as e:
        kce_logger.error(f"YAML loading test failed: {e}")

    # Test JSON loading
    test_json_content = """{"param1": 10, "param2": "hello"}"""
    try:
        data = load_json_string(test_json_content)
        assert data["param1"] == 10
        kce_logger.info(f"JSON string loaded successfully: {data}")
    except KCEError as e:
        kce_logger.error(f"JSON string loading test failed: {e}")


    # Test RDF utils
    uri1 = to_uriref("MyClass", KCE)
    uri2 = to_uriref("kce:MyInstance", KCE) # KCE namespace here is just for demonstration
                                          # normally, prefixed names are handled by graph.namespace_manager
    uri3 = to_uriref("http://example.com/AnotherClass")
    kce_logger.info(f"URIs: {uri1}, {uri2}, {uri3}")

    lit_int = to_literal(123)
    lit_str_typed = to_literal("test", datatype=XSD.string)
    lit_bool = to_literal(True)
    kce_logger.info(f"Literals: {lit_int} ({lit_int.datatype}), {lit_str_typed}, {lit_bool} ({lit_bool.datatype})")

    xsd_uri = get_xsd_uriref("integer")
    assert xsd_uri == XSD.integer
    kce_logger.info(f"XSD URI for 'integer': {xsd_uri}")

    # Test generate_unique_id
    uid = generate_unique_id()
    kce_logger.info(f"Generated UID: {uid}")

    # Test get_from_dict_path
    nested_dict = {"a": {"b": {"c": 100}, "d": [1,2,3]}, "e": "top"}
    val1 = get_from_dict_path(nested_dict, ["a", "b", "c"])
    assert val1 == 100
    val2 = get_from_dict_path(nested_dict, ["a", "d", 1]) # Accessing list element
    assert val2 == 2
    val_none = get_from_dict_path(nested_dict, ["a", "x", "y"])
    assert val_none is None
    val_default = get_from_dict_path(nested_dict, ["a", "x"], default="not found")
    assert val_default == "not found"
    kce_logger.info(f"get_from_dict_path tests passed. val1={val1}, val2={val2}, val_none={val_none}, val_default={val_default}")

    kce_logger.info("Utils tests completed.")