"""Autenticación JWT con registro, login y dependencias FastAPI."""

from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from src.core.config import settings
from src.core.rag.index_manifest import _conexion, _con

SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _init_users_table():
    """Crea la tabla de usuarios y el admin por defecto si no existen."""
    with _con() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol           TEXT DEFAULT 'usuario',
                creado_en     TEXT NOT NULL
            )
        """)
        con.commit()

        admin = con.execute("SELECT 1 FROM users WHERE username = 'admin'").fetchone()
        if not admin:
            admin_password = settings.admin_password
            con.execute(
                "INSERT INTO users (username, email, password_hash, rol, creado_en) VALUES (?, ?, ?, ?, ?)",
                ("admin", "admin@docuasist.local", _hash_password(admin_password), "admin", datetime.utcnow().isoformat()),
            )
            con.commit()


_init_users_table()


def crear_usuario(username: str, email: str, password: str) -> dict:
    """Registra un nuevo usuario."""
    with _con() as con:
        if con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise ValueError(f"El usuario '{username}' ya existe.")
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise ValueError(f"El email '{email}' ya esta registrado.")

        ahora = datetime.utcnow().isoformat()
        con.execute(
            "INSERT INTO users (username, email, password_hash, rol, creado_en) VALUES (?, ?, ?, ?, ?)",
            (username, email, _hash_password(password), "usuario", ahora),
        )
        con.commit()

        user = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(user)


def autenticar_usuario(username: str, password: str) -> dict | None:
    """Verifica credenciales."""
    # TODO: añadir rate limiting antes de exponer este endpoint a producción.
    with _con() as con:
        user = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return dict(user)


def crear_token(user_id: int, username: str, rol: str) -> str:
    """Genera un token JWT."""
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "rol": rol,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verificar_token(token: str) -> dict:
    """Decodifica y valida un token JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado.",
        )


async def obtener_usuario_actual(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict | None:
    """Extrae el usuario del token Bearer, o None si no hay token."""
    if not credentials:
        return None
    return verificar_token(credentials.credentials)


async def requerir_usuario(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Exige autenticación. Lanza 401 si no hay token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida.",
        )
    return verificar_token(credentials.credentials)


async def requerir_admin(
    user: dict = Depends(requerir_usuario),
) -> dict:
    """Dependencia que exige rol admin."""
    if user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador.",
        )
    return user
