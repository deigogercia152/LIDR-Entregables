ESTIMATION_EXAMPLES = [
    {
        "meeting_summary": """
            El cliente necesita una solución de automatización para gestionar sus tareas cotidianas, incluyendo notificaciones y recordatorios programados. Quiere integrar WhatsApp Business API para enviar mensajes automáticos.
        """,

        "estimation": """
            ## Estimación: Sistema de Automatización WhatsApp con Notificaciones

            ### Desglose de tareas:
            1. Configuración del servidor y entornos (prod/dev): 8 horas — USD 400
            2. Desarrollo de integración WhatsApp Business API: 40 horas — USD 2.000
            3. Creación de notificaciones push personalizadas: 25 horas — USD 1.250
            4. Panel de administración para gestionar campañas: 35 horas — USD 1.750
            5. Testing, seguridad y documentación: 15 horas — USD 750

            **Total estimado: 123 horas**
            **Coste estimado: USD 6.150 (tarifa de referencia: USD 50/hora)**
            **Equipo recomendado: 1 desarrollador backend + 1 diseñador UX (part-time)**
            **Duración estimada: 4-5 semanas**
        """
    },
    {
        "meeting_summary": """
            La empresa requiere una auditoría completa de sus procesos internos para identificar cuellos de botella, optimizar el flujo de trabajo y proponer mejoras en la eficiencia operativa. Necesitan un análisis detallado con métricas específicas.
        """,
        "estimation": """
            ## Estimación: Auditoría de Procesos y Optimización Operativa

            ### Desglose de tareas:
            1. Recopilación de datos actuales (4 semanas): 10 horas — USD 500
            2. Mapeo de flujos de proceso existentes: 20 horas — USD 1.000
            3. Identificación de cuellos de botella y riesgos: 15 horas — USD 750
            4. Análisis de métricas y KPIs actuales: 20 horas — USD 1.000
            5. Propuesta de optimización con recomendaciones: 25 horas — USD 1.250
            6. Presentación y seguimiento de hallazgos: 8 horas — USD 400

            **Total estimado: 98 horas**
            **Coste estimado: USD 4.900 (tarifa de referencia: USD 50/hora)**
            **Equipo recomendado: 1 consultor especialista en operaciones (full-time)**
            **Duración estimada: 3-4 semanas**
        """
    },
    {
        "meeting_summary": """
            El cliente necesita migrar su base de datos PostgreSQL de servidor local a AWS RDS, con requerimientos específicos de alta disponibilidad y copias de seguridad automáticas. Además requiere scripts de migración de datos existentes.
        """,
        "estimation": """
            ## Estimación: Migración Base de Datos PostgreSQL a AWS RDS

            ### Desglose de tareas:
            1. Estructura inicial en AWS (RDS, S3, IAM): 6 horas — USD 300
            2. Scripts de exportación de base de datos actual: 10 horas — USD 500
            3. Scripts de conversión y migración de datos: 25 horas — USD 1.250
            4. Creación de réplica de alta disponibilidad: 12 horas — USD 600
            5. Testing de integridad y rendimiento: 15 horas — USD 750
            6. Documentación del plan de rollback y recuperación: 8 horas — USD 400

            **Total estimado: 76 horas**
            **Coste estimado: USD 3.800 (tarifa de referencia: USD 50/hora)**
            **Equipo recomendado: 1 desarrollador DBA/DevOps + 1 ingeniero AWS**
            **Duración estimada: 2-3 semanas**
        """
    },
]

def get_estimation_examples() -> list[dict[str, str]]:
    """
    Devuelve una lista de ejemplos de estimaciones de proyectos de software.

    Returns:
        list[dict[str, str]]: Lista de diccionarios con resúmenes de reuniones y sus estimaciones correspondientes.
    """
    return ESTIMATION_EXAMPLES