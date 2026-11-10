
from typing import Annotated

from email_validator import validate_email  # type: ignore
from pydantic import AfterValidator, BaseModel, Field  # pyright: ignore[reportMissingImports]

from app.models.user import UserRole


def validate_app_email(value: str) -> str:
    result = validate_email(
        value,
        check_deliverability=False,
        test_environment=True,
    )
    return result.normalized


AppEmail = Annotated[str, AfterValidator(validate_app_email)]


class LoginRequest(BaseModel):
    email: AppEmail
    password: str


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: AppEmail
    password: str = Field(min_length=8)
    role: UserRole


class UserResponse(BaseModel):
    id: int
    campus_id: int
    full_name: str
    email: AppEmail
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
