from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


# ── Users ────────────────────────────────────────────────────────────────────

class CanvasUserCreate(BaseModel):
    name: str = Field(..., examples=["Juan García"])
    short_name: Optional[str] = None
    sortable_name: Optional[str] = None
    email: EmailStr
    login_id: str = Field(..., examples=["jgarcia"])
    password: Optional[str] = None
    sis_user_id: Optional[str] = None
    send_confirmation: bool = False


class CanvasUserUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    email: Optional[EmailStr] = None
    login_id: Optional[str] = None
    sis_user_id: Optional[str] = None


# ── Courses ───────────────────────────────────────────────────────────────────

class CanvasCourseCreate(BaseModel):
    name: str = Field(..., examples=["Matemáticas I"])
    course_code: Optional[str] = Field(None, examples=["MAT-001"])
    sis_course_id: Optional[str] = None
    start_at: Optional[str] = None   # ISO 8601
    end_at: Optional[str] = None
    license: Optional[str] = "public_domain"
    is_public: bool = False
    enroll_me: bool = False


class CanvasCourseUpdate(BaseModel):
    name: Optional[str] = None
    course_code: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    workflow_state: Optional[Literal["unpublished", "available", "completed", "deleted"]] = None


# ── Enrollments ───────────────────────────────────────────────────────────────

EnrollmentType = Literal[
    "StudentEnrollment", "TeacherEnrollment", "TaEnrollment",
    "DesignerEnrollment", "ObserverEnrollment"
]


class CanvasEnrollmentCreate(BaseModel):
    user_id: str = Field(..., examples=["123"])
    type: EnrollmentType = "StudentEnrollment"
    enrollment_state: Literal["active", "invited", "inactive"] = "active"
    notify: bool = False
    role_id: Optional[str] = None
    course_section_id: Optional[str] = None


class CanvasEnrollmentDelete(BaseModel):
    task: Literal["delete", "conclude", "deactivate", "inactivate"] = "conclude"


# ── Groups ────────────────────────────────────────────────────────────────────

class CanvasGroupCreate(BaseModel):
    name: str = Field(..., examples=["Grupo A"])
    description: Optional[str] = None
    is_public: bool = False
    join_level: Literal["parent_context_auto_join", "parent_context_request", "invitation_only"] = "invitation_only"
    sis_group_id: Optional[str] = None


class CanvasGroupMemberCreate(BaseModel):
    user_id: str = Field(..., examples=["1"])
    role: Literal["member", "owner"] = "member"


class CanvasGroupMemberAdd(BaseModel):
    user_ids: list[str] = Field(..., examples=[["1", "2", "3"]])
    role: Literal["member", "owner"] = "member"


# ── Bulk helpers ─────────────────────────────────────────────────────────────

class BulkCanvasUserCreate(BaseModel):
    users: list[CanvasUserCreate]


class BulkCanvasCourseCreate(BaseModel):
    courses: list[CanvasCourseCreate]


class BulkCanvasEnrollmentCreate(BaseModel):
    course_id: str
    enrollments: list[CanvasEnrollmentCreate]


class BulkCanvasEnrollmentDelete(BaseModel):
    course_id: str
    enrollment_ids: list[str]
    task: Literal["delete", "conclude", "deactivate", "inactivate"] = "conclude"


class BulkResult(BaseModel):
    succeeded: list[dict] = []
    failed: list[dict] = []
