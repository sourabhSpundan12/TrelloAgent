from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TrelloBoard(BaseModel):
    id: str
    name: str
    desc: Optional[str] = ""
    closed: bool = False
    url: Optional[str] = None
    shortUrl: Optional[str] = None


class TrelloList(BaseModel):
    id: str
    name: str
    idBoard: str
    closed: bool = False
    pos: Optional[float] = None


class TrelloCard(BaseModel):
    id: str
    name: str
    desc: Optional[str] = ""
    idList: str
    idBoard: str
    closed: bool = False
    url: Optional[str] = None
    shortUrl: Optional[str] = None
    due: Optional[str] = None
    labels: List[Dict[str, Any]] = Field(default_factory=list)


class TrelloCardCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Title/name of the card")
    list_id: Optional[str] = Field(None, description="Target list ID on the board")
    desc: Optional[str] = Field("", description="Card description")
    board_id: Optional[str] = Field(None, description="Board ID to use if list_id is not specified")


class TrelloCardUpdateRequest(BaseModel):
    card_id: str = Field(..., description="ID of the card to update")
    name: Optional[str] = Field(None, min_length=1, description="New title of the card")
    desc: Optional[str] = Field(None, description="New description of the card")


class TrelloCardMoveRequest(BaseModel):
    card_id: str = Field(..., description="ID of the card to move")
    list_id: str = Field(..., description="Destination list ID")
    board_id: Optional[str] = Field(None, description="Optional board ID for validation")


class TrelloCardArchiveRequest(BaseModel):
    card_id: str = Field(..., description="ID of the card to archive")

