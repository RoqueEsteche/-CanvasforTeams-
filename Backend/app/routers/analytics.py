import logging
import asyncio
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from app.services import canvas_client, teams_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/licenses", summary="Obtener consumo de licencias M365")
async def get_licenses() -> Dict[str, Any]:
    """Obtiene información sobre licencias A1, A3, etc."""
    try:
        skus = await teams_client.get_subscribed_skus()
        
        license_data = []
        for sku in skus:
            # skuPartNumber suele ser 'STANDARDWOFFPACK_FACULTY' (A1), etc.
            consumed = sku.get("consumedUnits", 0)
            prepaid = sku.get("prepaidUnits", {}).get("enabled", 0)
            available = max(0, prepaid - consumed)
            
            license_data.append({
                "skuId": sku.get("skuId"),
                "skuPartNumber": sku.get("skuPartNumber"),
                "consumed": consumed,
                "prepaid": prepaid,
                "available": available,
                "capabilityStatus": sku.get("capabilityStatus")
            })
            
        return {"status": "success", "licenses": license_data}
    except Exception as e:
        logger.error(f"Error obteniendo licencias: {e}")
        raise HTTPException(status_code=500, detail="Error al consultar licencias de Microsoft 365")

@router.get("/orphans", summary="Detectar cuentas huérfanas")
async def get_orphaned_accounts() -> Dict[str, Any]:
    """
    Compara de forma básica los usuarios activos en Canvas contra Teams.
    Para no demorar demasiado, solo analiza una muestra o se debe llamar periódicamente.
    """
    try:
        # Obtener primeros 100 usuarios de Canvas
        canvas_users = await canvas_client.get("/accounts/1/users", params={"per_page": 100, "sort": "last_login"})
        
        # Obtener 100 usuarios de Teams
        teams_users = await teams_client.get("/users", params={"$top": 100, "$select": "id,userPrincipalName,employeeId"})
        
        # Extraer correos / IDs
        canvas_emails = {u.get("login_id", "").lower() for u in canvas_users if u.get("login_id")}
        teams_upns = {u.get("userPrincipalName", "").lower() for u in teams_users.get("value", []) if u.get("userPrincipalName")}
        
        # Simulación de detección: (En un sistema real iteraríamos toda la DB local)
        canvas_only = list(canvas_emails - teams_upns)
        teams_only = list(teams_upns - canvas_emails)
        
        return {
            "status": "success",
            "orphaned_in_canvas_sample": canvas_only[:10],
            "orphaned_in_teams_sample": teams_only[:10],
            "total_canvas_analyzed": len(canvas_emails),
            "total_teams_analyzed": len(teams_upns)
        }
    except Exception as e:
        logger.error(f"Error detectando huérfanos: {e}")
        raise HTTPException(status_code=500, detail="Error en el análisis de cuentas")
