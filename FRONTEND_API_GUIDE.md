# Frontend API guide: categories and books

This guide covers category and book CRUD, uploading their images, and bulk
creating books. The examples use the API's default prefix, `/api/v1`.

## Base URL and authentication

Set `API_BASE_URL` to the backend origin, for example `http://localhost:8000`.
Requests below use `${API_BASE_URL}/api/v1`.

Category and book browsing is public. Creating or updating categories and books,
uploading category/book images, and bulk importing books require an admin access
token:

```http
Authorization: Bearer <accessToken>
```

Get the token from `POST /api/v1/auth/login`. Send JSON requests with
`Content-Type: application/json`. Image and CSV uploads use
`Content-Type: multipart/form-data`; let the browser set the multipart boundary
when using `FormData`.

Successful create requests return `201 Created`; updates return `200 OK`.
Validation errors return `422`, and API errors use this shape:

```json
{
  "success": false,
  "message": "Validation failed",
  "errors": [
    {
      "field": "price",
      "message": "Input should be greater than or equal to 0"
    }
  ]
}
```

## Upload a category or book image

Upload the image first, then use its returned `imageUrl` in the category or
book JSON request.

```http
POST /api/v1/uploads/categories
Authorization: Bearer <adminAccessToken>
Content-Type: multipart/form-data
```

For book covers use `POST /api/v1/uploads/books`. Both endpoints accept a
multipart field named `file`. Supported formats are JPEG, PNG, and WEBP; the
maximum upload size is 2 MB and each image dimension must be at most 6000 px.
The server re-encodes uploaded images and generates the filename.

Example using browser `fetch`:

```js
const formData = new FormData();
formData.append("file", selectedFile);

const response = await fetch(`${API_BASE_URL}/api/v1/uploads/categories`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
  body: formData,
});
const uploadedImage = await response.json();
```

Response (`201 Created`):

```json
{
  "imageUrl": "/static/uploads/categories/8cc12605ee714337b2b7f02c8947e11c.jpg",
  "contentType": "image/jpeg",
  "size": 48231
}
```

Save `imageUrl` and send it unchanged in the category/book request. It is a
relative URL served by the backend; for display, resolve it against the backend
origin (for example,
`${API_BASE_URL}${uploadedImage.imageUrl}`). An HTTPS image URL can also be
provided directly instead of uploading.

## Categories

### Create a category

```http
POST /api/v1/categories
Authorization: Bearer <adminAccessToken>
Content-Type: application/json
```

Request:

```json
{
  "categoryName": "Biography",
  "description": "Biographies and autobiographies",
  "imageUrl": "/static/uploads/categories/8cc12605ee714337b2b7f02c8947e11c.jpg"
}
```

`description` defaults to an empty string and `imageUrl` is optional. The
category name must be 2–80 characters; the description can be up to 500
characters. HTML angle brackets are not allowed in text fields. Category names
must be unique.

Response (`201 Created`):

```json
{
  "id": "6650aab217cd9bf223598eed",
  "categoryName": "Biography",
  "description": "Biographies and autobiographies",
  "imageUrl": "/static/uploads/categories/8cc12605ee714337b2b7f02c8947e11c.jpg",
  "slug": "biography",
  "categoryColors": {
    "color": "#294C3B",
    "spineColor": "#1D362A",
    "textColor": "#FFF4D8",
    "accentColor": "#E9D7A5"
  },
  "bookCount": 0,
  "createdAt": "2026-10-18T01:30:00Z",
  "updatedAt": "2026-10-18T01:30:00Z"
}
```

The `slug` is generated from the name and is used to retrieve a category.
`categoryColors` is randomly assigned by the server at creation from its
built-in palette. Do not send it in create or update requests; unknown request
fields are rejected. The same colors are returned by category list and detail
responses.

### Update a category

```http
PUT /api/v1/categories/{categoryId}
Authorization: Bearer <adminAccessToken>
Content-Type: application/json
```

Request fields are optional; send only the fields to change:

```json
{
  "categoryName": "Memoir & Biography",
  "description": "Memoirs, biographies, and autobiographies",
  "imageUrl": "/static/uploads/categories/44f84791111549c39cd56132e76ded3f.webp"
}
```

Response (`200 OK`) has the same shape as the category create response, with
the updated `slug` and `updatedAt`. To remove an existing category image, send
`"imageUrl": null`. Category name and description cannot be cleared with null.
The old locally uploaded image is removed when replaced or cleared.

### Public category reads

```http
GET /api/v1/categories?page=1&limit=50&q=bio
GET /api/v1/categories/{slug}
```

The list response is:

```json
{
  "items": [
    {
      "id": "6650aab217cd9bf223598eed",
      "categoryName": "Biography",
      "description": "Biographies and autobiographies",
      "imageUrl": "/static/uploads/categories/8cc12605ee714337b2b7f02c8947e11c.jpg",
      "slug": "biography",
      "categoryColors": {
        "color": "#294C3B",
        "spineColor": "#1D362A",
        "textColor": "#FFF4D8",
        "accentColor": "#E9D7A5"
      },
      "bookCount": 12,
      "createdAt": "2026-10-18T01:30:00Z",
      "updatedAt": "2026-10-18T01:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 50
}
```

The single-category endpoint returns one category object in the same shape.
`page` defaults to 1, `limit` defaults to 50 and has a maximum of 100, and `q`
searches category names.

## Books

### Create a book

```http
POST /api/v1/books
Authorization: Bearer <adminAccessToken>
Content-Type: application/json
```

Request:

