"""Bounded, dataset-bound conversation leases; completed turns only."""

import json
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Callable, Iterator
from uuid import UUID, uuid4

from backend.data.dataset_manager import DatasetManager, DatasetNotFoundError
from backend.schemas import AnalyzeResponse

MAX_TURNS = 5
MAX_TURN_BYTES = 4096


class ConversationError(RuntimeError):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.status_code = status_code


def compact_turn(question: str, response: AnalyzeResponse) -> dict:
    """Store verified SQL evidence, never model prose as numerical truth."""
    turn = {
        'question': question, 'sql': response.sql, 'columns': response.columns[:20],
        'rows': [row[:20] for row in response.rows[:5]], 'row_count': response.row_count,
        'tools_used': response.tools_used[:6],
        'statistics': deepcopy(response._statistics_evidence),
        'evidence_truncated': len(response.rows) > 5 or len(response.columns) > 20,
    }
    def size():
        return len(json.dumps(turn, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    while size() > MAX_TURN_BYTES:
        turn['evidence_truncated'] = True
        if turn['statistics']:
            turn['statistics'] = {}
        elif turn['rows']:
            turn['rows'].pop()
        elif turn['columns']:
            turn['columns'] = []
        elif turn['sql'] is not None:
            turn['sql'] = None
        else:
            turn['question'] = turn['question'][:len(turn['question']) // 2]
    return turn


@dataclass
class _Conversation:
    dataset_id: UUID
    last_access: float
    turns: list[dict] = field(default_factory=list)
    busy: bool = False


@dataclass
class ConversationLease:
    conversation_id: UUID
    context: list[dict]
    _response: AnalyzeResponse | None = None
    _question: str = ''

    def complete(self, question: str, response: AnalyzeResponse) -> None:
        self._question, self._response = question, response


class ConversationManager:
    """One lock for short transitions; model work occurs outside the lock."""

    def __init__(self, datasets: DatasetManager, *, ttl_seconds: int = 1800,
                 max_conversations: int = 100, clock: Callable[[], float] = monotonic) -> None:
        for value in (ttl_seconds, max_conversations):
            if type(value) is not int or value <= 0:
                raise ValueError('Conversation limits must be positive integers.')
        self.datasets = datasets
        self.ttl_seconds = ttl_seconds
        self.max_conversations = max_conversations
        self.clock = clock
        self._entries: dict[UUID, _Conversation] = {}
        self._lock = Lock()

    def _cleanup(self) -> None:
        now = self.clock()
        for key, entry in list(self._entries.items()):
            try:
                self.datasets.uploaded_at(entry.dataset_id)  # Does not refresh dataset TTL.
                alive = True
            except DatasetNotFoundError:
                alive = False
            if not alive or (not entry.busy and now - entry.last_access >= self.ttl_seconds):
                del self._entries[key]

    @contextmanager
    def turn(self, dataset_id: UUID, conversation_id: UUID | None = None) -> Iterator[ConversationLease]:
        with self._lock:
            self._cleanup()
            self.datasets.uploaded_at(dataset_id)
            fresh = conversation_id is None
            if fresh:
                if len(self._entries) >= self.max_conversations:
                    raise ConversationError('Conversation capacity reached. Wait for an inactive conversation to expire.', 503)
                conversation_id = uuid4()
                entry = _Conversation(dataset_id, self.clock())
                self._entries[conversation_id] = entry
            else:
                entry = self._entries.get(conversation_id)
                if entry is None:
                    raise ConversationError('Conversation not found or expired. Start a new conversation.', 410)
                if entry.dataset_id != dataset_id:
                    raise ConversationError('Conversation belongs to a different dataset. Start a new conversation.', 409)
                if entry.busy:
                    raise ConversationError('Conversation already has an analysis in progress. Wait before submitting another question.', 409)
            entry.busy = True
            lease = ConversationLease(conversation_id, deepcopy(entry.turns))
        try:
            yield lease
            if lease._response is not None:
                evidence = compact_turn(lease._question, lease._response)
                with self._lock:
                    self.datasets.uploaded_at(dataset_id)
                    if self._entries.get(conversation_id) is not entry:
                        raise ConversationError('Conversation expired during analysis. Start a new conversation.', 410)
                    entry.turns = (entry.turns + [evidence])[-MAX_TURNS:]
                    entry.last_access = self.clock()
        finally:
            with self._lock:
                entry.busy = False
                if fresh and not entry.turns and self._entries.get(conversation_id) is entry:
                    del self._entries[conversation_id]
                self._cleanup()

    def prune(self) -> None:
        """Remove lazily expired conversations after dataset session operations."""
        with self._lock:
            self._cleanup()

    def reset(self, dataset_id: UUID, conversation_id: UUID) -> None:
        with self._lock:
            self._cleanup()
            entry = self._entries.get(conversation_id)
            if entry is None:
                raise ConversationError('Conversation not found or expired. Start a new conversation.', 410)
            if entry.dataset_id != dataset_id:
                raise ConversationError('Conversation belongs to a different dataset.', 409)
            if entry.busy:
                raise ConversationError('Conversation already has an analysis in progress. Wait before resetting.', 409)
            del self._entries[conversation_id]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
