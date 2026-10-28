import os
import secrets
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import RedirectResponse
import httpx
from pydantic import BaseModel, Field
from app.orchestrator import PipelineOrchestrator
from app.models import ProjectScope, ScopeChangeSet

logger = logging.getLogger("Task3Server")

TASK1_URL = os.getenv("TASK1_URL", "http://127.0.0.1:8000")
INTERNAL_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")


class CreateMeetingRequest(BaseModel):
    transcript: str = Field(min_length=5, description="Raw meeting transcript dialogue")
    project_id: str | None = None


class FollowUpMeetingRequest(BaseModel):
    transcript: str = Field(min_length=5, description="Follow-up meeting transcript dialogue")


class ApproveScopeRequest(BaseModel):
    approved_by: str = Field(min_length=1, description="Human approver name or identifier")


async def get_current_user_or_service(request: Request) -> Dict[str, Any]:
    """
    Authenticates requests to Task 3:
    1. Validates X-Internal-Service-Key for internal backend calls.
    2. Validates session cookie or Bearer authorization header against Task 1.
    Rejects unauthorized requests.
    """
    internal_key = request.headers.get("x-internal-service-key")
    if internal_key:
        if INTERNAL_KEY and secrets.compare_digest(internal_key, INTERNAL_KEY):
            return {"id": "service_internal", "role": "service"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service key."
        )

    session_id = request.cookies.get("session_id")
    if not session_id:
        auth_hdr = request.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            session_id = auth_hdr[7:].strip()

    if not session_id:
        if os.getenv("ENVIRONMENT") == "production":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please sign in."
            )
        # Development fallback when no credentials are provided at all
        return {"id": "dev_user", "role": "user"}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {"Cookie": f"session_id={session_id}", "Authorization": f"Bearer {session_id}"}
            res = await client.get(f"{TASK1_URL}/api/v1/auth/me", headers=headers)
            if res.status_code == 200:
                data = res.json()
                return data.get("user", {"id": "unknown", "role": "user"})
    except Exception as e:
        logger.warning(f"Task 1 auth check error: {e}")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session has expired or is invalid. Please sign in again."
    )


