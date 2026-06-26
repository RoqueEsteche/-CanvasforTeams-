"""Email sender via Microsoft Graph API (sendMail).

Three HTML templates matching the institutional Word templates:
  - grado     → Plantilla_GA_Grado   (IT Dept, Teams + Canvas)
  - mba       → Plantilla_MBA        (UBS Business School MBA)
  - diplomado → Plantilla_UBS_Diplomado (UBS, Teams only, program name required)

Requires 'Mail.Send' application permission on the Azure app registration.
"""
import base64
import httpx
from pathlib import Path

from app.core.config import settings
from app.services import teams_client as graph

# ── Common style constants ────────────────────────────────────────────────────

_BASE_CSS = "font-family:'Segoe UI',Arial,sans-serif;background:#f4f6fb;margin:0;padding:0;"
_WRAP_CSS  = "background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.09);overflow:hidden;max-width:600px;margin:0 auto;"

_CANVAS_URL = "https://usilparaguay.instructure.com/login/canvas"
_TEAMS_URL  = "https://teams.cloud.microsoft/"

_IT_CONTACT = """
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px;font-size:.82rem;color:#4a5568;">
  <tr><td colspan="2" style="font-weight:700;padding-bottom:6px;color:#2d3748;">Contacto – Dpto. IT</td></tr>
  <tr><td style="padding:2px 0;">✉ Correo</td><td style="padding:2px 8px;"><a href="mailto:it@usil.edu.py">it@usil.edu.py</a> | <a href="mailto:resteche@usil.edu.py">resteche@usil.edu.py</a></td></tr>
  <tr><td style="padding:2px 0;">📱 WhatsApp</td><td style="padding:2px 8px;">+595 991 856 488 | +595 992 298 599</td></tr>
  <tr><td style="padding:2px 0;">☎ Teléfono</td><td style="padding:2px 8px;">+595 21 282 801 | 282 806 | 297 085</td></tr>
  <tr><td style="padding:2px 0;">📍 Dirección</td><td style="padding:2px 8px;">Av. Venezuela Nro. 2087 c/ Av. Artigas – Asunción</td></tr>
</table>
"""

_UBS_CONTACT = """
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px;font-size:.82rem;color:#4a5568;">
  <tr><td colspan="2" style="padding-bottom:6px;color:#2d3748;">En caso de inconvenientes con el acceso a Teams, puede contactar al área de Tecnología de la Información (TI):</td></tr>
  <tr><td style="padding:2px 0;">✉ Correo</td><td style="padding:2px 8px;"><a href="mailto:lflorentin@usil.edu.py">lflorentin@usil.edu.py</a></td></tr>
  <tr><td style="padding:2px 0;">✉ Correo</td><td style="padding:2px 8px;"><a href="mailto:glezcano@usil.edu.py">glezcano@usil.edu.py</a></td></tr>
  <tr><td style="padding:2px 0;">✉ Correo</td><td style="padding:2px 8px;"><a href="mailto:resteche@usil.edu.py">resteche@usil.edu.py</a></td></tr>
  <tr><td style="padding:2px 0;">📱 WhatsApp corporativo</td><td style="padding:2px 8px;"><a href="https://wa.me/595991856488" style="color:#4e73df;text-decoration:none;font-weight:bold;">0991 856 488</a></td></tr>
</table>
<p style="color:#4a5568;font-size:.85rem;margin-top:16px;">
  Quedamos atentos a cualquier consulta relacionada con TI y le deseamos mucho éxito en sus estudios.<br><br>
  <strong>Área de Tecnología de la Información (TI UBS)</strong><br>
  USIL Business School – Universidad San Ignacio de Loyola<br>
  Correo: lflorentin@usil.edu.py | glezcano@usil.edu.py | resteche@usil.edu.py<br>
  WhatsApp corporativo: 0991 856 488
</p>
"""


