"""Perfiles multi-turno del stress test del CAG.

Cada perfil es una lista de `(turn_index, transcript, fact_to_remember)`. El fact es
el string corto que `MemoryDriftMetric` buscará (sin distinguir mayúsculas) en el
snapshot de los turnos posteriores; `None` si el turno no declara ninguno.

Cada conversación se ejecuta una vez con el máximo de turnos (20) y la curva
"recall vs N" se lee de esa misma ejecución en los checkpoints N ∈ {1, 3, 6, 10, 20}:
una conversación de N turnos es exactamente el prefijo de la de 20.
"""

from dataclasses import dataclass, field

CHECKPOINTS = (1, 3, 6, 10, 20)
MAX_TURNS = 20

Turn = tuple[int, str, str | None]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    turns: list[Turn]
    # fact -> turno en el que deja de ser verdad. Una vez pasado ese turno, que siga
    # en la memoria cuenta como dato obsoleto (`stale_present`).
    superseded: dict[str, int] = field(default_factory=dict)

    def turns_up_to(self, n: int) -> list[Turn]:
        return [turn for turn in self.turns if turn[0] <= n]

    def facts_declared_before(self, turn_index: int) -> list[str]:
        """Facts declarados en turnos k < turn_index (los que ya deberían recordarse)."""
        return [fact for k, _, fact in self.turns if fact and k < turn_index]


_GROWING_REQUIREMENTS = [
    ("autenticación con SSO de Google", "SSO"),
    ("soporte multi-tenant: cada cliente aísla sus datos", "multi-tenant"),
    ("un audit log inmutable de todas las acciones", "audit log"),
    ("exportación de reservas a CSV", "CSV"),
    ("notificaciones por email al confirmar una reserva", "notificaciones"),
    ("cobro con Stripe y facturas automáticas", "Stripe"),
    ("roles y permisos: admin, gestor y usuario", "roles"),
    ("sincronización con Google Calendar", "Google Calendar"),
    ("un dashboard de ocupación por sala", "dashboard"),
    ("API pública REST con tokens por cliente", "API pública"),
    ("lista de espera cuando una sala está llena", "lista de espera"),
    ("check-in con código QR en la puerta", "QR"),
    ("integración con Slack para avisos al equipo", "Slack"),
    ("modo oscuro y accesibilidad WCAG AA", "WCAG"),
    ("informes mensuales en PDF para finanzas", "informes mensuales"),
    ("cancelaciones con política de penalización", "penalización"),
    ("localización a inglés y portugués", "portugués"),
    ("copias de seguridad diarias con retención de 30 días", "retención"),
    ("un portal de administración para soporte", "portal de administración"),
]


def _growing() -> Scenario:
    turns: list[Turn] = [
        (
            1,
            "Queremos construir una plataforma llamada Nimbus para gestionar reservas de "
            "salas en espacios de coworking. Somos un equipo de 4 personas.",
            "Nimbus",
        )
    ]
    for offset, (requirement, fact) in enumerate(_GROWING_REQUIREMENTS, start=2):
        turns.append((offset, f"Añade este requisito a Nimbus: {requirement}.", fact))
    return Scenario(
        "growing",
        "El proyecto crece: cada turno añade un requisito coherente. ¿Sobrevive el nombre?",
        turns,
    )


def _pivot() -> Scenario:
    steps = [
        "Seguimos con Nimbus: el panel de administración también lleva gráficas de ocupación.",
        "Nimbus necesita un sistema de reservas recurrentes (todos los lunes a las 9).",
        "Añadimos facturación mensual por cliente en Nimbus.",
    ]
    turns: list[Turn] = [
        (
            1,
            "Queremos construir una app llamada Nimbus para reservar salas de coworking. "
            "El equipo son 4 personas y el frontend será React con una API en Django.",
            "React",
        )
    ]
    for turn_index, text in enumerate(steps, start=2):
        turns.append((turn_index, text, None))
    turns.append(
        (
            5,
            "Cambio de planes: el cliente quiere app móvil nativa, así que dejamos React y "
            "pasamos el frontend a Flutter.",
            "Flutter",
        )
    )
    for turn_index in range(6, MAX_TURNS + 1):
        turns.append(
            (turn_index, f"Sobre Nimbus con Flutter: detalla el impacto de la tarea {turn_index} "
             "en el plan y el esfuerzo.", None)
        )  # fmt: skip
    return Scenario(
        "pivot",
        "El turno 5 cambia el stack de React a Flutter. ¿Se limpia la metadata o acumula ambas?",
        turns,
        superseded={"React": 5},
    )


def _contradiction() -> Scenario:
    turns: list[Turn] = [
        (
            1,
            "Queremos construir una plataforma llamada Nimbus para reservar salas de coworking. "
            "Somos un equipo de 4 personas.",
            "Nimbus",
        ),
        (2, "Nimbus debe permitir reservas por horas y por día completo.", None),
        (
            3,
            "El cliente tiene un presupuesto cerrado de 30000 EUR para Nimbus.",
            "30000",
        ),
    ]
    for turn_index in range(4, 8):
        turns.append((turn_index, f"Nimbus: precisa cómo afectaría la tarea {turn_index} al plan.", None))
    turns.append(
        (
            8,
            "Corrección importante: el presupuesto de Nimbus ya no es 30000, el cliente lo ha "
            "ampliado y ahora es de 80000 EUR.",
            "80000",
        )
    )
    for turn_index in range(9, MAX_TURNS + 1):
        turns.append((turn_index, f"Nimbus: precisa cómo afectaría la tarea {turn_index} al plan.", None))
    return Scenario(
        "contradiction",
        "El turno 3 fija 30000 EUR y el 8 lo cambia a 80000 EUR. ¿Cuál se preserva?",
        turns,
        superseded={"30000": 8},
    )


SCENARIOS: dict[str, Scenario] = {s.name: s for s in (_growing(), _pivot(), _contradiction())}
