import os
import pyodbc


def initialize_database():
    """Ensure the configured SQL Server database exists.

    Tables are created by the Compose database-init service from the
    versioned BaseDeDatos/01-tables.sql script.
    """
    server = os.getenv("SQL_SERVER", "sqlserver")
    port = os.getenv("SQL_PORT", "1433")
    username = os.getenv("SQL_USER", "sa")
    password = os.getenv("SQL_PASSWORD")

    master_connection = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server},{port};"
        "DATABASE=master;"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;",
        autocommit=True
    )

    try:
        cursor = master_connection.cursor()
        cursor.execute(
            "IF DB_ID(N'AnimeDB') IS NULL CREATE DATABASE [AnimeDB]"
        )
        cursor.close()
    finally:
        master_connection.close()

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