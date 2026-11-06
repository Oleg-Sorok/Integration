from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Property parameters that feed the ML model (a change => re-forecast)
FEATURE_FIELDS = (
    "gr_liv_area", "total_bsmt_sf", "garage_area",
    "year_built", "overall_qual", "ms_zoning",
)


class PropertyFeatures(BaseModel):
    gr_liv_area: float = Field(gt=0, le=10000)
    total_bsmt_sf: float = Field(ge=0, le=10000)
    garage_area: float = Field(ge=0, le=2000)
    year_built: int = Field(ge=1872, le=2010)
    overall_qual: int = Field(ge=1, le=10)
    ms_zoning: str = Field(min_length=1, max_length=10)


class OrderCreate(PropertyFeatures):
    client_name: str = Field(min_length=2, max_length=120)


class OrderUpdate(BaseModel):
    """PATCH body: every field optional, same constraints as on create."""
    client_name: str | None = Field(default=None, min_length=2, max_length=120)
    gr_liv_area: float | None = Field(default=None, gt=0, le=10000)
    total_bsmt_sf: float | None = Field(default=None, ge=0, le=10000)
    garage_area: float | None = Field(default=None, ge=0, le=2000)
    year_built: int | None = Field(default=None, ge=1872, le=2010)
    overall_qual: int | None = Field(default=None, ge=1, le=10)
    ms_zoning: str | None = Field(default=None, min_length=1, max_length=10)

    @model_validator(mode="after")
    def no_explicit_nulls(self):
        # omitted field = "don't touch"; explicit null is not allowed (columns are NOT NULL)
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class OrderRead(OrderCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    predicted_price: float | None
    model_version: str | None
    status: str
    created_at: datetime


class UserCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str

    @model_validator(mode='after')
    def valid_password(self):
        n = len(self.password.encode('utf-8'))
        if not 8 <= n <= 72:
            raise ValueError('Password must be 8-72 bytes long')
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = 'bearer'
