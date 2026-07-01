from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.services import auth as auth_service
from app.core.config import settings

router = APIRouter(tags=["Auth"])


@router.get("/auth/login", summary="Iniciar sesión con Azure AD")
async def login(request: Request):
    return RedirectResponse(url=auth_service.build_auth_url(request))

@router.get("/auth/debug", summary="Debug redirect URI")
async def debug_auth(request: Request):
    return {"redirect_uri": auth_service.get_redirect_uri(request), "site_url": settings.site_url}


@router.get("/auth/callback", summary="Callback de Azure AD")
async def callback(request: Request):
    code = request.query_params.get("code")
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Login fallido: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="No se recibió el código de autorización")

    user = auth_service.exchange_code(code, request)
    session_token = auth_service.create_session_token(user)
    response = RedirectResponse(url="/ui/profile")
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session_token,
        httponly=True,
        secure=(settings.environment != "development"),
        samesite="lax",
        max_age=60 * 60 * 8,
        path="/",
    )
    return response


@router.get("/auth/logout", summary="Cerrar sesión")
async def logout():
    response = RedirectResponse(url="/ui/login")
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return response
