# Contribución a CAMEIA

## Flujo de trabajo

1. Crear desde `develop` una rama `CM-<numero>-<descripcion-kebab-case>`.
2. Usar una clave Jira real y mantenerla igual en la rama, el título y el enlace del Pull Request.
3. Abrir el Pull Request `CM-* → develop` y utilizar Squash and merge.
4. Promover únicamente mediante un Pull Request `develop → main` y utilizar Merge commit.
5. Nunca abrir un Pull Request `CM-* → main` ni eliminar `develop` después de una promoción.
6. Eliminar la rama `CM-*` después de integrarla.
7. Solicitar revisión a una persona distinta del autor. `develop` utiliza temporalmente cero
   aprobaciones obligatorias; `main` mantiene una.
8. Resolver conversaciones y controles requeridos antes de integrar.

No usar `<tipo>/CM-NNN-<descripcion>`, ni prefijos de rama `feature/`, `fix/` o `chore/`. El tipo
pertenece al título del PR y al mensaje de commit, no al nombre de la rama.

No hacer push directo, force-push ni eliminar `main` o `develop`. Ningún team, cuenta
administrativa o rol DEV tiene bypass operativo: incluso una reparación de CI entra por rama
`CM-*` y PR. Una emergencia fuera del flujo requiere una decisión humana explícita, no una
excepción permanente.

La política de cero aprobaciones formales en `develop` no elimina la revisión por pares. Comprobar
las Reviews y conversaciones reales; no sustituirlas por una casilla del autor. En promoción,
verificar también que el origen sea `develop`; la revisión es manual mientras no exista un check
automático estable que la valide.

## Nombres de PR y commits

- PR ordinario: `CM-NNN | tipo(scope): resultado`.
- Promoción: `release: promover <version> de develop a main`.
- Tipos admitidos: `feat`, `fix`, `test`, `docs`, `refactor`, `build`, `ci` y `chore`.
- Los commits describen cambios coherentes; se recomienda Conventional Commits y no es obligatorio
  incluir `CM-NNN` ni la clave Jira en cada commit.

Ejemplo de formato, no una tarea o PR existente:

```text
Rama: CM-123-documentar-configuracion
PR: CM-123 | docs(web): documentar configuracion
Commit: docs(web): documentar configuracion
```

El cuerpo de una promoción identifica tareas incluidas, versión/artefacto, validación, riesgos y
recuperación. Integrar en Git no demuestra una publicación ni aceptación funcional.

## Evidencia y revisión del cambio

- Usar la plantilla de PR adoptada en el repositorio; una propuesta de plantilla o validador no se
  vuelve obligatoria por aparecer en documentación.
- Explicar el cambio y el criterio esperado; enlazar controles ejecutados y resultados sobre un SHA
  identificado. Separar `PASA`, `FALLA`, `BLOQUEADO` y `PENDIENTE`, sin presentar resultados de
  otro SHA como propios.
- Si el cambio afecta un atributo de calidad, identificar criterio/fuente, resultado observado y
  evidencia; incluir método, condiciones y muestra o denominador cuando corresponda en el registro
  enlazado, sin duplicar el informe.
- No deducir cobertura de la cantidad de pruebas. Para la entrega P2 Sprint 1, la fuente académica
  exige cobertura superior al 70 %; un PR aislado no acredita el conjunto de requisitos académicos.
- Resolver los controles requeridos antes de integrar. La activación de checks obligatorios
  requiere validación positiva y negativa; su ausencia no convierte un requisito académico en
  opcional.
- Justificar los controles no aplicables y someterlos a revisión según el acuerdo vigente; no usar
  No aplica para omitir controles obligatorios. Aplicar evidencia proporcional a documentación,
  código o configuración.
- La confirmación del autor, la revisión independiente y la aceptación funcional del PO son
  actuaciones diferentes. Identificar por separado el trabajo DEV y TST; no dar por adoptada una
  propuesta DoD.

## Uso de IA

- Para código asistido incluido en el PR, utilizar la marca exacta `[IA-ASISTIDO]` exigida por la
  plantilla P2, con herramienta y validación real. Respetar la ubicación que acuerde el equipo; no
  reemplazarla por `[IA]`.
- Identificar el alcance: código, pruebas, configuración ejecutable, documentación o solo redacción
  del PR. Si solo se asistió la redacción, declararlo sin atribuir por ello el código a IA.
- Enlazar una bitácora saneada: fecha, herramienta, petición/prompt relevante, resultado, qué se
  aceptó, corrigió o rechazó y por qué, y responsable de la comprobación. No inventar rechazos ni
  validaciones.
- Mantener la revisión humana pendiente hasta que ocurra. La IA no confirma aprobación, ejecución
  de controles ni aceptación de producto.

## Documentación y seguridad

- Actualizar `README.md` cuando cambien alcance, stack, comandos, variables, contratos, pruebas o
  despliegue.
- Actualizar `.env.example` cuando cambien variables, solo con ejemplos no sensibles. Desarrollo
  define las variables consumidas por cada componente; DEV revisa el mecanismo de suministro y sus
  permisos, sin inventar contratos o valores.
- No versionar secretos, credenciales, archivos `.env` reales, datos personales ni evidencia sin
  sanear. No incluirlos tampoco en mensajes de PR, bitácoras, logs o artefactos.
- `.gitignore` no elimina del historial archivos ya versionados ni reemplaza una revisión de
  secretos. Ante una exposición, comunicarla y coordinar revocación/rotación y tratamiento del
  historial; no ocultarla añadiendo un patrón.
- Conservar lockfiles y wrappers del build que utilice el proyecto; revisar procedencia e
  integridad de sus cambios. No sustituir archivos existentes ni renormalizar todo el repositorio
  por copiar estas bases.
- No afirmar como implementada una capacidad que todavía esté pendiente.
