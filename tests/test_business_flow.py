import asyncio

from tests.conftest import login

CSV_HEADER = "name,author,publisher,description,categorySlug,isbn,price,stock\n"


async def _category(client, admin, name="Fiction"):
    r = await client.post("/api/v1/categories", json={"categoryName": name, "description": "Stories"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


async def _book(client, admin, category_id, **over):
    body = {"name": "Dune", "author": "Frank Herbert", "publisher": "Chilton", "categoryId": category_id,
            "price": 250.5, "stock": 10, "isbn": "978-0441013593"}
    body.update(over)
    return await client.post("/api/v1/books", json=body, headers=admin)


async def test_category_and_book_crud(client, admin):
    cat = await _category(client, admin, "Science Fiction")
    assert cat["slug"] == "science-fiction" and cat["bookCount"] == 0
    assert cat["categoryColors"] in [
        {"color": "#294C3B", "spineColor": "#1D362A", "textColor": "#FFF4D8", "accentColor": "#E9D7A5"},
        {"color": "#233B65", "spineColor": "#172744", "textColor": "#FFFFFF", "accentColor": "#7FD9E8"},
        {"color": "#493323", "spineColor": "#2E2017", "textColor": "#FFF4D8", "accentColor": "#D9B77C"},
        {"color": "#5B2C3A", "spineColor": "#3D1D27", "textColor": "#FFF4E8", "accentColor": "#E6B8A2"},
        {"color": "#3B6663", "spineColor": "#274542", "textColor": "#F4F7E8", "accentColor": "#D5DFA5"},
        {"color": "#3B3632", "spineColor": "#282522", "textColor": "#F5EFE6", "accentColor": "#C9A87C"},
    ]
    assert (await client.post(
        "/api/v1/categories",
        json={"categoryName": "Color Injection", "categoryColors": {"color": "#fff"}},
        headers=admin,
    )).status_code == 422
    assert (await client.post("/api/v1/categories", json={"categoryName": "Science Fiction"}, headers=admin)).status_code == 409

    r = await _book(client, admin, cat["id"])
    assert r.status_code == 201, r.text
    book = r.json()
    assert book["stock"] == 10 and book["soldCount"] == 0 and book["isbn"] == "9780441013593"
    assert (await _book(
        client,
        admin,
        cat["id"],
        isbn=None,
        name="Unknown request field",
        unexpectedField=True,
    )).status_code == 422
    assert (await _book(client, admin, cat["id"])).status_code == 409  # duplicate ISBN
    assert (await _book(client, admin, "f" * 24, isbn=None)).status_code == 404  # unknown category
    assert (await _book(client, admin, cat["id"], isbn=None, name="<script>x</script>")).status_code == 422
    assert (await _book(client, admin, cat["id"], isbn=None, price=-5)).status_code == 422
    assert (await _book(client, admin, cat["id"], isbn=None, stock=5, soldCount=999)).status_code == 422  # mass assignment
    without_isbn = await _book(client, admin, cat["id"], isbn="", name="Book without ISBN")
    assert without_isbn.status_code == 201 and without_isbn.json()["isbn"] is None
    assert (await client.delete(
        f"/api/v1/books/{without_isbn.json()['id']}", headers=admin
    )).status_code == 204

    # public view hides stock + sold numbers, admin view shows them
    pub = (await client.get(f"/api/v1/books/{book['id']}")).json()
    assert pub["inStock"] is True and "stock" not in pub and "soldCount" not in pub
    assert pub["categoryName"] == "Science Fiction"
    adm = (await client.get("/api/v1/books/manage/list", headers=admin)).json()
    assert adm["total"] == 1 and adm["items"][0]["stock"] == 10

    # update, stock moves (never negative)
    r = await client.put(f"/api/v1/books/{book['id']}", json={"price": 300}, headers=admin)
    assert r.status_code == 200 and r.json()["price"] == 300
    assert (await client.put(
        f"/api/v1/books/{book['id']}",
        json={"unexpectedField": True},
        headers=admin,
    )).status_code == 422
    assert (await client.patch(f"/api/v1/books/{book['id']}/stock", json={"delta": 5}, headers=admin)).json()["stock"] == 15
    assert (await client.patch(f"/api/v1/books/{book['id']}/stock", json={"delta": -99}, headers=admin)).status_code == 409

    # search is literal text, never a regex
    assert (await client.get("/api/v1/books", params={"q": "dun"})).json()["total"] == 1
    assert (await client.get("/api/v1/books", params={"q": ".*"})).json()["total"] == 0
    assert (await client.get("/api/v1/books", params={"limit": 1000})).status_code == 422
    assert (await client.get("/api/v1/books", params={"categoryId": {"$ne": 1}})).status_code in (200, 422)
    assert (await client.get("/api/v1/books/not-an-id")).status_code == 422

    # category with books cannot be deleted; book delete then category delete works
    assert (await client.delete(f"/api/v1/categories/{cat['id']}", headers=admin)).status_code == 409
    assert (await client.delete(f"/api/v1/books/{book['id']}", headers=admin)).status_code == 204
    assert (await client.delete(f"/api/v1/categories/{cat['id']}", headers=admin)).status_code == 204


async def test_bulk_csv_import_and_safe_export(client, admin):
    await _category(client, admin, "Fiction")
    csv_body = CSV_HEADER + (
        "Good Book,A. Author,Pub,Nice,fiction,9780306406157,199.99,5\n"
        "Second Book,B. Author,Pub,,fiction,,99,0\n"
        "Bad Price,C,Pub,,fiction,,abc,1\n"
        "No Category,C,Pub,,ghost,,10,1\n"
        "Dup ISBN,C,Pub,,fiction,9780306406157,10,1\n"
        "=HYPERLINK(\"http://evil\"),D,Pub,,fiction,,10,1\n"
    )
    files = {"file": ("books.csv", csv_body.encode(), "text/csv")}

    dry = await client.post("/api/v1/books/bulk", params={"dryRun": True}, files=files, headers=admin)
    assert dry.status_code == 200 and dry.json()["inserted"] == 3 and len(dry.json()["failed"]) == 3
    assert (await client.get("/api/v1/books/manage/list", headers=admin)).json()["total"] == 0  # dry run saved nothing

    res = await client.post("/api/v1/books/bulk", files=files, headers=admin)
    body = res.json()
    assert res.status_code == 200, res.text
    assert body["totalRows"] == 6 and body["inserted"] == 3
    assert {f["row"] for f in body["failed"]} == {4, 5, 6}
    imported = (await client.get("/api/v1/books/manage/list", headers=admin)).json()["items"]
    exp = await client.get("/api/v1/books/export/csv", headers=admin)
    assert exp.status_code == 200 and exp.headers["content-type"].startswith("text/csv")
    assert "attachment" in exp.headers["content-disposition"]
    text = exp.text
    assert "Good Book" in text and "'=HYPERLINK" in text  # formula injection neutralised

    # guard rails
    assert (await client.post("/api/v1/books/bulk", files={"file": ("x.txt", b"a", "text/plain")}, headers=admin)).status_code == 400
    assert (await client.post("/api/v1/books/bulk", files={"file": ("x.csv", b"name,author\n1,2\n", "text/csv")}, headers=admin)).status_code == 400
    assert (await client.post("/api/v1/books/bulk", files={"file": ("x.csv", b"\xff\xfe\x00bad", "text/csv")}, headers=admin)).status_code == 400
    many = CSV_HEADER + "".join(f"B{i},A,P,,fiction,,1,1\n" for i in range(1001))
    assert (await client.post("/api/v1/books/bulk", files={"file": ("m.csv", many.encode(), "text/csv")}, headers=admin)).status_code == 400


def _strip_timezone(pipeline):
    """mongomock cannot evaluate $dateToString{timezone}; real MongoDB can. Strip it for the mock only."""
    import copy
    pipeline = copy.deepcopy(pipeline)
    for stage in pipeline:
        group_id = stage.get("$group", {}).get("_id")
        if isinstance(group_id, dict) and "$dateToString" in group_id:
            group_id["$dateToString"].pop("timezone", None)
    return pipeline


async def test_sales_stock_and_analytics(client, admin, viewer, monkeypatch):
    from mongomock_motor import AsyncMongoMockCollection
    original = AsyncMongoMockCollection.aggregate
    monkeypatch.setattr(AsyncMongoMockCollection, "aggregate",
                        lambda self, pipeline, *a, **k: original(self, _strip_timezone(pipeline), *a, **k))

    cat = await _category(client, admin)
    book = (await _book(client, admin, cat["id"], stock=10, price=100)).json()
    book2 = (await _book(client, admin, cat["id"], name="Emma", isbn=None, stock=3, price=50)).json()

    sale = {"bookId": book["id"], "quantity": 2, "buyerName": "Ravi Kumar", "buyerMobile": "98765 43210"}
    r = await client.post("/api/v1/sales", json=sale, headers=admin)
    assert r.status_code == 201, r.text
    assert r.json()["totalAmount"] == 200 and r.json()["buyerMobile"] == "9876543210"
    await client.post("/api/v1/sales", json={**sale, "quantity": 1}, headers=admin)
    await client.post("/api/v1/sales", json={"bookId": book2["id"], "quantity": 3, "buyerName": "Meena S", "buyerMobile": "+919000000000"}, headers=admin)

    # stock decreased atomically, sold count increased
    items = {b["name"]: b for b in (await client.get("/api/v1/books/manage/list", headers=admin)).json()["items"]}
    assert items["Dune"]["stock"] == 7 and items["Dune"]["soldCount"] == 3
    assert items["Emma"]["stock"] == 0 and items["Emma"]["inStock"] is False

    # no overselling, bad input, wrong id
    assert (await client.post("/api/v1/sales", json={**sale, "quantity": 8}, headers=admin)).status_code == 409
    assert (await client.post("/api/v1/sales", json={**sale, "quantity": 0}, headers=admin)).status_code == 422
    assert (await client.post("/api/v1/sales", json={**sale, "buyerMobile": "12ab"}, headers=admin)).status_code == 422
    assert (await client.post("/api/v1/sales", json={**sale, "bookId": "e" * 24}, headers=admin)).status_code == 404

    # concurrent buyers can never push stock below zero
    results = await asyncio.gather(*[
        client.post("/api/v1/sales", json={**sale, "quantity": 3}, headers=admin) for _ in range(5)])
    assert sorted(r.status_code for r in results).count(201) == 2  # only 7 // 3 = 2 can succeed
    assert (await client.get(f"/api/v1/books/manage/list", headers=admin)).json()["items"]

    # sold data with buyer name + mobile, filters, csv
    listing = (await client.get("/api/v1/sales", params={"q": "ravi"}, headers=admin)).json()
    assert listing["total"] >= 3 and all(i["buyerName"] == "Ravi Kumar" for i in listing["items"])
    assert (await client.get("/api/v1/sales", params={"q": "90000"}, headers=admin)).json()["total"] == 1
    assert (await client.get("/api/v1/sales", params={"dateFrom": "2999-01-01"}, headers=admin)).json()["total"] == 0
    csv_text = (await client.get("/api/v1/sales/export/csv", headers=admin)).text
    assert "buyerMobile" in csv_text and "9876543210" in csv_text and "Ravi Kumar" in csv_text

    # analytics
    ov = (await client.get("/api/v1/dashboard/overview", headers=admin)).json()
    assert ov["totalBooks"] == 2 and ov["totalCategories"] == 1 and ov["totalViewers"] == 1
    assert ov["totalSales"] == 5 and ov["totalSoldUnits"] == 3 + 3 + 6 and ov["today"]["sales"] == 5
    assert ov["outOfStock"] == 1 and ov["lowStock"] == 1 and ov["totalRevenue"] > 0  # Emma 0 left, Dune 1 left
    trend = (await client.get("/api/v1/dashboard/sales-trend", params={"days": 7}, headers=admin)).json()
    assert len(trend) == 7 and sum(p["sales"] for p in trend) == 5 and trend[0]["sales"] == 0
    top = (await client.get("/api/v1/dashboard/top-books", params={"by": "revenue"}, headers=admin)).json()
    assert top[0]["bookName"] == "Dune"
    cats = (await client.get("/api/v1/dashboard/categories", headers=admin)).json()
    assert cats[0]["categoryName"] == "Fiction" and cats[0]["unitsSold"] == 12
    low = (await client.get("/api/v1/dashboard/low-stock", headers=admin)).json()
    assert {b["name"] for b in low} == {"Dune", "Emma"}
    buyers = (await client.get("/api/v1/dashboard/top-buyers", headers=admin)).json()
    assert buyers[0]["buyerMobileMasked"].endswith("3210") and "9876" not in buyers[0]["buyerMobileMasked"]
    summary = (await client.get("/api/v1/dashboard/summary", headers=admin)).json()
    assert set(summary) == {"overview", "salesTrend", "topBooks", "categories", "lowStock", "topBuyers", "advertisements"}
    assert (await client.get("/api/v1/dashboard/top-books", params={"by": "x"}, headers=admin)).status_code == 422


async def test_advertisements_with_time_limit_and_ownership(client, admin, viewer):
    ad = {"title": "Used books sale", "description": "50% off", "linkUrl": "https://example.com/sale", "durationDays": 2}
    r = await client.post("/api/v1/advertisements", json=ad, headers=viewer)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["status"] == "active" and created["durationDays"] == 2
    assert 47 * 3600 < (_dt(created["expiresAt"]) - _dt(created["startsAt"])).total_seconds() <= 48 * 3600 + 1

    # only 1, 2 or 3 days; https links only; no html; anonymous cannot create
    assert (await client.post("/api/v1/advertisements", json={**ad, "durationDays": 5}, headers=viewer)).status_code == 422
    assert (await client.post("/api/v1/advertisements", json={**ad, "linkUrl": "javascript:alert(1)"}, headers=viewer)).status_code == 422
    assert (await client.post("/api/v1/advertisements", json={**ad, "linkUrl": "http://plain.com"}, headers=viewer)).status_code == 422
    assert (await client.post("/api/v1/advertisements", json={**ad, "title": "<img src=x onerror=1>"}, headers=viewer)).status_code == 422
    assert (await client.post("/api/v1/advertisements", json=ad)).status_code == 401

    # public sees it without login, and without the owner's identity
    pub = (await client.get("/api/v1/advertisements")).json()
    assert pub["total"] == 1 and "ownerId" not in pub["items"][0] and "ownerName" not in pub["items"][0]

    # another viewer cannot touch it (404, no id probing)
    await client.post("/api/v1/auth/register", json={"name": "Viewer Two", "email": "v2@x.com", "password": "Viewer@1234"})
    other = await login(client, "v2@x.com", "Viewer@1234")
    assert (await client.put(f"/api/v1/advertisements/{created['id']}", json={"title": "Hacked ad"}, headers=other)).status_code == 404
    assert (await client.delete(f"/api/v1/advertisements/{created['id']}", headers=other)).status_code == 404

    # owner updates, renews with a new time limit
    r = await client.put(f"/api/v1/advertisements/{created['id']}", json={"title": "Sale extended", "durationDays": 3}, headers=viewer)
    assert r.status_code == 200 and r.json()["title"] == "Sale extended" and r.json()["durationDays"] == 3
    assert (await client.put(f"/api/v1/advertisements/{created['id']}", json={}, headers=viewer)).status_code == 400
    assert (await client.put(f"/api/v1/advertisements/{created['id']}", json={"owner": "x"}, headers=viewer)).status_code == 422

    # expiry: past-due ads disappear from the public list, cannot be edited without renewing
    from app.core.db import MongoDB
    from bson import ObjectId
    from datetime import datetime, timedelta, timezone
    await MongoDB.db.advertisements.update_one({"_id": ObjectId(created["id"])},
                                               {"$set": {"expiresAt": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    assert (await client.get("/api/v1/advertisements")).json()["total"] == 0
    mine = (await client.get("/api/v1/advertisements/mine", headers=viewer)).json()
    assert mine["total"] == 1 and mine["items"][0]["status"] == "expired"
    assert (await client.put(f"/api/v1/advertisements/{created['id']}", json={"title": "Late edit"}, headers=viewer)).status_code == 400
    assert (await client.put(f"/api/v1/advertisements/{created['id']}", json={"durationDays": 1}, headers=viewer)).json()["status"] == "active"

    # admin moderation + dashboard counts
    assert (await client.get("/api/v1/advertisements/manage/all", headers=admin)).json()["items"][0]["ownerName"] == "Viewer One"
    ads = (await client.get("/api/v1/dashboard/advertisements", headers=admin)).json()
    assert ads["active"] == 1 and ads["activeByDuration"]["1"] == 1
    assert (await client.delete(f"/api/v1/advertisements/{created['id']}", headers=admin)).status_code == 204
    assert (await client.get("/api/v1/advertisements/mine", headers=viewer)).json()["total"] == 0


async def test_active_ads_per_user_cap(client, viewer):
    ad = {"title": "Ad number", "durationDays": 1}
    for _ in range(5):
        assert (await client.post("/api/v1/advertisements", json=ad, headers=viewer)).status_code == 201
    assert (await client.post("/api/v1/advertisements", json=ad, headers=viewer)).status_code == 409


def _dt(value: str):
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
