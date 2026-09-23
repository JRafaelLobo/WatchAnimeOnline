"""Allow isolated tests without an ODBC driver; unexpected SQL always fails."""

import sys
from types import ModuleType


try:
    import pyodbc  # noqa: F401
except ImportError:
    pyodbc = ModuleType("pyodbc")

    def unexpected_connection(*args, **kwargs):
        raise AssertionError("Tests must mock SQL connections")

    pyodbc.connect = unexpected_connection
    sys.modules["pyodbc"] = pyodbc
