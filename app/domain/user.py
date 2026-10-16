"""User: the investor.

OOM principles: Composition (a User owns exactly one Portfolio, created with
the User and never shared), Encapsulation.
"""

from __future__ import annotations

import uuid

from app.domain.portfolio import Portfolio


class User:
    def __init__(self, username: str, portfolio: Portfolio | None = None) -> None:
        self._user_id = str(uuid.uuid4())
        self._username = username
        self._portfolio = portfolio or Portfolio()

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    def get_portfolio(self) -> Portfolio:
        return self._portfolio
