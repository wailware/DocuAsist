"""Persistencia relacional del sistema en SQLite.

ChromaDB se encarga del corpus vectorial; SQLite cubre todo lo demás:

- `documentos`: manifiesto de cada fichero indexado, con metadatos
  estructurados (fechas, tipo, salario, alertas de compliance…).
- `consultas`: auditoría de cada pregunta y su respuesta, incluyendo
  la traza completa del grafo. Permite reconstruir cualquier sesión.
- `sesiones_meta` / `sesiones_mensajes`: persistencia del historial
  conversacional para que el usuario pueda continuar una sesión.
- `users`: cuentas con hash de contraseña y rol (admin/usuario).

La estructura usa ALTER TABLE ADD COLUMN con try/except para soportar
migraciones suaves: arrancar el backend sobre una BD antigua añade las
columnas que falten sin romper los datos existentes.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from ..config import settings


def _conexion() -> sqlite3.Connection:
    ruta = Path(settings.sqlite_path)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row

    con.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            doc_id       TEXT PRIMARY KEY,
            nombre       TEXT NOT NULL,
            ruta         TEXT NOT NULL,
            indexado_en  TEXT NOT NULL,
            num_chunks   INTEGER NOT NULL,
            coleccion    TEXT NOT NULL DEFAULT 'documentos_privados'
        )
    """)

    # Columnas añadidas con posterioridad al esquema inicial. El try/except
    # permite ejecutar el backend sobre BDs antiguas sin migraciones
    # explícitas: SQLite lanza error si la columna ya existe, lo ignoramos.
    for col, tipo in [
        ("fecha_inicio", "TEXT"),
        ("fecha_fin", "TEXT"),
        ("tipo_contrato", "TEXT DEFAULT ''"),
        ("resumen", "TEXT DEFAULT ''"),
        ("alertas", "TEXT DEFAULT '[]'"),
        ("datos_extraidos", "TEXT DEFAULT '{}'"),
    ]:
        try:
            con.execute(f"ALTER TABLE documentos ADD COLUMN {col} {tipo}")
        except Exception:
            pass

    con.execute("""
        CREATE TABLE IF NOT EXISTS consultas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            session_id   TEXT NOT NULL,
            pregunta     TEXT NOT NULL,
            respuesta    TEXT NOT NULL,
            intent       TEXT DEFAULT '',
            modo         TEXT DEFAULT '',
            no_consta    INTEGER DEFAULT 0,
            num_fragmentos INTEGER DEFAULT 0,
            traza        TEXT DEFAULT '[]'
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS sesiones_meta (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            titulo        TEXT NOT NULL,
            creada_en     TEXT NOT NULL,
            actualizada_en TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS sesiones_mensajes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT NOT NULL,
            rol          TEXT NOT NULL,
            contenido    TEXT NOT NULL,
            timestamp    TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_sesiones_msg_session
        ON sesiones_mensajes(session_id)
    """)

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
    return con


@contextmanager
def _con():
    conexion = _conexion()
    try:
        yield conexion
    finally:
        conexion.close()



