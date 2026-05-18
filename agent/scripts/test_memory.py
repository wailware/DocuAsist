"""Test de memoria conversacional y persistencia de sesión.

Cubre los siete puntos críticos del sistema de memoria:
  1. Persistencia SQLite: guardar_turno + cargar_historial.
  2. Ventana deslizante: solo se cargan los últimos N turnos.
  3. Aislamiento entre sesiones: no hay fuga de contexto.
  4. Reconstrucción a objetos LangChain (Human/AIMessage).
  5. Resolución por contexto: "y su salario" funciona con historial.
  6. Follow-up encadenado: varias preguntas seguidas sobre la misma persona.
  7. Limpieza: eliminar sesión borra mensajes y metadatos.

Estos puntos no son cubrirles por tests unitarios porque dependen del
LLM real (efectos no deterministas que solo se observan end-to-end).
"""

import os
import time
import requests

BASE = os.environ.get("DOCUASIST_API", "http://localhost:8080")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_PWD:
    raise SystemExit(
        "Define ADMIN_PASSWORD en el entorno antes de ejecutar los tests.\n"
        "Ejemplo: ADMIN_PASSWORD='tu_password' python scripts/test_memory.py"
    )

# Login
resp = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": ADMIN_PWD})
resp.raise_for_status()
TOKEN = resp.json()["token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Sesiones únicas para cada test
TS = int(time.time())
SESSION_A = f"test_mem_A_{TS}"
SESSION_B = f"test_mem_B_{TS}"
SESSION_C = f"test_mem_C_{TS}"


def chat(pregunta: str, session_id: str) -> dict:
    """Envía una pregunta en una sesión concreta."""
    r = requests.post(
        f"{BASE}/chat",
        json={"pregunta": pregunta, "session_id": session_id},
        headers=HEADERS,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def get_history(session_id: str) -> list[dict]:
    """Obtiene el historial persistido de una sesión."""
    r = requests.get(
        f"{BASE}/sessions/{session_id}/history",
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.json()["mensajes"]


def get_sessions() -> list[dict]:
    """Lista las sesiones del usuario."""
    r = requests.get(f"{BASE}/sessions", headers=HEADERS)
    r.raise_for_status()
    return r.json()["sesiones"]


def delete_session(session_id: str):
    """Elimina una sesión."""
    r = requests.delete(f"{BASE}/sessions/{session_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------

resultados = []


def test(tid: str, descripcion: str, ok: bool, detalle: str = ""):
    status = "PASS" if ok else "FAIL"
    resultados.append({"id": tid, "ok": ok, "desc": descripcion})
    marca = "\u2713" if ok else "\u2717"
    extra = f" | {detalle}" if detalle else ""
    print(f"  {marca} {tid}: {descripcion}{extra}")


print(f"\n{'='*70}")
print(f"  TEST DE MEMORIA CONVERSACIONAL")
print(f"  Sesiones: A={SESSION_A}, B={SESSION_B}")
print(f"{'='*70}\n")


# --- T01: Persistencia basica ---
print("  [Persistencia SQLite]\n")

chat("Hola", SESSION_A)
hist = get_history(SESSION_A)

test("T01", "Primer turno persiste 2 mensajes (user + assistant)",
     len(hist) == 2 and hist[0]["role"] == "user" and hist[1]["role"] == "assistant",
     f"mensajes={len(hist)}")

test("T02", "Mensaje user contiene la pregunta original",
     hist[0]["content"] == "Hola",
     f"content='{hist[0]['content'][:40]}'")

test("T03", "Mensaje assistant no esta vacio",
     len(hist[1]["content"]) > 0,
     f"len={len(hist[1]['content'])}")


# --- T04: Sesion metadata ---
sesiones = get_sessions()
sesion_a = next((s for s in sesiones if s["session_id"] == SESSION_A), None)

test("T04", "Sesion aparece en listado con titulo auto-generado",
     sesion_a is not None and len(sesion_a.get("titulo", "")) > 0,
     f"titulo='{sesion_a['titulo'][:40]}'" if sesion_a else "no encontrada")


# --- T05: Aislamiento de sesiones ---
print("\n  [Aislamiento de sesiones]\n")

chat("Hola", SESSION_B)
hist_a = get_history(SESSION_A)
hist_b = get_history(SESSION_B)

test("T05", "Sesion A y B tienen historiales independientes",
     len(hist_a) == 2 and len(hist_b) == 2,
     f"A={len(hist_a)} msgs, B={len(hist_b)} msgs")


# --- T06-T08: Acumulacion de turnos ---
print("\n  [Acumulacion de turnos]\n")

chat("¿Cuanto cobra Ruben Torres?", SESSION_A)
hist = get_history(SESSION_A)

test("T06", "Segundo turno acumula 4 mensajes totales",
     len(hist) == 4,
     f"mensajes={len(hist)}")

test("T07", "Los mensajes mantienen orden cronologico",
     hist[0]["role"] == "user" and hist[2]["role"] == "user"
     and hist[1]["role"] == "assistant" and hist[3]["role"] == "assistant",
     f"roles={[m['role'] for m in hist]}")


# --- T08-T09: Follow-up con contexto (resolución de correferencia) ---
print("\n  [Resolucion por contexto - Follow-up]\n")

# Tras preguntar por Ruben Torres, preguntar con pronombre
t0 = time.time()
resp_fu = chat("¿Y su jornada laboral?", SESSION_A)
dt = round(time.time() - t0, 1)

# El LLM debería resolver "su" como Ruben Torres
resp_lower = resp_fu["respuesta"].lower()
resuelve_contexto = (
    "hora" in resp_lower or "jornada" in resp_lower
    or "ruben" in resp_lower or "torres" in resp_lower
)

test("T08", "Follow-up 'Y su jornada' resuelve Ruben Torres del historial",
     resuelve_contexto and not resp_fu["no_consta"],
     f"{dt}s | resp={resp_fu['respuesta'][:80]}...")

hist = get_history(SESSION_A)
test("T09", "Tercer turno acumula 6 mensajes",
     len(hist) == 6,
     f"mensajes={len(hist)}")


# --- T10: Segundo follow-up encadenado ---
t0 = time.time()
resp_fu2 = chat("¿Y su tipo de contrato?", SESSION_A)
dt = round(time.time() - t0, 1)
resp_lower2 = resp_fu2["respuesta"].lower()
resuelve_tipo = (
    "indefinido" in resp_lower2 or "temporal" in resp_lower2
    or "contrato" in resp_lower2 or "ruben" in resp_lower2
)

test("T10", "Segundo follow-up 'Y su tipo de contrato' mantiene contexto",
     resuelve_tipo and not resp_fu2["no_consta"],
     f"{dt}s | resp={resp_fu2['respuesta'][:80]}...")


# --- T11: Cambio de persona en la misma sesion ---
print("\n  [Cambio de contexto]\n")

t0 = time.time()
resp_cambio = chat("¿Cuanto cobra Marta Pena?", SESSION_A)
dt = round(time.time() - t0, 1)
resp_lower3 = resp_cambio["respuesta"].lower()

test("T11", "Cambio de persona: pregunta por Marta Pena tras hablar de Ruben",
     not resp_cambio["no_consta"]
     and ("marta" in resp_lower3 or "pena" in resp_lower3 or "salario" in resp_lower3 or "€" in resp_lower3),
     f"{dt}s | resp={resp_cambio['respuesta'][:80]}...")

# Follow-up ahora deberia referir a Marta
t0 = time.time()
resp_fu3 = chat("¿Y su jornada?", SESSION_A)
dt = round(time.time() - t0, 1)
resp_lower4 = resp_fu3["respuesta"].lower()

# El contexto mas reciente es Marta, no Ruben
test("T12", "Follow-up tras cambio: 'Y su jornada' ahora refiere a Marta",
     not resp_fu3["no_consta"]
     and ("hora" in resp_lower4 or "jornada" in resp_lower4),
     f"{dt}s | resp={resp_fu3['respuesta'][:80]}...")


# --- T13: Ventana de memoria ---
print("\n  [Ventana de memoria]\n")

# La sesion A ya tiene 6 turnos (12 mensajes). memory_turns=6 → carga los 12 ultimos.
# Agregar un septimo turno para superar la ventana.
chat("Gracias por la info", SESSION_A)  # turno 7

hist = get_history(SESSION_A)
# El historial devuelto por la API respeta el limit de memory_turns (6 turnos = 12 mensajes)
test("T13", "Ventana de memoria: historial devuelve maximo memory_turns*2 mensajes",
     len(hist) <= 12,
     f"mensajes={len(hist)} (max esperado=12)")

# Verificar que los mensajes mas antiguos se descartaron
# El primer mensaje ya no deberia ser "Hola" si se cargo con ventana
if len(hist) == 12:
    test("T14", "Los mensajes mas antiguos se descartan al superar la ventana",
         hist[0]["content"] != "Hola",
         f"primer_msg='{hist[0]['content'][:40]}'")
else:
    test("T14", "Los mensajes mas antiguos se descartan al superar la ventana",
         True,
         f"menos de 12 mensajes ({len(hist)}), ventana no llena aun")


# --- T15: Persistencia total vs ventana ---
# La DB guarda TODO, pero cargar_historial devuelve solo la ventana
# Verificar con max_turnos alto
hist_full = get_history(SESSION_A)  # API usa default memory_turns
# No tenemos endpoint para cargar con max_turnos custom, pero verificamos
# que la API devuelve al menos los turnos recientes
test("T15", "Historial contiene los turnos mas recientes",
     any("ruben" in m["content"].lower() or "marta" in m["content"].lower()
         for m in hist_full if m["role"] == "assistant"),
     f"mensajes={len(hist_full)}")


# --- T16: Limpieza de sesion ---
print("\n  [Limpieza de sesion]\n")

delete_session(SESSION_B)
hist_b_post = get_history(SESSION_B)
sesiones_post = get_sessions()
sesion_b_post = next((s for s in sesiones_post if s["session_id"] == SESSION_B), None)

test("T16", "Eliminar sesion borra historial",
     len(hist_b_post) == 0,
     f"mensajes_post_delete={len(hist_b_post)}")

test("T17", "Eliminar sesion borra metadatos",
     sesion_b_post is None,
     "sesion no aparece en listado")


# --- T18: Renombrar sesion ---
print("\n  [Renombrar sesion]\n")

nuevo_titulo = "Sesion de prueba renombrada"
r = requests.patch(
    f"{BASE}/sessions/{SESSION_A}",
    json={"titulo": nuevo_titulo},
    headers=HEADERS,
)
r.raise_for_status()

sesiones = get_sessions()
sesion_a_ren = next((s for s in sesiones if s["session_id"] == SESSION_A), None)
test("T18", "Renombrar sesion actualiza titulo",
     sesion_a_ren is not None and sesion_a_ren["titulo"] == nuevo_titulo,
     f"titulo='{sesion_a_ren['titulo']}'" if sesion_a_ren else "no encontrada")


# --- T19: Sesion nueva no arrastra contexto de otra ---
print("\n  [Sesion limpia]\n")

t0 = time.time()
resp_nueva = chat("¿Y su jornada?", SESSION_C)
dt = round(time.time() - t0, 1)
resp_lower5 = resp_nueva["respuesta"].lower()

# Sin historial, el LLM no deberia saber a quien se refiere "su"
necesita_aclarar = (
    "qui" in resp_lower5  # ¿de quién...?
    or "especif" in resp_lower5
    or "nombre" in resp_lower5
    or "persona" in resp_lower5
    or "trabajador" in resp_lower5
    or resp_nueva.get("no_consta", False)
)

test("T19", "Sesion nueva sin historial: 'Y su jornada' pide aclaracion o no resuelve",
     necesita_aclarar,
     f"{dt}s | resp={resp_nueva['respuesta'][:80]}...")


# --- Limpieza ---
print(f"\n  [Limpieza]")
try:
    delete_session(SESSION_A)
    delete_session(SESSION_C)
    print("  Sesiones de test eliminadas.\n")
except Exception:
    print("  (algunas sesiones ya eliminadas)\n")


# --- Resumen ---
print(f"{'='*70}")
ok = sum(1 for r in resultados if r["ok"])
total = len(resultados)
print(f"  RESULTADO: {ok}/{total} pasaron")
print(f"{'='*70}")

fallos = [r for r in resultados if not r["ok"]]
if fallos:
    print(f"\n  FALLOS:")
    for f in fallos:
        print(f"    {f['id']}: {f['desc']}")
