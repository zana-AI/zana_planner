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

