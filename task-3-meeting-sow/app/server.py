from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.orchestrator import PipelineOrchestrator
from app.models import ProjectScope, ScopeChangeSet


class CreateMeetingRequest(BaseModel):
    transcript: str = Field(min_length=5, description="Raw meeting transcript dialogue")
    project_id: str | None = None


class FollowUpMeetingRequest(BaseModel):
    transcript: str = Field(min_length=5, description="Follow-up meeting transcript dialogue")


class ApproveScopeRequest(BaseModel):
    approved_by: str = Field(min_length=1, description="Human approver name or identifier")


def create_app(orchestrator: PipelineOrchestrator | None = None) -> FastAPI:
    app = FastAPI(
        title="Meeting-to-Scope & Proposal Service",
        description="Autonomous multi-agent pipeline converting meeting transcripts into structured SOWs.",
        version="1.0.0",
    )
    orch = orchestrator or PipelineOrchestrator()

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": "task-3-meeting-sow"}

    @app.post("/api/v1/projects/from-meeting", response_model=ProjectScope)
    async def create_project(req: CreateMeetingRequest):
        try:
            scope = await orch.create_project_from_meeting(
                transcript=req.transcript, project_id=req.project_id
            )
            return scope
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err))

    @app.post("/api/v1/projects/{project_id}/follow-up")
    async def process_follow_up(project_id: str, req: FollowUpMeetingRequest):
        try:
            scope, changes = await orch.process_follow_up(
                project_id=project_id, follow_up_transcript=req.transcript
            )
            return {"scope": scope, "changes": changes}
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err))

    @app.get("/api/v1/projects/{project_id}/scope", response_model=ProjectScope)
    def get_scope(project_id: str):
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        return scope

    @app.post("/api/v1/projects/{project_id}/proposal")
    def get_proposal(project_id: str):
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        return {
            "project_id": scope.project_id,
            "version": scope.version,
            "client_ready": scope.client_ready,
            "proposal_markdown": scope.proposal_markdown,
        }

    @app.post("/api/v1/projects/{project_id}/approve", response_model=ProjectScope)
    def approve_scope(project_id: str, req: ApproveScopeRequest):
        try:
            scope = orch.approve_scope(project_id=project_id, approved_by=req.approved_by)
            return scope
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err))

    return app


app = create_app()
