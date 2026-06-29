"""GET /api/variables — variable catalog endpoint (Sprint 3 B8)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import variable_registry
from app.auth import get_current_user

router = APIRouter(prefix="/api/variables", tags=["variables"])


class VariableMetadataModel(BaseModel):
    label: str
    description: str
    boundary: Literal["BG", "ZCTA5", "Tract", "County"]
    coverage_years: tuple[int, int]
    coverage_region: Literal["CONUS", "US", "AK_HI"]
    experiment: str
    ontology_id: str | None = None
    data_source: str | None = None
    temporal: Literal["static", "yearly"] = "yearly"
    variable_type: Literal["categorical", "continuous"]
    display_unit: str
    value_cols: list[str]


class VariableCatalogResponse(BaseModel):
    schema_version: int
    variables: dict[str, VariableMetadataModel]


@router.get(
    "",
    response_model=VariableCatalogResponse,
    include_in_schema=True,
)
def list_variables(_user=Depends(get_current_user)) -> VariableCatalogResponse:
    try:
        payload = variable_registry.load_variables()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "metadata_unavailable", "message": str(e)},
        )
    except variable_registry.MetadataSchemaError as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "metadata_schema_invalid", "message": str(e)},
        )
    return payload
