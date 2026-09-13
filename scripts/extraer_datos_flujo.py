#!/usr/bin/env python3
"""Extrae de Jira Cloud los datos reales para las 4 graficas de flujo de CAMEIA
(Velocity/CFD/Aging WIP/Waste Snake) y los deja en CSV listos para Prism.

Migrado desde `informacion/material/scripts/extraer_datos_flujo.py` (CM-142) a este
repo dedicado (CM-151) para poder correrlo con evidencia real (workflow de GitHub
Actions), no solo a mano. Reproduce exactamente el procedimiento manual usado el
11-sep-2026 para el corte `informacion/material/datos-flujo-cameia-2026-09-11/`:
JQL para los issues del sprint + changelog por issue para reconstruir transiciones
de estado. No inventa ningun dato: si algo no se puede obtener, se deja
explicitamente vacio/"pendiente", nunca en 0 ni interpolado.

No incluye Discord_intervalos ni Desperdicio: no hay fuente real en Jira para eso
todavia (ver comunicaciones/11092026_scrum-texto_propuesta-metricas-agiles-reales.md
e informe del impediment backlog pedido a Juan Jose, CM-142).

Requisitos
----------
Solo libreria estandar de Python 3 (no hace falta instalar nada).

Configuracion (variables de entorno, NUNCA hardcodeadas ni commiteadas):
  JIRA_BASE_URL    ej. https://tu-dominio.atlassian.net
  JIRA_EMAIL       correo de la cuenta Atlassian que ejecuta el script
  JIRA_API_TOKEN   token personal, se crea en
                   https://id.atlassian.com/manage-profile/security/api-tokens
  JIRA_PROJECT_KEY opcional, por defecto "CM"
  JIRA_BOARD_ID    opcional, por defecto "1" (id real del "SCRUM board" de CAMEIA)
  JIRA_SPRINT_ID   opcional. Si no se define, se usa el sprint activo del board
                   (comportamiento anterior). Fijarlo explicitamente permite
                   repetir un corte de un sprint ya cerrado o evitar el aviso de
                   "hay mas de un sprint activo".

Uso
---
  set JIRA_BASE_URL=https://tu-dominio.atlassian.net   (PowerShell: $env:JIRA_BASE_URL=...)
  set JIRA_EMAIL=paulamunoz@unicauca.edu.co
  set JIRA_API_TOKEN=xxxxx
  python extraer_datos_flujo.py

Salida: crea `datos-flujo-cameia-<AAAA-MM-DD>/` (hoy, relativo al cwd) con
Contexto.csv, CFD_diario.csv, Burndown_diario.csv, WIP_corte.csv, Eventos.csv,
Ciclos_terminados.csv y un README.md de metodologia, mismo formato que el corte
del 11-sep-2026. El workflow de este repo (`.github/workflows/extraer-metricas.yml`)
sube esa carpeta como *artifact* del run -- copiarla a mano a
`informacion/material/` en el otro workspace despues de revisar los pendientes.

Que SI necesita revision humana cada vez que se corre (no lo decide el script,
tampoco el workflow):
- Si hay issues que deben excluirse de la poblacion (ej. las propias tareas de
  seguimiento de esta iniciativa de metricas) -> lista EXCLUDE_KEYS abajo.
- Si cambia el orden real de columnas del tablero -> lista STATE_ORDER abajo.
- El Sprint Goal, la fecha de entrega academica y las exclusiones declaradas de
  poblacion (ej. una cola de "En pruebas" fuera de sprint) se anotan en el
  Contexto.csv generado bajo "revision_manual_pendiente" -- completarlas a mano.
El script imprime al final un resumen explicito de estos pendientes (ver
`_imprimir_resumen_pendientes`) para que quede visible en el log del run de
Actions sin tener que abrir el CSV.
"""
from __future__ import annotations

