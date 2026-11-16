from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.models.content import (
    ContactResponse,
    ErrorResponse,
    ProfileResponse,
    ProjectDetail,
    ProjectSummary,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(tags=["content"])

UNAVAILABLE = "Portfolio content is temporarily unavailable."
UNAVAILABLE_RESPONSE = {status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}}


def get_knowledge_service(request: Request) -> KnowledgeService:
    service: KnowledgeService | None = request.app.state.knowledge
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=UNAVAILABLE)
    return service


Knowledge = Annotated[KnowledgeService, Depends(get_knowledge_service)]


@router.get("/profile", response_model=ProfileResponse, responses=UNAVAILABLE_RESPONSE)
def get_profile(knowledge: Knowledge) -> ProfileResponse:
    if knowledge.profile is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=UNAVAILABLE)
    return knowledge.profile


@router.get("/projects", response_model=list[ProjectSummary], responses=UNAVAILABLE_RESPONSE)
def list_projects(knowledge: Knowledge) -> list[ProjectSummary]:
    return knowledge.list_projects()


@router.get(
    "/projects/{project_id}",
    response_model=ProjectDetail,
    responses={**UNAVAILABLE_RESPONSE, status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def get_project(
    knowledge: Knowledge,
    project_id: Annotated[str, Path(max_length=100, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")],
) -> ProjectDetail:
    project = knowledge.get_project(project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.get("/contact", response_model=ContactResponse, responses=UNAVAILABLE_RESPONSE)
def get_contact(knowledge: Knowledge) -> ContactResponse:
    return knowledge.contact()
