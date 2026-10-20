from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=100_000)
    sources: list[SourceInput] = Field(min_length=1, max_length=50)


class ClaimUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


class RepairApply(BaseModel):
    claim_id: str
    action: Literal["REMOVE", "QUALIFY", "REWRITE", "MANUAL_REVIEW"]
    replacement_text: str | None = Field(default=None, max_length=10_000)

    @field_validator("replacement_text")
    @classmethod
    def replacement_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("replacement_text cannot be blank")
        return value


class DecisionInput(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    comment: str = Field(default="", max_length=2_000)
