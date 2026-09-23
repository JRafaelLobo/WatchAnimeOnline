FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app


# ============================================================
# SYSTEM DEPENDENCIES
# ============================================================

RUN apt-get update && \
    apt-get install -y \
        curl \
        gnupg \
        ca-certificates \
        unixodbc \
        unixodbc-dev \
        default-jdk-headless && \
    rm -rf /var/lib/apt/lists/*


# ============================================================
# MICROSOFT ODBC
# ============================================================

RUN curl -sSL \
    https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor \
    > /usr/share/keyrings/microsoft-prod.gpg

RUN echo \
    "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
    > /etc/apt/sources.list.d/mssql-release.list

RUN apt-get update && \
    ACCEPT_EULA=Y apt-get install -y \
        msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*


# ============================================================
# PYTHON
# ============================================================

COPY requirement.txt requirements.txt

RUN pip install \
    --no-cache-dir \
    -r requirements.txt

RUN pip install --no-cache-dir numpy==2.2.6


# ============================================================
# SQL SERVER JDBC FOR SPARK
# ============================================================

RUN mkdir -p /app/jars

RUN curl -L \
    -o /app/jars/mssql-jdbc.jar \
    https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/12.10.0.jre11/mssql-jdbc-12.10.0.jre11.jar


# ============================================================
# APPLICATION
# ============================================================

COPY . .


# ============================================================
# FLASK
# ============================================================

EXPOSE 5000

CMD ["python", "app.py"]