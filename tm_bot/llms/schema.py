from pydantic import BaseModel, Field
from typing import Optional


class LLMResponse(BaseModel):
    function_call: Optional[str] = Field(None, description="Function name to call")
    function_args: Optional[dict] = Field(None, description="Function arguments if any")
    response_to_user: str = Field(..., description="Short response to the user (Obligatory)")


# Legacy compatibility classes for existing code
class UserAction(BaseModel):
    """Legacy UserAction class for backward compatibility."""
    action_date: str = Field(..., description="Date of the action")
    action_time: str = Field(..., description="Time of the action in HH:MM format")
    promise_id: str = Field(..., description="ID of the related promise")
    time_spent: float = Field(..., description="Time spent in hours")


