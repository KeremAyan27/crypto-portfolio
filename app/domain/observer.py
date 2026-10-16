"""Observer pattern contracts.

OOM principles: Abstraction (Observer is an interface), Observer design
pattern (Subject keeps a list of observers and notifies them).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.news_event import NewsEvent


class Observer(ABC):
    @abstractmethod
    def update(self, event: NewsEvent) -> None:
        """Called by the subject for every new NewsEvent."""


class Subject:
    def __init__(self) -> None:
        self._observers: list[Observer] = []

    def register_observer(self, observer: Observer) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def unregister_observer(self, observer: Observer) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def notify_observers(self, event: NewsEvent) -> None:
        for observer in list(self._observers):
            observer.update(event)
