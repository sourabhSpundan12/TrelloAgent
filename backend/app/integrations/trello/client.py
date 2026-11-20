import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx


def parse_due_date_for_trello(raw_due: Any) -> Optional[str]:
    """
    Parses date strings (e.g. 'Nov 19, 2026', '19 Nov 2026', '2026-11-19',
    'tomorrow', 'next week', 'Friday') or datetime objects into a valid ISO 8601
    UTC string ('YYYY-MM-DDTHH:MM:SS.000Z') strictly accepted by Trello REST API.
    """
    if not raw_due:
        return None
    if isinstance(raw_due, datetime):
        dt = raw_due if raw_due.tzinfo else raw_due.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    val = str(raw_due).strip()
    if not val or val.lower() in ("no due date", "none", "null", "undefined", "—", "-"):
        return None

    val_lower = val.lower()
    now = datetime.now(timezone.utc)

    # Relative shortcuts
    if val_lower == "today":
        return now.replace(hour=17, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if val_lower == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if "day after tomorrow" in val_lower:
        return (now + timedelta(days=2)).replace(hour=17, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if "next week" in val_lower:
        return (now + timedelta(days=7)).replace(hour=17, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # in X days / weeks
    m_in_days = re.search(r"in\s+(\d+)\s+days?", val_lower)
    if m_in_days:
        d = int(m_in_days.group(1))
        return (now + timedelta(days=d)).replace(hour=17, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    m_in_weeks = re.search(r"in\s+(\d+)\s+weeks?", val_lower)
    if m_in_weeks:
        w = int(m_in_weeks.group(1))
        return (now + timedelta(weeks=w)).replace(hour=17, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Day of week (e.g. Friday, next Monday)
    weekdays = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    for day_name, day_num in weekdays.items():
        if day_name in val_lower:
            days_ahead = (day_num - now.weekday()) % 7
            if days_ahead <= 0:
                days_ahead += 7
            return (now + timedelta(days=days_ahead)).replace(hour=17, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Clean string: strip ordinal suffixes (e.g., 19th -> 19, 1st -> 1)
    clean_val = re.sub(r"(\d+)(?:st|nd|rd|th)\b", r"\1", val, flags=re.IGNORECASE)
    # Remove commas and normalize spaces
    clean_val_no_comma = clean_val.replace(",", " ")
    clean_val_no_comma = re.sub(r"\s+", " ", clean_val_no_comma).strip()

    # Try standard strptime formats
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%b %d %Y",
        "%B %d %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d",
        "%B %d",
        "%d %b",
        "%d %B",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(clean_val_no_comma, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=now.year)
                if parsed.replace(tzinfo=timezone.utc) < (now - timedelta(days=30)):
                    parsed = parsed.replace(year=now.year + 1)
            parsed_utc = parsed.replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            return parsed_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except ValueError:
            continue

    # Try ISO fromisoformat
    try:
        clean_iso = val.replace("Z", "+00:00").replace("z", "+00:00")
        dt = datetime.fromisoformat(clean_iso)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        pass

    return None
from app.core.config import settings
from app.core.logging import logger
from app.integrations.trello.exceptions import (
    TrelloAPIError,
    TrelloAuthenticationError,
    TrelloConfigError,
    TrelloError,
    TrelloResourceNotFoundError,
    TrelloValidationError,
)


class TrelloClient:
    """
    Asynchronous REST client for the Trello API (v1).
    Ensures safe, robust interaction with Trello boards, lists, and cards.
    """

    BASE_URL = "https://api.trello.com/1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        board_id: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key if api_key is not None else settings.TRELLO_API_KEY
        self.token = token if token is not None else settings.TRELLO_TOKEN
        self.board_id = board_id if board_id is not None else settings.TRELLO_BOARD_ID
        self.timeout = timeout
        self._custom_http_client = http_client

    def validate_credentials(self) -> None:
        """Verifies that Trello API credentials are present."""
        if not self.api_key or not self.token:
            raise TrelloConfigError(
                "Trello API credentials are missing. Please configure TRELLO_API_KEY and TRELLO_TOKEN in .env"
            )

    def _get_auth_params(self) -> Dict[str, str]:
        self.validate_credentials()
        return {
            "key": self.api_key,
            "token": self.token,
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Executes an authenticated HTTP request against Trello REST API."""
        url = f"{self.BASE_URL}{path}"
        all_params = self._get_auth_params()
        if params:
            all_params.update(params)

        # Log sanitized request path without credentials
        logger.debug(f"Trello API {method.upper()} {path}")

        try:
            if self._custom_http_client:
                response = await self._custom_http_client.request(
                    method=method,
                    url=url,
                    params=all_params,
                    json=json_data,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        params=all_params,
                        json=json_data,
                    )

            if response.status_code == 401:
                raise TrelloAuthenticationError(
                    "Trello authentication failed: Invalid API key or token.",
                    details={"status_code": 401, "response": response.text[:200]},
                )
            elif response.status_code == 404:
                raise TrelloResourceNotFoundError(
                    f"Trello resource '{path}' not found.",
                    details={"status_code": 404, "response": response.text[:200]},
                )
            elif response.status_code == 400:
                raise TrelloValidationError(
                    f"Trello rejected request parameters for '{path}': {response.text[:200]}",
                    details={"status_code": 400, "response": response.text[:200]},
                )
            elif response.status_code >= 400:
                raise TrelloAPIError(
                    f"Trello returned error {response.status_code} on '{path}': {response.text[:200]}",
                    status_code=response.status_code,
                    details={"status_code": response.status_code, "response": response.text[:200]},
                )

            return response.json()

        except (TrelloError, TrelloConfigError):
            raise
        except httpx.TimeoutException as exc:
            logger.error(f"Trello API request timeout on '{path}': {exc}")
            raise TrelloError(f"Trello API request timed out on '{path}'.", status_code=504) from exc
        except httpx.RequestError as exc:
            logger.error(f"Trello API network error on '{path}': {exc}")
            raise TrelloError(f"Trello network error on '{path}': {str(exc)}", status_code=502) from exc
        except Exception as exc:
            logger.error(f"Unexpected error communicating with Trello: {exc}")
            raise TrelloError(f"Unexpected Trello communication error: {str(exc)}", status_code=500) from exc

    # 1. List all Trello boards
    async def list_boards(self) -> List[Dict[str, Any]]:
        """Lists all boards accessible to the authenticated user."""
        boards = await self._request("GET", "/members/me/boards")
        return [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "desc": b.get("desc", ""),
                "closed": b.get("closed", False),
                "url": b.get("url"),
                "shortUrl": b.get("shortUrl"),
            }
            for b in boards
        ]

    # 2. Get board details
    async def get_board(self, board_id: Optional[str] = None) -> Dict[str, Any]:
        """Gets detailed metadata for a specific board."""
        target_board = board_id or self.board_id
        if not target_board:
            raise TrelloValidationError("No board_id provided and TRELLO_BOARD_ID is not configured.")
        b = await self._request("GET", f"/boards/{target_board}")
        return {
            "id": b.get("id"),
            "name": b.get("name"),
            "desc": b.get("desc", ""),
            "closed": b.get("closed", False),
            "url": b.get("url"),
            "shortUrl": b.get("shortUrl"),
        }

    # 3. List board lists
    async def list_lists(self, board_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all open lists on the target board."""
        target_board = board_id or self.board_id
        if not target_board:
            raise TrelloValidationError("No board_id provided and TRELLO_BOARD_ID is not configured.")
        lists = await self._request("GET", f"/boards/{target_board}/lists")
        return [
            {
                "id": l.get("id"),
                "name": l.get("name"),
                "idBoard": l.get("idBoard"),
                "closed": l.get("closed", False),
                "pos": l.get("pos"),
            }
            for l in lists
        ]

    # 3b. Create a new list on board
    async def create_list(
        self,
        name: str,
        board_id: Optional[str] = None,
        pos: Optional[str] = "bottom",
    ) -> Dict[str, Any]:
        """Creates a new list/column on the target board."""
        if not name or not name.strip():
            raise TrelloValidationError("List name is required.")
        target_board = board_id or self.board_id
        if not target_board:
            raise TrelloValidationError("No board_id provided and TRELLO_BOARD_ID is not configured.")

        params = {"name": name.strip(), "pos": pos or "bottom"}
        l = await self._request("POST", f"/boards/{target_board}/lists", params=params)
        return {
            "id": l.get("id"),
            "name": l.get("name"),
            "idBoard": l.get("idBoard"),
            "closed": l.get("closed", False),
            "pos": l.get("pos"),
        }

    # 3c. List board members
    async def list_board_members(self, board_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all members belonging to the target board."""
        target_board = board_id or self.board_id
        if not target_board:
            raise TrelloValidationError("No board_id provided and TRELLO_BOARD_ID is not configured.")
        members = await self._request("GET", f"/boards/{target_board}/members")
        return [
            {
                "id": m.get("id"),
                "fullName": m.get("fullName", ""),
                "username": m.get("username", ""),
                "initials": m.get("initials", ""),
            }
            for m in members
        ]

    # 3d. Add member to card
    async def add_member_to_card(
        self,
        card_id: str,
        member_name: Optional[str] = None,
        member_id: Optional[str] = None,
        board_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adds an existing board member to a card by member ID or name."""
        if not card_id or not card_id.strip():
            raise TrelloValidationError("card_id is required.")

        target_member_id = member_id
        if not target_member_id and member_name:
            members = await self.list_board_members(board_id=board_id)
            query = member_name.lower().strip()
            norm_q = re.sub(r"[\s\-_]+", "", query)
            for m in members:
                full = m.get("fullName", "").lower()
                user = m.get("username", "").lower()
                norm_full = re.sub(r"[\s\-_]+", "", full)
                if query == full or query == user or norm_q == norm_full:
                    target_member_id = m["id"]
                    break
                if query in full or full in query or query in user:
                    target_member_id = m["id"]
                    break

        if not target_member_id:
            logger.warning(f"Could not resolve board member for name: '{member_name}'")
            return {"status": "NOT_FOUND", "message": f"Member '{member_name}' not found on board."}

        # Check if member is already assigned to the card to ensure idempotency
        try:
            raw_card = await self._request("GET", f"/cards/{card_id.strip()}")
            existing_members = raw_card.get("idMembers", [])
            if target_member_id in existing_members:
                return {"status": "SUCCESS", "member_id": target_member_id, "already_assigned": True}
        except Exception:
            pass

        try:
            res = await self._request("POST", f"/cards/{card_id.strip()}/idMembers", params={"value": target_member_id})
            return {"status": "SUCCESS", "member_id": target_member_id, "members": res}
        except TrelloError as te:
            if "already on the card" in str(te).lower():
                return {"status": "SUCCESS", "member_id": target_member_id, "already_assigned": True}
            raise

    # 4. List cards on a board or list
    async def list_cards(
        self,
        board_id: Optional[str] = None,
        list_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists cards on a specific list, or all cards across the board."""
        if list_id:
            cards = await self._request("GET", f"/lists/{list_id}/cards")
        else:
            target_board = board_id or self.board_id
            if not target_board:
                raise TrelloValidationError("No board_id provided and TRELLO_BOARD_ID is not configured.")
            cards = await self._request("GET", f"/boards/{target_board}/cards")

        return [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "desc": c.get("desc", ""),
                "idList": c.get("idList"),
                "idBoard": c.get("idBoard"),
                "closed": c.get("closed", False),
                "url": c.get("url"),
                "due": c.get("due"),
                "dueComplete": c.get("dueComplete", False),
                "dateLastActivity": c.get("dateLastActivity"),
                "labels": c.get("labels", []),
                "idMembers": c.get("idMembers", []),
            }
            for c in cards
        ]

    # 5. Get card details
    async def get_card(self, card_id: str) -> Dict[str, Any]:
        """Retrieves details of a specific card by its ID."""
        if not card_id or not card_id.strip():
            raise TrelloValidationError("card_id is required.")
        c = await self._request("GET", f"/cards/{card_id.strip()}")
        return {
            "id": c.get("id"),
            "name": c.get("name"),
            "desc": c.get("desc", ""),
            "idList": c.get("idList"),
            "idBoard": c.get("idBoard"),
            "closed": c.get("closed", False),
            "url": c.get("url"),
            "due": c.get("due"),
            "labels": c.get("labels", []),
            "idMembers": c.get("idMembers", []),
        }

    # 6. Create a card
    async def create_card(
        self,
        name: str,
        list_id: Optional[str] = None,
        desc: Optional[str] = "",
        due: Optional[str] = None,
        member_name: Optional[str] = None,
        board_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new card in the specified list (or the first list of the configured board)."""
        if not name or not name.strip():
            raise TrelloValidationError("Card name is required.")

        target_list_id = list_id
        if not target_list_id:
            # Auto-resolve the first list on board
            lists = await self.list_lists(board_id=board_id)
            if not lists:
                raise TrelloResourceNotFoundError("No lists found on the target board to place the card.")
            target_list_id = lists[0]["id"]

        params: Dict[str, Any] = {
            "name": name.strip(),
            "idList": target_list_id,
            "desc": (desc or "").strip(),
        }
        if due:
            parsed_due = parse_due_date_for_trello(due)
            if parsed_due:
                params["due"] = parsed_due

        c = await self._request("POST", "/cards", params=params)
        card_id = c.get("id")
        if member_name and card_id:
            try:
                await self.add_member_to_card(card_id=card_id, member_name=member_name, board_id=board_id)
            except Exception as e:
                logger.warning(f"Failed to assign member '{member_name}' to new card: {e}")

        return {
            "id": c.get("id"),
            "name": c.get("name"),
            "desc": c.get("desc", ""),
            "idList": c.get("idList"),
            "idBoard": c.get("idBoard"),
            "closed": c.get("closed", False),
            "url": c.get("url"),
            "due": c.get("due"),
            "shortUrl": c.get("shortUrl"),
        }

    # 7. Update card name, description, due date, or assigned member
    async def update_card(
        self,
        card_id: str,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        due: Optional[str] = None,
        member_name: Optional[str] = None,
        member_id: Optional[str] = None,
        board_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates the title, description, due date, and/or assigns a member to an existing card."""
        if not card_id or not card_id.strip():
            raise TrelloValidationError("card_id is required.")
        if name is None and desc is None and due is None and member_name is None and member_id is None:
            raise TrelloValidationError("At least one field ('name', 'desc', 'due', or 'member_name') must be provided to update.")

        params: Dict[str, Any] = {}
        if name is not None:
            params["name"] = name.strip()
        if desc is not None:
            params["desc"] = desc.strip()
        if due is not None:
            parsed_due = parse_due_date_for_trello(due)
            if parsed_due:
                params["due"] = parsed_due

        if params:
            c = await self._request("PUT", f"/cards/{card_id.strip()}", params=params)
        else:
            c = await self.get_card(card_id.strip())

        if member_name or member_id:
            try:
                mem_res = await self.add_member_to_card(card_id=card_id.strip(), member_name=member_name, member_id=member_id, board_id=board_id)
                if mem_res and mem_res.get("status") == "NOT_FOUND":
                    raise TrelloValidationError(f"Member '{member_name}' not found on the Trello board.")
                # Refresh card representation to include the new member
                c = await self.get_card(card_id.strip())
            except (TrelloValidationError, TrelloError):
                raise
            except Exception as e:
                logger.warning(f"Failed to assign member '{member_name}' to card '{card_id}': {e}")

        return {
            "id": c.get("id"),
            "name": c.get("name"),
            "desc": c.get("desc", ""),
            "idList": c.get("idList"),
            "idBoard": c.get("idBoard"),
            "closed": c.get("closed", False),
            "url": c.get("url"),
            "due": c.get("due"),
            "idMembers": c.get("idMembers", []),
        }

    # 8. Move a card between lists
    async def move_card(
        self,
        card_id: str,
        list_id: str,
        due: Optional[str] = None,
        desc: Optional[str] = None,
        board_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Moves a card to a different list, optionally updating due date and description."""
        if not card_id or not card_id.strip():
            raise TrelloValidationError("card_id is required.")
        if not list_id or not list_id.strip():
            raise TrelloValidationError("list_id is required.")

        params: Dict[str, Any] = {"idList": list_id.strip()}
        if due is not None:
            parsed_due = parse_due_date_for_trello(due)
            if parsed_due:
                params["due"] = parsed_due
        if desc is not None and not str(desc).lower().startswith("move card"):
            params["desc"] = desc.strip()

        c = await self._request("PUT", f"/cards/{card_id.strip()}", params=params)
        return {
            "id": c.get("id"),
            "name": c.get("name"),
            "idList": c.get("idList"),
            "idBoard": c.get("idBoard"),
            "closed": c.get("closed", False),
            "url": c.get("url"),
            "due": c.get("due"),
        }

    # 9. Archive a card
    async def archive_card(self, card_id: str) -> Dict[str, Any]:
        """Archives (closes) a card."""
        if not card_id or not card_id.strip():
            raise TrelloValidationError("card_id is required.")

        c = await self._request("PUT", f"/cards/{card_id.strip()}", params={"closed": "true"})
        return {
            "id": c.get("id"),
            "name": c.get("name"),
            "idList": c.get("idList"),
            "closed": c.get("closed", True),
            "archived": True,
        }

    # 10. Permanently delete a card
    async def delete_card(self, card_id: str) -> Dict[str, Any]:
        """Permanently deletes a card from Trello board."""
        if not card_id or not card_id.strip():
            raise TrelloValidationError("card_id is required.")

        await self._request("DELETE", f"/cards/{card_id.strip()}")
        return {
            "id": card_id.strip(),
            "deleted": True,
        }

    # 11. Post a comment on a card (Module 5 One-Hour Reminder)
    async def add_comment(self, card_id: str, text: str) -> Dict[str, Any]:
        """Posts a comment on a Trello card."""
        if not card_id or not card_id.strip():
            raise TrelloValidationError("card_id is required.")
        if not text or not text.strip():
            raise TrelloValidationError("text is required.")

        res = await self._request(
            "POST",
            f"/cards/{card_id.strip()}/actions/comments",
            params={"text": text.strip()}
        )
        return {
            "id": res.get("id"),
            "card_id": card_id.strip(),
            "text": text.strip(),
            "created_at": res.get("date"),
        }

