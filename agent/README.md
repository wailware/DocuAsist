# DocuAsist — Backend

Pipeline RAG sobre contratos laborales, expuesto como API REST con FastAPI y orquestado con LangGraph.

## Arquitectura

El núcleo del sistema es un grafo de seis nodos con estado tipado compartido:

```
Intent → [routing] → Retrieval → [routing] → Analysis → Response
                ↘ Temporal                  ↘ Response
                ↘ Estadistica
                ↘ END (si conversacional)
```

- **Intent** (`src/core/nodes/intent.py`): clasifica el tipo de consulta (buscar, resumir, comparar, legal, temporal, estadística, conversacional) y extrae entidades.
- **Retrieval** (`src/core/nodes/retrieval.py`): búsqueda híbrida sobre ChromaDB. Combina embeddings semánticos (`qwen3-embedding:8b`), BM25 léxico, fusión RRF y HyDE para consultas coloquiales. Estrategia multi-persona en consultas comparativas.
- **Analysis** (`src/core/nodes/analysis.py`): extracción estructurada de campos contractuales o cruce con el Estatuto en modo legal.
- **Response** (`src/core/nodes/response.py`): generación de la respuesta final con citas inline al documento de origen.
- **Temporal** y **Estadistica**: consultas que se resuelven sobre SQLite sin pasar por el LLM.

## Pipeline RAG

`src/core/rag/` implementa todas las etapas de la canalización:

| Módulo | Función |
|---|---|
| `loader.py` | Extracción de texto desde PDF (PyMuPDF), DOCX (python-docx) y HTML (BeautifulSoup). |
| `chunker.py` | Chunking semántico padre-hijo con umbral de similitud coseno θ = 0,3 y máximo de 512 caracteres por hijo. |
| `embedder.py` | Generación de embeddings de 4096 dimensiones vía Ollama. |
| `store.py` | Interfaz con ChromaDB (cuatro colecciones: hijos y padres para contratos y normativa). |
| `retriever.py` | Búsqueda híbrida con HyDE + semántica + BM25 + fusión RRF (k = 60). |
| `metadata_extractor.py` | Regex sobre la primera página: nombre del trabajador, DNI, tipo de contrato. |
| `compliance_checker.py` | Detección por regex de incumplimientos del Estatuto (jornada, salario, vacaciones, periodo de prueba). |
| `index_manifest.py` | Gestión de SQLite: documentos, sesiones, audit, usuarios. |

## Persistencia

| Almacén | Contenido |
|---|---|
| **ChromaDB** | Embeddings de chunks hijo y metadatos (nombre, DNI, tipo de contrato, página). |
| **SQLite** (`storage/tfg.db`) | Documentos indexados, sesiones, mensajes, auditoría y usuarios. |
| **BM25 corpus** (`storage/bm25_corpus.json`) | Serialización del corpus léxico para búsqueda BM25 en memoria. |

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/auth/login` | Login con usuario y contraseña; devuelve JWT (24 h). |
| POST | `/chat` | Consulta síncrona al pipeline. |
| POST | `/chat/stream` | Consulta con *streaming* SSE. |
| GET | `/documents` | Lista documentos indexados con metadatos y alertas. |
| POST | `/documents` | Sube e indexa un documento nuevo. |
| POST | `/documents/scan-compliance` | Escaneo masivo de cumplimiento normativo. |
| GET | `/sessions/{id}/export` | Exporta una conversación a Markdown. |
| GET | `/health` | Estado de la API, ChromaDB y Ollama. |

Documentación interactiva en `http://localhost:8080/docs` (Swagger UI generada automáticamente por FastAPI).

## Configuración

Las variables relevantes se leen desde `.env` mediante Pydantic Settings (`src/core/config.py`):

| Variable | Función |
|---|---|
| `OLLAMA_BASE_URL` | URL del servidor Ollama (puede ser local o remoto). |
| `LLM_MODEL` | Modelo principal (por defecto `qwen3:14b-nothink`). |
| `EMBED_MODEL` | Modelo de embeddings (`qwen3-embedding:8b`). |
| `CONTEXT_MODEL` | Modelo para generar el documento hipotético de HyDE. |
| `CHROMA_HOST`, `CHROMA_PORT` | Conexión a ChromaDB. |
| `JWT_SECRET` | Clave de firma de los tokens. **Obligatorio**. |
| `ADMIN_PASSWORD` | Contraseña inicial del usuario administrador. **Obligatorio**. |

## Ejecución local

```bash
uv sync
cp ../.env.example .env
# Editar .env con valores reales
uv run uvicorn src.api:app --reload --port 8080
```

Para ejecutar los tests:

```bash
ADMIN_PASSWORD='tu_password' uv run python scripts/test_e2e.py
ADMIN_PASSWORD='tu_password' uv run python scripts/test_memory.py
```

## Generación del corpus

Para regenerar los 205 contratos ficticios desde cero:

```bash
uv run python scripts/generar_contratos.py     # 200 contratos legales
uv run python scripts/generar_ilegales.py      # 5 contratos con infracciones
```

Los datos personales son completamente ficticios (semilla fija para reproducibilidad).
