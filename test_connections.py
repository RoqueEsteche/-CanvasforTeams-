"""
Verifica la conexión con Canvas LMS y Microsoft Graph.
Uso: python test_connections.py

Las credenciales se leen del archivo .env en la misma carpeta.
Copia .env.example → .env y rellena los valores antes de ejecutar.
"""
import asyncio
import os
import httpx
import msal
from dotenv import load_dotenv

load_dotenv()

CANVAS_BASE  = os.environ["CANVAS_BASE_URL"]
CANVAS_TOKEN = os.environ["CANVAS_ACCESS_TOKEN"]
AZURE_TENANT = os.environ["AZURE_TENANT_ID"]
AZURE_CLIENT = os.environ["AZURE_CLIENT_ID"]
AZURE_SECRET = os.environ["AZURE_CLIENT_SECRET"]

SEP = "-" * 60


async def test_canvas():
    print(f"\n{'='*60}")
    print("CANVAS LMS")
    print(SEP)
    headers = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{CANVAS_BASE}/api/v1/users/self", headers=headers)
        if r.status_code == 200:
            me = r.json()
            print(f"OK  /users/self  id={me.get('id')}  name={me.get('name')}")
        else:
            print(f"ERR /users/self  {r.status_code}: {r.text[:200]}")
            return

        r = await c.get(f"{CANVAS_BASE}/api/v1/accounts", headers=headers)
        if r.status_code == 200:
            for a in r.json():
                print(f"OK  Account  id={a['id']}  name={a['name']}")
        else:
            print(f"ERR /accounts  {r.status_code}: {r.text[:200]}")

        r = await c.get(f"{CANVAS_BASE}/api/v1/accounts/1/courses",
                        headers=headers, params={"per_page": 5})
        if r.status_code == 200:
            for co in r.json()[:3]:
                print(f"OK  Course  id={co['id']}  name={co.get('name')}")
        else:
            print(f"ERR /courses  {r.status_code}: {r.text[:200]}")


async def test_azure():
    print(f"\n{'='*60}")
    print("MICROSOFT GRAPH / AZURE AD")
    print(SEP)
    msal_app = msal.ConfidentialClientApplication(
        client_id=AZURE_CLIENT, client_credential=AZURE_SECRET,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT}")
    result = msal_app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        print(f"ERR Token: {result.get('error_description')}"); return
    print(f"OK  Token Azure (expires={result.get('expires_in')}s)")

    headers = {"Authorization": f"Bearer {result['access_token']}"}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://graph.microsoft.com/v1.0/organization", headers=headers)
        if r.status_code == 200:
            for o in r.json().get("value", []):
                print(f"OK  Tenant: {o.get('displayName')}")
        else:
            print(f"ERR /organization  {r.status_code}: {r.text[:200]}")

        r = await c.get("https://graph.microsoft.com/v1.0/users", headers=headers,
                        params={"$top": 5, "$select": "displayName,userPrincipalName"})
        if r.status_code == 200:
            for u in r.json().get("value", []):
                print(f"OK  User: {u.get('displayName')}  <{u.get('userPrincipalName')}>")
        else:
            print(f"ERR /users  {r.status_code}: {r.text[:200]}")


async def main():
    print("Canvas & Teams Connection Test")
    await test_canvas()
    await test_azure()
    print(f"\n{'='*60}\nListo.\n")

if __name__ == "__main__":
    asyncio.run(main())
