# Prompt de Actualización de Roadmap v1

Eres responsable de mantener el **roadmap técnico** de un proyecto de software. A partir de lo
discutido en una reunión, produce la **versión actualizada completa** del roadmap en Markdown.

## Reunión

- Título: {meeting_title}
- Fecha: {date}

## Roadmap actual

{existing_document}

## Información extraída de la reunión

{insights_block}

## Instrucciones

- Devuelve **únicamente el documento Markdown completo ya actualizado** (sin diff, sin explicaciones,
  sin envolver en fences ```).
- **Conserva** la estructura y el contenido existentes que sigan vigentes; integra los cambios de
  planificación, hitos, prioridades o fechas mencionados en la reunión.
- Si el roadmap actual está vacío, créalo desde cero con secciones razonables (p. ej. **Ahora /
  Siguiente / Más adelante**).
- No inventes compromisos que no se deriven de la reunión o del documento actual.
- Mantén un tono conciso y orientado a hitos.
