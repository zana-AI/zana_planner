from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """
    A high-level, non-chain-of-thought step.

    Notes:
    - This is intentionally NOT a reasoning trace.
    - Keep `purpose` short and user-safe (can be shown in debug).
    """

    kind: Literal["tool", "respond", "ask_user"] = Field(
        ...,
        description="Step kind: call a tool, respond to user, or ask the user a clarifying question.",
    )

    purpose: str = Field(
        ...,
        description="Short description of why this step is needed (no chain-of-thought).",
        min_length=1,
        max_length=240,
    )

    # tool step
    tool_name: Optional[str] = Field(None, description="Tool name to call when kind='tool'.")
    tool_args: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Tool args when kind='tool' (user_id is implicit)."
    )

    # ask_user step
    question: Optional[str] = Field(None, description="Clarifying question when kind='ask_user'.")

    # respond step
    response_hint: Optional[str] = Field(
        None,
        description="Optional short instruction for the responder (e.g., tone/format).",
        max_length=240,
    )


class Plan(BaseModel):
    """Planner output: a short plan the executor can follow."""

    steps: List[PlanStep] = Field(..., description="Ordered steps to complete the user's request.")

    final_response_if_no_tools: Optional[str] = Field(
        None,
        description="If no tools are needed, the planner may provide a direct final response.",
        max_length=2000,
    )

    detected_intent: Optional[str] = Field(
        None,
        description="Open-text description of the user's primary intent (e.g., 'LOG_ACTION', 'CREATE_PROMISE', 'QUERY_PROGRESS', 'MANAGE_PROMISE', 'GET_IDEAS', 'USER_CORRECTION', etc.).",
    )

    intent_confidence: Optional[str] = Field(
        None,
        description="Confidence level for the detected intent: 'high', 'medium', or 'low'.",
    )

    safety: Optional[Dict[str, Any]] = Field(
        None,
        description="Safety metadata including flags like requires_confirmation, assumptions, risk_level.",
    )


class RouteDecision(BaseModel):
    """Router output: determines which agent mode to use for handling the user's request."""

    mode: Literal["operator", "strategist", "social", "engagement"] = Field(
        ...,
        description="Agent mode to use: 'operator' for transactional actions (promises/actions/settings), 'strategist' for high-level goals/coaching, 'social' for community/followers/feed, 'engagement' for casual chat/humor.",
    )

    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence level for the routing decision: 'high', 'medium', or 'low'.",
    )

    reason: str = Field(
        ...,
        description="Short label explaining why this mode was chosen (e.g., 'transactional_intent', 'coaching_intent', 'community_intent', 'casual_chat').",
        max_length=100,
    )

