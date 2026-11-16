import httpx
import pytest
from app.integrations.trello import (
    TrelloAuthenticationError,
    TrelloClient,
    TrelloConfigError,
    TrelloResourceNotFoundError,
    TrelloValidationError,
)


def create_mock_trello_client(custom_handler=None):
    def default_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        # 401 Unauthorized test
        if "invalid_key" in str(request.url.params):
            return httpx.Response(401, text="invalid key")

        # 404 Not Found test
        if "not_found" in path:
            return httpx.Response(404, text="The requested resource was not found.")

        # Boards
        if path == "/1/members/me/boards":
            return httpx.Response(
                200,
                json=[
                    {"id": "b101", "name": "Sprint Board 2026", "desc": "Sprint Tasks", "closed": False},
                    {"id": "b102", "name": "Backlog Board", "desc": "Future ideas", "closed": False},
                ],
            )
        elif path == "/1/boards/b101":
            return httpx.Response(200, json={"id": "b101", "name": "Sprint Board 2026", "desc": "Sprint Tasks", "closed": False})

        # Lists
        elif path == "/1/boards/b101/lists":
            return httpx.Response(
                200,
                json=[
                    {"id": "l_todo", "name": "To Do", "idBoard": "b101", "closed": False},
                    {"id": "l_doing", "name": "In Progress", "idBoard": "b101", "closed": False},
                    {"id": "l_done", "name": "Done", "idBoard": "b101", "closed": False},
                ],
            )

        # Cards on Board
        elif path == "/1/boards/b101/cards":
            return httpx.Response(
                200,
                json=[
                    {"id": "c1", "name": "Setup DB", "idList": "l_todo", "idBoard": "b101", "closed": False},
                    {"id": "c2", "name": "API Auth", "idList": "l_doing", "idBoard": "b101", "closed": False},
                ],
            )

        # Cards on List
        elif path == "/1/lists/l_todo/cards":
            return httpx.Response(
                200,
                json=[
                    {"id": "c1", "name": "Setup DB", "idList": "l_todo", "idBoard": "b101", "closed": False},
                ],
            )

        # Single Card details
        elif path == "/1/cards/c1":
            if request.method == "GET":
                return httpx.Response(200, json={"id": "c1", "name": "Setup DB", "desc": "Task details", "idList": "l_todo", "idBoard": "b101", "closed": False})
            elif request.method == "PUT":
                params = dict(request.url.params)
                closed = params.get("closed") == "true"
                new_list = params.get("idList", "l_todo")
                new_name = params.get("name", "Setup DB")
                new_desc = params.get("desc", "Task details")
                return httpx.Response(200, json={"id": "c1", "name": new_name, "desc": new_desc, "idList": new_list, "idBoard": "b101", "closed": closed})

        # Card Creation
        elif path == "/1/cards" and request.method == "POST":
            params = dict(request.url.params)
            return httpx.Response(
                200,
                json={
                    "id": "c_new",
                    "name": params.get("name", "New Card"),
                    "desc": params.get("desc", ""),
                    "idList": params.get("idList", "l_todo"),
                    "idBoard": "b101",
                    "closed": False,
                    "url": "https://trello.com/c/mock123",
                },
            )

        return httpx.Response(404, text="Not Found")

    handler = custom_handler or default_handler
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TrelloClient(
        api_key="mock_key",
        token="mock_token",
        board_id="b101",
        http_client=http_client,
    )


@pytest.mark.asyncio
async def test_trello_missing_credentials_raises_config_error():
    client = TrelloClient(api_key="", token="", board_id="b1")
    with pytest.raises(TrelloConfigError):
        await client.list_boards()


@pytest.mark.asyncio
async def test_trello_invalid_credentials_raises_auth_error():
    client = create_mock_trello_client()
    client.api_key = "invalid_key"
    with pytest.raises(TrelloAuthenticationError):
        await client.list_boards()


@pytest.mark.asyncio
async def test_trello_resource_not_found():
    client = create_mock_trello_client()
    with pytest.raises(TrelloResourceNotFoundError):
        await client.get_card("not_found_card")


@pytest.mark.asyncio
async def test_trello_validation_errors():
    client = create_mock_trello_client()
    # Empty card name
    with pytest.raises(TrelloValidationError):
        await client.create_card(name="")

    # Missing card_id on update
    with pytest.raises(TrelloValidationError):
        await client.update_card(card_id="", name="test")

    # Update with neither name nor desc
    with pytest.raises(TrelloValidationError):
        await client.update_card(card_id="c1")

    # Missing list_id on move
    with pytest.raises(TrelloValidationError):
        await client.move_card(card_id="c1", list_id="")


@pytest.mark.asyncio
async def test_trello_list_boards():
    client = create_mock_trello_client()
    boards = await client.list_boards()
    assert len(boards) == 2
    assert boards[0]["id"] == "b101"
    assert boards[0]["name"] == "Sprint Board 2026"


@pytest.mark.asyncio
async def test_trello_get_board():
    client = create_mock_trello_client()
    board = await client.get_board("b101")
    assert board["id"] == "b101"
    assert board["name"] == "Sprint Board 2026"


@pytest.mark.asyncio
async def test_trello_list_lists():
    client = create_mock_trello_client()
    lists = await client.list_lists("b101")
    assert len(lists) == 3
    assert lists[0]["name"] == "To Do"
    assert lists[1]["name"] == "In Progress"


@pytest.mark.asyncio
async def test_trello_list_cards():
    client = create_mock_trello_client()
    # Board cards
    all_cards = await client.list_cards(board_id="b101")
    assert len(all_cards) == 2

    # List cards
    list_cards = await client.list_cards(list_id="l_todo")
    assert len(list_cards) == 1
    assert list_cards[0]["name"] == "Setup DB"


@pytest.mark.asyncio
async def test_trello_get_card():
    client = create_mock_trello_client()
    card = await client.get_card("c1")
    assert card["id"] == "c1"
    assert card["name"] == "Setup DB"
    assert card["idList"] == "l_todo"


@pytest.mark.asyncio
async def test_trello_create_card():
    client = create_mock_trello_client()
    # Explicit list ID
    new_card = await client.create_card(name="Implement User Authentication", list_id="l_todo", desc="OAuth flow")
    assert new_card["id"] == "c_new"
    assert new_card["name"] == "Implement User Authentication"
    assert new_card["idList"] == "l_todo"

    # Auto-resolve list from board
    auto_card = await client.create_card(name="Auto Placed Task")
    assert auto_card["id"] == "c_new"
    assert auto_card["idList"] == "l_todo"


@pytest.mark.asyncio
async def test_trello_update_card():
    client = create_mock_trello_client()
    updated = await client.update_card(card_id="c1", name="Setup PostgreSQL", desc="New details")
    assert updated["id"] == "c1"
    assert updated["name"] == "Setup PostgreSQL"
    assert updated["desc"] == "New details"


@pytest.mark.asyncio
async def test_trello_move_card():
    client = create_mock_trello_client()
    moved = await client.move_card(card_id="c1", list_id="l_done")
    assert moved["id"] == "c1"
    assert moved["idList"] == "l_done"


@pytest.mark.asyncio
async def test_trello_archive_card():
    client = create_mock_trello_client()
    archived = await client.archive_card(card_id="c1")
    assert archived["id"] == "c1"
    assert archived["closed"] is True
    assert archived["archived"] is True

