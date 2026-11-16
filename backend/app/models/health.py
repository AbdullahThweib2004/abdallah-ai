from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.content import KnowledgeBaseHealth


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    version: str
    knowledge_base: KnowledgeBaseHealth
    approved_documents: int
