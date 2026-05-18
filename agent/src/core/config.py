"""Configuración global de la aplicación.

Lee variables de entorno (con valores por defecto cuando aplique) a través
de Pydantic Settings. Las variables sin default tienen que estar definidas
en el fichero .env antes de arrancar.
"""

from pathlib import Path
from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # --- Ollama ---
    ollama_base_url: str
    llm_model: str                       # Modelo principal para Response y Analysis
    embed_model: str                     # Modelo de embeddings (vectores 4096-d)
    context_model: str                   # Modelo usado para generar el documento hipotético en HyDE

    # --- ChromaDB ---
    chroma_host: str
    chroma_port: int
    # Colecciones de hijos (chunks pequeños con embeddings para búsqueda semántica)
    chroma_collection_private: str       # Contratos privados de la organización
    chroma_collection_public: str        # Normativa pública (Estatuto de los Trabajadores)
    # Colecciones de padres (páginas completas, sin embeddings). Se mantienen
    # separadas porque ChromaDB exige dimensionalidad homogénea por colección.
    chroma_collection_padres_private: str = "padres_privados"
    chroma_collection_padres_public: str = "padres_publicos"

    # --- SQLite ---
    sqlite_path: str

    # --- Chunking semántico padre-hijo ---
    semantic_threshold: float = 0.3      # Umbral de similitud para agrupar oraciones en un mismo hijo
    max_chunk_chars: int = 512           # Tamaño máximo de un chunk hijo en caracteres

    # --- Retrieval ---
    retrieval_k: int = 12                # Número de fragmentos devueltos tras la fusión RRF
    rrf_k: int = 60                      # Constante de suavizado de RRF (paper original Cormack et al. 2009)
    use_hyde: bool = True                # Genera documento hipotético antes de embedder la consulta
    k_normativa: int = 5                 # Fragmentos a recuperar de la colección pública en modo legal
    min_score_bm25: float = 0.05
    min_chars_resultado: int = 50        # Descarta fragmentos demasiado cortos (artefactos de chunking)

    # --- LLM ---
    llm_temperature: float = 0.0         # Determinismo en respuestas
    context_temperature: float = 0.3     # Algo de creatividad para el documento hipotético de HyDE

    # --- Compliance (Estatuto de los Trabajadores) ---
    smi_anual: int = 15_876              # SMI 2025 bruto anual (14 pagas). Actualizar cada año.
    pagas_anuales: int = 14

    # --- CORS: orígenes desde los que el frontend puede consumir la API ---
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # --- Memoria conversacional ---
    memory_turns: int = 6                # Ventana deslizante: número de turnos previos incluidos en el prompt

    # --- BM25 ---
    bm25_corpus_path: str = "./storage/bm25_corpus.json"

    # --- Auth ---
    jwt_secret: str                      # Clave de firma de los JWT. OBLIGATORIO en .env
    admin_password: str                  # Contraseña inicial del usuario admin. OBLIGATORIO en .env

    model_config = {"env_file": str(_ROOT / ".env")}


settings = Settings()