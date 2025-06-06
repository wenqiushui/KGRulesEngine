# kce_core/common/exceptions.py

class KCEError(Exception):
    """Base class for KCE specific errors."""
    pass

class DefinitionError(KCEError):
    """Error related to parsing or validity of KCE definitions."""
    pass

class RDFStoreError(KCEError):
    """Error related to RDF store operations."""
    pass

class ExecutionError(KCEError):
    """Error related to the execution of nodes or plans."""
    pass

class ConfigurationError(KCEError):
    """Error related to system configuration."""
    pass
