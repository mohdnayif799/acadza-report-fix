import pytest

from engine.models import load_questions, load_reports, load_taxonomy


@pytest.fixture(scope="session")
def questions():
    return load_questions()


@pytest.fixture(scope="session")
def reports():
    return load_reports()


@pytest.fixture(scope="session")
def taxonomy():
    return load_taxonomy()


@pytest.fixture(scope="session")
def q(questions):
    """Look up a question by id prefix (ids are long)."""

    def get(prefix: str):
        matches = [v for k, v in questions.items() if k.startswith(prefix)]
        assert len(matches) == 1, prefix
        return matches[0]

    return get
