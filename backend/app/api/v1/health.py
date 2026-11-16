from fastapi import APIRouter, Request

from app.core.version import VERSION
from app.models.health import HealthResponse
from app.services.knowledge_service import KnowledgeService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    # The API itself stays healthy even when the knowledge base failed to load.
    knowledge: KnowledgeService | None = request.app.state.knowledge
    return HealthResponse(
        status="ok",
        version=VERSION,
        knowledge_base="ok" if knowledge is not None else "error",
        approved_documents=knowledge.approved_documents if knowledge is not None else 0,
    )
