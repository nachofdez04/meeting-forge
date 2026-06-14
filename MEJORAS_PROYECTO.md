# Mejoras del Proyecto MeetingForge

> **⚠️ Documento superado — sustituido por [`planes/`](planes/).** Este análisis es **anterior a la
> "Fase 5: Mejoras"**. Sus prioridades P0 (corregir `ruff`, `mypy`, el test flaky, añadir CI/pre-commit y
> alinear README↔estado) **ya están resueltas y verificadas** (`ruff` y `mypy --strict` limpios, 189 tests en
> verde). La **fuente de verdad actual** son los planes en [`planes/`](planes/):
> [`00-orquestador.md`](planes/00-orquestador.md), [`01-bugs-y-deuda-tecnica.md`](planes/01-bugs-y-deuda-tecnica.md)
> y [`02-features.md`](planes/02-features.md). Este fichero se conserva por contexto histórico.

## Resumen del análisis

Este documento resume el análisis de `propuesta_tfm.pdf` y del estado actual del repositorio. La propuesta del TFM plantea una aplicación de IA generativa capaz de transformar reuniones técnicas en conocimiento estructurado y documentación versionada. El sistema esperado incluye transcripción automática, análisis semántico con LLMs, RAG sobre documentación Markdown en Git, generación de actas, documentación técnica, roadmap y ADRs, validación humana y evaluación mediante métricas.

El proyecto actual ya cubre una parte muy relevante de esa visión:

- Pipeline de audio a transcripción con Whisper.
- Extracción de decisiones, tareas, temas y resumen mediante LLM.
- RAG sobre documentación Markdown con ChromaDB y `sentence-transformers`.
- Generación de ADRs y actas con citas a fuentes documentales.
- UI Streamlit para visualizar resultados, evidencias y documentos.
- Validación humana de documentos generados.
- Publicación en un repositorio Git destino y creación de PR mediante `gh`.

Estado técnico observado:

- `pytest`: 189 tests pasan y 2 tests de integración están saltados por depender de audio, modelos, API keys o descargas externas.
- `ruff check .`: falla con 27 avisos, principalmente imports no usados, uso de `Enum` modernizable, `datetime.UTC`, orden de imports y reglas `B008` en Typer.
- `mypy src`: falla con 10 errores, especialmente en tipos de clientes Anthropic/OpenAI, ChromaDB, configuración, transcripción y creación de `MeetingMetadata` en la UI.
- Coverage: alrededor del 70% en la ejecución con cobertura.
- La ejecución con coverage destapó un test flaky en `ui.loader`: `test_sorted_most_recent_first`, relacionado con ordenación por `mtime` en Windows.

## Mejoras sobre lo existente

### Prioridad P0: estabilizar calidad y coherencia del proyecto

1. Corregir `ruff check .`

   Resolver los 27 avisos actuales para que el lint vuelva a ser una señal fiable. En concreto:

   - Eliminar imports no usados en módulos de generación, validación, publicación y tests.
   - Sustituir `str, Enum` por `StrEnum` si se mantiene Python 3.11+.
   - Usar `datetime.UTC` en lugar de `timezone.utc`.
   - Ordenar imports con las reglas de Ruff.
   - Revisar la regla `B008` en comandos Typer. Si se decide mantener el patrón habitual de Typer, documentar una excepción explícita en la configuración de Ruff.

2. Corregir `mypy src`

   Resolver los 10 errores actuales para que el modo estricto declarado en `pyproject.toml` sea real. Puntos concretos:

   - Tipar correctamente las llamadas a Anthropic y OpenAI o aislarlas detrás de adaptadores con tipos propios.
   - Ajustar tipos de embeddings enviados a ChromaDB.
   - Evitar retornos `Any` en `Settings._parse_generation_modes`.
   - Revisar la creación de `TranscriptSegment` en el transcriptor frente al campo `speaker`.
   - Completar los campos requeridos de `MeetingMetadata` en la UI o ajustar el modelo si realmente son opcionales.

3. Arreglar el test flaky de `list_meetings`

   El test `test_sorted_most_recent_first` puede fallar porque dos ficheros quedan con el mismo `mtime` o resolución temporal insuficiente. Conviene:

   - Hacer la ordenación determinista con un segundo criterio, por ejemplo `(mtime, meeting_id)`.
   - En el test, fijar timestamps explícitos con `os.utime` en lugar de depender de `touch`.
   - Mantener la intención de producto: mostrar primero las reuniones procesadas más recientemente.

