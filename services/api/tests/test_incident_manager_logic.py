"""Gestor centralizado de incidencias: las decisiones de negocio, sin HTTP.

Unidades: las funciones de ruta de `app/modules/incident_manager/router.py`,
llamadas con el cuerpo como diccionario y el repositorio ya resuelto, e
`IncidentRepository` con una TinyDB temporal y un reloj inyectado. Contexto:
docs/centralized-incident-manager.md y SPECS.md Parte E.

`test_incident_manager_repository.py` ya prueba el repositorio por dentro
(transiciones una a una, filtros, seed del fixture). Aquí se prueba la capa de
decisión que hoy solo cubría HTTP: la validación antes de escribir, el 400 de
una transición inválida sin tocar nada, el 404 y el desempate del orden
cuando varias incidencias comparten fecha.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from nexova_shared.incidents import IncidentDraft, IncidentStatus, SeedIncident, validate_incident_fields

from app.core.errors import IncidentFieldsError, IncidentNotFoundError, InvalidStatusTransitionApiError
from app.modules.incident_manager import router
from app.modules.incident_manager.models import Incident
from app.modules.incident_manager.repository import IncidentRepository

from .conftest import FakeClock


def _payload(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "title": "Synthetic incident",
        "description": "Synthetic description",
        "category": "technical_failure",
        "origin": "branch",
        "branch": "miami_office",
    }
    values.update(changes)
    return values


def _create(repo: IncidentRepository, **changes: Any) -> Incident:
    return router.create_incident(_payload(**changes), repo)


def _fields(error: IncidentFieldsError | InvalidStatusTransitionApiError) -> list[tuple[str, str]]:
    return [(detail["field"], detail["error"]) for detail in error.detail]


# --- POST /api/incidents ---


def test_created_incident_is_open_with_trimmed_text_and_the_creation_time(
    incident_repo: IncidentRepository, clock: FakeClock
) -> None:
    incident = _create(incident_repo, title="  Synthetic incident  ")

    assert incident.status == IncidentStatus.OPEN
    assert incident.title == "Synthetic incident"
    assert incident.created_at == incident.updated_at == clock.now
    assert incident_repo.get(incident.id) == incident


@pytest.mark.parametrize(("length", "accepted"), [(120, True), (121, False)])
def test_title_may_have_120_characters_but_not_121(incident_repo: IncidentRepository, length: int, accepted: bool) -> None:
    if accepted:
        assert len(_create(incident_repo, title="t" * length).title) == length
    else:
        with pytest.raises(IncidentFieldsError) as exc:
            _create(incident_repo, title="t" * length)
        assert [field for field, _ in _fields(exc.value)] == ["title"]


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"branch": None}, id="sin sede"),
        pytest.param({"status": "resolved"}, id="nace resuelta"),
        pytest.param({"category": "catering"}, id="categoría desconocida"),
        pytest.param({"id": str(uuid4())}, id="id del cliente"),
    ],
)
def test_invalid_incident_is_rejected_before_writing_anything(
    incident_repo: IncidentRepository, changes: dict[str, Any]
) -> None:
    # Toda incidencia nueva nace `open`, con sede, y con valores del CONTEXT; si no, 400 y nada escrito.
    with pytest.raises(IncidentFieldsError):
        _create(incident_repo, **changes)
    assert incident_repo.find() == []


# --- GET /api/incidents ---


def test_filters_are_combined_with_and(incident_repo: IncidentRepository) -> None:
    # Cada incidencia descartada difiere del objetivo en un solo campo: así cada filtro es necesario.
    target = _create(incident_repo, origin="branch", branch="miami_office", category="sla_breach")
    _create(incident_repo, origin="customer", branch="miami_office", category="sla_breach")
    _create(incident_repo, origin="branch", branch="central", category="sla_breach")
    _create(incident_repo, origin="branch", branch="miami_office", category="technical_failure")

    found = router.list_incidents(incident_repo, origin="branch", branch="miami_office", category="sla_breach")

    assert found == [target]


def test_list_is_newest_first_and_ties_are_broken_by_id(incident_repo: IncidentRepository, clock: FakeClock) -> None:
    # El seed carga varias incidencias con la misma fecha (medianoche): el `id` da un orden estable.
    same_time = [_create(incident_repo) for _ in range(3)]
    clock.advance(minutes=1)
    newest = _create(incident_repo)

    listed = router.list_incidents(incident_repo)

    assert listed[0] == newest
    assert listed[1:] == sorted(same_time, key=lambda incident: str(incident.id), reverse=True)
    assert router.list_incidents(incident_repo) == listed


@pytest.mark.parametrize(("field", "value"), [("status", "closed"), ("branch", "madrid"), ("origin", "")])
def test_filter_outside_the_vocabulary_is_rejected(incident_repo: IncidentRepository, field: str, value: str) -> None:
    # Un filtro desconocido es un error, no una lista vacía que parezca «no hay incidencias».
    with pytest.raises(IncidentFieldsError) as exc:
        router.list_incidents(incident_repo, **{field: value})
    assert [name for name, _ in _fields(exc.value)] == [field]


# --- GET /api/incidents/summary ---


def test_summary_counts_by_status_and_keeps_every_key(incident_repo: IncidentRepository) -> None:
    first = _create(incident_repo)
    _create(incident_repo)
    router.change_incident_status(first.id, {"status": "discarded"}, incident_repo)

    summary = router.incident_summary(incident_repo)

    assert summary.total == 2
    assert summary.by_status == {
        IncidentStatus.OPEN: 1,
        IncidentStatus.IN_PROGRESS: 0,
        IncidentStatus.RESOLVED: 0,
        IncidentStatus.DISCARDED: 1,
    }


def test_summary_of_an_empty_manager_is_all_zeros(incident_repo: IncidentRepository) -> None:
    summary = router.incident_summary(incident_repo)
    assert summary.total == 0
    assert set(summary.by_status.values()) == {0}


# --- GET /api/incidents/{id} ---


def test_get_returns_the_incident(incident_repo: IncidentRepository) -> None:
    incident = _create(incident_repo)
    assert router.get_incident(incident.id, incident_repo) == incident


def test_get_of_an_unknown_id_is_not_found(incident_repo: IncidentRepository) -> None:
    with pytest.raises(IncidentNotFoundError):
        router.get_incident(uuid4(), incident_repo)


# --- PATCH /api/incidents/{id}/status ---


def test_valid_transition_changes_status_and_updated_at_only(incident_repo: IncidentRepository, clock: FakeClock) -> None:
    incident = _create(incident_repo)
    clock.advance(hours=2)

    changed = router.change_incident_status(incident.id, {"status": "in_progress"}, incident_repo)

    assert (changed.status, changed.updated_at, changed.created_at) == (
        IncidentStatus.IN_PROGRESS,
        clock.now,
        incident.created_at,
    )
    assert incident_repo.get(incident.id) == changed


def test_an_open_incident_can_be_discarded_directly_but_a_discarded_one_is_final(incident_repo: IncidentRepository) -> None:
    incident = _create(incident_repo)
    router.change_incident_status(incident.id, {"status": "discarded"}, incident_repo)

    with pytest.raises(InvalidStatusTransitionApiError):
        router.change_incident_status(incident.id, {"status": "open"}, incident_repo)


def test_invalid_transition_is_rejected_and_writes_nothing(
    incident_repo: IncidentRepository, clock: FakeClock
) -> None:
    # open → resolved se salta in_progress: 400 y el archivo queda byte a byte igual.
    incident = _create(incident_repo)
    before = incident_repo.path.read_bytes()
    clock.advance(hours=1)

    with pytest.raises(InvalidStatusTransitionApiError) as exc:
        router.change_incident_status(incident.id, {"status": "resolved"}, incident_repo)

    assert _fields(exc.value) == [("status", "invalid_transition")]
    assert incident_repo.path.read_bytes() == before


def test_status_change_of_an_unknown_id_is_not_found(incident_repo: IncidentRepository) -> None:
    with pytest.raises(IncidentNotFoundError):
        router.change_incident_status(uuid4(), {"status": "in_progress"}, incident_repo)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="sin status"),
        pytest.param({"status": "closed"}, id="estado desconocido"),
        pytest.param({"status": "in_progress", "title": "otro"}, id="otro campo"),
    ],
)
def test_malformed_status_change_is_rejected_without_touching_the_incident(
    incident_repo: IncidentRepository, body: dict[str, Any]
) -> None:
    # Solo se cambia `status`: el cuerpo se valida antes de buscar la incidencia.
    incident = _create(incident_repo)
    with pytest.raises(IncidentFieldsError):
        router.change_incident_status(incident.id, body, incident_repo)
    assert incident_repo.get(incident.id) == incident


# --- Seed ---


def _seed_incident(key: str, draft: IncidentDraft) -> SeedIncident:
    return SeedIncident(
        row_number=1,
        source_key=key * 64,
        draft=draft,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


def test_seed_is_idempotent_by_source_key_and_keeps_the_csv_date(incident_repo: IncidentRepository) -> None:
    # El seed (a diferencia de la API) puede cargar cualquier estado del histórico.
    draft = validate_incident_fields(
        _payload(origin="customer", branch="central", status="resolved"), allowed_statuses=tuple(IncidentStatus)
    )

    first = incident_repo.seed([_seed_incident("a", draft)])
    second = incident_repo.seed([_seed_incident("a", draft), _seed_incident("b", draft)])

    assert (first.inserted, first.existing, first.total) == (1, 0, 1)
    assert (second.inserted, second.existing, second.total) == (1, 1, 2)
    # El histórico conserva su fecha y su estado: `updated_at` = `created_at` al insertar.
    for incident in incident_repo.find():
        assert incident.created_at == incident.updated_at == datetime(2026, 3, 1, tzinfo=UTC)
        assert incident.status == IncidentStatus.RESOLVED
