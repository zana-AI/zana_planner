from pydantic import BaseModel, Field
from typing import get_type_hints, Optional, Dict, Any
from datetime import date
import inspect

from planner_api import PlannerAPI


class UserPromise(BaseModel):
    promise_text: str = Field(..., description="The text of the promise")
    promise_id: str = Field(..., description="A unique 12-character ID derived from the promise text")
    num_hours_promised_per_week: int = Field(..., description="Number of hours promised per week")
    start_date: Optional[date] = Field(..., description="Start date of the promise")
    end_date: Optional[date] = Field(..., description="End date of the promise")
    promise_angle: int = Field(..., ge=0, lt=360, description="Angle [0-360] degrees, "
                                                              "0 if about learning and future, "
                                                              "90 if about health and self-care, "
                                                              "180 if about professional deliverables, "
                                                              "270 if about impacting others or social activity")
    promise_radius: Optional[int] = Field(default=0, ge=0, le=100, description="Radius between 1 and 100 years")

class UserAction(BaseModel):
    action_date: date = Field(..., description="Date of the action")
    action_time: str = Field(..., description="Time of the action in HH:MM format")
    promise_id: str = Field(..., description="ID of the related promise")
    time_spent: float = Field(..., description="Time spent in hours")

class LLMResponse(BaseModel):
    # user_promise: Optional[UserPromise] = Field(None, description="Promise object")
    # user_action: Optional[UserAction] = Field(None, description="Action object")
    # update_setting: Optional[dict] = Field(None, description="Setting dictionary")
    function_call: Optional[str] = Field(None, description="Function name to call")
    function_args: Optional[dict] = Field(None, description="Function arguments if any")
    response_to_user: str = Field(..., description="Short response to the user (Obligatory)")


