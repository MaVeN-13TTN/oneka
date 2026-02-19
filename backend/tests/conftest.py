"""
Test configuration and fixtures for pytest.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from src.database import Base, get_db
from src.main import app
from src.config import settings

# Test database URL
TEST_DATABASE_URL = "postgresql://oneka_user:password@localhost:5432/oneka_test"


@pytest.fixture(scope="session")
def test_engine():
    """
    Create test database engine.
    """
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_db(test_engine):
    """
    Create a new database session for each test.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    db = TestingSessionLocal()
    try:
        yield db
        # Rollback any uncommitted changes
        db.rollback()
    finally:
        # Clean up all tables after each test
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        db.close()


@pytest.fixture(scope="function")
def client(test_db):
    """
    Create FastAPI test client with test database.
    """

    def override_get_db():
        try:
            yield test_db
        finally:
            test_db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
