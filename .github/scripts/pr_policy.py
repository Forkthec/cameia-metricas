import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse


TYPES = ("feat", "fix", "test", "docs", "refactor", "build", "ci", "chore")
FIELDS = ("Jira", "Responsable", "Cambio", "Evidencia", "Impacto", "Riesgo", "IA", "Control humano")
MODULES = {"contrato": "Contrato", "datos": "Datos", "permisos": "Permisos", "despliegue": "Despliegue"}
TITLE = re.compile(r"(CM-[1-9][0-9]*) \| (" + "|".join(TYPES) + r")\(([a-z0-9]+(?:-[a-z0-9]+)*)\): (.+)")
BRANCH = re.compile(r"(CM-[1-9][0-9]*)-[a-z0-9]+(?:-[a-z0-9]+)*")
PLACEHOLDER = re.compile(r"<[^>]*>|\b(?:TODO|PEGAR_URL|CM-NNN)\b")


def validate(payload):
    errors = []
    category = None
    scope = None
    issue_keys = []
    required = ("title", "head", "base", "body")
    if not isinstance(payload, dict) or any(not isinstance(payload.get(field), str) for field in required):
        return {"schema": 1, "result": "FALLA_ESTRUCTURA", "errors": ["entrada: faltan cadenas title/head/base/body"]}
    if any(type(payload.get(field)) is not bool for field in ("draft", "same_repository")):
        return {"schema": 1, "result": "FALLA_ESTRUCTURA", "errors": ["entrada: draft y same_repository deben ser booleanos"]}
    if len(payload["body"]) > 65536 or len(payload["title"]) > 512:
        return {"schema": 1, "result": "FALLA_ESTRUCTURA", "errors": ["entrada: longitud excedida"]}
    assisted = payload["title"].endswith(" [IA-ASISTIDO]")
    title = payload["title"].removesuffix(" [IA-ASISTIDO]")
    promotion = payload["base"] == "main"
    if PLACEHOLDER.search(title):
        errors.append("titulo: reemplazar marcadores de ejemplo")
    if promotion:
        if payload["head"] != "develop" or not payload["same_repository"]:
            errors.append("rama: main solo recibe develop del mismo repositorio")
        if not re.fullmatch(r"release: promover \S+ de develop a main", title):
            errors.append("titulo: se requiere release: promover VERSION de develop a main")
        category = "release"
    else:
        branch_match = BRANCH.fullmatch(payload["head"])
        title_match = TITLE.fullmatch(title)
        if payload["base"] != "develop" or not branch_match:
            errors.append("rama: se requiere CM-numero-descripcion hacia develop")
        if not title_match:
            errors.append("titulo: usar CM-NNN | tipo(scope): resultado; tipo permitido, no testing")
        else:
            issue_keys = [title_match[1]]
            category, scope = title_match[2], title_match[3]
            if not title_match[4].strip():
                errors.append("titulo: falta resultado")
            if branch_match and branch_match[1] != title_match[1]:
                errors.append("jira: clave de rama y titulo distinta")
    body = re.sub(r"<!--.*?-->", "", payload["body"], flags=re.S)
    fields = {}
    for match in re.finditer(r"^- ([^:\n]+):[ \t]*(.*)$", body, re.M):
        label, value = match[1], match[2].strip()
        if label in fields:
            errors.append("campo duplicado: " + label)
        fields[label] = value
    for field in FIELDS + (("Promoción",) if promotion else ()):
        if not fields.get(field) or PLACEHOLDER.search(fields[field]):
            errors.append("campo incompleto: " + field)
    jira = fields.get("Jira", "")
    linked_keys = []
    for address in re.findall(r"https://[^\s<>\)]+", jira):
        parsed = urlparse(address)
        issue_match = re.fullmatch(r"/browse/(CM-[1-9][0-9]*)/?", parsed.path)
        if parsed.hostname and not parsed.username and not parsed.password and issue_match:
            linked_keys.append(issue_match[1])
    if not linked_keys or (issue_keys and issue_keys[0] not in linked_keys):
        errors.append("jira: falta enlace https /browse/CM-numero coherente; no se consulta Jira")
    if promotion:
        issue_keys = sorted(set(linked_keys))
    identity = fields.get("Responsable", "").split("|")
    if len(identity) != 2 or not all(part.strip() for part in identity):
        errors.append("responsable: usar nombre completo | rol; identidad no verificada")
    if not re.search(r"\b(PASA|FALLA|BLOQUEADO|PENDIENTE)\b", fields.get("Evidencia", "")):
        errors.append("evidencia: declarar resultado, sin inventarlo")
    impacts = [part.strip() for part in fields.get("Impacto", "").split(",")]
    if impacts != ["ninguno"]:
        if not impacts or any(impact not in MODULES for impact in impacts):
            errors.append("impacto: elegir ninguno o contrato, datos, permisos, despliegue")
        for impact in set(impacts) & MODULES.keys():
            field = MODULES[impact]
            if not fields.get(field) or PLACEHOLDER.search(fields[field]):
                errors.append("modulo requerido: " + field)
    if not re.fullmatch(r"(bajo|medio|alto) — \S.*", fields.get("Riesgo", "")):
        errors.append("riesgo: usar bajo/medio/alto — explicacion y recuperacion")
    ai_match = re.fullmatch(r"(si|no) — \S.*", fields.get("IA", ""))
    if not ai_match:
        errors.append("ia: usar si/no — alcance y registro real")
    elif (ai_match[1] == "si") != assisted:
        errors.append("ia: titulo y declaracion deben coincidir con [IA-ASISTIDO]")
    human_pattern = r"(pendiente|revisado por el autor) — \S.*" if payload["draft"] else r"revisado por el autor — \S.*"
    if not re.fullmatch(human_pattern, fields.get("Control humano", "")):
        errors.append("control humano: usar 'revisado por el autor — ...' antes de salir de Draft, o mantener 'pendiente' en Draft")
    return {
        "schema": 1,
        "result": "BORRADOR" if payload["draft"] else ("FALLA_ESTRUCTURA" if errors else "PASA_ESTRUCTURA"),
        "errors": errors,
        "type": category,
        "scope": scope,
        "issue_keys": issue_keys,
        "assisted": assisted,
        "draft": payload["draft"],
    }


def main():
    parser = argparse.ArgumentParser(description="Piloto CAMEIA: estructura local, no autorizacion de merge")
    parser.add_argument("input", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.input.stat().st_size > 131072:
            raise ValueError("entrada demasiado grande")
        report = validate(json.loads(arguments.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError):
        report = {"schema": 1, "result": "FALLA_ESTRUCTURA", "errors": ["entrada: archivo JSON ausente, invalido o demasiado grande"]}
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["result"] == "PASA_ESTRUCTURA" else (2 if report["result"] == "BORRADOR" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