import base64
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------
# Configuracion editable
# --------------------------------------------------------------------------
PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "CM")
BOARD_ID = os.environ.get("JIRA_BOARD_ID", "1")
SPRINT_ID_OVERRIDE = os.environ.get("JIRA_SPRINT_ID")
# Orden real de columnas del tablero, de izquierda a derecha. Revisar si el
# tablero cambia.
STATE_ORDER = ["Por hacer", "En curso", "En revisión", "En pruebas", "Finalizado"]
TERMINAL_STATE = "Finalizado"
INITIAL_STATE = "Por hacer"
# Estados que cuentan como WIP para Aging WIP / la convencion de "En curso +
# En revision + En pruebas" del diagnostico.
WIP_STATES = ["En curso", "En revisión"]
# Zona horaria de los timestamps que se reportan en las tablas (Jira ya trae el
# offset real en cada evento; esto solo define el corte de "fin de dia").
TZ_OFFSET = timezone(timedelta(hours=-5))  # -05:00, hora Colombia
# Issues que deben excluirse de la poblacion medida: son tareas de seguimiento
# de esta misma iniciativa de metricas (CM-142, CM-151), no trabajo de producto
# del sprint. Revisar esta lista en cada corte -- no se agrega nada aqui sin
# confirmar que el issue es realmente meta-trabajo, no producto.
EXCLUDE_KEYS: set[str] = {"CM-142", "CM-151"}
# Nombre del campo de story points a buscar (se resuelve el ID real via API,
# nunca se hardcodea el customfield_XXXXX porque cambia por sitio).
STORY_POINTS_FIELD_NAME_CANDIDATES = ["Story point estimate", "Story Points"]


def _env_or_die(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"Falta la variable de entorno {name}. Ver el docstring de este "
            f"archivo para configurarla. No se ejecuta nada sin credenciales "
            f"explicitas del usuario."
        )
    return value


BASE_URL = _env_or_die("JIRA_BASE_URL").rstrip("/")
EMAIL = _env_or_die("JIRA_EMAIL")
API_TOKEN = _env_or_die("JIRA_API_TOKEN")

_AUTH = base64.b64encode(f"{EMAIL}:{API_TOKEN}".encode()).decode()


def jira_get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {_AUTH}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        sys.exit(f"Error {exc.code} llamando a {url}:\n{body}")


def discover_story_points_field() -> str | None:
    fields = jira_get("/rest/api/3/field")
    for candidate in STORY_POINTS_FIELD_NAME_CANDIDATES:
        for field in fields:
            if field.get("name", "").strip().lower() == candidate.lower():
                return field["id"]
    print(
        "AVISO: no se encontro un campo de Story Points con los nombres "
        f"esperados {STORY_POINTS_FIELD_NAME_CANDIDATES}. Burndown_diario y "
        "Ciclos_terminados quedaran sin story points (columna 'sin estimar').",
        file=sys.stderr,
    )
    return None


def get_sprint(board_id: str, sprint_id_override: str | None) -> dict:
    if sprint_id_override:
        data = jira_get(f"/rest/agile/1.0/sprint/{sprint_id_override}")
        return data
    data = jira_get(f"/rest/agile/1.0/board/{board_id}/sprint", {"state": "active"})
    sprints = data.get("values", [])
    if not sprints:
        sys.exit(f"No hay sprint activo en el board {board_id}. Fija JIRA_SPRINT_ID a mano.")
    if len(sprints) > 1:
        print(
            f"AVISO: hay {len(sprints)} sprints activos en el board {board_id}; "
            f"se usa el primero ({sprints[0]['name']}). Fija JIRA_SPRINT_ID si no "
            "es el esperado.",
            file=sys.stderr,
        )
    return sprints[0]


