from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import settings
from app.services import canvas_client as canvas

router = APIRouter(prefix="/canvas/terms", tags=["Canvas · Terms"])
_ACCOUNT = settings.canvas_account_id


@router.get("", summary="Listar periodos / términos de la cuenta")
async def list_terms(
    search_term: Annotated[str | None, Query()] = None,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
):
    params: dict = {"per_page": per_page}
    if search_term:
        params["search_term"] = search_term
    return await canvas.paginate(f"/accounts/{_ACCOUNT}/terms", params)
