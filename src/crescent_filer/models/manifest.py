from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FilerInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    filer_id: str = Field(alias="filerId")
    legal_name: str = Field(alias="legalName")
    contact_email: str = Field(alias="contactEmail")

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "filerId": self.filer_id,
            "legalName": self.legal_name,
            "contactEmail": self.contact_email,
        }


class FilerSignature(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    signer_name: str = Field(alias="signerName")
    signer_title: str = Field(alias="signerTitle")
    signed_at_utc: str = Field(alias="signedAtUtc")

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "signerName": self.signer_name,
            "signerTitle": self.signer_title,
            "signedAtUtc": self.signed_at_utc,
        }


class ScenarioInput(BaseModel):
    """Partial manifest fields as stored in scenarios/*.json (no manifestId, filer, eta, signature)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    vessel: dict[str, Any]
    arrival: dict[str, Any]
    containers: list[dict[str, Any]]
    crew: list[dict[str, Any]]
    declared_value_total: float = Field(alias="declaredValueTotal")