def registrar(doc_id, nombre, ruta, num_chunks, coleccion=None,
              fecha_inicio=None, fecha_fin=None, tipo_contrato=""):
    """Guarda o actualiza el registro de un documento indexado."""
    col = coleccion or settings.chroma_collection_private
    with _con() as con:
        con.execute(
            """INSERT OR REPLACE INTO documentos
               (doc_id, nombre, ruta, indexado_en, num_chunks, coleccion,
                fecha_inicio, fecha_fin, tipo_contrato)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, nombre, ruta, datetime.utcnow().isoformat(), num_chunks, col,
             fecha_inicio, fecha_fin, tipo_contrato),
        )
        con.commit()


def esta_indexado(doc_id):
    with _con() as con:
        fila = con.execute("SELECT 1 FROM documentos WHERE doc_id = ?", (doc_id,)).fetchone()
    return fila is not None


def eliminar(doc_id):
    with _con() as con:
        con.execute("DELETE FROM documentos WHERE doc_id = ?", (doc_id,))
        con.commit()


def listar():
    with _con() as con:
        filas = con.execute("SELECT * FROM documentos ORDER BY indexado_en DESC").fetchall()
    return [dict(f) for f in filas]


def obtener(doc_id):
    with _con() as con:
        fila = con.execute("SELECT * FROM documentos WHERE doc_id = ?", (doc_id,)).fetchone()
    return dict(fila) if fila else None


def actualizar_metadatos(doc_id, fecha_inicio=None, fecha_fin=None, tipo_contrato=None):
    """Actualiza metadatos de fecha y tipo de un documento ya indexado."""
    campos = []
    valores = []
    if fecha_inicio is not None:
        campos.append("fecha_inicio = ?")
        valores.append(fecha_inicio)
    if fecha_fin is not None:
        campos.append("fecha_fin = ?")
        valores.append(fecha_fin)
    if tipo_contrato is not None:
        campos.append("tipo_contrato = ?")
        valores.append(tipo_contrato)
    if campos:
        valores.append(doc_id)
        with _con() as con:
            con.execute(f"UPDATE documentos SET {', '.join(campos)} WHERE doc_id = ?", valores)
            con.commit()


def actualizar_resumen(doc_id, resumen):
    """Actualiza el resumen de un documento."""
    with _con() as con:
        con.execute("UPDATE documentos SET resumen = ? WHERE doc_id = ?", (resumen, doc_id))
        con.commit()


def actualizar_alertas(doc_id, alertas):
    """Guarda las alertas de cumplimiento como JSON."""
    with _con() as con:
        con.execute(
            "UPDATE documentos SET alertas = ? WHERE doc_id = ?",
            (json.dumps(alertas, ensure_ascii=False), doc_id),
        )
        con.commit()


def obtener_alertas_por_trabajador(nombre_trabajador: str) -> list[dict]:
    """Devuelve las alertas de compliance de un trabajador.

    Necesario para vincular las alertas (calculadas a partir del texto
    del contrato durante la indexación) con la persona que aparece en
    la consulta. No hay un FK directo nombre → doc_id porque el nombre
    canónico vive en los metadatos de ChromaDB y los ficheros en disco
    pueden tener cualquier convención.

    Estrategia: tokenizamos el nombre y buscamos qué fichero contiene
    al menos 2 tokens. Sólido frente a variaciones de orden y acentos.
    """
    partes = nombre_trabajador.replace(",", "").lower().split()
    if not partes:
        return []
    # Filtramos tokens cortos (artículos, partículas) que generarían
    # falsos positivos en la coincidencia con nombres de fichero.
    tokens_busqueda = set()
    for p in partes:
        if len(p) >= 3:
            tokens_busqueda.add(p)

    with _con() as con:
        filas = con.execute(
            "SELECT nombre, alertas FROM documentos "
            "WHERE alertas IS NOT NULL AND alertas != '[]' AND alertas != ''"
        ).fetchall()

    # Umbral de 2 tokens: 1 daría demasiados falsos positivos
    # (nombre/apellido común); 3 sería muy estricto y fallaría con
    # convenciones de fichero abreviadas.
    for f in filas:
        nombre_fichero = f["nombre"].lower()
        coincidencias = sum(1 for t in tokens_busqueda if t in nombre_fichero)
        if coincidencias >= 2:
            try:
                return json.loads(f["alertas"])
            except (json.JSONDecodeError, TypeError):
                continue

    return []


def actualizar_datos_extraidos(doc_id, datos):
    """Guarda los datos estructurados extraídos como JSON."""
    with _con() as con:
        con.execute(
            "UPDATE documentos SET datos_extraidos = ? WHERE doc_id = ?",
            (json.dumps(datos, ensure_ascii=False), doc_id),
        )
        con.commit()


def obtener_estadisticas_contratos():
    """Devuelve estadísticas agregadas de los datos extraídos de contratos."""
    with _con() as con:
        filas = con.execute(
            "SELECT nombre, tipo_contrato, fecha_inicio, fecha_fin, datos_extraidos "
            "FROM documentos WHERE coleccion != 'normativa_publica'"
        ).fetchall()

    contratos = []
    for f in filas:
        d = dict(f)
        try:
            d["datos"] = json.loads(d.get("datos_extraidos") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["datos"] = {}
        contratos.append(d)

    # Agregaciones
    salarios = [c["datos"]["salario_anual"] for c in contratos if c["datos"].get("salario_anual")]
    jornadas = [c["datos"]["jornada_semanal"] for c in contratos if c["datos"].get("jornada_semanal")]
    vacaciones = [c["datos"]["vacaciones_dias"] for c in contratos if c["datos"].get("vacaciones_dias")]

    tipos = {}
    empresas = {}
    puestos = {}
    salarios_por_tipo = {}  # tipo -> lista de salarios
    for c in contratos:
        t = c.get("tipo_contrato") or "desconocido"
        tipos[t] = tipos.get(t, 0) + 1
        emp = c["datos"].get("empresa")
        if emp:
            empresas[emp] = empresas.get(emp, 0) + 1
        puesto = c["datos"].get("puesto")
        if puesto:
            puestos[puesto] = puestos.get(puesto, 0) + 1
        sal = c["datos"].get("salario_anual")
        if sal:
            salarios_por_tipo.setdefault(t, []).append(sal)

    # Antigüedad media (años) calculada desde fecha_inicio hasta hoy.
    # Solo aplica a indefinidos y temporales aún activos.
    from datetime import date
    hoy = date.today()
    antiguedades_anios = []
    for c in contratos:
        fi = c.get("fecha_inicio")
        if not fi:
            continue
        try:
            y, m, d = map(int, fi[:10].split("-"))
            dias = (hoy - date(y, m, d)).days
            antiguedades_anios.append(dias / 365.25)
        except (ValueError, AttributeError):
            continue

    # Mediana de salarios — más robusta que la media frente a outliers.
    def _mediana(xs):
        if not xs:
            return None
        s = sorted(xs)
        n = len(s)
        if n % 2 == 1:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2

    return {
        "total_contratos": len(contratos),
        "salario": {
            "media": round(sum(salarios) / len(salarios), 2) if salarios else None,
            "mediana": _mediana(salarios),
            "minimo": min(salarios) if salarios else None,
            "maximo": max(salarios) if salarios else None,
            "total_datos": len(salarios),
        },
        "jornada": {
            "media": round(sum(jornadas) / len(jornadas), 1) if jornadas else None,
            "total_datos": len(jornadas),
        },
        "vacaciones": {
            "media": round(sum(vacaciones) / len(vacaciones), 1) if vacaciones else None,
            "total_datos": len(vacaciones),
        },
        "antiguedad_anios": {
            "media": round(sum(antiguedades_anios) / len(antiguedades_anios), 1) if antiguedades_anios else None,
            "total_datos": len(antiguedades_anios),
        },
        "salario_por_tipo": {
            t: round(sum(xs) / len(xs), 0) for t, xs in salarios_por_tipo.items() if xs
        },
        "tipos_contrato": tipos,
        "empresas": empresas,
        "puestos": puestos,
        "contratos": [
            {
                "nombre": c["nombre"],
                "tipo": c.get("tipo_contrato", ""),
                "trabajador": c["datos"].get("trabajador"),
                "empresa": c["datos"].get("empresa"),
                "puesto": c["datos"].get("puesto"),
                "salario_anual": c["datos"].get("salario_anual"),
                "jornada_semanal": c["datos"].get("jornada_semanal"),
                "vacaciones_dias": c["datos"].get("vacaciones_dias"),
                "fecha_inicio": c.get("fecha_inicio"),
                "fecha_fin": c.get("fecha_fin"),
            }
            for c in contratos
        ],
    }


_CAMPOS_FECHA_VALIDOS = {"fecha_inicio", "fecha_fin"}


def consultar_por_fechas(campo="fecha_fin", desde=None, hasta=None):
    """Consulta documentos filtrando por un rango de fechas.

    Args:
        campo: 'fecha_inicio' o 'fecha_fin'.
        desde/hasta: strings ISO 'YYYY-MM-DD' (inclusivos).
    """
    # Whitelist obligatoria: el campo viene del nodo de intent (que lo
    # extrae con un LLM) y se interpola directamente en el SQL. Sin
    # esta validación habría una vía clara de SQL injection.
    if campo not in _CAMPOS_FECHA_VALIDOS:
        campo = "fecha_fin"

    query = "SELECT * FROM documentos WHERE coleccion != 'normativa_publica'"
    params = []

    if desde:
        query += f" AND {campo} >= ?"
        params.append(desde)
    if hasta:
        query += f" AND {campo} <= ?"
        params.append(hasta)

    query += f" AND {campo} IS NOT NULL ORDER BY {campo} ASC"
    with _con() as con:
        filas = con.execute(query, params).fetchall()
    return [dict(f) for f in filas]



def registrar_consulta(
    user_id, session_id, pregunta, respuesta,
    intent="", modo="", no_consta=False, num_fragmentos=0, traza=None,
):
    """Registra una consulta en la tabla de auditoría. Devuelve el ID de la consulta."""
    with _con() as con:
        cursor = con.execute(
            """INSERT INTO consultas
               (timestamp, user_id, session_id, pregunta, respuesta,
                intent, modo, no_consta, num_fragmentos, traza)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(), user_id, session_id,
                pregunta, respuesta, intent, modo, int(no_consta),
                num_fragmentos, json.dumps(traza or [], ensure_ascii=False),
            ),
        )
        consulta_id = cursor.lastrowid
        con.commit()
    return consulta_id


