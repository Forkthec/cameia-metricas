"""Pruebas del validador de PR (CM-123). Ejecutar: python3 .github/scripts/test_pr_policy.py

Cubre 14 casos negativos (cada regla del validador debe rechazar su caso malo) mas la
regresion encontrada el 11-sep-2026: con draft=true, 'result' siempre da 'BORRADOR' aunque
'errors' tenga hallazgos reales. El workflow que consume este script debe revisar 'errors',
no solo 'result' (ver validar-plantilla-pr.yml).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pr_policy import validate  # noqa: E402


BASE = {
    "title": "CM-500 | docs(web): caso base valido",
    "head": "CM-500-caso-base-valido",
    "base": "develop",
    "body": (
        "## Cambio\n"
        "- Jira: https://f0rktech.atlassian.net/browse/CM-500\n"
        "- Responsable: Paula Andrea Munoz Delgado | DevOps\n"
        "- Cambio: caso base para pruebas negativas.\n\n"
        "## Evidencia\n"
        "- Evidencia: PASA - revision manual\n\n"
        "## Riesgo\n"
        "- Impacto: ninguno\n"
        "- Riesgo: bajo — sin impacto real\n\n"
        "## IA y responsabilidad\n"
        "- IA: no — caso de prueba manual\n"
        "- Control humano: pendiente — Paula Andrea Munoz Delgado\n"
    ),
    "draft": True,
    "same_repository": True,
}


def case(name, expect_error_substr, mutate, draft=True):
    payload = json.loads(json.dumps(BASE))
    payload["draft"] = draft
    mutate(payload)
    return name, expect_error_substr, payload


CASES = [
    case("N1 rama con formato invalido", "rama:",
         lambda p: p.__setitem__("head", "mi-rama-sin-formato")),
    case("N2 titulo sin formato tipo(scope)", "titulo:",
         lambda p: p.__setitem__("title", "CM-500 arreglar cosas sin formato")),
    case("N3 titulo con placeholder CM-NNN", "titulo:",
         lambda p: p.__setitem__("title", "CM-NNN | docs(web): resultado")),
    case("N4 falta el campo Riesgo completo", "campo incompleto: Riesgo",
         lambda p: p.__setitem__("body", p["body"].replace(
             "## Riesgo\n- Impacto: ninguno\n- Riesgo: bajo — sin impacto real\n\n", ""))),
    case("N5 Jira sin enlace https valido", "jira:",
         lambda p: p.__setitem__("body", p["body"].replace(
             "https://f0rktech.atlassian.net/browse/CM-500", "CM-500 (sin enlace)"))),
    case("N6 Evidencia sin PASA/FALLA/BLOQUEADO/PENDIENTE", "evidencia:",
         lambda p: p.__setitem__("body", p["body"].replace(
             "- Evidencia: PASA - revision manual", "- Evidencia: se reviso manualmente todo bien"))),
    case("N7 Impacto con valor invalido", "impacto:",
         lambda p: p.__setitem__("body", p["body"].replace("- Impacto: ninguno", "- Impacto: quizas algo"))),
    case("N8 Impacto=contrato sin el campo Contrato", "modulo requerido: Contrato",
         lambda p: p.__setitem__("body", p["body"].replace("- Impacto: ninguno", "- Impacto: contrato"))),
    case("N9 Riesgo sin nivel bajo/medio/alto", "riesgo:",
         lambda p: p.__setitem__("body", p["body"].replace(
             "- Riesgo: bajo — sin impacto real", "- Riesgo: no se muy bien"))),
    case("N10 IA=si pero titulo sin [IA-ASISTIDO]", "ia:",
         lambda p: p.__setitem__("body", p["body"].replace(
             "- IA: no — caso de prueba manual", "- IA: si — uso real de IA"))),
    case("N11 Control humano con palabra vieja 'confirmado' (PR NO borrador)", "control humano:",
         lambda p: p.__setitem__("body", p["body"].replace(
             "- Control humano: pendiente — Paula Andrea Munoz Delgado",
             "- Control humano: confirmado — Paula Andrea Munoz Delgado")),
         draft=False),
    case("N12 promocion develop->main con head distinto de develop", "rama:",
         lambda p: (p.__setitem__("base", "main"),
                    p.__setitem__("title", "release: promover v0.1 de develop a main"),
                    p.__setitem__("head", "CM-500-caso-base-valido"))),
    case("N13 campo duplicado (Riesgo dos veces)", "campo duplicado",
         lambda p: p.__setitem__("body", p["body"] + "- Riesgo: alto — duplicado a proposito\n")),
]


def main():
    failures = []

    for name, expect, payload in CASES:
        out = validate(payload)
        errors = out.get("errors", [])
        if not any(expect in e for e in errors):
            failures.append(f"{name}: se esperaba un error con '{expect}', se obtuvo {errors}")

    # Control: caso base sin mutar debe quedar sin errores
    base_out = validate(BASE)
    if base_out["errors"]:
        failures.append(f"Caso base sin mutar no deberia tener errores: {base_out['errors']}")

    # Regresion CM-123: un PR Draft con un campo invalido debe seguir reportando el error
    # en 'errors' aunque 'result' diga BORRADOR (asi lo consume el workflow: por longitud de errors).
    broken_draft = json.loads(json.dumps(BASE))
    broken_draft["body"] = broken_draft["body"].replace("- Impacto: ninguno", "- Impacto: quizas algo")
    out = validate(broken_draft)
    if out["result"] != "BORRADOR" or not out["errors"]:
        failures.append(
            f"Regresion CM-123: se esperaba result=BORRADOR con errors no vacios, se obtuvo {out}")

    print(f"Casos ejecutados: {len(CASES) + 2} (incluye control y regresion CM-123)")
    if failures:
        print(f"FALLARON {len(failures)}:")
        for f in failures:
            print(" -", f)
        return 1
    print("Todos los casos pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
