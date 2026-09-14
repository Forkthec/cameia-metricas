# cameia-metricas

Mecanismo real (con evidencia, no solo a mano) para extraer de Jira Cloud los datos de flujo que
alimentan las 4 gráficas ágiles que pide el profesor de CAMEIA: Velocity Chart, Diagrama de Flujo
Acumulado (CFD), Kanban Aging WIP y Kanban Waste Snake.

> **Estado:** repositorio nuevo (CM-151). Migra y mejora el script que ya se usó a mano el
> 11-sep-2026 (`informacion/material/scripts/extraer_datos_flujo.py`, workspace `cameia`), que sigue
> ahí como referencia histórica y no se borra.

## Qué hace y qué no hace

- **Sí** extrae, con la API real de Jira Cloud, los issues del sprint (JQL) y su changelog completo
  (transiciones de estado), y calcula CFD diario, Burndown diario, Aging WIP, el registro crudo de
  eventos y los ciclos ya terminados. Nunca inventa ni interpola un dato: lo que no se puede obtener
  queda explícitamente vacío o "pendiente".
- **No** genera Velocity Chart como serie independiente (se deriva de Burndown + histórico de
  sprints cerrados, fuera del alcance de este script) ni Waste Snake (sin fuente real en Jira hasta
  que exista el impediment backlog pedido a Juan José — ver `comunicaciones/11092026_scrum-texto_propuesta-metricas-agiles-reales.md`
  en el workspace `cameia`).
- **No** corre en cron ni de forma desatendida. El disparo es manual
  (`workflow_dispatch`) a propósito: el script necesita revisión humana de varios campos (Sprint
  Goal, exclusiones de población, fecha de entrega académica) que no puede decidir solo. Automatizar
  la corrida no automatiza esa revisión — fingir que sí sería exactamente lo que este repo existe
  para evitar.
- **No** dibuja las gráficas. Eso lo hace Prism a partir de los CSV que este repo produce (ver
  `informacion/material/11092026_v1_analisis-flujo-equipo-p2.tex` en el workspace `cameia`).

## Cómo correrlo

### Localmente

```
set JIRA_BASE_URL=https://tu-dominio.atlassian.net
set JIRA_EMAIL=tu-correo@dominio.com
set JIRA_API_TOKEN=xxxxx
python scripts/extraer_datos_flujo.py
```

El token es personal — se crea en https://id.atlassian.com/manage-profile/security/api-tokens.
Nunca se comparte, nunca se comittea, nunca se pega en un PR/issue/log.

### Desde GitHub Actions (con evidencia real de run)

1. Configurar una vez, en **Settings → Secrets and variables → Actions** de este repo:
   - Variables: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_PROJECT_KEY` (opcional, por defecto `CM`),
     `JIRA_BOARD_ID` (opcional, por defecto `1`).
   - Secret: `JIRA_API_TOKEN`.
2. Disparar el workflow **"Extraer datos de flujo de Jira"** manualmente (pestaña Actions →
   `workflow_dispatch`). Opcionalmente fijar `sprint_id` si no se quiere el sprint activo.
3. Descargar el *artifact* del run (`datos-flujo-cameia-<run_id>`).
4. **Revisar a mano** el `Contexto.csv` del artifact (campo `revision_manual_pendiente`) y el
   resumen que el script imprime al final del log del run.
5. Copiar la carpeta a `informacion/material/` del workspace `cameia` y avisar a Prism.

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `JIRA_BASE_URL` | Sí | URL del sitio Jira Cloud (ej. `https://tu-dominio.atlassian.net`) |
| `JIRA_EMAIL` | Sí | Correo de la cuenta que ejecuta el script |
| `JIRA_API_TOKEN` | Sí | Token personal — nunca hardcodeado ni committeado |
| `JIRA_PROJECT_KEY` | No (`CM` por defecto) | Clave del proyecto Jira |
| `JIRA_BOARD_ID` | No (`1` por defecto) | Id del tablero Scrum de CAMEIA |
| `JIRA_SPRINT_ID` | No (sprint activo por defecto) | Fijar para repetir un corte de un sprint ya cerrado |

## Contribución

- `main` es estable y solo recibe promociones `develop → main` mediante Merge commit.
- `develop` integra ramas `CM-<numero>-<descripcion-kebab-case>` mediante Squash and merge.
- Todo cambio ordinario entra mediante PR y revisión de una persona distinta del autor; la rama
  `CM-*` se elimina después de integrarla. Ver `CONTRIBUTING.md`.

## Cuándo actualizar este README

Actualizarlo en el mismo PR que cambie el alcance del script, las variables de entorno, el
procedimiento de ejecución, o la relación con Prism/el impediment backlog.
