# DocuAsist

Asistente documental corporativo basado en RAG (*Retrieval-Augmented Generation*) y modelos de lenguaje locales aplicado al ámbito de los contratos laborales españoles. Permite consultar documentación contractual en lenguaje natural y obtener respuestas con citas verificables, incluyendo un modo de consulta legal que cruza cláusulas con el Estatuto de los Trabajadores.

Trabajo de Fin de Grado — Universidad Europea de Valencia (Grado en Ciencia de Datos, curso 2025-2026). Autor: Wail Achalhi.

## Componentes principales

- **Backend (`agent/`)**: pipeline RAG construido con LangGraph (6 nodos: intent, retrieval, analysis, response, temporal, estadistica), API REST con FastAPI, recuperación híbrida (semántica + BM25 + RRF + HyDE), detección de incumplimientos normativos por regex sobre el Estatuto de los Trabajadores.
- **Frontend (`frontend/`)**: SPA en React 18 con dos páginas (chat y gestión documental), autenticación JWT y *streaming* de respuestas vía Server-Sent Events.
- **Datos**: 205 contratos ficticios generados de forma reproducible y el texto íntegro del Estatuto de los Trabajadores como normativa pública.

## Requisitos

- Python 3.11 o superior
- Node.js 20 o superior
- Docker y Docker Compose
- Una instancia de Ollama accesible por red, con los modelos `qwen3:14b-nothink` y `qwen3-embedding:8b` descargados

## Puesta en marcha rápida

### 1. Clonar el repositorio y preparar el entorno

```bash
git clone <url-del-repositorio> docuasist
cd docuasist
cp .env.example .env
# Edita .env con tus valores (especialmente OLLAMA_BASE_URL, JWT_SECRET y ADMIN_PASSWORD)
```

### 2. Descargar los modelos en Ollama

```bash
ollama pull qwen3:14b-nothink
ollama pull qwen3-embedding:8b
```

### 3. Arrancar los servicios con Docker Compose

```bash
docker compose up -d
```

Esto levanta tres contenedores conectados a una red interna:

| Servicio | Puerto | Función |
|----------|--------|---------|
| chroma | 8000 | Base de datos vectorial |
| backend | 8080 | API FastAPI |
| frontend | 3000 | Aplicación React (Nginx) |

### 4. Indexar el corpus inicial

Los 205 contratos ficticios y el Estatuto ya están incluidos en `agent/data/`. Para indexarlos:

```bash
docker compose exec backend python scripts/index_documents.py
docker compose exec backend python scripts/index_documents.py --legal
```

### 5. Acceder a la aplicación

- Aplicación: <http://localhost:3000>
- API REST y documentación interactiva: <http://localhost:8080/docs>
- Endpoint de salud: <http://localhost:8080/health>

El usuario administrador inicial se crea automáticamente al arrancar el backend, con la contraseña indicada en `ADMIN_PASSWORD` del fichero `.env`. El nombre de usuario por defecto es `admin`.

## Desarrollo fuera de Docker

### Backend

```bash
cd agent
uv sync
uv run uvicorn src.api:app --reload --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # servidor de desarrollo en http://localhost:5173 con proxy /api → backend
```

## Pruebas automatizadas

El sistema incluye dos baterías de pruebas que lanzan consultas reales contra la API:

```bash
ADMIN_PASSWORD='tu_password' docker compose exec backend python scripts/test_e2e.py
ADMIN_PASSWORD='tu_password' docker compose exec backend python scripts/test_memory.py
```

- **`test_e2e.py`**: 15 consultas que cubren todos los caminos del grafo (buscar, comparar, modo legal, estadísticas, temporal, conversacional).
- **`test_memory.py`**: 19 pruebas sobre la persistencia y aislamiento del historial conversacional.

## Estructura del proyecto

```
.
├── agent/                              # Backend Python (FastAPI + LangGraph)
│   ├── data/
│   │   ├── raw/                        # 205 contratos ficticios en PDF
│   │   └── legal/                      # Estatuto de los Trabajadores
│   ├── scripts/
│   │   ├── index_documents.py          # Indexación masiva del corpus
│   │   ├── generar_contratos.py        # Generador de 200 contratos sintéticos
│   │   ├── generar_ilegales.py         # Generador de contratos con infracciones
│   │   ├── diagnostico.py              # Comprobación de salud del sistema
│   │   ├── test_e2e.py                 # Batería de tests end-to-end
│   │   └── test_memory.py              # Batería de tests de memoria conversacional
│   ├── src/
│   │   ├── api.py                      # Endpoints FastAPI
│   │   ├── main.py                     # CLI interactiva
│   │   └── core/
│   │       ├── auth.py                 # Autenticación JWT
│   │       ├── config.py               # Configuración Pydantic
│   │       ├── graph.py                # Construcción del grafo LangGraph
│   │       ├── llm.py                  # Cliente Ollama
│   │       ├── pdf_report.py           # Informes PDF de auditoría
│   │       ├── nodes/                  # Nodos del grafo
│   │       │   ├── intent.py           # Clasificación de intención
│   │       │   ├── retrieval.py        # Recuperación híbrida
│   │       │   ├── analysis.py         # Análisis estructurado / cruce legal
│   │       │   ├── response.py         # Generación de respuesta
│   │       │   ├── temporal.py         # Consultas con rangos de fechas
│   │       │   └── estadistica.py      # Consultas agregadas sobre el corpus
│   │       ├── rag/                    # Pipeline RAG
│   │       │   ├── loader.py           # Carga de PDF, DOCX, HTML
│   │       │   ├── chunker.py          # Chunking semántico padre-hijo
│   │       │   ├── embedder.py         # Generación de embeddings
│   │       │   ├── store.py            # Interfaz con ChromaDB
│   │       │   ├── retriever.py        # Búsqueda híbrida (semántica + BM25 + RRF + HyDE)
│   │       │   ├── index_manifest.py   # Gestión de sesiones, audit, usuarios en SQLite
│   │       │   ├── metadata_extractor.py  # Extracción de campos estructurados
│   │       │   └── compliance_checker.py  # Detección de incumplimientos normativos
│   │       └── prompts/                # Plantillas de prompts en español
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/                           # SPA React 18 + Vite
│   └── src/
│       ├── App.jsx
│       ├── api/                        # Cliente HTTP y streaming SSE
│       ├── components/                 # Componentes reutilizables
│       ├── contexts/                   # Auth context
│       ├── hooks/                      # Lógica de chat y sesiones
│       └── pages/                      # Login, Chat, Documentos
├── docker-compose.yml
├── .env.example
└── README.md
```

