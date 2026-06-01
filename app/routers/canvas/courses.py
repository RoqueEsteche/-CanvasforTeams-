"""Canvas course management endpoints."""
import asyncio
import logging
from typing import Annotated
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import cache as _cache, database
from app.core.config import settings
from app.models.canvas import (
    BulkCanvasCourseCreate,
    BulkResult,
    CanvasCourseCreate,
    CanvasCourseUpdate,
)
from app.services import canvas_client as canvas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canvas/courses", tags=["Canvas · Courses"])
_ACCOUNT = settings.canvas_account_id

# TTL de 5 min para la lista de cursos (datos que cambian poco)
_COURSES_TTL = 300


def _courses_cache_key(search_term: str | None, state_key: str, per_page: int) -> str:
    return f"canvas:courses:{search_term or ''}:{state_key}:{per_page}"


@router.get("", summary="Listar cursos de la cuenta")
async def list_courses(
    search_term: Annotated[str | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
):
    state_key = ",".join(sorted(state)) if state else ""
    cache_key = _courses_cache_key(search_term, state_key, per_page)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # Serve from local DB if data is fresh (avoids Canvas API round-trip)
    if not await database.is_stale("canvas_courses") and await database.count_courses() > 0:
        db_result = await database.get_courses(search_term)
        if db_result:
            _cache.set(cache_key, db_result, ttl=_COURSES_TTL)
            return db_result

    params: dict = {"per_page": per_page}
    if search_term:
        params["search_term"] = search_term
    if state:
        params["state[]"] = state
    result = await canvas.paginate_limited(f"/accounts/{_ACCOUNT}/courses", params, max_records=1000)
    await database.upsert_courses(result)
    await database.mark_synced("canvas_courses")
    _cache.set(cache_key, result, ttl=_COURSES_TTL)
    return result


@router.get("/{course_id}", summary="Obtener curso por ID")
async def get_course(course_id: str):
    try:
        return await canvas.get(f"/courses/{course_id}")
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201, summary="Crear curso individual")
async def create_course(body: CanvasCourseCreate):
    payload: dict = {
        "course": {
            "name": body.name,
            "course_code": body.course_code,
            "sis_course_id": body.sis_course_id,
            "start_at": body.start_at,
            "end_at": body.end_at,
            "license": body.license,
            "is_public": body.is_public,
        }
    }
    if body.enroll_me:
        payload["enroll_me"] = True
    try:
        return await canvas.post(f"/accounts/{_ACCOUNT}/courses", payload)
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bulk", summary="Crear cursos de forma masiva")
async def create_courses_bulk(body: BulkCanvasCourseCreate) -> BulkResult:
    result = BulkResult()

    async def _create(course: CanvasCourseCreate):
        try:
            data = await canvas.post(
                f"/accounts/{_ACCOUNT}/courses",
                {"course": {
                    "name": course.name,
                    "course_code": course.course_code,
                    "sis_course_id": course.sis_course_id,
                    "start_at": course.start_at,
                    "end_at": course.end_at,
                }},
            )
            result.succeeded.append(data)
        except Exception as exc:
            result.failed.append({"input": course.model_dump(), "error": str(exc)})

    await asyncio.gather(*[_create(c) for c in body.courses])
    return result


@router.put("/{course_id}", summary="Actualizar curso")
async def update_course(course_id: str, body: CanvasCourseUpdate):
    fields = body.model_dump(exclude_none=True)
    try:
        return await canvas.put(f"/courses/{course_id}", {"course": fields})
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{course_id}", summary="Eliminar / concluir curso")
async def delete_course(
    course_id: str,
    event: Annotated[str, Query(description="delete | conclude")] = "conclude",
):
    try:
        result = await canvas.delete(f"/courses/{course_id}", {"event": event})
        await database.delete_course(course_id)
        _cache.invalidate("canvas:courses:")
        return result
    except StarletteHTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{course_id}/attendance", summary="Obtener matriz de asistencias en formato planilla")