def listar_consultas(limite=50, user_id=None):
    with _con() as con:
        if user_id:
            filas = con.execute(
                "SELECT * FROM consultas WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limite),
            ).fetchall()
        else:
            filas = con.execute(
                "SELECT * FROM consultas ORDER BY id DESC LIMIT ?", (limite,),
            ).fetchall()

    resultado = []
    for f in filas:
        d = dict(f)
        d["no_consta"] = bool(d["no_consta"])
        try:
            d["traza"] = json.loads(d["traza"])
        except (json.JSONDecodeError, TypeError):
            d["traza"] = []
        resultado.append(d)
    return resultado



def guardar_turno(session_id, user_id, pregunta, respuesta):
    """Persiste un turno (pregunta + respuesta) en el historial.

    Crea la sesión si es la primera interacción, generando un título
    desde los primeros 50 caracteres de la pregunta (heurística: la
    primera pregunta suele resumir bien la sesión y se puede renombrar
    luego desde la UI).
    """
    with _con() as con:
        ahora = datetime.utcnow().isoformat()

        # Guardando mensajes
        con.execute(
            "INSERT INTO sesiones_mensajes (session_id, rol, contenido, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, "user", pregunta, ahora),
        )
        con.execute(
            "INSERT INTO sesiones_mensajes (session_id, rol, contenido, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, "assistant", respuesta, ahora),
        )

        # Creando o actualizando metadatos de sesión
        existente = con.execute(
            "SELECT 1 FROM sesiones_meta WHERE session_id = ?", (session_id,)
        ).fetchone()

        if existente:
            con.execute(
                "UPDATE sesiones_meta SET actualizada_en = ? WHERE session_id = ?",
                (ahora, session_id),
            )
        else:
            # Título = primera pregunta truncada a 50 caracteres
            titulo = pregunta[:50].strip()
            if len(pregunta) > 50:
                titulo += "..."
            con.execute(
                """INSERT INTO sesiones_meta
                   (session_id, user_id, titulo, creada_en, actualizada_en)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, user_id, titulo, ahora, ahora),
            )

        con.commit()


def listar_sesiones(user_id=None, limite=30):
    """Devuelve las sesiones ordenadas por última actividad."""
    with _con() as con:
        if user_id:
            filas = con.execute(
                """SELECT * FROM sesiones_meta WHERE user_id = ?
                   ORDER BY actualizada_en DESC LIMIT ?""",
                (user_id, limite),
            ).fetchall()
        else:
            filas = con.execute(
                "SELECT * FROM sesiones_meta ORDER BY actualizada_en DESC LIMIT ?",
                (limite,),
            ).fetchall()
    return [dict(f) for f in filas]


def obtener_owner_sesion(session_id: str) -> str | None:
    """Devuelve el user_id propietario de una sesión, o None si no existe."""
    with _con() as con:
        fila = con.execute(
            "SELECT user_id FROM sesiones_meta WHERE session_id = ?", (session_id,)
        ).fetchone()
    return fila["user_id"] if fila else None


def cargar_historial(session_id, max_turnos=None):
    """Recupera el historial conversacional de una sesión.

    La subquery interna recupera los últimos N mensajes en orden
    descendente y la externa los devuelve en orden cronológico
    ascendente; esto es necesario porque el LLM espera el historial en
    el orden natural pero queremos limitar al tramo más reciente.
    """
    limite_mensajes = (max_turnos or settings.memory_turns) * 2
    with _con() as con:
        filas = con.execute(
            """SELECT rol, contenido FROM (
                SELECT id, rol, contenido FROM sesiones_mensajes
                WHERE session_id = ? ORDER BY id DESC LIMIT ?
            ) sub ORDER BY id ASC""",
            (session_id, limite_mensajes),
        ).fetchall()
    return [{"role": f["rol"], "content": f["contenido"]} for f in filas]


def renombrar_sesion(session_id, titulo):
    """Actualiza el título de una sesión."""
    with _con() as con:
        con.execute(
            "UPDATE sesiones_meta SET titulo = ? WHERE session_id = ?",
            (titulo, session_id),
        )
        con.commit()


def limpiar_sesion(session_id):
    """Elimina una sesión completa: mensajes y metadatos."""
    with _con() as con:
        con.execute("DELETE FROM sesiones_mensajes WHERE session_id = ?", (session_id,))
        con.execute("DELETE FROM sesiones_meta WHERE session_id = ?", (session_id,))
        con.commit()



def crear_usuario(username, email, password_hash, rol="usuario"):
    """Crea un usuario y devuelve su ID."""
    with _con() as con:
        cursor = con.execute(
            """INSERT INTO users (username, email, password_hash, rol, creado_en)
               VALUES (?, ?, ?, ?, ?)""",
            (username, email, password_hash, rol, datetime.utcnow().isoformat()),
        )
        user_id = cursor.lastrowid
        con.commit()
    return user_id


def obtener_usuario_por_username(username):
    """Devuelve dict del usuario o None."""
    with _con() as con:
        fila = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(fila) if fila else None


def obtener_usuario_por_id(user_id):
    """Devuelve dict del usuario o None."""
    with _con() as con:
        fila = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(fila) if fila else None


def obtener_usuario_por_email(email):
    """Devuelve dict del usuario o None."""
    with _con() as con:
        fila = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return dict(fila) if fila else None