4. Corregir el bug de publicación desde UI

   En `src/meeting_forge/ui/app.py`, la publicación construye `MeetingMetadata` solo con `meeting_id` y `title`, mientras `mypy` detecta que faltan `date` y `source_audio`. Aunque el modelo define defaults, la señal de tipos indica que conviene revisar la compatibilidad real entre Pydantic, mypy y el contrato de generación/publicación.

5. Alinear README y ARCHITECTURE con el estado real

   El README indica "Estado: Fase 3" y marca Fase 4 como pendiente, pero el repo ya contiene módulos, tests y UI de validación/publicación Git. Hay que actualizar:

   - Estado global del proyecto.
   - Roadmap completado/pendiente.
   - Instrucciones de uso de validación y publicación.
   - Requisitos de `gh`, repo destino y variables `GIT_*`.

6. Revisar `validation.json` en la raíz

   Existe un `validation.json` versionado en la raíz, mientras la arquitectura dice que el estado de validación vive bajo `data/outputs/<meeting>/validation.json`. Conviene decidir si:

   - Es un fixture y debe moverse a `tests/fixtures`.
   - Es un artefacto accidental y debe eliminarse del control de versiones.
   - Es documentación de ejemplo y debe renombrarse de forma explícita.

7. Añadir CI y pre-commit reales

   README menciona pre-commit, pero no se observó `.pre-commit-config.yaml`. También falta `.github/workflows`. Recomendación:

   - Añadir workflow de CI con `ruff check`, `mypy src` y `pytest`.
   - Añadir `.pre-commit-config.yaml` con Ruff y, si procede, mypy.
   - Decidir si `uv.lock` debe versionarse. Actualmente existe en disco pero `.gitignore` lo ignora; para una aplicación reproducible de TFM sería preferible versionarlo.

### Prioridad P1: robustecer el pipeline funcional

8. Robustecer proveedores LLM

   El cliente LLM funciona como abstracción, pero necesita endurecimiento para uso real:

   - Validar API keys al iniciar proveedor y dar errores accionables.
   - Añadir retries con backoff para rate limits y errores temporales.
   - Registrar modelo, tokens, latencia y coste estimado por llamada.
   - Mejorar parseo de JSON con errores más claros y posible reparación controlada.
   - Evaluar structured outputs más estrictos donde el proveedor lo permita.

9. Completar proveedor Ollama

   `ollama` aparece en `.env.example`, `Settings` y documentación, pero en `llm_client.py` sigue como TODO. Hay que implementarlo o retirarlo temporalmente de la configuración pública para no prometer una capacidad inexistente.

10. Mejorar RAG y trazabilidad documental

   El RAG ya está implementado, pero puede hacerse más fiable:

   - Limpiar chunks obsoletos cuando se borran o renombran documentos.
   - Guardar junto al resultado los textos exactos de evidencia usados, no solo `SourceRef`, para que la UI no dependa de que el archivo fuente siga igual.
   - Añadir métricas de retrieval como `precision@k` o `recall@k`.
   - Registrar score, query/window y chunk recuperado para facilitar depuración.
   - Considerar filtros por tipo de documento, carpeta o fecha.

11. Endurecer integración Git

   La publicación Git ya existe, pero conviene proteger casos reales:

   - Evitar path traversal al escribir `rel_path` dentro del repo destino.
   - Detectar repo destino con cambios sin commitear antes de escribir.
   - Manejar commits sin cambios, por ejemplo cuando el contenido aprobado ya existe.
   - Separar comprobación de `gh --version` de comprobación de autenticación real.
   - Permitir salida manual si no se puede crear PR: mostrar comando o URL de compare.

12. Mejorar UI y validación humana

   La UI cubre visualización y validación, pero puede ser más operativa:

   - Añadir tests ligeros de funciones puras y, si es viable, smoke tests de Streamlit.
   - Invalidar caché al modificar validación o publicar.
   - Mostrar diffs entre documento original y edición aprobada.
   - Añadir estados de error más accionables para Git, `gh`, RAG y documentos faltantes.
   - Evitar que el usuario pierda ediciones en reruns de Streamlit.

13. Completar ingesta y audio

   La propuesta del TFM habla de reuniones semanales largas y reales. El módulo de preprocesado aún es un stub. Mejoras recomendadas:

   - Normalización de volumen.
   - Resampleo a 16 kHz cuando sea necesario.
   - Reducción de ruido opcional.
   - Idioma configurable en lugar de fijar `language="es"`.
   - Diarización o identificación básica de hablantes.
   - Fixture de audio pequeño para smoke test local.

## Cosas a añadir

### Evaluación del TFM