def _cred_table(usuario: str, contrasena: str) -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#f8f9fc;border-radius:8px;border:1px solid #e3e6f0;margin:12px 0;">
  <tr>
    <td style="color:#6c757d;font-size:.85rem;padding:8px 14px;">Usuario</td>
    <td style="font-weight:700;font-size:.92rem;padding:8px 14px;color:#2d3748;">{usuario}</td>
  </tr>
  <tr style="border-top:1px solid #e3e6f0;">
    <td style="color:#6c757d;font-size:.85rem;padding:8px 14px;">Contraseña</td>
    <td style="font-family:monospace;font-size:.98rem;font-weight:700;padding:8px 14px;color:#4e73df;">{contrasena}</td>
  </tr>
</table>"""


def _platform_btn(label: str, url: str, color: str) -> str:
    return (f'<a href="{url}" style="display:inline-block;background:{color};color:#fff;'
            f'padding:10px 22px;border-radius:6px;text-decoration:none;font-weight:bold;'
            f'font-size:.88rem;margin:4px 6px 4px 0;">{label}</a>')


def _warning_box(text: str) -> str:
    return (f'<p style="color:#e74a3b;font-size:.82rem;background:#fff5f5;'
            f'border-left:4px solid #e74a3b;padding:10px 14px;border-radius:4px;margin:14px 0;">'
            f'<strong>Importante:</strong> {text}</p>')


def _footer_note(text: str) -> str:
    return (f'<hr style="border:none;border-top:1px solid #e3e6f0;margin:20px 0;">'
            f'<p style="color:#a0aec0;font-size:.75rem;text-align:center;">{text}</p>')


# ── Template: GA Grado ────────────────────────────────────────────────────────

def _html_grado(full_name: str, usuario: str, contrasena: str) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"></head>
<body style="{_BASE_CSS}">
<div style="{_WRAP_CSS}">
  <div style="background:#1a2035;padding:28px 36px;">
    <h1 style="color:#fff;margin:0;font-size:1.2rem;">Universidad San Ignacio de Loyola</h1>
    <p style="color:rgba(255,255,255,.7);margin:6px 0 0;font-size:.88rem;">
      ¡Bienvenido/a! – Credenciales de Acceso a Plataformas Virtuales
    </p>
  </div>
  <div style="padding:30px 36px;">
    <p style="font-size:1rem;color:#2d3748;">¡Bienvenido/a, <strong>{full_name}</strong>!</p>
    <p style="color:#4a5568;font-size:.9rem;">
      Antes que nada, ¡felicitaciones! Esperamos que este nuevo semestre esté lleno de éxitos y
      nuevos logros. A continuación encontrarás tus credenciales para acceder a los recursos
      virtuales de la universidad.
    </p>

    <p style="font-weight:700;color:#2d3748;margin-bottom:4px;">🖥 Tus credenciales de acceso</p>
    {_cred_table(usuario, contrasena)}
    {_warning_box("Por seguridad, cambiá tu contraseña en tu primer inicio de sesión.")}

    <p style="font-weight:700;color:#2d3748;margin:16px 0 8px;">Plataformas disponibles</p>

    <p style="color:#4a5568;font-size:.88rem;margin:0 0 4px;">
      <strong>Microsoft Teams</strong> — Clases virtuales, grabaciones y comunicación con docentes
    </p>
    {_platform_btn("Acceder a Microsoft Teams", _TEAMS_URL, "#6264A7")}

    <p style="color:#4a5568;font-size:.88rem;margin:14px 0 4px;">
      <strong>Canvas LMS</strong> — Materiales académicos, tareas y calificaciones
    </p>
    {_platform_btn("Acceder a Canvas LMS", _CANVAS_URL, "#E66000")}

    <p style="color:#4a5568;font-size:.85rem;margin-top:16px;">
      En adjunto encontrarás instructivos paso a paso para acceder a cada plataforma sin inconvenientes.
    </p>

    {_IT_CONTACT}
    {_footer_note("No dudes en contactarnos si tenés alguna consulta. ¡Mucho éxito en tu semestre! &bull; Este mensaje fue generado automáticamente.")}
  </div>
</div>
</body></html>"""


# ── Template: MBA ─────────────────────────────────────────────────────────────

