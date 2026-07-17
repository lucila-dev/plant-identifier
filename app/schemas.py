from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Issue(BaseModel):
    name: str
    severity: str = "moderate"
    description: str
    causes: list[str] = Field(default_factory=list)
    treatments: list[str] = Field(default_factory=list)


class DiagnosisResult(BaseModel):
    plant_common_name: str
    plant_scientific_name: Optional[str] = None
    matched_plant_id: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    is_healthy: bool
    summary: str
    issues: list[Issue] = Field(default_factory=list)
    care_tips: list[str] = Field(default_factory=list)
    is_mock: bool = False


class PlantCare(BaseModel):
    light: str
    water: str
    humidity: str


class CommonIssue(BaseModel):
    symptom: str
    causes: list[str]
    treatments: list[str]


class Plant(BaseModel):
    id: str
    common_names: list[str]
    scientific_name: str
    family: str
    description: str
    image_url: str = ""
    care: PlantCare
    common_issues: list[CommonIssue] = Field(default_factory=list)


class PlantSummary(BaseModel):
    id: str
    primary_name: str
    common_names: list[str]
    scientific_name: str
    family: str
    description: str
    image_url: str = ""
    watering_frequency: str = ""
