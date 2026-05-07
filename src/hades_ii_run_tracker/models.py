from typing import Any, Literal

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


class AdminSettings(BaseModel):
    password: str = ""


class PublicUser(BaseModel):
    id: str
    display_name: str


class AdminUser(ConfigUser):
    run_count: int = 0


DEFAULT_FEAR_IMAGE_URL = "/static/assets/fear/shrine-point.png"
DEFAULT_FEAR_SOURCE_URL = "https://hades.fandom.com/wiki/Fear?file=ShrinePoint.png"


def default_fear_option() -> "ConfigOption":
    return ConfigOption(
        name="Fear",
        image_url=DEFAULT_FEAR_IMAGE_URL,
        source_url=DEFAULT_FEAR_SOURCE_URL,
    )


class ConfigOption(BaseModel):
    name: str
    image_url: str | None = None
    source_url: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Option name cannot be blank.")
        return value


class AnalyticsSettings(BaseModel):
    date_range_days: int = Field(default=7, ge=1, le=365)
    fear_weight: float = Field(
        default=1.0,
        ge=0,
        description="Multiplier for fear contribution in win score.",
    )
    run_amount_topside: float = Field(
        default=1.3,
        ge=0,
        description="Run-type multiplier for topside victories.",
    )
    run_amount_bottomside: float = Field(
        default=1.0,
        ge=0,
        description="Run-type multiplier for bottomside victories.",
    )


class TrackerConfig(BaseModel):
    users: list[ConfigUser]
    weapons: list[ConfigOption] = Field(default_factory=list)
    boons: list[ConfigOption] = Field(default_factory=list)
    fear: ConfigOption = Field(default_factory=default_fear_option)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)

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
    fear: ConfigOption
    sides: list[dict[str, str]]


class AdminLogin(BaseModel):
    password: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def strip_password(cls, value: str) -> str:
        return value.strip()


class AdminUserCreate(ConfigUser):
    @field_validator("id", "display_name", "access_code")
    @classmethod
    def strip_required_user_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value


class AdminUserUpdate(BaseModel):
    display_name: str = Field(min_length=1)
    access_code: str = Field(min_length=1)

    @field_validator("display_name", "access_code")
    @classmethod
    def strip_required_user_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value


class RunCreate(BaseModel):
    access_code: str = Field(min_length=1)
    side: RunSide
    weapon: str | None = None
    boons: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)
    fear: int | None = Field(default=None, ge=0, le=99)

    @field_validator("fear", mode="before")
    @classmethod
    def coerce_fear(cls, value):
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError("Fear must be an integer.")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return int(stripped)
            except ValueError as exc:
                raise ValueError("Fear must be an integer.") from exc
        raise ValueError("Fear must be an integer.")

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


class AdminRunUpdate(BaseModel):
    user_id: str = Field(min_length=1)
    side: RunSide
    weapon: str | None = None
    boons: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)
    fear: int = Field(default=0, ge=0, le=99)

    @field_validator("fear", mode="before")
    @classmethod
    def coerce_fear_admin(cls, value):
        if value is None or value == "":
            return 0
        if isinstance(value, bool):
            raise ValueError("Fear must be an integer.")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return 0
            try:
                return int(stripped)
            except ValueError as exc:
                raise ValueError("Fear must be an integer.") from exc
        raise ValueError("Fear must be an integer.")

    @field_validator("user_id")
    @classmethod
    def strip_user_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value

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
    fear: int = Field(default=0, ge=0, le=99)
    computed_win_score: float = Field(
        ...,
        description="Raw win score at submission time (display as round(score * 100)).",
    )
    created_at: str

    @field_validator("fear", mode="before")
    @classmethod
    def coerce_fear_record(cls, value):
        if value is None or value == "":
            return 0
        if isinstance(value, bool):
            raise ValueError("Fear must be an integer.")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return 0
            try:
                return int(stripped)
            except ValueError as exc:
                raise ValueError("Fear must be an integer.") from exc
        raise ValueError("Fear must be an integer.")


class AdminConfigUpdate(BaseModel):
    weapons: list[ConfigOption] = Field(default_factory=list)
    boons: list[ConfigOption] = Field(default_factory=list)
    fear: ConfigOption | None = None
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)

    @field_validator("weapons", "boons", mode="before")
    @classmethod
    def normalize_options(cls, values):
        return [
            {"name": value} if isinstance(value, str) else value
            for value in values or []
        ]


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


class FearUserRow(BaseModel):
    user_id: str
    display_name: str
    run_count: int
    avg_fear: float
    max_fear: int


class FearAnalytics(BaseModel):
    avg_fear: float
    max_fear: int
    max_fear_user_id: str | None
    max_fear_display_name: str | None
    runs_with_fear_positive: int
    pct_runs_fear_positive: float
    avg_fear_topside: float
    avg_fear_bottomside: float
    max_fear_topside: int
    max_fear_bottomside: int
    fear_buckets: dict[str, int]
    by_user: list[FearUserRow]
    highest_avg_fear_user: FearUserRow | None
    highest_max_fear_user: FearUserRow | None


class WinScoreLeaderboardSettings(BaseModel):
    fear_weight: float
    run_amount_topside: float
    run_amount_bottomside: float


class WinScoreLeaderboardUserRow(BaseModel):
    user_id: str
    display_name: str
    run_count: int
    avg_display_points: float
    max_display_points: int
    display_points_total: int


class WinScoreLeaderboardAnalytics(BaseModel):
    settings: WinScoreLeaderboardSettings
    grand_total_display_points: int
    avg_score: float
    max_single_display_points: int
    max_score_user_id: str | None
    max_score_display_name: str | None
    avg_score_topside: float
    avg_score_bottomside: float
    max_score_topside: int
    max_score_bottomside: int
    score_buckets: dict[str, int]
    by_user: list[WinScoreLeaderboardUserRow]
    highest_avg_score_user: WinScoreLeaderboardUserRow | None
    highest_max_score_user: WinScoreLeaderboardUserRow | None


class UserWinScoreStackedRow(BaseModel):
    """All-time display points per side for stacked bar chart (not date-filtered)."""

    user_id: str
    display_name: str
    topside_display_points: int
    bottomside_display_points: int


class Analytics(BaseModel):
    date_range_days: int
    total_runs: int
    by_side: dict[str, int]
    by_weapon: dict[str, int]
    by_boon: dict[str, int]
    daily_runs: list[DateBucket]
    users: list[UserAnalytics]
    extra_metrics: ExtraAnalytics
    fear: FearAnalytics
    win_score_leaderboard: WinScoreLeaderboardAnalytics
    win_score_stacked_by_user: list[UserWinScoreStackedRow]
    recent_runs: list[RunRecord]


class AdminBackupImport(BaseModel):
    """Body for POST /api/admin/import (same shape as export backup)."""

    config: dict[str, Any]
    runs: list[dict[str, Any]]
    confirm_replace: bool = False
