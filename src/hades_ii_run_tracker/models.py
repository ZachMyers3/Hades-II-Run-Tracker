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


class AnalyticsSettings(BaseModel):
    date_range_days: int = Field(default=7, ge=1, le=365)


class TrackerConfig(BaseModel):
    users: list[ConfigUser]
    weapons: list[ConfigOption] = Field(default_factory=list)
    boons: list[ConfigOption] = Field(default_factory=list)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)

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


class DateBucket(BaseModel):
    date: str
    total: int
    topside: int
    bottomside: int
    cumulative_total: int
    by_user: dict[str, int]
    by_user_topside: dict[str, int]
    by_user_bottomside: dict[str, int]
    by_user_cumulative: dict[str, int]


class UserMetric(BaseModel):
    user_id: str
    display_name: str
    total: int


class UserExtraAnalytics(BaseModel):
    user_id: str
    display_name: str
    recent_total: int
    weapon_variety: int
    boon_variety: int
    topside_percent: float
    bottomside_percent: float


class ExtraAnalytics(BaseModel):
    current_leader: UserMetric | None
    recent_momentum: list[UserMetric]
    user_stats: list[UserExtraAnalytics]


class Analytics(BaseModel):
    date_range_days: int
    total_runs: int
    by_side: dict[str, int]
    by_weapon: dict[str, int]
    by_boon: dict[str, int]
    daily_runs: list[DateBucket]
    users: list[UserAnalytics]
    extra_metrics: ExtraAnalytics
    recent_runs: list[RunRecord]
