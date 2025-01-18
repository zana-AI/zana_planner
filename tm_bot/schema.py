from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class Promise(BaseModel):
    """Represents a user's promise."""
    promise_text: str = Field(..., description="The text of the promise.")
    promise_id: str = Field(..., description="A unique 12-character ID derived from the promise text.")
    num_hours_promised_per_week: int = Field(..., description="Number of hours promised per week.")
    start_date: date = Field(..., description="Start date of the promise.")
    end_date: date = Field(..., description="End date of the promise.")
    promise_angle: float = Field(..., ge=0, lt=360, description="Angle between 0 and 360 degrees.")
    promise_radius: int = Field(..., ge=1, le=100, description="Radius between 1 and 100 years.")

class Action(BaseModel):
    """Represents an action taken towards a promise."""
    date: date = Field(..., description="Date of the action.")
    time: str = Field(..., description="Time of the action in HH:MM format.")
    promise_id: str = Field(..., description="ID of the related promise.")
    time_spent: float = Field(..., description="Time spent in hours.")
