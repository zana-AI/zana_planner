from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

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
    user_promise: Optional[UserPromise] = Field(None, description="Promise object")
    user_action: Optional[UserAction] = Field(None, description="Action object")
    update_setting: Optional[dict] = Field(None, description="Setting dictionary")
    response_to_user: str = Field(..., description="Response to the user")


# utils.py

from typing import List, Type
from langchain.output_parsers import ResponseSchema
from pydantic import BaseModel

def generate_response_schemas(model: Type[BaseModel]) -> List[ResponseSchema]:
    """
    Generates a list of ResponseSchema instances from a given Pydantic BaseModel.

    Args:
        model (Type[BaseModel]): The Pydantic model to generate schemas from.

    Returns:
        List[ResponseSchema]: A list of ResponseSchema instances.
    """
    response_schemas = []
    for field_name, field in model.model_fields.items():
        description = field.description or "No description provided."
        response_schemas.append(
            ResponseSchema(
                name=field_name,
                description=description
            )
        )
    return response_schemas

if __name__ == "__main__":
    response_schemas = generate_response_schemas(LLMResponse)
    for schema in response_schemas:
        print(schema)