from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Any


class RecipeModel(BaseModel):
    """Contrat de données Bronze : une recette non conforme est rejetée."""
    recipe_id: str
    site: str
    url: HttpUrl
    title: str = Field(..., min_length=2)
    ingredients: List[str] = Field(..., min_length=1)

    instructions: Optional[str] = None
    total_time: Optional[int] = None
    prep_time: Optional[int] = None
    cook_time: Optional[int] = None
    yields: Optional[str] = None
    image: Optional[str] = None
    host: Optional[str] = None
    category: Optional[str] = None
    cuisine: Optional[str] = None
    nutrients: Optional[dict[str, Any]] = None
    ratings: Optional[float] = Field(None, ge=0, le=5)