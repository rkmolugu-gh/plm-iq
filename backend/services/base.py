"""BaseService - shared plumbing for every tenant-scoped service class.

Why this class exists
---------------------
Before the OOP port, three modules carried private near-copies of the same
mechanics (optimistic-lock update, lifecycle-transition guard, row->DTO
conversion). ``user_service._execute_versioned_update`` and
``vertex_service._execute_versioned_update`` were literal twins drifting
apart. BaseService makes those mechanics exist exactly once, protected
(``_``-prefixed) so subclasses extend behavior without reaching sideways
into another module's internals - the encapsulation leak that motivated the
port.

Benefits
--------
* One implementation of version-race detection: concurrent writers always
  lose deterministically with an actionable Conflict message.
* One place to add cross-cutting concerns later (audit hooks, soft-delete
  policies, outbox events) - every service inherits them automatically.

How to extend (future scenarios)
--------------------------------
Subclass and declare two things::

    class WidgetService(BaseService):
        out_model = WidgetOut            # pydantic DTO for rows
        transitions = {Status.A: frozenset({Status.B})}   # optional

then implement your public API with plain methods that take ``session``
explicitly (services stay stateless; transactions belong to the caller's
``db.tenant_session`` block). Reuse the protected helpers instead of
reimplementing mechanics:

* ``self._to_out(row_or_mapping)``       -> validated DTO
* ``self._versioned_update(...)``        -> optimistic-lock UPDATE + race check
* ``self._check_transition(...)``        -> state-machine guard using ``transitions``
* ``self._fetch_one(table, ...)``        -> tenant-filtered single-row SELECT

Do NOT put sessions, caches, or config on ``self``: instances are meant to be
long-lived module singletons shared across requests.
"""
from __future__ import annotations

import logging
from datetime import datetime as dt
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .errors import Conflict, NotFound, ValidationFailed
from .schemas import CamelModel, from_row

logger = logging.getLogger(__name__)


class BaseService:
    """Common mechanics for tenant-scoped services. Stateless by design."""

    #: Pydantic Out model describing one row. Subclasses MUST set this.
    out_model: type[CamelModel]

    #: Optional state machine: {StateEnum: frozenset(allowed next states)}.
    transitions: Mapping[Any, frozenset] = {}

    # ── conversion ───────────────────────────────────────────────────────────

    def _to_out(self, row) -> Any:
        """Validate a result row (or plain mapping) into ``self.out_model``."""
        if isinstance(row, Mapping):
            return self.out_model.model_validate(dict(row))
        return from_row(self.out_model, row)

    # ── optimistic locking ───────────────────────────────────────────────────

    def _versioned_update(
        self,
        session: Session,
        table: Any,
        changes: dict[str, Any],
        *,
        row_id: UUID,
        expected_version: int,
        actor: str,
        tenant_id: UUID | None = None,
    ):
        """UPDATE ... WHERE id/version match; raise on any lost race.

        ``changes`` may be empty - the statement still stamps modified_by/on
        and fires the table's bump_version() trigger, which is exactly what
        file-only operations need to consume a lock token.
        """
        conditions = [table.c.id == row_id, table.c.version == expected_version]
        if tenant_id is not None:
            conditions.append(table.c.tenant_id == tenant_id)
        stmt = (
            update(table)
            .where(*conditions)
            .values(**changes, modified_by=actor, modified_on=dt.now())
            .returning(*table.c)
        )
        row = session.execute(stmt).one_or_none()
        if row is not None:
            return row
        refreshed = self._fetch_one(session, table, row_id=row_id, tenant_id=tenant_id)
        if refreshed is None:
            raise NotFound(f"{table.name} row {row_id} not found")
        logger.warning("base.update.race_lost", extra={"table": table.name, "id": str(row_id)})
        raise Conflict(
            f"concurrent modification on {table.name} {row_id}: expected version "
            f"{expected_version}, current {refreshed['version']}"
        )

    # ── state machines ───────────────────────────────────────────────────────

    def _check_transition(
        self,
        *,
        row_id: Any,
        old: Any,
        new: Any,
        transitions: Mapping[Any, frozenset] | None = None,
    ) -> None:
        allowed = (transitions if transitions is not None else self.transitions).get(old, frozenset())
        if new not in allowed:
            raise ValidationFailed(
                f"illegal lifecycle transition on {row_id}: "
                f"'{getattr(old, 'value', old)}' -> '{getattr(new, 'value', new)}'; "
                f"allowed next: {sorted(getattr(s, 'value', s) for s in allowed)}"
            )

    # ── row access ───────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_one(session: Session, table: Any, *, row_id: UUID, tenant_id: UUID | None = None) -> dict | None:
        conditions = [table.c.id == row_id]
        if tenant_id is not None:
            conditions.append(table.c.tenant_id == tenant_id)
        row = session.execute(select(table).where(*conditions)).one_or_none()
        return dict(row._mapping) if row else None
