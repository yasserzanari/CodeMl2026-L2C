from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Armature(BaseModel):
    model_config = ConfigDict(extra='forbid')
    repere: str | None = None
    diametre: str | None = None
    quantite: int | None = Field(default=None, ge=0)
    espacement_mm: float | None = Field(default=None, gt=0)
    longueur_mm: float | None = Field(default=None, gt=0)

class Information(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    source: Literal['plan', 'atelier']
    fichier: str
    feuillet: str
    page: int = Field(ge=1)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    type_element: str
    element: str
    armature: list[Armature]

class AnalysisRequest(BaseModel):
    profile: Literal['complete', 'native', 'sample'] = 'complete'
    max_ocr_pages: int = Field(default=4, ge=1, le=1000)

class Settings(BaseModel):
    ocr_engine: Literal['easyocr','rapidocr'] = 'easyocr'
    device: Literal['auto', 'cuda', 'cpu'] = 'auto'
    batch_size: int = Field(default=32, ge=1, le=64)
    dpi: int = Field(default=144, ge=96, le=216)
    canvas_size: int = Field(default=2560, ge=1280, le=3200)
    ocr_confidence: float = Field(default=0.25, ge=0.05, le=0.95)
    ocr_rotations: bool = True

class Review(BaseModel):
    decision: Literal['confirme', 'rejete', 'a_verifier']
    note: str = Field(default='', max_length=2000)
