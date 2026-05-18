FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para pymupdf
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copiando pyproject.toml para instalar dependencias (cache de capas)
COPY pyproject.toml ./

# Instalando dependencias del proyecto
RUN pip install --no-cache-dir .

# Copiando el código fuente
COPY src/ ./src/
COPY scripts/ ./scripts/

# Creando directorios de datos y storage
RUN mkdir -p data/raw storage

# Puerto de la API
EXPOSE 8080

# Arrancando el servidor
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8080"]
