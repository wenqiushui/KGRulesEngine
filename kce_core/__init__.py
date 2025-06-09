# kce_core/__init__.py

import logging

# --- Package Information ---
__version__ = "0.1.0" # KCE MVP version
__author__ = "Your Name/Team Name" # Replace with actual author
__email__ = "your.email@example.com" # Replace with actual email

# --- Setup a package-level logger (optional, can also rely on kce_logger from utils) ---
# This logger can be used by modules within this package if they don't define their own.
# It's often good practice for libraries not to configure the root logger directly,
# but to provide their own named loggers.
# We already have kce_logger in utils, which is fine. This is an alternative or supplement.

# Get a logger specific to this package
package_logger = logging.getLogger(__name__) # __name__ will be 'kce_core'
if not package_logger.handlers: # Avoid adding handlers multiple times if re-imported
    package_logger.addHandler(logging.NullHandler()) # Libraries should not add handlers by default
                                                    # Application using the library configures logging.
    # However, for internal KCE development and CLI, we might want some default.
    # For now, let's assume the application (e.g., CLI) will set up logging,
    # or individual modules use kce_logger from utils.py which has a basic setup.

# --- Expose Key Classes and Functions for easier import ---
# This makes it possible to do `from kce_core import StoreManager`
# instead of `from kce_core.rdf_store.store_manager import StoreManager`.

from .common.utils import (
    kce_logger, # Re-exporting the logger from utils for convenience
    DefinitionError,
    RDFStoreError,
    ExecutionError,
    ConfigurationError,
    load_yaml_file,
    load_json_file,
    load_json_string,
    to_uriref,
    to_literal,
    get_xsd_uriref,
    generate_unique_id,
    resolve_path,
    # Namespaces are also useful to expose if users will construct RDF outside KCE
    KCE, PROV, RDF, RDFS, OWL, XSD, DCTERMS, EX
)

from .rdf_store.store_manager import StoreManager
from .rdf_store import sparql_queries # Expose the module itself for access to query strings

from .definitions.loader import DefinitionLoader

from .provenance.logger import ProvenanceLogger

from .execution.node_executor import NodeExecutor
from .execution.rule_evaluator import RuleEvaluator
from .execution.workflow_executor import WorkflowExecutor


# --- Optional: A simple function to get KCE version ---
def get_kce_version() -> str:
    """Returns the current version of the KCE package."""
    return __version__

# --- Optional: Initialization message when the package is imported ---
# Use with caution, can be verbose if kce_core is imported many times by different modules.
# kce_logger.info(f"Knowledge-CAD-Engine (KCE) core library v{__version__} initialized.")
# Or use the package_logger:
# package_logger.info(f"Knowledge-CAD-Engine (KCE) core library v{__version__} initialized.")


# --- Define what `from kce_core import *` imports (though `import *` is generally discouraged) ---
# This is a good practice to explicitly state the public API of the package.
__all__ = [
    # Loggers
    "kce_logger",
    # Exceptions
    "DefinitionError", "RDFStoreError", "ExecutionError", "ConfigurationError",
    # Utility functions
    "load_yaml_file", "load_json_file", "load_json_string",
    "to_uriref", "to_literal", "get_xsd_uriref", "generate_unique_id", "resolve_path",
    # Namespaces
    "KCE", "PROV", "RDF", "RDFS", "OWL", "XSD", "DCTERMS", "EX",
    # Core Classes
    "StoreManager",
    "DefinitionLoader",
    "ProvenanceLogger",
    "NodeExecutor",
    "RuleEvaluator",
    "WorkflowExecutor",
    # Modules
    "sparql_queries",
    # Package info
    "get_kce_version",
    "__version__",
]

# A simple print statement to confirm the package is loaded (for development)
# print(f"KCE Core Package (v{__version__}) loaded successfully.")