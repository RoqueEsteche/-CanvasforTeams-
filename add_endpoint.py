import sys

with open('Backend/app/routers/excel.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find("class DiplomadosUrlRequest(BaseModel):")
idx_end = content.find("class PreviewResponse", idx)

new_models = '''
class UrlOnlyRequest(BaseModel):
    url: str
'''

content = content[:idx_end] + new_models + content[idx_end:]

idx_preview = content.find("@router.post(\"/excel/diplomados/preview\"")

new_sheets_endpoints = '''
@router.post("/excel/diplomados/sheets", response_model=list[str])
async def get_diplomados_sheets(req: UrlOnlyRequest) -> list[str]:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL invalida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        sheets_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudieron cargar las pestanas. {e}")

    values = sheets_data.get("value", [])
    return [s.get("name") for s in values if s.get("name")]

@router.post("/excel/egreso/sheets", response_model=list[str])
async def get_egreso_sheets(req: UrlOnlyRequest) -> list[str]:
    if not req.url or "http" not in req.url:
        raise HTTPException(status_code=400, detail="URL invalida.")
    
    encoded_url = _encode_share_url(req.url)
    try:
        sheets_data = await graph.get(f"/shares/{encoded_url}/driveItem/workbook/worksheets")
    exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudieron cargar las pestanas. {e}")

    values = sheets_data.get("value", [])
    return [s.get("name") for s in values if s.get("name")]
'''

content = content[:idx_preview] + new_sheets_endpoints + content[idx_preview:]

with open('Backend/app/routers/excel.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added sheets endpoints")