async def get_attendance(course_id: str):
    """Obtiene matriz de asistencias desde Canvas Roll Call Attendance.

    Devuelve los datos en formato planilla Excel:
    - Nombre del curso e instructor
    - Fechas de asistencia registradas
    - Matriz de estudiantes x fechas con estados de asistencia
    """
    logger.info(f"GET /courses/{course_id}/attendance - obteniendo asistencias")

    try:
        # 1. Obtener información del curso
        course = await canvas.get(f"/courses/{course_id}")
        course_name = course.get("name", f"Curso {course_id}")

        # 2. Obtener instructor del curso
        enrollments_all = await canvas.paginate_limited(
            f"/courses/{course_id}/enrollments",
            {"per_page": 100, "type": "TeacherEnrollment"},
            max_records=100
        )
        instructor_name = ""
        if enrollments_all:
            teacher = enrollments_all[0].get("user", {})
            instructor_name = teacher.get("name", "")

        # 3. Obtener estudiantes activos
        enrollments = await canvas.paginate_limited(
            f"/courses/{course_id}/enrollments",
            {"per_page": 100},
            max_records=1000
        )

        student_enrollments = [
            e for e in enrollments
            if e.get("type") == "StudentEnrollment" and
               e.get("enrollment_state") in ["active", "completed"]
        ]
        logger.info(f"Filtrados {len(student_enrollments)} estudiantes")

        students_map = {}
        student_ids = set()
        for enrollment in student_enrollments:
            user_id = enrollment.get("user_id")
            user = enrollment.get("user", {})
            if user_id:
                students_map[user_id] = {
                    "id": user_id,
                    "name": user.get("name", f"Usuario {user_id}"),
                    "login": user.get("login", ""),
                }
                student_ids.add(user_id)

        # 4. Obtener todas las asignaciones
        assignments = await canvas.paginate_limited(
            f"/courses/{course_id}/assignments",
            {"per_page": 100},
            max_records=200
        )
        logger.info(f"Obtuvo {len(assignments)} asignaciones")

        # 5. Buscar la asignación de Roll Call Attendance
        attendance_assignment = None
        for assignment in assignments:
            name = assignment.get("name", "").lower()
            if "attendance" in name or "roll call" in name or "asistencia" in name:
                attendance_assignment = assignment
                logger.info(f"Encontrada asignacion de asistencia: {assignment.get('name')} (ID: {assignment.get('id')})")
                break

        # 6. Obtener submisiones de asistencia
        attendance_by_student_date = {}  # {user_id: {date: score}}
        submission_dates = []

        if attendance_assignment:
            assignment_id = attendance_assignment.get("id")

            submissions = await canvas.paginate_limited(
                f"/courses/{course_id}/assignments/{assignment_id}/submissions",
                {"per_page": 100},
                max_records=1000
            )
            logger.info(f"Obtuvo {len(submissions)} submisiones de attendance")

            for submission in submissions:
                user_id = submission.get("user_id")
                if not user_id or user_id not in student_ids:
                    continue

                try:
                    score = submission.get("score")
                    submitted_at = submission.get("submitted_at") or submission.get("updated_at")

                    if submitted_at and isinstance(submitted_at, str):
                        date_str = submitted_at.split("T")[0]
                        if date_str not in submission_dates:
                            submission_dates.append(date_str)

                        # Guardar el score/porcentaje por estudiante y fecha
                        if str(user_id) not in attendance_by_student_date:
                            attendance_by_student_date[str(user_id)] = {}

                        attendance_by_student_date[str(user_id)][date_str] = score
                        logger.debug(f"Usuario {user_id}: score={score}% en {date_str}")
                except Exception as e:
                    logger.error(f"Error procesando submission {user_id}: {e}")

        # 7. Ordenar fechas
        attendance_dates = sorted(submission_dates) if submission_dates else []

        # 8. Construir matriz de asistencia en formato planilla
        # Formato: {student_id: {date1: status, date2: status, ...}}
        attendance_matrix = {}
        for user_id in student_ids:
            attendance_matrix[str(user_id)] = {}

            # Si tiene datos de score, convertir a estado (P/A/L/E)
            if str(user_id) in attendance_by_student_date:
                dates_data = attendance_by_student_date[str(user_id)]
                for date in attendance_dates:
                    score = dates_data.get(date)
                    if score is not None:
                        # Convertir score a estado de asistencia
                        # Usar umbral inteligente: >= 80% = Presente
                        if isinstance(score, (int, float)):
                            attendance_matrix[str(user_id)][date] = "P" if score >= 80 else "A"
                        else:
                            attendance_matrix[str(user_id)][date] = str(score)
                    else:
                        attendance_matrix[str(user_id)][date] = ""

        logger.info(f"Matriz con {len(attendance_matrix)} estudiantes x {len(attendance_dates)} fechas")

        return {
            "course": {
                "id": int(course_id),
                "name": course_name,
                "instructor": instructor_name,
            },
            "attendance_dates": attendance_dates,
            "students": [
                {
                    **students_map[uid],
                    "attendance": attendance_matrix.get(str(uid), {date: "" for date in attendance_dates})
                }
                for uid in sorted(student_ids)
            ],
            "summary": {
                "total_students": len(student_ids),
                "total_dates": len(attendance_dates),
                "has_attendance_data": bool(attendance_assignment),
            }
        }

    except StarletteHTTPException:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        logger.error(f"Error en attendance (tipo incorrecto): {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error procesando datos: {str(exc)}")
    except Exception as exc:
        logger.error(f"Error inesperado en attendance: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error obteniendo asistencias: {str(exc)}")

