"""Capa HTTP de incidentes: request → servicio → respuesta. Sin lógica de análisis."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response

from .schemas import EXPORT_FILENAME, AnalysisResponse
from .service import IncidentService

router = APIRouter(tags=["incidents"])

EXPORT_ROUTE_NAME = "export_incident_results"
# El resultado cambia con cada análisis y la URL de exportación es fija:
# ningún navegador ni proxy debe guardar ni reutilizar estas respuestas.
NO_STORE = "no-store"


def get_incident_service(request: Request) -> IncidentService:
    return IncidentService(request.app.state.result_store)


ServiceDep = Annotated[IncidentService, Depends(get_incident_service)]


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_incidents(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="Incidents CSV (UTF-8, header row, .csv extension)")],
    service: ServiceDep,
) -> AnalysisResponse:
    stored = service.analyze_upload(file.filename, file.file)
    response.headers["Cache-Control"] = NO_STORE
    return AnalysisResponse.from_stored(stored, export_url=request.app.url_path_for(EXPORT_ROUTE_NAME))


# Sin cuerpo JSON: `response_model=None` declarado y el CSV y sus cabeceras
# documentados en `responses=` (auditoría de serialización, D7).
EXPORT_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Último análisis correcto como CSV `metric,value` (una métrica por fila), el mismo que escribe la CLI",
        "content": {"text/csv": {"schema": {"type": "string"}}},
        "headers": {
            "Content-Disposition": {"description": f'attachment; filename="{EXPORT_FILENAME}"', "schema": {"type": "string"}},
            "X-Analysis-Id": {"description": "`analysis_id` del análisis exportado", "schema": {"type": "string", "format": "uuid"}},
            "Cache-Control": {"description": NO_STORE, "schema": {"type": "string"}},
        },
    },
}


@router.get(
    "/results/export",
    name=EXPORT_ROUTE_NAME,
    response_model=None,
    response_class=Response,
    responses=EXPORT_RESPONSES,
)
def export_incident_results(service: ServiceDep) -> Response:
    stored, csv_text = service.export_latest()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{EXPORT_FILENAME}"',
            "X-Analysis-Id": str(stored.analysis_id),
            "Cache-Control": NO_STORE,
        },
    )
