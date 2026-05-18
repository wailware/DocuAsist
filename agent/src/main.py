"""CLI interactiva del agente para pruebas manuales.

Ejecuta el grafo en bucle leyendo preguntas del usuario por stdin, sin
depender del API HTTP ni de la base de datos de sesiones. Útil para
depurar nodos en aislamiento o probar prompts antes de exponerlos a
través del backend.
"""

import sys
from src.core.graph import grafo


def main():
    print("=== DocuAsist — Asistente Documental ===")
    print("Escribe tu pregunta o 'salir' para terminar.\n")

    mensajes = []

    while True:
        try:
            pregunta = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo...")
            break

        if pregunta.lower() in ("salir", "exit", "quit"):
            break
        if not pregunta:
            continue

        estado_entrada = {
            "user_id": "usuario_prueba",
            "session_id": "sesion_prueba",
            "pregunta": pregunta,
            "messages": mensajes,
            "traza": [],
        }

        resultado = grafo.invoke(estado_entrada)
        mensajes = resultado.get("messages", mensajes)

        if resultado.get("necesita_aclaracion"):
            print(f"\nAsistente: {resultado['pregunta_aclaracion']}\n")
        else:
            print(f"\nAsistente: {resultado['respuesta']}\n")

            citas = resultado.get("citas", [])
            if citas:
                print("Fuentes consultadas:")
                for cita in citas:
                    nombre = cita.get("nombre_trabajador", "Desconocido")
                    pagina = cita.get("pagina", "?")
                    print(f"  · {nombre} — Pág. {pagina}")
            print()

            traza = resultado.get("traza", [])
            if traza:
                tiempos = " | ".join(
                    f"{t['nodo']}: {t['latencia_s']}s" for t in traza
                )
                print(f"[{tiempos}]\n")


if __name__ == "__main__":
    main()