```json
{
  "name": "Wings of Fire",
  "author": "A. P. J. Abdul Kalam",
  "publisher": "Universities Press",
  "description": "Autobiography of the Missile Man",
  "imageUrl": "/static/uploads/books/58dc86f0dd26465c93f4b6b21d7469e4.jpg",
  "categoryId": "6650aab217cd9bf223598eed",
  "isbn": "9788173711466",
  "price": 250,
  "stock": 12
}
```

Required fields: `name`, `author`, `publisher`, `categoryId`, and `price`.
`description` defaults to `""`, `imageUrl` and `isbn` are optional, and `stock`
defaults to `0`. Text fields must not contain HTML angle brackets. `categoryId`
must identify an existing category. ISBN may be ISBN-10 or ISBN-13; spaces and
hyphens are removed. Price must be from 0 to 1,000,000; stock must be from 0
to 1,000,000.

Response (`201 Created`):

```json
{
  "id": "6650b12d17cd9bf223598ef0",
  "name": "Wings of Fire",
  "author": "A. P. J. Abdul Kalam",
  "publisher": "Universities Press",
  "description": "Autobiography of the Missile Man",
  "imageUrl": "/static/uploads/books/58dc86f0dd26465c93f4b6b21d7469e4.jpg",
  "categoryId": "6650aab217cd9bf223598eed",
  "categoryName": "Biography",
  "isbn": "9788173711466",
  "price": 250.0,
  "inStock": true,
  "stock": 12,
  "soldCount": 0,
  "createdAt": "2026-10-18T01:30:00Z",
  "updatedAt": "2026-10-18T01:30:00Z"
}
```

`inStock` is derived from `stock`. Admin responses include exact `stock` and `soldCount`;
public book responses omit those values.

### Update a book

```http
PUT /api/v1/books/{bookId}
Authorization: Bearer <adminAccessToken>
Content-Type: application/json
```

Request fields are optional; send only the fields to change:

```json
{
  "price": 275,
  "categoryId": "6650aab217cd9bf223598eed",
  "imageUrl": "/static/uploads/books/972222a4a2ea4af8990bcfbb4ee0bde5.png"
}
```

Response (`200 OK`) has the same shape as the book create response, with
updated values and `updatedAt`. Send `"imageUrl": null` to remove the current
image; when a local image is replaced or removed, the old upload is deleted.
Null values for other optional fields are ignored. The update endpoint does not
change stock or sold count: use `PATCH /api/v1/books/{bookId}/stock` with
`{"delta": 5}` or `{"delta": -2}` to adjust stock.

### Public book reads

```http
GET /api/v1/books?page=1&limit=20&q=wings&categoryId=6650aab217cd9bf223598eed&inStock=true&sortBy=price&order=asc
GET /api/v1/books/{bookId}
```

The list response has the pagination shape shown for categories, with `items`
containing public book objects. Public book objects have the book response
fields above except `stock`, `soldCount`, `createdAt`, and `updatedAt`.
`page` defaults to 1; `limit` defaults to 20 and has a maximum of 100. Search
matches book name and author. Supported public `sortBy` values are `name`,
`price`, and `createdAt`; `order` is `asc` or `desc`.

## Bulk book creation from CSV

Bulk creation accepts a CSV file, not a JSON array. Use an existing category's
`slug` or `id` in each row. The category slug can be retrieved from the category
API.

```http
POST /api/v1/books/bulk?dryRun=true
Authorization: Bearer <adminAccessToken>
Content-Type: multipart/form-data
```

Attach the CSV in the multipart field named `file`. `dryRun` is optional and
defaults to `false`. Set it to `true` to validate rows without creating books.
Maximum file size is 2 MB; maximum number of data rows is 1000. The CSV must be
UTF-8 encoded.

Required CSV columns are `name`, `author`, `publisher`, and `price`, plus at
least one of `categorySlug` or `categoryId`. If both category columns exist,
`categoryId` takes precedence for a row when it is populated. Supported
optional columns are `description`, `imageUrl`, `isbn`, and `stock`. Missing or
blank optional values use the same defaults as single book creation.

Example CSV:

```csv
name,author,publisher,description,categorySlug,isbn,price,stock,imageUrl
Wings of Fire,A. P. J. Abdul Kalam,Universities Press,Autobiography,biography,9788173711466,250,12,/static/uploads/books/58dc86f0dd26465c93f4b6b21d7469e4.jpg
The Alchemist,Paulo Coelho,HarperOne,A fable about following a dream,fiction,9780062315007,299,20,
```

Example `fetch`:

```js
const formData = new FormData();
formData.append("file", csvFile);

const response = await fetch(
  `${API_BASE_URL}/api/v1/books/bulk?dryRun=true`,
  {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  },
);
const result = await response.json();
```

Response (`200 OK`):

```json
{
  "dryRun": true,
  "totalRows": 2,
  "inserted": 2,
  "failed": []
}
```

In a dry run, `inserted` is the number of valid rows that would be created; no
books are written to the database. With `dryRun=false`, it is the number
successfully created. Row failures include the physical CSV line number
(header is line 1), and up to 100 failures are returned:

```json
{
  "dryRun": false,
  "totalRows": 2,
  "inserted": 1,
  "failed": [
    {
      "row": 3,
      "errors": [
        "categorySlug: 'unknown-category' does not exist",
        "price: Input should be greater than or equal to 0"
      ]
    }
  ]
}
```

Rows that fail validation are not created; valid rows are still created unless
`dryRun=true`. A duplicate ISBN already present in the database is reported as a
row failure.
