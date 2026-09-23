from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class BaseQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class NoulQuestion(BaseQuestion):
    type: Literal["noul"]
    criteria: dict[str, object] | None = None

    @field_validator("criteria")
    @classmethod
    def check_criteria(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        if value is not None and (set(value) - {"true", "false"}):
            raise ValueError("noul criteria keys must be true or false")
        return value


class ChoiceQuestion(BaseQuestion):
    type: Literal["choice"]
    criteria: Annotated[dict[str, object] | list[str], Field(min_length=2, max_length=50)]

    @field_validator("criteria")
    @classmethod
    def check_choice(cls, value: dict[str, object] | list[str]) -> dict[str, object] | list[str]:
        labels = list(value)
        normalized = [label.strip() for label in labels]
        if any(not label for label in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("choice labels must be nonempty and unique")
        return value


class ScoreQuestion(BaseQuestion):
    type: Literal["score"]
    criteria: Annotated[list[str], Field(min_length=2, max_length=50)]

    @field_validator("criteria")
    @classmethod
    def check_score(cls, value: list[str]) -> list[str]:
        normalized = [label.strip() for label in value]
        if any(not label for label in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("score criteria labels must be nonempty and unique")
        return value


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]


class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str | dict[str, object] | list[object]
    questions: Annotated[dict[str, Question], Field(min_length=1, max_length=50)]
    model: Literal["auto", "english", "multilingual", "typed-decisions"] = "auto"


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateKeyRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
