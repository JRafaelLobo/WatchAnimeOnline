import os
import pyodbc


def get_connection():
    server = os.getenv("SQL_SERVER", "sqlserver")
    port = os.getenv("SQL_PORT", "1433")
    database = os.getenv("SQL_DATABASE", "AnimeDB")
    username = os.getenv("SQL_USER", "sa")
    password = os.getenv("SQL_PASSWORD")

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )

    return pyodbc.connect(connection_string)