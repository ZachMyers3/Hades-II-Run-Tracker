from typing import Literal

from pydantic import BaseModel, Field, field_validator


RunSide = Literal["topside", "bottomside"]

SIDES = [
    {"id": "topside", "label": "Topside"},
    {"id": "bottomside", "label": "Bottomside"},
]


class ConfigUser(BaseModel):
    id: str
    display_name: str
    access_code: str


class PublicUser(BaseModel):
    id: str
    display_name: str


class ConfigOption(BaseModel):
    name: str
    image_url: str | None = None
    source_url: str | None = None


class TrackerConfig(BaseModel):
    users: list[ConfigUser]
    weapons: list[ConfigOption] = Field(default_factory=list)
    boons: list[ConfigOption] = Field(default_factory=list)

    @field_validator("weapons", "boons", mode="before")
    @classmethod
    def normalize_options(cls, values):
        return [
            {"name": value} if isinstance(value, str) else value
            for value in values or []
        ]

    def public_users(self) -> list[PublicUser]:
        return [
            PublicUser(id=user.id, display_name=user.display_name)
            for user in self.users
        ]

    def user_for_code(self, access_code: str) -> ConfigUser | None:
        return next(
            (
                user
                for user in self.users
                if user.access_code == access_code.strip()
            ),
            None,
        )


class PublicConfig(BaseModel):
    users: list[PublicUser]
    weapons: list[ConfigOption]
    boons: list[ConfigOption]
    sides: list[dict[str, str]]


class RunCreate(BaseModel):
    access_code: str = Field(min_length=1)
    side: RunSide
    weapon: str | None = None
    boons: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("access_code")
    @classmethod
    def strip_access_code(cls, value: str) -> str:
        return value.strip()

    @field_validator("weapon", "notes")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("boons")
    @classmethod
    def clean_boons(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            boon = value.strip()
            if boon and boon not in cleaned:
                cleaned.append(boon)
        return cleaned


class RunRecord(BaseModel):
    id: str
    user_id: str
    side: RunSide
    weapon: str | None = None
    boons: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: str


class UserAnalytics(BaseModel):
    user_id: str
    display_name: str
    total: int
    topside: int
    bottomside: int
    favorite_weapon: str | None
    favorite_boons: list[str]


class Analytics(BaseModel):
    total_runs: int
    by_side: dict[str, int]
    by_weapon: dict[str, int]
    by_boon: dict[str, int]
    users: list[UserAnalytics]
    recent_runs: list[RunRecord]
