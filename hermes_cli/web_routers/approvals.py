"""Cross-session prompt routes: the approvals / clarifies parked on the user, and a click-through answer.

``GET /api/approvals/pending`` lists them (the owner's read-only ``approval.pending_all``);
``POST /api/approvals/respond`` forwards ONE explicit answer to the owner's existing per-session
``approval.respond`` / ``clarify.respond``, generation-fenced, so a stale click never answers a newer
prompt. The owner only takes an answer from a viewer of the session, so the forward attaches as one
(``session.resume`` without the transcript), answers, and detaches again, as a Desktop tab would. Nothing here answers on its own. Both reach the live gateway owner over its control socket,
as a standalone dashboard's session mutations do (``web_server_sessions._mutate_via_gateway_owner``):
pending prompts live only in the owner's memory, never in state.db.
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()

_REFUSAL_STATUS = {'permission_denied': 403, 'profile_mismatch': 403, 'not_found': 404,
                   'invalid_params': 400, 'runtime_draining': 503}


class PromptAnswer(BaseModel):
    session_id: str = Field(min_length=1, max_length=256)
    request_id: str = Field(min_length=1, max_length=256)
    kind: Literal['approval', 'clarify']
    execution_generation: int
    choice: str = Field(max_length=16384)  # an approval choice, or the clarify answer ("" skips)
    profile: Optional[str] = None


async def _owner_rpc(request: Request, profile: Optional[str], calls):
    """Run ``calls(client)`` on one owner connection; owner refusals map to HTTP statuses."""
    from gateway.owner_identity import host_owner_subject
    from hermes_cli.gateway_client import GatewayClientError, GatewayRPCError, connect_gateway
    from hermes_cli.gateway_runtime import discover_gateway_endpoint
    from hermes_cli.gateway_runtime_discovery import DiscoveryError
    from hermes_cli.web_server_sessions import _session_db_path_for_profile, _session_mutation_context

    _authority, actor = _session_mutation_context(request, profile)  # 401 without a dashboard principal
    home = _session_db_path_for_profile(profile).parent
    discovery = await asyncio.to_thread(discover_gateway_endpoint, home, timeout=1.5)
    endpoint = discovery.endpoint
    if endpoint is None:
        raise HTTPException(status_code=503, detail=f'owner_unavailable: {discovery.reason_code or discovery.state}')
    if not getattr(endpoint, 'control_home', True):
        from dataclasses import replace
        endpoint = replace(endpoint, control_home=str(home.expanduser().resolve()))
    subject = None if actor.subject == host_owner_subject() else actor.subject
    try:
        async with connect_gateway(endpoint=endpoint, subject=subject) as client:
            return await calls(client)
    except GatewayRPCError as exc:
        if exc.unknown_method:
            raise HTTPException(status_code=503, detail='owner_too_old: restart the gateway') from exc
        raise HTTPException(status_code=_REFUSAL_STATUS.get(str(exc), 409), detail=str(exc)) from exc
    except (GatewayClientError, DiscoveryError, OSError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail='owner_unreachable') from exc


@router.get("/api/approvals/pending")
async def pending_prompts(request: Request, profile: Optional[str] = None):
    """``[{session_id, request_id, kind, summary, choices, multi_select, since, execution_generation}]``."""
    result = await _owner_rpc(request, profile, lambda client: client.rpc('approval.pending_all'))
    return result.get('prompts', [])


@router.post("/api/approvals/respond")
async def respond_prompt(request: Request, body: PromptAnswer):
    """One explicit answer, as the per-session verbs take it; ``already_resolved`` when it was settled."""
    field = 'answer' if body.kind == 'clarify' else 'choice'

    async def answer(client):
        view = await client.rpc('session.resume', session_id=body.session_id, omit_messages=True)
        try:
            return await client.rpc(f'{body.kind}.respond', session_id=view['session_id'],
                                    prompt_id=body.request_id, execution_generation=body.execution_generation,
                                    **{field: body.choice})
        finally:
            await client.rpc('session.detach', session_id=view['session_id'],
                             subscription_id=view['subscription_id'])

    return await _owner_rpc(request, body.profile, answer)
