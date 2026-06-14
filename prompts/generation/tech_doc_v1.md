# Prompt de Actualización de Documentación Técnica v1

Eres responsable de mantener la **documentación técnica** de un proyecto de software. A partir de lo
discutido en una reunión, produce la **versión actualizada completa** del documento en Markdown.

## Reunión

- Título: {meeting_title}
- Fecha: {date}

## Documentación actual

{existing_document}

## Información extraída de la reunión

{insights_block}

## Instrucciones

- Devuelve **únicamente el documento Markdown completo ya actualizado** (sin diff, sin explicaciones,
  sin envolver en fences ```).
- **Conserva** lo que siga siendo correcto; integra las decisiones técnicas, cambios de arquitectura
  o aclaraciones surgidas en la reunión.
- Si no existe documentación previa, créala con una estructura clara (visión general, componentes,
  decisiones, configuración…).
- No inventes detalles técnicos que no se deriven de la reunión o del documento actual.
