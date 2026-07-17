from __future__ import annotations

import base64
import json
import os
from typing import Optional

from openai import OpenAI

from app.plants import match_catalog_plant
from app.schemas import DiagnosisResult, Issue

DIAGNOSIS_SCHEMA_HINT = """
Return ONLY valid JSON matching this shape:
{
  "plant_common_name": string,
  "plant_scientific_name": string or null,
  "confidence": number between 0 and 1,
  "is_healthy": boolean,
  "summary": string,
  "issues": [
    {
      "name": string,
      "severity": "low" | "moderate" | "high",
      "description": string,
      "causes": [string],
      "treatments": [string]
    }
  ],
  "care_tips": [string]
}
"""


def _attach_catalog_match(result: DiagnosisResult, notes: Optional[str] = None) -> DiagnosisResult:
    matched = match_catalog_plant(
        common_name=result.plant_common_name,
        scientific_name=result.plant_scientific_name,
        notes=notes,
    )
    if matched:
        result.matched_plant_id = matched.id
        if not result.plant_scientific_name:
            result.plant_scientific_name = matched.scientific_name
    return result


def mock_diagnosis(_: bytes, notes: Optional[str] = None) -> DiagnosisResult:
    matched = match_catalog_plant(notes=notes)
    if matched and matched.common_issues:
        issue = matched.common_issues[0]
        note_bit = f" Your notes (“{notes}”) helped narrow the guess." if notes else ""
        result = DiagnosisResult(
            plant_common_name=matched.common_names[0],
            plant_scientific_name=matched.scientific_name,
            matched_plant_id=matched.id,
            confidence=0.68,
            is_healthy=False,
            summary=(
                f"Demo diagnosis for {matched.common_names[0]} "
                f"({matched.scientific_name}).{note_bit} "
                "Add an OpenAI API key for real photo analysis."
            ),
            issues=[
                Issue(
                    name=issue.symptom,
                    severity="moderate",
                    description=(
                        f"A common issue for {matched.common_names[0]}. "
                        "Live AI will judge this from the actual photo."
                    ),
                    causes=issue.causes,
                    treatments=issue.treatments,
                )
            ],
            care_tips=[
                f"Light: {matched.care.light}",
                f"Water: {matched.care.water}",
                f"Humidity: {matched.care.humidity}",
            ],
            is_mock=True,
        )
        return result

    note_bit = f" Notes considered: {notes}." if notes else ""
    result = DiagnosisResult(
        plant_common_name="Monstera Deliciosa",
        plant_scientific_name="Monstera deliciosa",
        confidence=0.72,
        is_healthy=False,
        summary=(
            "The plant looks like a Monstera with mild stress—"
            "likely watering or humidity related."
            f"{note_bit} This is a demo result until you add an OpenAI API key."
        ),
        issues=[
            Issue(
                name="Yellowing lower leaves",
                severity="moderate",
                description=(
                    "Older leaves are yellowing while new growth still looks active, "
                    "a common early stress signal."
                ),
                causes=[
                    "Overwatering or soggy soil",
                    "Inconsistent watering schedule",
                    "Low light slowing water use",
                ],
                treatments=[
                    "Let the top 2–3 cm of soil dry before watering again",
                    "Confirm the pot has drainage holes",
                    "Move to bright indirect light",
                    "Trim fully yellow leaves at the base",
                ],
            ),
            Issue(
                name="Crispy leaf edges",
                severity="low",
                description="Leaf margins look dry, often linked to dry air or salts.",
                causes=[
                    "Low indoor humidity",
                    "Mineral buildup from tap water",
                    "Underwatering between soaks",
                ],
                treatments=[
                    "Raise humidity with a tray of pebbles and water or a small humidifier",
                    "Water thoroughly until runoff, then empty the saucer",
                    "Flush soil monthly with plain water",
                ],
            ),
        ],
        care_tips=[
            "Bright indirect light is ideal; avoid harsh midday sun on the leaves",
            "Water when the top layer of soil feels dry",
            "Wipe leaves monthly so they can photosynthesize well",
        ],
        is_mock=True,
    )
    return _attach_catalog_match(result, notes)


async def diagnose_plant(image_bytes: bytes, notes: Optional[str] = None) -> DiagnosisResult:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return mock_diagnosis(image_bytes, notes)

    client = OpenAI(api_key=api_key)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    user_text = (
        "Identify this plant and diagnose any visible problems. "
        "If it looks healthy, say so. Be specific about causes and treatments."
    )
    if notes:
        user_text += f"\nGardener notes: {notes}"

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful plant pathologist and horticulture assistant. "
                    + DIAGNOSIS_SCHEMA_HINT
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content or "{}"
    data = json.loads(content)
    result = DiagnosisResult.model_validate(data)
    result.is_mock = False
    return _attach_catalog_match(result, notes)