def get_sprint_issues(sprint_id: int, sp_field_id: str | None) -> list[dict]:
    fields = ["summary", "issuetype", "status", "created"]
    if sp_field_id:
        fields.append(sp_field_id)
    issues: list[dict] = []
    start_at = 0
    jql = f"project = {PROJECT_KEY} AND sprint = {sprint_id}"
    while True:
        data = jira_get(
            "/rest/api/3/search",
            {
                "jql": jql,
                "fields": ",".join(fields),
                "startAt": start_at,
                "maxResults": 100,
            },
        )
        batch = data.get("issues", [])
        issues.extend(batch)
        if start_at + len(batch) >= data.get("total", 0) or not batch:
            break
        start_at += len(batch)
    excluded = [i for i in issues if i["key"] in EXCLUDE_KEYS]
    if excluded:
        print(
            "Excluidos de la población (EXCLUDE_KEYS): "
            + ", ".join(i["key"] for i in excluded),
            file=sys.stderr,
        )
    return [i for i in issues if i["key"] not in EXCLUDE_KEYS]


def get_status_changelog(issue_key: str) -> list[dict]:
    """Devuelve [{fecha_hora: datetime con tz, de: str, a: str}], orden cronologico."""
    events: list[dict] = []
    start_at = 0
    while True:
        data = jira_get(
            f"/rest/api/3/issue/{issue_key}/changelog",
            {"startAt": start_at, "maxResults": 100},
        )
        for entry in data.get("values", []):
            created = datetime.fromisoformat(entry["created"].replace("Z", "+00:00"))
            for item in entry.get("items", []):
                if item.get("field") == "status":
                    events.append(
                        {
                            "fecha_hora": created,
                            "de": item.get("fromString") or INITIAL_STATE,
                            "a": item.get("toString"),
                        }
                    )
        total = data.get("total", len(data.get("values", [])))
        start_at += len(data.get("values", []))
        if start_at >= total or not data.get("values"):
            break
    events.sort(key=lambda e: e["fecha_hora"])
    return events


def state_at(events: list[dict], cutoff: datetime) -> str:
    """Estado del issue justo antes/en `cutoff`, o INITIAL_STATE si no hay eventos previos."""
    state = INITIAL_STATE
    for ev in events:
        if ev["fecha_hora"] <= cutoff:
            state = ev["a"]
        else:
            break
    return state


def daterange(start: datetime, end: datetime):
    d = start.date()
    while d <= end.date():
        yield d
        d += timedelta(days=1)


