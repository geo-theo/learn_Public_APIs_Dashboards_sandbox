from __future__ import annotations

import pytest

from montana_data_lab.db import configure_database, init_database, session_scope
from montana_data_lab.pipeline.orchestrator import seed_reference_data


@pytest.fixture
def test_database(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    configure_database(database_url)
    init_database()
    with session_scope() as session:
        seed_reference_data(session)
    yield database_url