La mayor brecha respecto a la propuesta es la evaluación. La carpeta `evaluation/` existe, pero está vacía salvo `.gitkeep`. Para una memoria de TFM sólida habría que añadir:

- Dataset anotado con transcripciones de referencia.
- Métrica WER para calidad de transcripción.
- Ground truth de decisiones y tareas para medir precision/recall/F1.
- Dataset de queries o reuniones para medir `precision@k` del RAG.
- Rúbrica humana para evaluar ADRs y actas.
- Medición automática de latencia por fase.
- Estimación de coste por reunión y por proveedor.
- Scripts reproducibles que generen tablas o JSON de resultados.

### UI para ejecutar el pipeline

La propuesta menciona una interfaz que permita cargar audio, visualizar transcripciones y aprobar actualizaciones. La UI actual visualiza outputs ya procesados. Sería valioso añadir:

- Carga de audio desde Streamlit.
- Ejecución del pipeline desde la UI.
- Progreso por fases: transcripción, RAG, extracción, generación.
- Gestión de errores por fase.
- Vista del run recién creado sin tener que relanzar manualmente la app.

### Más tipos de documentación generada

El proyecto genera ADRs y actas, pero la propuesta también menciona documentación técnica y roadmap tecnológico. Añadir:

- Modo `technical-doc-update` para proponer cambios en documentación existente.
- Modo `roadmap-update` para extraer cambios de planificación.
- Plantillas específicas por tipo de documento.
- Estrategia para modificar documentos existentes, no solo crear documentos nuevos.
- Diffs Markdown antes de publicar a Git.

### Modo automático opcional

La propuesta contempla un modo completamente automático opcional. Para añadirlo de forma controlada:

- Nueva configuración explícita, por ejemplo `AUTO_APPROVE_ENABLED=false`.
- Reglas de seguridad: solo actas, solo ramas draft, solo repos permitidos, o solo si la confianza supera un umbral.
- Registro claro de qué documentos fueron autoaprobados y por qué.
- Posibilidad de rollback o cierre automático del PR si se detecta error.

### Observabilidad y reproducibilidad

Para uso real y defensa académica conviene añadir:

- ID único de run.
- Logs estructurados por fase.
- Tiempos por módulo.
- Modelo usado en cada llamada LLM.
- Tokens de entrada/salida y coste estimado.
- Versión de prompts, hash de documentación indexada y configuración efectiva.
- Export de resultados en formato apto para anexos del TFM.

### Empaquetado y demo

Para que el proyecto sea fácil de ejecutar por tribunal, tutor o evaluador:

- Entrypoints CLI en `pyproject.toml`, por ejemplo `meeting-forge-run` e `meeting-forge-index`.
- Guía de demo con datos sintéticos.
- Dockerfile opcional para UI y pipeline.
- Script de setup/verificación de prerequisitos.
- Ejemplo completo de reunión procesada con outputs anonimizados.

## Roadmap sugerido

### P0: dejar el proyecto limpio y coherente

- Corregir `ruff`.
- Corregir `mypy`.
- Arreglar test flaky de `list_meetings`.
- Corregir o aclarar creación de `MeetingMetadata` en publicación desde UI.
- Actualizar README y ARCHITECTURE a Fase 4 real.
- Revisar `validation.json` raíz.
- Añadir CI y pre-commit.
- Decidir política de `uv.lock`.

### P1: completar requisitos nucleares del TFM

- Implementar harness de evaluación.
- Añadir métricas WER, precision/recall, `precision@k`, latencia y coste.
- Añadir fixture E2E pequeño o modo smoke sin dependencias externas pesadas.
- Persistir evidencias RAG usadas en cada resultado.
- Mejorar indexación para limpiar chunks obsoletos.
- Añadir ejecución del pipeline desde la UI.

### P2: ampliar producto y demostrabilidad

- Añadir generación de documentación técnica.
- Añadir generación o actualización de roadmap.
- Implementar Ollama o retirar la promesa de soporte.
- Añadir modo automático opcional con límites claros.
- Añadir observabilidad completa por run.
- Preparar demo reproducible y empaquetado.

## Criterio de éxito recomendado

Una versión sólida para el TFM debería cumplir:

- `pytest`, `ruff` y `mypy` pasan en CI.
- Hay al menos un flujo E2E demostrable con datos de ejemplo.
- La memoria puede mostrar métricas cuantitativas de transcripción, extracción, RAG, latencia y coste.
- La UI permite revisar y validar documentos con evidencias.
- La publicación Git produce PRs trazables y seguros.
- La documentación del repo coincide con el comportamiento real del sistema.
