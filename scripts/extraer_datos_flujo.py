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

No incluye Discord_intervalos: no hay fuente real en Jira para eso todavia (ver
comunicaciones/11092026_scrum-texto_propuesta-metricas-agiles-reales.md).

Desperdicio / impedimentos (CORREGIDO 19-sep-2026): desde que se creo el issue
type "Impediment / Bloqueo" (Espacio CAMEIA > Configuracion del espacio > Tipos de
actividad) SI hay fuente real en Jira para esto. Cada impedimento es un issue
INDEPENDIENTE (no un campo dentro de la tarea bloqueada) con sus propios campos:
Resumen, Categoria de desperdicio, Horas-persona desperdiciadas, Tipo de Bloqueo y
Descripcion. Este script los extrae a un archivo nuevo, `Impedimentos.csv`.

POBLACION DE FLUJO vs. EXCLUDE_KEYS (CORREGIDO 25-sep-2026): son dos filtros
distintos, no lo mismo. EXCLUDE_KEYS saca issues puntuales del corte COMPLETO
(ni siquiera aparecen en Impedimentos.csv ni en Eventos.csv) porque son
meta-trabajo de esta misma iniciativa de metricas (CM-142, CM-151), no trabajo
del sprint. FLOW_EXCLUDE_ISSUE_TYPES, en cambio, decidido con el equipo el
25-sep-2026, saca del CFD/Burndown/WIP/Ciclos_terminados (la "poblacion de
flujo") los issues tipo "Impediment / Bloqueo", porque son artefactos de
registro de desperdicio, no trabajo de producto comprometido en el sprint --
pero esos mismos issues SI se conservan enteros en Impedimentos.csv (para lo que
existen) y en Eventos.csv (bitacora cruda completa, deliberadamente sin este
filtro, para no perder trazabilidad de ningun evento real).

OJO -- confirmado con el equipo el 19-sep-2026: hoy esos issues de tipo
"Impediment / Bloqueo" NO se enlazan en Jira (con un issue link tipo "bloquea a" /
"esta bloqueado por" o similar) a la tarea que bloquearon. Por eso:
  - Impedimentos.csv sirve para saber CUANTO se perdio en total (horas-persona,
    categoria, tipo de bloqueo) pero NO para saber QUE tarea especifica de WIP se
    demoro por cada impedimento -- esa relacion no existe en los datos hoy.
  - El script SI intenta leer el campo estandar de Jira `issuelinks` en cada issue
    (impedimentos y tareas normales por igual), sin asumir un nombre de tipo de
    enlace fijo. Hoy eso devolvera casi siempre "sin enlace registrado" en
    WIP_corte.csv.bloqueo e Impedimentos.csv.enlace_a_item_bloqueado. El dia que el
    equipo empiece a enlazar impedimentos a tareas, ambas columnas se llenaran
    solas, sin tocar este script.

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
Ciclos_terminados.csv, Impedimentos.csv y un README.md de metodologia, mismo
formato que el corte del 11-sep-2026 (mas Impedimentos.csv, nuevo). El workflow de
este repo (`.github/workflows/extraer-metricas.yml`) sube esa carpeta como
*artifact* del run -- copiarla a mano a `informacion/material/` en el otro
workspace despues de revisar los pendientes.

Que SI necesita revision humana cada vez que se corre (no lo decide el script,
tampoco el workflow):
- Si hay issues que deben excluirse del corte completo (ej. las propias tareas de
  seguimiento de esta iniciativa de metricas) -> lista EXCLUDE_KEYS abajo.
- Si el tipo "Impediment / Bloqueo" sigue siendo el unico que debe excluirse de la
  poblacion de flujo (CFD/Burndown/WIP/Ciclos_terminados) -> lista
  FLOW_EXCLUDE_ISSUE_TYPES abajo. Decidido con el equipo el 25-sep-2026: SI se
  excluyen (antes, hasta ese corte, se contaban igual que cualquier otro issue).
  Impedimentos.csv y Eventos.csv NO aplican este filtro -- ahi se conservan
  enteros a proposito.
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
# Nombre exacto del tipo de issue usado para registrar impedimentos/desperdicio
# (Espacio CAMEIA > Configuracion del espacio > Tipos de actividad). Revisar si
# el equipo le cambia el nombre.
IMPEDIMENT_ISSUE_TYPE_NAME = "Impediment / Bloqueo"
# Zona horaria de los timestamps que se reportan en las tablas (Jira ya trae el
# offset real en cada evento; esto solo define el corte de "fin de dia").
TZ_OFFSET = timezone(timedelta(hours=-5))  # -05:00, hora Colombia
# Issues que deben excluirse del corte COMPLETO (no aparecen en ningun CSV,
# tampoco en Impedimentos.csv/Eventos.csv): son tareas de seguimiento de esta
# misma iniciativa de metricas (CM-142, CM-151), no trabajo de producto del
# sprint. Revisar esta lista en cada corte -- no se agrega nada aqui sin
# confirmar que el issue es realmente meta-trabajo, no producto.
EXCLUDE_KEYS: set[str] = {"CM-142", "CM-151"}
# Tipos de issue que deben excluirse SOLO de la poblacion de flujo (CFD,
# Burndown, WIP_corte, Ciclos_terminados) por ser artefactos de registro de
# desperdicio y no trabajo de producto comprometido en el sprint. Impedimentos.csv
# y Eventos.csv NO usan este filtro -- ahi se conservan completos. Decidido con
# el equipo el 25-sep-2026. Revisar esta lista en cada corte, igual que
# EXCLUDE_KEYS.
FLOW_EXCLUDE_ISSUE_TYPES: set[str] = {IMPEDIMENT_ISSUE_TYPE_NAME}
# Nombres de campo a buscar por API (se resuelve el ID real via /rest/api/3/field,
# nunca se hardcodea el customfield_XXXXX porque cambia por sitio). Cada lista es
# de candidatos, por si el nombre exacto varia levemente.
STORY_POINTS_FIELD_NAME_CANDIDATES = ["Story point estimate", "Story Points"]
CATEGORIA_DESPERDICIO_FIELD_NAME_CANDIDATES = ["Categoría de desperdicio", "Categoria de desperdicio"]
HORAS_PERSONA_FIELD_NAME_CANDIDATES = ["Horas-persona desperdiciadas", "Horas persona desperdiciadas"]
TIPO_BLOQUEO_FIELD_NAME_CANDIDATES = ["Tipo de Bloqueo", "Tipo de bloqueo"]


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


def discover_field_id(candidates: list[str], label: str) -> str | None:
    """Resuelve el customfield_XXXXX real para un campo, buscandolo por nombre
    visible entre `candidates` (case-insensitive). Devuelve None si no se
    encuentra -- el llamador debe manejar ese caso explicitamente (dejar el dato
    como "sin registrar"/"sin estimar", nunca asumir 0 o interpolar)."""
    fields = jira_get("/rest/api/3/field")
    for candidate in candidates:
        for field in fields:
            if field.get("name", "").strip().lower() == candidate.lower():
                return field["id"]
    print(
        f"AVISO: no se encontro un campo '{label}' con los nombres esperados "
        f"{candidates} en este sitio de Jira. Las columnas correspondientes "
        f"quedaran sin dato ('sin registrar'/'sin estimar').",
        file=sys.stderr,
    )
    return None


def _adf_to_plain_text(adf) -> str:
    """Extrae texto plano de un campo en formato Atlassian Document Format (ADF),
    tal como lo devuelve la API v3 de Jira para 'description' y otros campos de
    texto enriquecido. No interpreta formato (negrita, listas, etc.), solo
    concatena los nodos de texto en orden. Devuelve "" si el campo viene
    vacio/None -- nunca inventa contenido."""
    if not adf:
        return ""
    if isinstance(adf, str):
        return adf
    parts: list[str] = []

    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text" and "text" in node:
                parts.append(node["text"])
            for child in node.get("content", []) or []:
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(adf)
    return " ".join(parts).strip()


def _field_display_value(value):
    """Representacion de texto legible para un valor de campo de Jira, sin asumir
    su tipo: campos de seleccion/radio llegan como dict ({'value': ...} o
    {'name': ...}); texto plano llega como str; numero llega como int/float; una
    seleccion multiple llega como list. Devuelve None si el valor es None (no lo
    convierte en "" ni en 0)."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("value") or value.get("name") or json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "; ".join(str(_field_display_value(v)) for v in value if v is not None)
    return value


def _resumen_enlaces_bloqueo(issue: dict) -> str:
    """Describe, a partir del campo ESTANDAR de Jira 'issuelinks' (disponible en
    cualquier issue, no solo en 'Impediment / Bloqueo'), cualquier enlace que
    tenga el issue, en cualquier direccion y con cualquier nombre de tipo de
    enlace configurado en el proyecto -- no asume un tipo fijo como "Blocks",
    porque el equipo puede haber configurado uno con otro nombre.

    CONFIRMADO CON EL EQUIPO (19-sep-2026): hoy los issues tipo
    'Impediment / Bloqueo' NO se enlazan a la tarea que bloquearon. Por eso esta
    funcion devolvera casi siempre el mensaje de "sin enlace" en el corte actual.
    Se deja implementada (no se omite ni se hardcodea un texto fijo) para que, el
    dia que el equipo empiece a enlazar impedimentos a tareas -- con cualquier
    tipo de enlace -- el script capture esa relacion automaticamente, sin
    necesitar otro cambio de codigo.
    """
    links = issue.get("fields", {}).get("issuelinks") or []
    descripciones = []
    for link in links:
        link_type = link.get("type", {})
        if "outwardIssue" in link:
            otro = link["outwardIssue"]["key"]
            verbo = link_type.get("outward") or link_type.get("name") or "enlazado con"
        elif "inwardIssue" in link:
            otro = link["inwardIssue"]["key"]
            verbo = link_type.get("inward") or link_type.get("name") or "enlazado con"
        else:
            continue
        descripciones.append(f"{verbo} {otro}")
    if descripciones:
        return "; ".join(descripciones)
    return (
        "sin enlace registrado en Jira — el tipo de issue 'Impediment / Bloqueo' "
        "no se vincula actualmente a la tarea afectada (confirmado con el equipo, "
        "corte 19-sep-2026)"
    )


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


def get_sprint_issues(
    sprint_id: int,
    sp_field_id: str | None,
    categoria_desperdicio_field_id: str | None,
    horas_persona_field_id: str | None,
    tipo_bloqueo_field_id: str | None,
) -> list[dict]:
    fields = ["summary", "issuetype", "status", "created", "description", "issuelinks"]
    for fid in (sp_field_id, categoria_desperdicio_field_id, horas_persona_field_id, tipo_bloqueo_field_id):
        if fid:
            fields.append(fid)
    issues: list[dict] = []
    start_at = 0
    jql = f"project = {PROJECT_KEY} AND sprint = {sprint_id}"
    while True:
        data = jira_get(
            "/rest/api/3/search/jql",
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
            "Excluidos del corte completo (EXCLUDE_KEYS): "
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


def _imprimir_resumen_pendientes(
    sprint: dict,
    out_dir: str,
    n_issues_corte: int,
    n_flow_keys: int,
    n_impedimentos: int,
    horas_persona_total: float,
) -> None:
    """Resumen legible en el log del run de Actions de lo que exige revision
    humana antes de entregar el corte a Prism -- no basta con generar los CSV."""
    print("\n" + "=" * 72)
    print("REVISION HUMANA PENDIENTE ANTES DE ENTREGAR ESTE CORTE A PRISM:")
    print("=" * 72)
    print(f"1. Sprint Goal declarado en Jira: {sprint.get('goal') or '(vacio, confirmar con el equipo)'}")
    print("2. Confirmar EXCLUDE_KEYS vigente (corte completo): " + ", ".join(sorted(EXCLUDE_KEYS)))
    print("3. Confirmar que no hay otra cola (ej. \"En pruebas\" fuera de sprint) que deba declararse.")
    print(f"4. Revisar {out_dir}/Contexto.csv, fila 'revision_manual_pendiente', antes de copiar a informacion/material/.")
    print(
        f"5. Impedimentos.csv: {n_impedimentos} issues tipo '{IMPEDIMENT_ISSUE_TYPE_NAME}' en el corte "
        f"(suma de horas-persona desperdiciadas registradas: {horas_persona_total}). NINGUNO tiene enlace de "
        "Jira a una tarea especifica todavia -> sirve para el total de desperdicio, NO para saber que tarea "
        "se demoro por cada impedimento. Si el equipo empieza a enlazarlos, esto se resuelve solo (ver "
        "_resumen_enlaces_bloqueo en el codigo)."
    )
    print(
        f"6. Poblacion de flujo (CFD/Burndown/WIP/Ciclos_terminados): {n_flow_keys} de {n_issues_corte} "
        f"issues del corte, tras excluir FLOW_EXCLUDE_ISSUE_TYPES = {sorted(FLOW_EXCLUDE_ISSUE_TYPES)} "
        f"({n_issues_corte - n_flow_keys} issues tipo '{IMPEDIMENT_ISSUE_TYPE_NAME}' excluidos de estas "
        "cuatro tablas). Decidido con el equipo el 25-sep-2026. Impedimentos.csv y Eventos.csv NO aplican "
        "este filtro -- ahi se conservan completos. Confirmar que FLOW_EXCLUDE_ISSUE_TYPES sigue vigente "
        "en cada corte, igual que EXCLUDE_KEYS."
    )
    print("=" * 72)


def main() -> None:
    sprint = get_sprint(BOARD_ID, SPRINT_ID_OVERRIDE)
    sprint_id = sprint["id"]
    sprint_start = datetime.fromisoformat(sprint["startDate"].replace("Z", "+00:00"))
    today = datetime.now(TZ_OFFSET)

    sp_field_id = discover_field_id(STORY_POINTS_FIELD_NAME_CANDIDATES, "Story Points")
    categoria_desperdicio_field_id = discover_field_id(
        CATEGORIA_DESPERDICIO_FIELD_NAME_CANDIDATES, "Categoría de desperdicio"
    )
    horas_persona_field_id = discover_field_id(
        HORAS_PERSONA_FIELD_NAME_CANDIDATES, "Horas-persona desperdiciadas"
    )
    tipo_bloqueo_field_id = discover_field_id(TIPO_BLOQUEO_FIELD_NAME_CANDIDATES, "Tipo de Bloqueo")

    issues = get_sprint_issues(
        sprint_id, sp_field_id, categoria_desperdicio_field_id, horas_persona_field_id, tipo_bloqueo_field_id
    )
    print(f"Sprint: {sprint['name']} (id {sprint_id}), {len(issues)} issues en el corte.")

    fuente = (
        f"Jira Cloud API ({BASE_URL}), proyecto {PROJECT_KEY}, sprint id {sprint_id}, "
        f"extraido {today.isoformat()}"
    )

    timelines: dict[str, list[dict]] = {}
    story_points: dict[str, float | None] = {}
    created_at: dict[str, datetime] = {}
    tipos: dict[str, str] = {}
    resumenes: dict[str, str] = {}
    descripciones: dict[str, str] = {}
    categorias_desperdicio: dict[str, object] = {}
    horas_persona: dict[str, object] = {}
    tipos_bloqueo: dict[str, object] = {}
    enlaces_bloqueo: dict[str, str] = {}
    for issue in issues:
        key = issue["key"]
        timelines[key] = get_status_changelog(key)
        tipos[key] = issue["fields"]["issuetype"]["name"]
        created_at[key] = datetime.fromisoformat(
            issue["fields"]["created"].replace("Z", "+00:00")
        )
        sp_value = issue["fields"].get(sp_field_id) if sp_field_id else None
        story_points[key] = sp_value
        resumenes[key] = issue["fields"].get("summary") or ""
        descripciones[key] = _adf_to_plain_text(issue["fields"].get("description"))
        categorias_desperdicio[key] = _field_display_value(
            issue["fields"].get(categoria_desperdicio_field_id) if categoria_desperdicio_field_id else None
        )
        horas_persona[key] = _field_display_value(
            issue["fields"].get(horas_persona_field_id) if horas_persona_field_id else None
        )
        tipos_bloqueo[key] = _field_display_value(
            issue["fields"].get(tipo_bloqueo_field_id) if tipo_bloqueo_field_id else None
        )
        enlaces_bloqueo[key] = _resumen_enlaces_bloqueo(issue)

    # Poblacion de flujo: todos los issues del corte MENOS los tipos listados en
    # FLOW_EXCLUDE_ISSUE_TYPES (hoy, "Impediment / Bloqueo"). Se usa para
    # CFD_diario, Burndown_diario, WIP_corte y Ciclos_terminados. Impedimentos.csv
    # y Eventos.csv siguen usando `timelines` completo (todas las keys), sin este
    # filtro -- ver docstring del modulo.
    flow_keys = [k for k in timelines if tipos.get(k) not in FLOW_EXCLUDE_ISSUE_TYPES]
    excluidos_de_flujo = [k for k in timelines if k not in flow_keys]
    if excluidos_de_flujo:
        print(
            "Excluidos de la poblacion de flujo (FLOW_EXCLUDE_ISSUE_TYPES): "
            + ", ".join(sorted(excluidos_de_flujo)),
            file=sys.stderr,
        )

    out_dir = os.path.join(os.getcwd(), f"datos-flujo-cameia-{today.date().isoformat()}")
    out_dir = os.path.normpath(out_dir)

    # --- CFD_diario ---------------------------------------------------
    cfd_rows = []
    for day in daterange(sprint_start, today):
        cutoff = datetime.combine(day, datetime.max.time(), tzinfo=TZ_OFFSET)
        counts = {s: 0 for s in STATE_ORDER}
        for key in flow_keys:
            counts[state_at(timelines[key], cutoff)] += 1
        cfd_rows.append(
            [day.isoformat()] + [counts[s] for s in STATE_ORDER]
            + [len(flow_keys), fuente, "observado"]
        )
    write_csv(
        os.path.join(out_dir, "CFD_diario.csv"),
        ["fecha_corte"] + [s.lower().replace(" ", "_") for s in STATE_ORDER]
        + ["total", "fuente", "calidad_dato"],
        cfd_rows,
    )

    # --- Burndown_diario ------------------------------------------------
    estimated_keys = [k for k in flow_keys if story_points.get(k) is not None]
    unestimated_keys = [k for k in flow_keys if k not in estimated_keys]
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
    # NOTA (corregido 19-sep-2026): la columna "bloqueo" ya NO escribe un texto
    # fijo ("pendiente de registrar"). Se llena con lo que devuelva
    # _resumen_enlaces_bloqueo(issue), es decir, con los issuelinks REALES del
    # item. Hoy eso sera casi siempre el mensaje de "sin enlace registrado",
    # porque el equipo confirmo que los impedimentos no se enlazan todavia a la
    # tarea afectada -- pero ya no es un placeholder, es lo que Jira devuelve.
    # NOTA (corregido 25-sep-2026): itera sobre `flow_keys`, no sobre todo
    # `timelines` -- los issues tipo Impediment/Bloqueo ya no cuentan aqui (ver
    # FLOW_EXCLUDE_ISSUE_TYPES).
    wip_rows = []
    for key in flow_keys:
        events = timelines[key]
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
                enlaces_bloqueo[key],
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
    # A proposito, esta bitacora cruda NO aplica FLOW_EXCLUDE_ISSUE_TYPES: incluye
    # tambien las transiciones de estado de los issues tipo Impediment/Bloqueo,
    # para no perder trazabilidad de ningun evento real ocurrido en el sprint.
    # El filtro de poblacion de flujo solo aplica a las tablas agregadas
    # (CFD/Burndown/WIP/Ciclos_terminados), no a este registro completo.
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
    # NOTA (corregido 25-sep-2026): itera sobre `flow_keys`, no sobre todo
    # `timelines` -- consistente con WIP_corte, para que la mitad "abierta" y la
    # mitad "terminada" de la poblacion de flujo usen el mismo criterio.
    ciclos_rows = []
    for key in flow_keys:
        events = timelines[key]
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

    # --- Impedimentos (NUEVO 19-sep-2026) ----------------------------------
    # Un issue por impedimento, tal como los modela el equipo (issue type propio,
    # no un campo de la tarea afectada). "enlace_a_item_bloqueado" usa la MISMA
    # funcion que WIP_corte.bloqueo (_resumen_enlaces_bloqueo): hoy devolvera casi
    # siempre "sin enlace registrado", porque no hay issue link configurado entre
    # el impedimento y la tarea. No se inventa esa relacion.
    # A proposito, esta tabla NO aplica FLOW_EXCLUDE_ISSUE_TYPES (itera sobre todo
    # `timelines`, no sobre `flow_keys`): es precisamente donde SI deben quedar
    # capturados enteros los issues tipo Impediment/Bloqueo que la poblacion de
    # flujo excluye en las otras cuatro tablas.
    impedimento_keys = [k for k in timelines if tipos.get(k) == IMPEDIMENT_ISSUE_TYPE_NAME]
    impedimento_rows = []
    horas_persona_total = 0.0
    for key in impedimento_keys:
        horas_val = horas_persona.get(key)
        try:
            horas_num = float(horas_val)
            horas_persona_total += horas_num
        except (TypeError, ValueError):
            horas_num = horas_val  # se deja tal cual (p. ej. None o texto) si no es numerico
        impedimento_rows.append(
            [
                key,
                resumenes.get(key, ""),
                categorias_desperdicio.get(key) if categorias_desperdicio.get(key) is not None else "sin registrar",
                horas_num if horas_num is not None else "sin registrar",
                tipos_bloqueo.get(key) if tipos_bloqueo.get(key) is not None else "sin registrar",
                descripciones.get(key, ""),
                state_at(timelines[key], today),
                created_at[key].date().isoformat(),
                enlaces_bloqueo[key],
                fuente,
                "observado",
            ]
        )
    write_csv(
        os.path.join(out_dir, "Impedimentos.csv"),
        [
            "id_elemento", "resumen", "categoria_desperdicio", "horas_persona_desperdiciadas",
            "tipo_bloqueo", "descripcion", "estado_actual", "creado",
            "enlace_a_item_bloqueado", "fuente", "calidad_dato",
        ],
        impedimento_rows,
    )
    print(
        f"Impedimentos: n={len(impedimento_rows)} issues tipo '{IMPEDIMENT_ISSUE_TYPE_NAME}'. "
        f"Horas-persona desperdiciadas (suma de los valores numericos registrados): {horas_persona_total}. "
        "Ninguno enlazado a una tarea especifica (ver columna enlace_a_item_bloqueado). Excluidos de la "
        "poblacion de flujo (CFD/Burndown/WIP/Ciclos_terminados), conservados enteros aqui."
    )

    # --- Contexto (parcial, requiere revision humana) -----------------
    contexto_rows = [
        ["identificador_del_corte", f"CAMEIA-{PROJECT_KEY}-{sprint['name']}-{today.date().isoformat()}"],
        ["fecha_extraccion", today.isoformat()],
        ["proyecto", f'Jira "{PROJECT_KEY}"'],
        ["tablero", f"board id {BOARD_ID}"],
        ["sprint", f"{sprint['name']} (id {sprint_id}), inicio {sprint['startDate']}, fin previsto {sprint.get('endDate', 'desconocido')}, goal: {sprint.get('goal') or 'no definido'}"],
        [
            "poblacion",
            f"{len(issues)} issues en el corte, excluidos del corte completo (EXCLUDE_KEYS): "
            f"{', '.join(sorted(EXCLUDE_KEYS)) or 'ninguno'}. De esos {len(issues)}, la poblacion de flujo "
            f"(CFD/Burndown/WIP/Ciclos_terminados) es {len(flow_keys)}, tras excluir "
            f"{len(issues) - len(flow_keys)} issues tipo '{IMPEDIMENT_ISSUE_TYPE_NAME}' "
            "(FLOW_EXCLUDE_ISSUE_TYPES, decidido con el equipo el 25-sep-2026). Esos mismos issues se "
            "conservan enteros en Impedimentos.csv y Eventos.csv.",
        ],
        [
            "revision_manual_pendiente",
            "Confirmar poblaciones excluidas (ej. colas fuera de sprint), fecha de entrega académica, "
            "calidad_dato de cada tabla, y que EXCLUDE_KEYS y FLOW_EXCLUDE_ISSUE_TYPES sigan vigentes "
            "para este corte, antes de entregar a Prism.",
        ],
    ]
    write_csv(os.path.join(out_dir, "Contexto.csv"), ["campo", "valor"], contexto_rows)

    _imprimir_resumen_pendientes(
        sprint, out_dir, len(issues), len(flow_keys), len(impedimento_rows), horas_persona_total
    )
    print(f"\nListo. Revisar {out_dir} antes de copiarlo a informacion/material/ y entregarlo a Prism.")


if __name__ == "__main__":
    main()