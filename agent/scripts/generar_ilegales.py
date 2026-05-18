"""Generador de contratos con infracciones legales documentadas.

Corpus de prueba para validar el compliance_checker: cada contrato
contiene una sola infracción aislada (salario por debajo del SMI,
jornada excesiva, periodo de prueba demasiado largo, vacaciones
insuficientes…) anotada con el artículo del Estatuto que vulnera.

Aisladas para que cada test pueda comprobar de forma unívoca que el
detector identifica la infracción correcta. El resto del clausulado
del contrato es legalmente válido.

Uso:
    cd agent && uv run python scripts/generar_ilegales.py
"""

from datetime import date
from pathlib import Path

# Reutilizamos las funciones y constantes del generador legal.
from generar_contratos import (
    generar_contrato,
    _formato_salario,
    _fecha_firma_texto,
    _fecha_ddmmyyyy,
    _calcular_dni,
    EMPRESAS,
)


# Cada contrato infringe UN artículo distinto del Estatuto.
# Los datos básicos siguen el mismo formato que el resto del corpus.
INFRACCIONES = [
    {
        # Infracción: salario anual por debajo del SMI (art. 27 ET).
        # SMI 2024: 15.876 EUR/año (1.134 EUR/mes × 14 pagas).
        "trabajador_nombre": "MENDOZA RIVAS, RICARDO",
        "salario": 13000,
        "puesto": "RECEPCIONISTA",
        "grupo": "ADMINISTRATIVO",
        "tipo": "indefinido",
        "vacaciones": "30 días naturales",
        "periodo_prueba": "1 Mes",
        "conceptos": "Según Convenio",
    },
    {
        # Infracción: jornada semanal > 40h (art. 34.1 ET).
        # Se especifica explícitamente 45h/semana en lugar del máximo legal.
        "trabajador_nombre": "VARGAS LEON, NATALIA",
        "salario": 22000,
        "puesto": "ADMINISTRATIVO/A",
        "grupo": "ADMINISTRATIVO",
        "tipo": "indefinido",
        "jornada_horas": 45.0,
        "vacaciones": "30 días naturales",
        "periodo_prueba": "1 Mes",
        "conceptos": "Salario base más complementos según convenio",
    },
    {
        # Infracción: periodo de prueba > 2 meses para no titulado (art. 14.1 ET).
        # Para grupos no técnicos / no titulados, el máximo son 2 meses.
        "trabajador_nombre": "PALOMO CRUZ, ANGELA",
        "salario": 19000,
        "puesto": "AUXILIAR CONTABLE",
        "grupo": "ADMINISTRATIVO",
        "tipo": "indefinido",
        "periodo_prueba": "6 Meses",
        "vacaciones": "30 días naturales",
        "conceptos": "Según Convenio",
    },
    {
        # Infracción: vacaciones por debajo del mínimo legal (art. 38.1 ET).
        # El mínimo son 30 días naturales (~22 laborables).
        "trabajador_nombre": "QUEVEDO LIMA, BORJA",
        "salario": 24000,
        "puesto": "COMERCIAL",
        "grupo": "COMERCIAL",
        "tipo": "indefinido",
        "vacaciones": "20 días naturales",
        "periodo_prueba": "1 Mes",
        "conceptos": "Salario base más complementos según convenio",
    },
]


def _construir_contrato(infraccion: dict, idx: int) -> dict:
    """Construye el dict de contrato listo para generar_contrato()."""
    # Datos comunes
    empresa = EMPRESAS[idx % len(EMPRESAS)]
    centro_data = empresa.get("centros", [{
        "municipio": empresa["municipio"],
        "cp": empresa["cp"],
        "direccion": empresa["domicilio"],
    }])[0]
    centro = {"municipio": centro_data["municipio"], "cp": centro_data["cp"]}

    # DNI predecible (fuera del rango del generador principal)
    dni = _calcular_dni(99000000 + idx * 397)

    # Fechas fijas para reproducibilidad
    fecha_inicio = date(2024, 6, 1)
    fecha_firma = date(2024, 5, 25)

    contrato = {
        "empresa": empresa,
        "centro": centro,
        "centro_direccion": centro_data["direccion"],
        "trabajador": {
            "nombre": infraccion["trabajador_nombre"],
            "nif": dni,
        },
        "tipo": infraccion["tipo"],
        "puesto": infraccion["puesto"],
        "grupo": infraccion["grupo"],
        "fecha_inicio": _fecha_ddmmyyyy(fecha_inicio),
        "periodo_prueba": infraccion["periodo_prueba"],
        "salario_texto": _formato_salario(infraccion["salario"]),
        "pagas": "12 PAGAS",
        "conceptos_salariales": infraccion["conceptos"],
        "vacaciones": infraccion["vacaciones"],
        "fecha_firma": _fecha_firma_texto(fecha_firma),
    }

    # Si la infracción es de jornada, se mantiene jornada completa pero con
    # más horas semanales de las permitidas (40h es el máximo legal).
    if "jornada_horas" in infraccion:
        contrato["horas_semana"] = infraccion["jornada_horas"]

    return contrato


def main():
    output_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generando {len(INFRACCIONES)} contratos con infracciones...\n")

    for i, infraccion in enumerate(INFRACCIONES):
        contrato = _construir_contrato(infraccion, i)
        nombre_trab = infraccion["trabajador_nombre"]
        partes = nombre_trab.replace(",", "").lower().split()
        filename = f"contrato_ilegal_{i+1:02d}_{partes[0]}_{partes[-1]}.pdf"

        generar_contrato(contrato, output_dir / filename)
        print(f"  [{i+1}/{len(INFRACCIONES)}] {filename}")
        print(f"        Trabajador: {nombre_trab}")
        print(f"        Salario:    {infraccion['salario']} EUR/año")
        print(f"        Vacaciones: {infraccion['vacaciones']}")
        print(f"        Prueba:     {infraccion['periodo_prueba']}")
        if "jornada_horas" in infraccion:
            print(f"        Jornada:    {infraccion['jornada_horas']}h/semana")
        print()


if __name__ == "__main__":
    main()