def create_app(orchestrator: PipelineOrchestrator | None = None) -> FastAPI:
    app = FastAPI(
        title="Meeting-to-Scope & Proposal Service",
        description="Autonomous multi-agent pipeline converting meeting transcripts into structured SOWs.",
        version="1.0.0",
    )
    orch = orchestrator or PipelineOrchestrator()

    def check_project_access(scope: ProjectScope, caller: Dict[str, Any]):
        if caller.get("role") == "service" or caller.get("id") == "service_internal":
            return
        if scope.user_id and scope.user_id != caller.get("id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Project '{scope.project_id}' belongs to another user account."
            )

    @app.get("/")
    def root():
        return RedirectResponse(url="/docs")

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": "task-3-meeting-sow"}

    @app.post("/api/v1/projects/from-meeting", response_model=ProjectScope)
    async def create_project(
        req: CreateMeetingRequest,
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        try:
            scope = await orch.create_project_from_meeting(
                transcript=req.transcript, project_id=req.project_id, user_id=caller.get("id")
            )
            return scope
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err))

    @app.post("/api/v1/projects/{project_id}/follow-up")
    async def process_follow_up(
        project_id: str,
        req: FollowUpMeetingRequest,
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        check_project_access(scope, caller)

        try:
            updated_scope, changes = await orch.process_follow_up(
                project_id=project_id, follow_up_transcript=req.transcript
            )
            return {"scope": updated_scope, "changes": changes}
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err))

    @app.get("/api/v1/projects/{project_id}/scope", response_model=ProjectScope)
    def get_scope(
        project_id: str,
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        check_project_access(scope, caller)
        return scope

    @app.get("/api/v1/projects/{project_id}/draft-proposal")
    def get_draft_proposal(
        project_id: str,
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        """Internal view of unapproved draft proposal."""
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        check_project_access(scope, caller)
        return {
            "project_id": scope.project_id,
            "version": scope.version,
            "client_ready": scope.client_ready,
            "proposal_markdown": scope.proposal_markdown,
        }

    @app.api_route("/api/v1/projects/{project_id}/proposal", methods=["GET", "POST"])
    def get_client_proposal(
        project_id: str,
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        """
        Client-facing proposal endpoint.
        STRICT GATING: Returns HTTP 403 Forbidden if scope is not yet human-approved (client_ready=False).
        """
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        check_project_access(scope, caller)

        if not scope.client_ready:
            raise HTTPException(
                status_code=403,
                detail="Proposal is an unapproved internal draft (client_ready=False). "
                       "Explicit human approval via POST /api/v1/projects/{project_id}/approve is required before client release.",
            )

        return {
            "project_id": scope.project_id,
            "version": scope.version,
            "client_ready": scope.client_ready,
            "approved_by": scope.approved_by,
            "approved_at": scope.approved_at,
            "proposal_markdown": scope.proposal_markdown,
        }

    @app.get("/api/v1/projects")
    def list_projects(
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        """Returns all SOW projects accessible to the caller."""
        all_projects = orch.store.list_all()
        if caller.get("role") == "service" or caller.get("id") == "service_internal":
            return all_projects
        user_id = caller.get("id")
        return [p for p in all_projects if not p.user_id or p.user_id == user_id]

    @app.get("/api/v1/projects/{project_id}/export")
    def export_sow(
        project_id: str,
        format: str = "html",
        draft: bool = False,
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        """
        Exports SOW as HTML or Markdown.
        Unapproved proposals are strictly gated:
        - If client_ready is False and draft is False, returns 403 Forbidden.
        - If draft=True, exports with prominent DRAFT watermarks and banners.
        - If client_ready is True, exports finalized client-ready document with approval metadata.
        """
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        check_project_access(scope, caller)

        if not scope.client_ready and not draft:
            raise HTTPException(
                status_code=403,
                detail="Proposal is an unapproved internal draft (client_ready=False). "
                       "Explicit human approval is required before final client release. "
                       "Pass ?draft=true to export an internal draft preview."
            )

        is_draft = not scope.client_ready
        raw_markdown = scope.proposal_markdown or ""

        if format.lower() == "markdown" or format.lower() == "md":
            header = f"# DRAFT STATEMENT OF WORK (UNAPPROVED)\n\n" if is_draft else f"# FINAL STATEMENT OF WORK (APPROVED)\n# Approver: {scope.approved_by} ({scope.approved_at})\n\n"
            content = header + raw_markdown
            from fastapi.responses import Response
            return Response(
                content=content,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="{project_id}_sow{"_draft" if is_draft else ""}.md"',
                    "X-SOW-Status": "DRAFT" if is_draft else "APPROVED",
                    "X-Client-Ready": str(scope.client_ready).lower()
                }
            )

        # HTML format
        import html
        def md_to_html_simple(text: str) -> str:
            lines = text.split("\n")
            out = []
            in_table = False
            for line in lines:
                s = line.strip()
                if s.startswith("|") and s.endswith("|"):
                    if not in_table:
                        out.append('<div class="table-wrap"><table class="sow-table">')
                        in_table = True
                    cells = [c.strip() for c in s[1:-1].split("|")]
                    if all(set(c).issubset({"-", ":", " "}) for c in cells):
                        continue
                    row_html = "".join(f"<td>{html.escape(c)}</td>" for c in cells)
                    out.append(f"<tr>{row_html}</tr>")
                    continue
                else:
                    if in_table:
                        out.append("</table></div>")
                        in_table = False

                if s.startswith("### "):
                    out.append(f"<h3>{html.escape(s[4:])}</h3>")
                elif s.startswith("## "):
                    out.append(f"<h2>{html.escape(s[3:])}</h2>")
                elif s.startswith("# "):
                    out.append(f"<h1>{html.escape(s[2:])}</h1>")
                elif s.startswith("- ") or s.startswith("* "):
                    out.append(f'<li class="bullet">{html.escape(s[2:])}</li>')
                elif s:
                    out.append(f"<p>{html.escape(s)}</p>")
                else:
                    out.append("<br/>")
            if in_table:
                out.append("</table></div>")
            return "\n".join(out)

        rendered_body = md_to_html_simple(raw_markdown)

        banner = ""
        if is_draft:
            banner = """
            <div class="draft-banner">
                <span class="badge">INTERNAL DRAFT</span>
                <span>This Statement of Work is pending formal human approval. Not approved for client release.</span>
            </div>
            """
        else:
            approved_at_str = scope.approved_at.isoformat() if hasattr(scope.approved_at, "isoformat") else str(scope.approved_at or "")
            banner = f"""
            <div class="approved-banner">
                <span class="badge">APPROVED &amp; CLIENT READY</span>
                <span>Verified by <strong>{html.escape(str(scope.approved_by or "Authorized Reviewer"))}</strong> on {html.escape(approved_at_str)}.</span>
            </div>
            """

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Statement of Work - {html.escape(project_id)}</title>
  <style>
    @media print {{
      body {{ font-size: 11pt; }}
      .no-print {{ display: none !important; }}
      .draft-watermark {{ position: fixed; top: 40%; left: 15%; transform: rotate(-30deg); font-size: 72pt; opacity: 0.12; color: #ef4444; z-index: 9999; pointer-events: none; }}
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      color: #1e293b;
      background: #f8fafc;
      padding: 40px 20px;
      margin: 0;
    }}
    .container {{
      max-width: 860px;
      margin: 0 auto;
      background: #ffffff;
      padding: 48px;
      border-radius: 12px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.06);
      position: relative;
    }}
    .draft-banner {{
      background: #fef2f2;
      border: 1px solid #fecaca;
      color: #991b1b;
      padding: 12px 18px;
      border-radius: 8px;
      margin-bottom: 28px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
    }}
    .approved-banner {{
      background: #ecfdf5;
      border: 1px solid #a7f3d0;
      color: #065f46;
      padding: 12px 18px;
      border-radius: 8px;
      margin-bottom: 28px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
    }}
    .badge {{
      font-weight: 700;
      text-transform: uppercase;
      font-size: 10px;
      letter-spacing: 0.05em;
      padding: 3px 8px;
      border-radius: 4px;
      background: rgba(0,0,0,0.06);
    }}
    h1 {{ font-size: 26px; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; color: #0f172a; margin-top: 0; }}
    h2 {{ font-size: 20px; color: #1e293b; margin-top: 28px; border-bottom: 1px solid #f1f5f9; padding-bottom: 6px; }}
    h3 {{ font-size: 16px; color: #334155; margin-top: 20px; }}
    p {{ margin: 10px 0; }}
    li.bullet {{ margin-left: 20px; }}
    .table-wrap {{ overflow-x: auto; margin: 16px 0; }}
    .sow-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .sow-table td {{ border: 1px solid #cbd5e1; padding: 8px 12px; }}
    .sow-table tr:first-child td {{ background: #f1f5f9; font-weight: 600; }}
    .actions-bar {{
      margin-bottom: 20px;
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }}
    .btn {{
      padding: 8px 16px;
      background: #2563eb;
      color: #ffffff;
      border-radius: 6px;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: none;
    }}
    .btn:hover {{ background: #1d4ed8; }}
    .btn-secondary {{ background: #e2e8f0; color: #334155; }}
    .btn-secondary:hover {{ background: #cbd5e1; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="actions-bar no-print">
      <button class="btn btn-secondary" onclick="window.print()">Print / Save as PDF</button>
      <a class="btn" href="?format=markdown&draft={str(is_draft).lower()}">Download Markdown</a>
    </div>
    {banner}
    {rendered_body}
  </div>
</body>
</html>
"""
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            content=full_html,
            headers={
                "X-SOW-Status": "DRAFT" if is_draft else "APPROVED",
                "X-Client-Ready": str(scope.client_ready).lower()
            }
        )

    @app.post("/api/v1/projects/{project_id}/approve", response_model=ProjectScope)
    def approve_scope(
        project_id: str,
        req: ApproveScopeRequest,
        caller: Dict[str, Any] = Depends(get_current_user_or_service)
    ):
        scope = orch.store.get(project_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        check_project_access(scope, caller)

        # Authenticate approver from caller identity
        approver = caller.get("username") or caller.get("email") or caller.get("id") or req.approved_by
        if approver == "dev_user" and req.approved_by:
            approver = req.approved_by

        try:
            approved_scope = orch.approve_scope(project_id=project_id, approved_by=approver)
            return approved_scope
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err))

    return app


app = create_app()