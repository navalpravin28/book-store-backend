# BookStore API — FastAPI + MongoDB (RBAC, VAPT-hardened)

Roles: **admin** and **viewer**. Browsing books / categories / active ads needs **no login**.
Viewers log in only to create, update and delete their own advertisements.

## Folder structure (same layout as your TIAA app)

```
BookStore/
└── app/
    ├── api/
    │   ├── endpoints/
    │   │   ├── advertisement.py   auth.py   book.py   category.py
    │   │   ├── dashboard.py       sale.py   upload.py   user.py
    │   └── router.py
    ├── core/
    │   ├── config.py       settings + production guards
    │   ├── db.py           Mongo client, get_db, indexes
    │   ├── exception.py    custom exceptions + handlers
    │   ├── security.py     bcrypt, JWT, get_current_user, require_roles
    │   ├── middleware.py   (added) security headers, body-size limit, rate limiter
    │   └── utils.py        (added) ObjectId, slug, csv_safe, date helpers
    ├── models/
    │   └── userModel.py    UserRole enum + user document factory
    ├── schema/             commonSchema, userSchema, categorySchema, bookSchema,
    │                       saleSchema, advertisementSchema, uploadSchema, dashboardSchema
    ├── services/           auth, user, category, book, sale, advertisement,
    │                       upload, dashboard, audit  (all class based: XService(db))
    ├── static/uploads/     books/  categories/  advertisements/   <- images stored in the project
    └── main.py
```
Request flow: **endpoint -> service -> Mongo**. Endpoints only validate and call a service.

## Run

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # set MONGO_URI, JWT_SECRET_KEY, ADMIN_*
uvicorn app.main:app --reload --no-server-header
```
Docs: http://localhost:8000/docs (hidden when `ENVIRONMENT=production`).
Tests: `pip install -r requirements-dev.txt && pytest`

On first start the admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` is created (only if no admin exists).
Login, then paste the `accessToken` into Swagger's **Authorize** button.

## Schemas (your fields + additions)

| Collection | Fields |
|---|---|
| **Category** | id, categoryName, description, imageUrl, slug (auto from name), server-assigned random `categoryColors` palette + *createdAt, updatedAt, bookCount* |
| **Book** | id, name, author, publisher, description, imageUrl, categoryId + *isbn, price, stock, soldCount, createdAt, updatedAt* |
| **Sale** (new) | bookId, bookName, categoryId, quantity, unitPrice, totalAmount, buyerName, buyerMobile, note, soldBy, soldByName, soldAt |
| **Advertisement** (new) | title, description, imageUrl, linkUrl, durationDays (1/2/3), startsAt, expiresAt, ownerId, ownerName |
| **User** | name, email, hashedPassword, role, isActive, failedLoginAttempts, lockUntil, lastLoginAt, passwordChangedAt |
| **AuditLog / RevokedToken** (new) | admin action trail / logged-out tokens (auto-expire) |

`stock` is the count on the shelf, `soldCount` is lifetime units sold. Sales store a snapshot of the
book name and price, so history stays correct if the book is later edited or deleted.

## Endpoints (`/api/v1`)

| Access | Method + path | What it does |
|---|---|---|
| public | `POST /auth/register` | create a **viewer** (role can never be chosen by the client) |
| public | `POST /auth/login` | JWT (30 min) |
| user | `POST /auth/logout` | revoke current token |
| user | `POST /auth/change-password` | invalidates all older tokens |
| user | `GET, PUT /users/me` | own profile |
| admin | `GET /users`, `PATCH /users/{id}/status` | list / enable / disable viewers |
| public | `GET /categories`, `GET /categories/{slug}` | browse |
| admin | `POST /categories`, `PUT, DELETE /categories/{id}` | manage (delete blocked while it has books) |
| public | `GET /books`, `GET /books/{id}` | search `q`, `categoryId`, `inStock`, `sortBy`, `order`, paging. No stock / sold numbers shown |
| admin | `GET /books/manage/list` | same + exact `stock`, `soldCount` |
| admin | `POST /books` | single create |
| admin | `POST /books/bulk?dryRun=` | CSV upload (see format below) |
| admin | `PUT, DELETE /books/{id}`, `PATCH /books/{id}/stock` | edit, delete, `{"delta": +5 / -2}` |
| admin | `GET /books/export/csv` | download the book list |
| admin | `POST /sales` | record a sale: reduces stock, increases soldCount, atomic |
| admin | `GET /sales` | sold data with buyer name + mobile; filters `dateFrom, dateTo, bookId, q` |
| admin | `GET /sales/export/csv`, `GET /sales/{id}` | download / one sale |
| public | `GET /advertisements` | only ads that have not expired |
| viewer/admin | `POST /advertisements` | `durationDays` must be 1, 2 or 3 |
| viewer/admin | `GET /advertisements/mine`, `PUT, DELETE /advertisements/{id}` | own ads only (admin: any). `PUT` with `durationDays` renews |
| admin | `GET /advertisements/manage/all?status=` | moderation |
| admin (books, categories) / any user (advertisements) | `POST /uploads/{kind}` | multipart `file` -> returns `imageUrl` |
| admin | `GET /dashboard/...` | analytics, below |

