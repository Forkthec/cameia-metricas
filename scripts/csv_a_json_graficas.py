#!/usr/bin/env python3
"""Convierte el paquete de 6 CSV que produce `extraer_datos_flujo.py` en
`site/data/graficas.json`, el formato que consume el sitio estático (Chart.js,
ver `site/js/charts.js`).

No inventa ni completa nada que el CSV no traiga: si una gráfica no tiene datos
reales (hoy: Waste Snake, sin impediment backlog en Jira), su entrada queda con
`"estado": "pendiente"` y sin serie de datos -- el sitio la muestra vacía con el
motivo, nunca con un número inventado. Igual que el script de extracción, esto
es deliberado, no un descuido.

Diseño pensado para agregar métricas sin tocar el resto: cada entrada de
`graficas` es independiente y su `tipo` decide qué renderer usa `charts.js`
(`linea_con_referencia`, `flujo_acumulado`, `edad_por_estado`,
`categorias_apiladas_con_total`). Agregar una gráfica nueva de un tipo ya
soportado es agregar un objeto a la lista; un tipo nuevo es una función nueva en
`charts.js`, sin tocar las demás.

Uso
---
  python scripts/csv_a_json_graficas.py <carpeta-con-los-6-csv> [salida.json]

Si no se da carpeta, busca la más reciente `datos-flujo-cameia-*/` en el cwd
(el mismo patrón que ya produce `extraer_datos_flujo.py`). Si no se da salida,
escribe en `site/data/graficas.json` relativo a este script.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

STATE_ORDER = ["Por hacer", "En curso", "En revisión", "En pruebas", "Finalizado"]
STATE_COLOR = {
    "Por hacer": "var(--serie-muted)",
    "En curso": "var(--serie-naranja)",
    "En revisión": "var(--serie-azul)",
    "En pruebas": "var(--serie-morado)",
    "Finalizado": "var(--serie-verde)",
}
CSV_COLUMN_POR_ESTADO = {
    "Por hacer": "por_hacer",
    "En curso": "en_curso",
    "En revisión": "en_revisión",
    "En pruebas": "en_pruebas",
    "Finalizado": "finalizado",
}


def _leer_csv(ruta: Path) -> list[dict[str, str]]:
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _ultima_carpeta_datos(cwd: Path) -> Path:
    candidatas = sorted(glob.glob(str(cwd / "datos-flujo-cameia-*")))
    if not candidatas:
        sys.exit(
            "No se encontro ninguna carpeta datos-flujo-cameia-*/ en el "
            "directorio actual. Pasa la ruta explicita como primer argumento."
        )
    return Path(candidatas[-1])


def _fecha_corta(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d-%b").replace(".", "")


def construir_contexto(carpeta: Path) -> dict:
    filas = {r["campo"]: r["valor"] for r in _leer_csv(carpeta / "Contexto.csv")}
    cfd = _leer_csv(carpeta / "CFD_diario.csv")
    ciclos = _leer_csv(carpeta / "Ciclos_terminados.csv")
    burndown = _leer_csv(carpeta / "Burndown_diario.csv")
    ultimo_cfd = cfd[-1] if cfd else {}
    por_estado = {
        estado: int(ultimo_cfd.get(CSV_COLUMN_POR_ESTADO[estado], 0) or 0)
        for estado in STATE_ORDER
    }
    return {
        "identificador_del_corte": filas.get("identificador_del_corte", ""),
        "fecha_extraccion": filas.get("fecha_extraccion", ""),
        "poblacion_total": int(ultimo_cfd.get("total", 0) or 0) if ultimo_cfd else None,
        "por_estado": por_estado,
        "story_points_comprometidos": int(burndown[-1]["puntos_comprometidos_totales"]) if burndown else None,
        "ciclos_terminados_n": len(ciclos),
        "fuente": filas.get("proyecto", "Jira Cloud"),
    }


def construir_progreso(carpeta: Path) -> dict:
    """Burndown real (puntos restantes por dia). Sustituye a la barra
    planeado-vs-completado del ejemplo del profesor porque en Jira no existe
    (todavia) un plan diario declarado -- inventar una serie "planeado" no
    respaldada por un dato real violaria el principio del proyecto."""
    filas = _leer_csv(carpeta / "Burndown_diario.csv")
    if not filas:
        return {
            "id": "progreso-diario",
            "tipo": "linea_con_referencia",
            "titulo": "Sprint 1 — Trabajo pendiente",
            "estado": "pendiente",
            "nota_estado": "No se dispone de datos de Burndown para este corte.",
        }
    return {
        "id": "progreso-diario",
        "tipo": "linea_con_referencia",
        "titulo": "Sprint 1 — Trabajo pendiente",
        "pregunta": "¿Cuántos puntos de historia quedan por completar cada día?",
        "estado": "real",
        "nota_estado": (
            "Esta serie sustituye al Velocity Chart y al ejemplo de barras "
            "planeado-versus-completado presentado por el docente, dado que Jira no "
            "registra un plan diario declarado por historia y, en consecuencia, dicha "
            "serie no constituye un dato verificable. El Velocity Chart propio del "
            "equipo estará disponible tras el cierre del Sprint 1."
        ),
        "fuente": "Burndown_diario.csv — Jira, puntos de historia reales",
        "eje_x": {"titulo": "Fecha de corte", "categorias": [_fecha_corta(f["fecha_corte"]) for f in filas]},
        "eje_y": {"titulo": "Puntos restantes"},
        "series": [
            {
                "nombre": "Puntos restantes",
                "color": "var(--serie-azul)",
                "valores": [int(f["puntos_restantes"]) for f in filas],
            }
        ],
        "referencias": [
            {
                "nombre": "Comprometido al inicio del corte",
                "valor": int(filas[0]["puntos_comprometidos_totales"]),
                "color": "var(--serie-muted)",
                "estilo": "dashed",
            }
        ],
        "lectura": {
            "resumen": (
                f"Del total comprometido ({filas[0]['puntos_comprometidos_totales']} puntos de "
                f"historia), restan {filas[-1]['puntos_restantes']} en el corte actual. "
                f"{filas[-1]['issues_sin_estimar_aun_abiertos']} issues abiertos permanecen sin estimar."
            ),
        },
    }


def construir_cfd(carpeta: Path) -> dict:
    filas = _leer_csv(carpeta / "CFD_diario.csv")
    if not filas:
        return {"id": "cfd", "tipo": "flujo_acumulado", "titulo": "Diagrama de Flujo Acumulado", "estado": "pendiente"}
    return {
        "id": "cfd",
        "tipo": "flujo_acumulado",
        "titulo": "Diagrama de Flujo Acumulado",
        "pregunta": "¿Dónde se acumula el trabajo, día a día?",
        "estado": "real",
        "fuente": "CFD_diario.csv — conteo real por estado, población de Sprint 1, corte diario 23:59:59 (hora Colombia)",
        "eje_x": {"titulo": "Fecha de corte", "categorias": [_fecha_corta(f["fecha_corte"]) for f in filas]},
        "eje_y": {"titulo": "Ítems acumulados"},
        "series": [
            {
                "nombre": estado,
                "color": STATE_COLOR[estado],
                "valores": [int(f[CSV_COLUMN_POR_ESTADO[estado]] or 0) for f in filas],
            }
            for estado in STATE_ORDER
        ],
        "lectura": {
            "resumen": (
                "El ensanchamiento sostenido de una banda indica acumulación de trabajo y "
                "sugiere un posible cuello de botella. El crecimiento de la banda «Finalizado» "
                "refleja trabajo efectivamente concluido."
            ),
        },
    }


def construir_aging_wip(carpeta: Path) -> dict:
    filas = _leer_csv(carpeta / "WIP_corte.csv")
    if not filas:
        return {"id": "aging-wip", "tipo": "edad_por_estado", "titulo": "Kanban — Edad del trabajo en curso", "estado": "pendiente"}
    hoy = datetime.strptime(filas[0]["fecha_corte"], "%Y-%m-%d").date()
    estados = sorted({f["estado_actual"] for f in filas}, key=lambda e: STATE_ORDER.index(e) if e in STATE_ORDER else 99)
    puntos = []
    edades = []
    for f in filas:
        inicio = datetime.fromisoformat(f["inicio_efectivo"]).date()
        edad = (hoy - inicio).days
        edades.append(edad)
        puntos.append({"estado": f["estado_actual"], "edad_dias": edad, "id": f["id_elemento"]})
    promedio = round(sum(edades) / len(edades), 1) if edades else 0
    promedio_txt = f"{promedio:.1f}".replace(".", ",")
    return {
        "id": "aging-wip",
        "tipo": "edad_por_estado",
        "titulo": "Kanban — Edad del trabajo en curso",
        "pregunta": "¿Dónde requiere apoyo el equipo en este momento?",
        "estado": "real",
        "nota_estado": (
            "No se incluye una línea de referencia SLE: con "
            f"{len(edades)} ítems abiertos, la muestra es insuficiente para declarar un "
            "umbral del equipo (percentil 85) sin incurrir en una estimación no "
            "verificable. Este valor se calculará cuando exista un acuerdo del equipo y "
            "una muestra suficiente."
        ),
        "fuente": "WIP_corte.csv — edad calculada desde la primera entrada real a «En curso»",
        "eje_x": {"titulo": "Estado actual", "categorias": estados},
        "eje_y": {"titulo": "Edad del ítem (días calendario)"},
        "puntos": puntos,
        "referencias": [
            {"nombre": f"Edad promedio observada: {promedio_txt} días", "valor": promedio, "color": "var(--ink)", "estilo": "dotted"}
        ],
        "lectura": {
            "resumen": (
                f"Ítems abiertos en el corte actual: {len(edades)}. Edad promedio observada: "
                f"{promedio_txt} días. Este valor no constituye una meta ni una estimación de "
                "tiempo restante."
            ),
        },
    }


def construir_waste_snake(carpeta: Path) -> dict:
    return {
        "id": "waste-snake",
        "tipo": "categorias_apiladas_con_total",
        "titulo": "Kanban — Registro de desperdicio (Waste Snake)",
        "pregunta": "¿En qué categoría se pierden horas-persona cada día?",
        "estado": "pendiente",
        "nota_estado": (
            "Aún no existe un registro de impedimentos («impediment backlog») en Jira: "
            "se verificaron 0 etiquetas y 0 componentes de «desperdicio». Esta gestión fue "
            "solicitada a Juan José Arias Chacua, con plazo al 15 de septiembre de 2026 "
            "(véase comunicaciones/11092026_scrum-texto_propuesta-metricas-agiles-reales.md). "
            "La gráfica permanece vacía de manera deliberada: no se sustituye por la cifra "
            "ilustrativa del ejemplo presentado por el docente."
        ),
        "fuente": "Sin fuente real disponible en Jira",
    }


def construir(carpeta: Path) -> dict:
    return {
        "generado_en": datetime.now().astimezone().isoformat(timespec="seconds"),
        "corte": construir_contexto(carpeta),
        "graficas": [
            construir_progreso(carpeta),
            construir_cfd(carpeta),
            construir_aging_wip(carpeta),
            construir_waste_snake(carpeta),
        ],
    }


def main() -> None:
    cwd = Path.cwd()
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else _ultima_carpeta_datos(cwd)
    salida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "site" / "data" / "graficas.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    datos = construir(carpeta)
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {salida} a partir de {carpeta}")


if __name__ == "__main__":
    main()