def _html_mba(full_name: str, usuario: str, contrasena: str) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"></head>
<body style="{_BASE_CSS}">
<div style="{_WRAP_CSS}">
  <div style="background:#0a1628;padding:28px 36px;">
    <p style="color:rgba(255,255,255,.5);font-size:.75rem;margin:0 0 4px;text-transform:uppercase;letter-spacing:.1em;">USIL Business School</p>
    <h1 style="color:#fff;margin:0;font-size:1.15rem;">Programa Master in Business Administration (MBA)</h1>
  </div>
  <div style="padding:30px 36px;">
    <p style="font-size:1rem;color:#2d3748;font-weight:600;">Bienvenido/a al Programa MBA</p>
    <p style="color:#4a5568;font-size:.9rem;">Estimado/a <strong>{full_name}</strong>,</p>
    <p style="color:#4a5568;font-size:.9rem;">
      Nos complace darle la bienvenida al inicio de sus actividades académicas en el <strong>MBA</strong>,
      perteneciente a la USIL Business School (UBS). Este programa ha sido diseñado para potenciar sus
      capacidades de liderazgo, fortalecer su visión estratégica y acompañarle en su desarrollo profesional.
    </p>
    <p style="color:#4a5568;font-size:.9rem;margin-bottom:4px;">
      A continuación encontrará sus credenciales de acceso a las plataformas institucionales:
    </p>

    <p style="font-weight:700;color:#2d3748;margin:16px 0 4px;">Microsoft Teams</p>
    {_cred_table(usuario, contrasena)}
    {_platform_btn("Acceder a Microsoft Teams", _TEAMS_URL, "#6264A7")}

    <p style="font-weight:700;color:#2d3748;margin:16px 0 4px;">Canvas LMS</p>
    {_cred_table(usuario, contrasena)}
    {_platform_btn("Acceder a Canvas LMS", _CANVAS_URL, "#E66000")}

    <div style="background:#fffbea;border:1px solid #f6d860;border-radius:6px;padding:12px 16px;margin:16px 0;font-size:.85rem;color:#4a5568;">
      ★ Verifique el acceso a ambas plataformas antes del inicio de clases para garantizar
      una experiencia académica fluida desde el primer día.
    </div>

    {_UBS_CONTACT}
    {_footer_note("Este mensaje fue generado por el Departamento de Tecnología de USIL Paraguay.")}
  </div>
</div>
</body></html>"""


# ── Template: UBS Diplomado ───────────────────────────────────────────────────

def _html_diplomado(full_name: str, usuario: str, contrasena: str,
                    program_name: str) -> str:
    prog_display = program_name or "Diplomado USIL Business School"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"></head>
<body style="{_BASE_CSS}">
<div style="{_WRAP_CSS}">
  <div style="background:#0a1628;padding:28px 36px;">
    <p style="color:rgba(255,255,255,.5);font-size:.75rem;margin:0 0 4px;text-transform:uppercase;letter-spacing:.1em;">USIL Business School</p>
    <h1 style="color:#fff;margin:0;font-size:1.1rem;">Credenciales de Acceso a Plataformas Virtuales</h1>
  </div>
  <div style="padding:30px 36px;">
    <p style="color:#4a5568;font-size:.9rem;">Estimado/a <strong>{full_name}</strong>,</p>
    <p style="color:#4a5568;font-size:.9rem;">Le damos la bienvenida a la <strong>USIL Business School (UBS)</strong>.</p>

    <div style="background:#f0f4ff;border-radius:8px;padding:14px 18px;margin:12px 0;font-size:.9rem;color:#2d3748;">
      Usted se encuentra inscrito/a en: <strong>{prog_display}</strong>
    </div>

    <p style="font-weight:700;color:#2d3748;margin:16px 0 4px;">Microsoft Teams</p>
    <p style="color:#4a5568;font-size:.85rem;margin:0 0 6px;">
      La plataforma oficial para sus clases virtuales, materiales académicos y comunicación con docentes.
    </p>
    {_cred_table(usuario, contrasena)}
    {_platform_btn("Acceder a Microsoft Teams", _TEAMS_URL, "#6264A7")}

    {_warning_box("Las contraseñas proporcionadas son directamente generadas por el departamento de tecnologia, ante cualquier error en su cuenta, comuniquese con IT.")}

    <p style="color:#4a5568;font-size:.85rem;margin-top:12px;">
      Adjunto encontrará los instructivos de Teams.
    </p>

    {_UBS_CONTACT}
    {_footer_note("Este mensaje fue generado automáticamente por el Área de Tecnología – USIL Paraguay.")}
  </div>
</div>
</body></html>"""