def write_csv(path: str, header: list[str], rows: list[list]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Escrito: {path}")


def _imprimir_resumen_pendientes(sprint: dict, out_dir: str) -> None:
    """Resumen legible en el log del run de Actions de lo que exige revision
    humana antes de entregar el corte a Prism -- no basta con generar los CSV."""
    print("\n" + "=" * 72)
    print("REVISION HUMANA PENDIENTE ANTES DE ENTREGAR ESTE CORTE A PRISM:")
    print("=" * 72)
    print(f"1. Sprint Goal declarado en Jira: {sprint.get('goal') or '(vacio, confirmar con el equipo)'}")
    print("2. Confirmar EXCLUDE_KEYS vigente: " + ", ".join(sorted(EXCLUDE_KEYS)))
    print("3. Confirmar que no hay otra cola (ej. \"En pruebas\" fuera de sprint) que deba declararse.")
    print(f"4. Revisar {out_dir}/Contexto.csv, fila 'revision_manual_pendiente', antes de copiar a informacion/material/.")
    print("=" * 72)


def main() -> None:
    sprint = get_sprint(BOARD_ID, SPRINT_ID_OVERRIDE)
    sprint_id = sprint["id"]
    sprint_start = datetime.fromisoformat(sprint["startDate"].replace("Z", "+00:00"))
    today = datetime.now(TZ_OFFSET)

    sp_field_id = discover_story_points_field()
    issues = get_sprint_issues(sprint_id, sp_field_id)
    print(f"Sprint: {sprint['name']} (id {sprint_id}), {len(issues)} issues.")

    fuente = (
        f"Jira Cloud API ({BASE_URL}), proyecto {PROJECT_KEY}, sprint id {sprint_id}, "
        f"extraido {today.isoformat()}"
    )

    timelines: dict[str, list[dict]] = {}
    story_points: dict[str, float | None] = {}
    created_at: dict[str, datetime] = {}
    tipos: dict[str, str] = {}
    for issue in issues:
        key = issue["key"]
        timelines[key] = get_status_changelog(key)
        tipos[key] = issue["fields"]["issuetype"]["name"]
        created_at[key] = datetime.fromisoformat(
            issue["fields"]["created"].replace("Z", "+00:00")
        )
        sp_value = issue["fields"].get(sp_field_id) if sp_field_id else None
        story_points[key] = sp_value

    out_dir = os.path.join(os.getcwd(), f"datos-flujo-cameia-{today.date().isoformat()}")
    out_dir = os.path.normpath(out_dir)

    # --- CFD_diario ---------------------------------------------------
    cfd_rows = []
    for day in daterange(sprint_start, today):
        cutoff = datetime.combine(day, datetime.max.time(), tzinfo=TZ_OFFSET)
        counts = {s: 0 for s in STATE_ORDER}
        for key in timelines:
            counts[state_at(timelines[key], cutoff)] += 1
        cfd_rows.append(
            [day.isoformat()] + [counts[s] for s in STATE_ORDER]
            + [len(issues), fuente, "observado"]
        )
    write_csv(
        os.path.join(out_dir, "CFD_diario.csv"),
        ["fecha_corte"] + [s.lower().replace(" ", "_") for s in STATE_ORDER]
        + ["total", "fuente", "calidad_dato"],
        cfd_rows,
    )

    # --- Burndown_diario ------------------------------------------------
    estimated_keys = [k for k, v in story_points.items() if v is not None]
    unestimated_keys = [k for k in timelines if k not in estimated_keys]
    total_sp = sum(story_points[k] for k in estimated_keys) if estimated_keys else 0
    burndown_rows = []
    for day in daterange(sprint_start, today):
        cutoff = datetime.combine(day, datetime.max.time(), tzinfo=TZ_OFFSET)
        remaining = sum(
            story_points[k]
            for k in estimated_keys
            if state_at(timelines[k], cutoff) != TERMINAL_STATE
        )
        open_unestimated = sum(
            1 for k in unestimated_keys if state_at(timelines[k], cutoff) != TERMINAL_STATE
        )
        burndown_rows.append(
            [day.isoformat(), remaining, total_sp, open_unestimated, fuente, "alta"]
        )
    write_csv(
        os.path.join(out_dir, "Burndown_diario.csv"),
        [
            "fecha_corte",
            "puntos_restantes",
            "puntos_comprometidos_totales",
            "issues_sin_estimar_aun_abiertos",
            "fuente",
            "calidad_dato",
        ],
        burndown_rows,
    )

    # --- WIP_corte --------------------------------------------------------
    wip_rows = []
    for key, events in timelines.items():
        current_state = state_at(events, today)
        if current_state not in WIP_STATES:
            continue
        # Edad = desde la PRIMERA entrada real a "En curso", no desde la última
        # transicion al estado actual -- un retroceso o reingreso NO reinicia
        # el reloj (corregido 12-sep-2026 tras deteccion en el analisis v2.1).
        primeras_en_curso = [e for e in events if e["a"] == "En curso"]
        inicio_efectivo = (
            primeras_en_curso[0]["fecha_hora"].isoformat()
            if primeras_en_curso
            else created_at[key].isoformat()
        )
        retrocesos = [
            e for e in events
            if STATE_ORDER.index(e["a"]) < STATE_ORDER.index(e["de"])
        ]
        nota_reapertura = (
            "; ".join(
                f"Retroceso {e['de']}->{e['a']} el {e['fecha_hora'].isoformat()} (ver Eventos)"
                for e in retrocesos
            )
            or "No"
        )
        wip_rows.append(
            [
                key,
                tipos[key],
                sprint["name"],
                current_state,
                inicio_efectivo,
                today.date().isoformat(),
                "pendiente de registrar",
                nota_reapertura,
                fuente,
                "observado",
            ]
        )
    write_csv(
        os.path.join(out_dir, "WIP_corte.csv"),
        [
            "id_elemento", "tipo", "sprint", "estado_actual", "inicio_efectivo",
            "fecha_corte", "bloqueo", "reapertura", "fuente", "calidad_dato",
        ],
        wip_rows,
    )

    # --- Eventos ------------------------------------------------------
    eventos_rows = []
    for key, events in timelines.items():
        for e in events:
            eventos_rows.append([key, e["fecha_hora"].isoformat(), e["de"], e["a"], "Jira changelog"])
    eventos_rows.sort(key=lambda r: r[1])
    write_csv(
        os.path.join(out_dir, "Eventos.csv"),
        ["id_elemento", "fecha_hora", "estado_anterior", "estado_nuevo", "fuente"],
        eventos_rows,
    )

    # --- Ciclos_terminados ------------------------------------------------
    ciclos_rows = []
    for key, events in timelines.items():
        if state_at(events, today) != TERMINAL_STATE:
            continue
        fin = next(e["fecha_hora"] for e in reversed(events) if e["a"] == TERMINAL_STATE)
        primeras_en_curso = [e for e in events if e["a"] == "En curso"]
        primera_en_curso = primeras_en_curso[0]["fecha_hora"] if primeras_en_curso else None
        lead_time = (fin.date() - created_at[key].date()).days
        cycle_time = (fin.date() - primera_en_curso.date()).days if primera_en_curso else None
        sp = story_points.get(key)
        ciclos_rows.append(
            [
                key,
                created_at[key].date().isoformat(),
                primera_en_curso.date().isoformat() if primera_en_curso else "N/A - nunca pasó por En curso",
                fin.date().isoformat(),
                lead_time,
                cycle_time if cycle_time is not None else "N/A",
                sp if sp is not None else "sin estimar",
                "Jira (created via JQL; transiciones via changelog)",
            ]
        )
    write_csv(
        os.path.join(out_dir, "Ciclos_terminados.csv"),
        [
            "id_elemento", "creado", "primera_vez_en_curso", "finalizado",
            "lead_time_dias", "cycle_time_dias", "story_points", "fuente",
        ],
        ciclos_rows,
    )
    print(
        f"\nCiclos_terminados: n={len(ciclos_rows)}. Si n < ~20-30, NO calcular "
        "un percentil P85/SLE con esta muestra -- dejarlo pendiente, no inventarlo."
    )

    # --- Contexto (parcial, requiere revision humana) -----------------
    contexto_rows = [
        ["identificador_del_corte", f"CAMEIA-{PROJECT_KEY}-{sprint['name']}-{today.date().isoformat()}"],
        ["fecha_extraccion", today.isoformat()],
        ["proyecto", f'Jira "{PROJECT_KEY}"'],
        ["tablero", f"board id {BOARD_ID}"],
        ["sprint", f"{sprint['name']} (id {sprint_id}), inicio {sprint['startDate']}, fin previsto {sprint.get('endDate', 'desconocido')}, goal: {sprint.get('goal') or 'no definido'}"],
        ["poblacion", f"{len(issues)} issues del sprint, excluidos: {', '.join(sorted(EXCLUDE_KEYS)) or 'ninguno'}"],
        ["revision_manual_pendiente", "Confirmar poblaciones excluidas (ej. colas fuera de sprint), fecha de entrega académica, y calidad_dato de cada tabla antes de entregar a Prism."],
    ]
    write_csv(os.path.join(out_dir, "Contexto.csv"), ["campo", "valor"], contexto_rows)

    _imprimir_resumen_pendientes(sprint, out_dir)
    print(f"\nListo. Revisar {out_dir} antes de copiarlo a informacion/material/ y entregarlo a Prism.")


if __name__ == "__main__":
    main()
