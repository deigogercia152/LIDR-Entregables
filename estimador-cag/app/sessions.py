"""Estado de las conversaciones del estimador: historial, memoria del proyecto y sesiones.

Todo vive en memoria del proceso, en un diccionario. Se acepta esa volatilidad en
esta fase: reiniciar el servicio (o `uvicorn --reload`) borra las sesiones y el
cliente simplemente abre una nueva. Y por la misma razón solo funciona con un
único worker de uvicorn: varios workers tendrían diccionarios distintos.
Persistir la memoria (BBDD, Redis) queda fuera del alcance de esta fase.

Historial y memoria son cosas distintas. El historial (`ConversationHistory`) es el
array `messages` que viaja a la API en cada llamada y se recorta con una ventana
deslizante. La memoria (`ProjectMetadata`) son los hechos del proyecto en curso: no
se recorta con la ventana y se inyecta aparte, en el system prompt de cada turno.
"""

import threading
import uuid
from collections import OrderedDict, deque

from pydantic import BaseModel, Field, field_validator

MAX_TURNS = 6  # turnos completos que se conservan en el historial (SESSION_MAX_TURNS)
MAX_SESSIONS = 500  # sesiones simultáneas antes de expulsar la menos usada (MAX_SESSIONS)
MAX_TECHNOLOGIES = 30
MAX_TECHNOLOGY_CHARS = 50
MAX_NAME_CHARS = 100
MAX_SCOPE_CHARS = 1000


def _clean(value: str, max_chars: int) -> str:
    """Quita `<` y `>` y acota la longitud.

    Estos valores los extrae un LLM de textos que pueden venir de un adjunto hostil
    y vuelven al system prompt del turno siguiente: sin esto, un valor podría cerrar
    la etiqueta `<project_metadata>` e inyectar instrucciones.
    """
    return value.replace("<", "").replace(">", "").strip()[:max_chars]


class ProjectMetadata(BaseModel):
    """Hechos del proyecto en curso que se preservan entre turnos."""

    project_name: str = ""
    assumed_team_size: int | None = Field(default=None, ge=1, le=1000)
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str = ""

    @field_validator("project_name", mode="before")
    @classmethod
    def _clean_name(cls, value: object) -> object:
        return _clean(value, MAX_NAME_CHARS) if isinstance(value, str) else (value or "")

    @field_validator("agreed_scope", mode="before")
    @classmethod
    def _clean_scope(cls, value: object) -> object:
        return _clean(value, MAX_SCOPE_CHARS) if isinstance(value, str) else (value or "")

    @field_validator("mentioned_technologies", mode="before")
    @classmethod
    def _clean_technologies(cls, value: object) -> object:
        if not isinstance(value, list):
            return value or []  # los LLM a veces devuelven null en lugar de una lista vacía
        cleaned = (_clean(tech, MAX_TECHNOLOGY_CHARS) for tech in value if isinstance(tech, str))
        return [tech for tech in cleaned if tech][:MAX_TECHNOLOGIES]

    def is_empty(self) -> bool:
        return not (
            self.project_name
            or self.assumed_team_size is not None
            or self.mentioned_technologies
            or self.agreed_scope
        )

    def merged_with(self, update: "ProjectMetadata") -> "ProjectMetadata":
        """Devuelve una copia con `update` aplicado: lo nuevo gana, lo ausente se conserva."""
        technologies = list(self.mentioned_technologies)
        known = {tech.casefold() for tech in technologies}
        for tech in update.mentioned_technologies:
            if tech.casefold() not in known:
                known.add(tech.casefold())
                technologies.append(tech)

        return ProjectMetadata(
            project_name=update.project_name or self.project_name,
            assumed_team_size=(
                update.assumed_team_size
                if update.assumed_team_size is not None
                else self.assumed_team_size
            ),
            mentioned_technologies=technologies,
            agreed_scope=update.agreed_scope or self.agreed_scope,
        )


class ConversationHistory:
    """Últimos `max_turns` turnos (pares usuario + asistente) de una conversación.

    La ventana cuenta turnos ya completados. La petición al LLM lleva, además, el
    mensaje nuevo del usuario: como máximo `2 * max_turns + 1` mensajes. El system
    prompt no forma parte de la ventana: se regenera en cada turno a partir de la
    memoria del proyecto, así que siempre está presente y nunca se descarta.
    """

    def __init__(self, max_turns: int) -> None:
        self._turns: deque[tuple[str, str]] = deque(maxlen=max_turns)

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        self._turns.append((user_message, assistant_message))

    def chat_messages(self, user_message: str | None = None) -> list[dict[str, str]]:
        """Turnos en el formato de la API, sin system, más el mensaje pendiente si lo hay."""
        messages: list[dict[str, str]] = []
        for user, assistant in self._turns:
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": assistant})
        if user_message is not None:
            messages.append({"role": "user", "content": user_message})
        return messages

    def to_messages_list(
        self, system_prompt: str, user_message: str | None = None
    ) -> list[dict[str, str]]:
        """Array `messages` completo, con el system prompt regenerado como primer mensaje."""
        return [{"role": "system", "content": system_prompt}, *self.chat_messages(user_message)]

    def __len__(self) -> int:
        return len(self._turns)


class Session:
    def __init__(self, session_id: str, max_turns: int) -> None:
        self.id = session_id
        self.history = ConversationHistory(max_turns)
        # Turnos totales de la sesión. No sale de `len(history)`, que se queda en `max_turns`.
        self.turn_count = 0
        self.metadata = ProjectMetadata()
        # Serializa los turnos de una misma sesión: dos peticiones simultáneas
        # leerían el mismo historial y una pisaría el turno de la otra.
        self.lock = threading.Lock()


class SessionStore:
    """Diccionario de sesiones con tope: al llenarse expulsa la menos usada recientemente."""

    def __init__(self, max_sessions: int) -> None:
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        # Protege el propio diccionario (crear, expulsar); cada sesión tiene su lock.
        self._lock = threading.Lock()

    def create(self, max_turns: int) -> Session:
        session = Session(str(uuid.uuid4()), max_turns)
        with self._lock:
            self._sessions[session.id] = session
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions.move_to_end(session_id)
            return session
