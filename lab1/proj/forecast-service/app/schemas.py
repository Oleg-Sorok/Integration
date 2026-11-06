from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    gr_liv_area: float = Field(gt=0, le=10000)
    total_bsmt_sf: float = Field(ge=0, le=10000)
    garage_area: float = Field(ge=0, le=2000)
    year_built: int = Field(ge=1872, le=2010)
    overall_qual: int = Field(ge=1, le=10)
    ms_zoning: str = Field(min_length=1, max_length=10)


class PredictResponse(BaseModel):
    predicted_price: float
    currency: str = "USD"
    model_version: str
    latency_ms: float