**Image flow:** `POST /uploads/books` (file) -> `{"imageUrl": "/static/uploads/books/<id>.jpg"}` -> send that
`imageUrl` in `POST /books`. Files are saved under `app/static/uploads/` and served at `/static/...`.

**CSV format** (`sample_books.csv`): required `name, author, publisher, price` and `categorySlug` (or `categoryId`);
optional `description, isbn, stock, imageUrl`. UTF-8, max 1000 rows /
2 MB. Valid rows are inserted, bad rows come back as `[{row, errors}]`; use `dryRun=true` to validate first.

## Analytics (admin) — `/dashboard`

| Path | Gives you |
|---|---|
| `/summary` | everything below in one call for the home screen |
| `/overview` | books, categories, total stock, inventory value, out-of-stock, low-stock, units sold, revenue, today / 7d / 30d, viewers, active ads |
| `/sales-trend?days=30` | sales, units, revenue per day (empty days filled with 0) |
| `/top-books?by=units\|revenue&limit=&days=` | best sellers |
| `/categories` | titles, stock, units sold, revenue per category |
| `/low-stock?threshold=` | books to restock |
| `/top-buyers` | repeat customers, mobile numbers masked |
| `/advertisements` | total / active / expired, active ads by 1-2-3 day length |

Day boundaries use `APP_TIMEZONE` (default Asia/Kolkata). All numbers come from MongoDB aggregation pipelines.

## VAPT checklist: what is built in

| Risk | Fix |
|---|---|
| Broken access control / privilege escalation | Role read from DB on every request (not trusted from token); `require_admin` on all admin routes; self-signup is always `viewer`; `extra="forbid"` blocks mass assignment |
| IDOR | Ads: owner-or-admin check, others get 404; sales / analytics admin only |
| Weak auth / brute force | bcrypt (cost 12), strong password policy, per-route rate limits, account lockout (5 fails -> 15 min), identical error + equal timing for unknown user vs wrong password |
| JWT attacks | Pinned algorithm, required `exp/iat/sub/jti`, issuer + audience checks, short life, logout revocation list, tokens die on password change or account disable |
| NoSQL injection | Typed Pydantic models (operators like `{"$ne": null}` are rejected), ObjectId validation, search text is regex-escaped, sort fields whitelisted |
| Insecure file upload | Magic-byte sniffing (filename / Content-Type ignored), only JPEG/PNG/WEBP (no SVG), size cap, pixel cap, image **re-encoded** (strips EXIF + payloads), random server-side names, traversal-proof delete, nosniff header |
| Stored XSS / bad links | `<` `>` rejected in text fields, `imageUrl` limited to our uploads or https, ad `linkUrl` https only, strict CSP header |
| CSV / formula injection | Exports prefix `'` to cells starting with `= + - @`; imports validated row by row, capped |
| Sensitive data exposure | Public book view hides stock / sold counts, ad owner hidden, buyer mobile masked in analytics, validation errors never echo input, 500s are generic |
| Security misconfiguration | Security headers, CORS allow-list (no `*` in production), TrustedHost, body-size limit (413), docs off in production, boot fails on weak production config |
| Race conditions | Sale and stock changes are single atomic Mongo updates, so stock can never go negative |
| Logging / repudiation | `auditLogs` for admin writes, exports (they contain phone numbers), user disable |

## Deployment items that code cannot do for you

- Serve only over **HTTPS** (TLS at nginx / load balancer); HSTS is sent in production.
- Run uvicorn with `--no-server-header`, and `--proxy-headers --forwarded-allow-ips=<proxy ip>` behind a proxy so rate limits see real client IPs.
- The rate limiter is in-memory per process. With several workers / servers back it with Redis (`Limiter(storage_uri="redis://...")`).
- Enable MongoDB authentication + TLS, keep it off the public network, take backups.
- Keep secrets in a secrets manager; remove `ADMIN_PASSWORD` from `.env` after first start.
- Consider antivirus scanning of uploads, a WAF, and `pip-audit` / dependency updates in CI.
- Ad creation requires a viewer login (so ads have an owner you can edit / delete / moderate); browsing never does.
- Prices are stored as floats rounded to 2 decimals; switch to integer paise if you add taxes / discounts.