# ── Public API ────────────────────────────────────────────────────────────────

def get_program_attachments(program_type: str) -> list[str]:
    """Escanea dinámicamente la carpeta de adjuntos según el tipo de programa."""
    base_dir = Path(__file__).parent.parent.parent / "Archivos para los correos"
    if not base_dir.exists():
        return []
        
    mapping = {
        "diplomado": "Diplomados (UBS - USIL Business School)",
        "mba": "MBA",
        "grado": "Grado"
    }
    
    target_folder = mapping.get(program_type)
    if not target_folder:
        return []
        
    target_dir = base_dir / target_folder
    if not target_dir.exists():
        return []
        
    files = []
    for f in target_dir.iterdir():
        if f.is_file():
            files.append(str(f))
    return files

async def send_welcome_email(
    to_email: str,
    full_name: str,
    institutional_email: str,
    login_id: str,
    password: str,
    platform: str = "both",
    program_type: str = "grado",
    program_name: str = "",
    extra_cc: list[str] | None = None,
    attachments: list[str] | None = None,
):
    """Send welcome email via Microsoft Graph API using the template for program_type.

    program_type: "grado" | "mba" | "diplomado"
    program_name: specific program name shown in diplomado template.
    attachments: list of file paths to attach (only for diplomado).
    """
    sender = settings.smtp_from
    if not sender:
        raise ValueError("SMTP_FROM no está configurado en .env")

    # The login shown in the email is login_id (cedula for students, email for teachers)
    usuario = login_id

    program_labels = {
        "grado":     program_name or "Grado",
        "mba":       program_name or "MBA",
        "diplomado": program_name or "Diplomado",
    }
    label = program_labels.get(program_type, program_name or program_type)
    if program_type == "grado":
        subject = f"Credenciales de acceso – {label}"
    else:
        subject = f"Credenciales de acceso – {label} – TI UBS"

    if program_type == "mba":
        html = _html_mba(full_name, usuario, password)
    elif program_type == "diplomado":
        html = _html_diplomado(full_name, usuario, password, program_name)
    else:
        html = _html_grado(full_name, usuario, password)

    cc_addresses: list[str] = [
        e.strip() for e in settings.email_cc.split(",") if e.strip()
    ]
    if extra_cc:
        cc_addresses += [e.strip() for e in extra_cc if e.strip()]

    message: dict = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html},
        "toRecipients": [{"emailAddress": {"address": to_email}}],
        "from": {"emailAddress": {"address": sender, "name": settings.smtp_from_name}},
    }
    if cc_addresses:
        message["ccRecipients"] = [
            {"emailAddress": {"address": addr}} for addr in cc_addresses
        ]

    # Add attachments if provided
    if attachments:
        message["attachments"] = []
        for file_path in attachments:
            try:
                file_path_obj = Path(file_path)
                if file_path_obj.exists():
                    with open(file_path_obj, "rb") as f:
                        file_bytes = f.read()
                        b64_content = base64.b64encode(file_bytes).decode("utf-8")
                        message["attachments"].append({
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": file_path_obj.name,
                            "contentBytes": b64_content,
                        })
            except Exception as e:
                # Log but don't fail the entire email send
                import logging
                logging.warning(f"Failed to attach {file_path}: {e}")

    payload = {"message": message, "saveToSentItems": False}

    token = graph._get_access_token()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if r.status_code not in (200, 202):
            try:
                err = r.json().get("error", {})
                detail = err.get("message", r.text[:300])
            except Exception:
                detail = r.text[:300]
            raise RuntimeError(f"Graph sendMail {r.status_code}: {detail}")
