"""Database engine and session configuration."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy import inspect

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign keys and WAL mode for SQLite."""
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Yield a database session, ensuring it's closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TenantScopedSession:
    """A session wrapper that automatically scopes queries by tenant_key.

    All ``query()`` and ``get()`` calls on models that have a ``tenant_key``
    column are automatically filtered to the current tenant.  Models without
    ``tenant_key`` (e.g. Role, AppSetting) are returned unscoped.

    This is the central "gateway" for all database access — no data from
    another tenant can leak through it.
    """

    def __init__(self, db: Session, tenant_key: str | None):
        self._db = db
        self.tenant_key = tenant_key

    # ------------------------------------------------------------------
    # Query scoping
    # ------------------------------------------------------------------

    def query(self, *args):
        """Return a tenant-scoped Query for the given entities.

        Accepts multiple positional arguments (entities) just like
        SQLAlchemy's ``Session.query()``.
        """
        # Determine the primary model for tenant-key filtering.
        # Look for:
        # 1. A model class (has __tablename__) with tenant_key column
        # 2. A column expression - use inspect() to get table and find model
        # This handles cases like:
        #   db.query(Part)                                    -> filters by Part.tenant_key
        #   db.query(Part.status, func.count(Part.part_number)) -> filters by Part.tenant_key
        #   db.query(func.count(Part.part_number))            -> filters by Part.tenant_key
        primary = None
        for arg in args:
            # Check if this is a model class (has __tablename__) with tenant_key column
            if hasattr(arg, "__tablename__"):
                # Check if the model has a tenant_key column
                if hasattr(arg, "tenant_key") or "tenant_key" in [c.name for c in arg.__table__.columns]:
                    primary = arg
                    break
            # Check if this is a column/expression - use inspect to get table
            else:
                try:
                    table = inspect(arg).table
                    if table and "tenant_key" in [c.name for c in table.columns]:
                        # Find the model class that maps to this table
                        # Try to get from the column's parent mapper
                        if hasattr(arg, "parent") and hasattr(arg.parent, "mapper"):
                            mapper = arg.parent.mapper
                            if hasattr(mapper, "class_"):
                                primary = mapper.class_
                                break
                except Exception:
                    pass
        if primary is not None and self.tenant_key is not None:
            return self._db.query(*args).filter(primary.tenant_key == self.tenant_key)
        return self._db.query(*args)

    def get(self, model, ident):
        """Fetch by primary key, scoped to the tenant."""
        if hasattr(model, "tenant_key") and self.tenant_key is not None:
            return (
                self._db.query(model)
                .filter(model.tenant_key == self.tenant_key)
                .get(ident)
            )
        return self._db.get(model, ident)

    # ------------------------------------------------------------------
    # Delegated session methods
    # ------------------------------------------------------------------

    def add(self, obj):
        return self._db.add(obj)

    def add_all(self, objects):
        return self._db.add_all(objects)

    def delete(self, obj):
        return self._db.delete(obj)

    def commit(self):
        return self._db.commit()

    def rollback(self):
        return self._db.rollback()

    def close(self):
        return self._db.close()

    def execute(self, statement, params=None):
        return self._db.execute(statement, params)

    def bulk_save_objects(self, objects):
        return self._db.bulk_save_objects(objects)

    def bulk_insert_mappings(self, mapper, mappings):
        return self._db.bulk_insert_mappings(mapper, mappings)

    def bulk_update_mappings(self, mapper, mappings):
        return self._db.bulk_update_mappings(mapper, mappings)

    def flush(self):
        return self._db.flush()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
