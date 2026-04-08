# FedEx Notification Service — Comprehensive Functionality Reference

> **Purpose:** This document captures every feature, endpoint, component, data model, and integration in the current on-prem FedEx Notification Service. It is intended as the single source of truth for modernization planning.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Database Schema](#database-schema)
4. [Backend API](#backend-api)
5. [Email Service (Azure Communication Services)](#email-service-azure-communication-services)
6. [Frontend Application](#frontend-application)
7. [Infrastructure & Deployment](#infrastructure--deployment)
8. [Data Seeding](#data-seeding)
9. [Testing](#testing)
10. [Environment Variables & Secrets](#environment-variables--secrets)
11. [Known Constraints & Modernization Notes](#known-constraints--modernization-notes)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                      Browser (Angular 21 SPA)            │
│   Port 4200  ──proxy /api──►  Port 8000 (PHP backend)   │
└──────────────┬───────────────────────────┬───────────────┘
               │                           │
               │  HTTP (JSON REST)         │  SMTP / HTTPS
               ▼                           ▼
     ┌──────────────────┐       ┌───────────────────────┐
     │   PostgreSQL DB   │       │  Azure Communication  │
     │   (Cloud-hosted)  │       │   Services (Email)    │
     └──────────────────┘       └───────────────────────┘
```

- **Frontend:** Angular 21 single-page application served by `ng serve` dev server on port 4200. A `proxy.conf.json` forwards all `/api` requests to the PHP backend on port 8000.
- **Backend:** PHP 8.3 + Slim Framework 4 micro-framework. Uses PHP's built-in web server (`php -S`) in development. Serves a JSON REST API under `/api`.
- **Database:** PostgreSQL (cloud-hosted, SSL required). Connected via PDO singleton with IPv4-forced DNS resolution.
- **Email:** Azure Communication Services REST API with HMAC-SHA256 authentication. Sends branded HTML + plain-text status-update emails.

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend framework | Angular | 21.2.x |
| Frontend language | TypeScript | 5.9.x |
| Charting | Chart.js + ng2-charts | 4.5 / 10.0 |
| Frontend test runner | Vitest | 4.0.x |
| Backend runtime | PHP | 8.3 |
| Backend framework | Slim Framework | 4.12.x |
| HTTP abstractions | PSR-7 (slim/psr7) | 1.7.x |
| Environment config | vlucas/phpdotenv | 5.6.x |
| Backend test framework | PHPUnit | 11.x |
| Database | PostgreSQL | (cloud-hosted) |
| Email provider | Azure Communication Services | REST API 2021-10-01-preview |
| Container | Docker (Alpine PHP 8.3 CLI) | — |
| Orchestration | docker-compose | — |
| Package managers | Composer (backend), npm (frontend) | — |

---

## Database Schema

### Custom Enums

#### `order_status`
```
'Picked Up' | 'In Transit' | 'Out for Delivery' | 'Delivered' | 'Delayed' | 'Exception'
```

#### `service_type`
```
'FedEx Ground' | 'FedEx Express' | 'FedEx Overnight' | 'FedEx 2Day' | 'FedEx International'
```

#### `event_type`
```
'Package Picked Up' | 'Arrived at FedEx Hub' | 'Departed FedEx Hub' | 'In Transit' |
'Out for Delivery' | 'Delivery Attempted' | 'Delivered' | 'Delay Reported' |
'Exception' | 'Package at Local Facility'
```

#### `notification_type`
```
'Status Update' | 'Delay Alert' | 'Delivery Confirmed' | 'Exception Alert' | 'Out for Delivery'
```

### Tables

#### `businesses`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, default `gen_random_uuid()` |
| `name` | TEXT | NOT NULL |
| `account_number` | TEXT | NOT NULL, UNIQUE |
| `address` | TEXT | — |
| `contact_email` | TEXT | — |
| `phone` | TEXT | — |
| `created_at` | TIMESTAMPTZ | NOT NULL, default `NOW()` |

#### `orders`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, default `gen_random_uuid()` |
| `business_id` | UUID | FK → `businesses(id)` ON DELETE CASCADE |
| `tracking_number` | TEXT | NOT NULL, UNIQUE |
| `origin` | TEXT | NOT NULL |
| `destination` | TEXT | NOT NULL |
| `status` | `order_status` | NOT NULL, default `'Picked Up'` |
| `weight_lbs` | NUMERIC(8,2) | — |
| `service_type` | `service_type` | NOT NULL, default `'FedEx Ground'` |
| `estimated_delivery` | DATE | — |
| `actual_delivery` | DATE | — |
| `created_at` | TIMESTAMPTZ | NOT NULL, default `NOW()` |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default `NOW()` |

**Indexes:** `idx_orders_business_id`, `idx_orders_status`, `idx_orders_created_at`

**Trigger:** `orders_updated_at` — auto-sets `updated_at = NOW()` before every UPDATE via `set_updated_at()` function.

#### `shipment_events`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, default `gen_random_uuid()` |
| `order_id` | UUID | FK → `orders(id)` ON DELETE CASCADE |
| `event_type` | `event_type` | NOT NULL |
| `location` | TEXT | NOT NULL |
| `description` | TEXT | — |
| `occurred_at` | TIMESTAMPTZ | NOT NULL, default `NOW()` |

**Indexes:** `idx_shipment_events_order_id`, `idx_shipment_events_occurred_at`

#### `notifications`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, default `gen_random_uuid()` |
| `order_id` | UUID | FK → `orders(id)` ON DELETE CASCADE |
| `business_id` | UUID | FK → `businesses(id)` ON DELETE CASCADE |
| `type` | `notification_type` | NOT NULL |
| `message` | TEXT | NOT NULL |
| `is_read` | BOOLEAN | NOT NULL, default `FALSE` |
| `created_at` | TIMESTAMPTZ | NOT NULL, default `NOW()` |

**Indexes:** `idx_notifications_business_id`, `idx_notifications_is_read`, `idx_notifications_created_at`

### Entity Relationships

```
businesses  1──────M  orders
orders      1──────M  shipment_events
orders      1──────M  notifications
businesses  1──────M  notifications
```

---

## Backend API

All endpoints are prefixed with `/api`. The backend uses Slim Framework 4 with PSR-7 request/response interfaces. CORS is handled via middleware that allows all origins (`*`) with `GET, POST, PATCH, OPTIONS` methods.

### Orders

#### `GET /api/orders` — List orders (paginated, filterable)

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default 1, min 1) |
| `limit` | int | Items per page (default 10, max 100) |
| `businessId` | UUID | Filter by business |
| `status` | string | Filter by `order_status` enum value |
| `serviceType` or `service_type` | string | Filter by `service_type` enum value |
| `fromDate` | string | Filter orders created on or after this date |
| `toDate` | string | Filter orders created on or before this date |
| `search` | string | ILIKE search across tracking_number (with/without spaces), origin, destination |

**Response:**
```json
{
  "orders": [
    {
      "id": "uuid",
      "tracking_number": "TRK...",
      "origin": "City, ST",
      "destination": "City, ST",
      "status": "In Transit",
      "weight_lbs": "12.50",
      "service_type": "FedEx Express",
      "estimated_delivery": "2026-04-10",
      "actual_delivery": null,
      "created_at": "2026-04-01T12:00:00+00",
      "updated_at": "2026-04-05T08:30:00+00",
      "business_id": "uuid",
      "business_name": "Acme Corp"
    }
  ],
  "total": 150,
  "page": 1,
  "limit": 10
}
```

#### `GET /api/orders/stats` — Aggregate order statistics

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `businessId` | UUID | Optional — scope stats to one business |

**Response:**
```json
{
  "by_status": {
    "total": 10000,
    "picked_up": 0,
    "in_transit": 397,
    "out_for_delivery": 1241,
    "delivered": 6770,
    "delayed": 1000,
    "exception": 592
  },
  "recent_orders": [ /* last 10 orders with business_name */ ],
  "unread_notifications": 30028
}
```

#### `GET /api/orders/{id}` — Get single order with shipment events

**Response:** Full order object joined with `business_name`, `contact_email`, `business_id`, plus a nested `shipment_events` array (sorted DESC by `occurred_at`).

#### `PATCH /api/orders/{id}/status` — Update order status

**Request Body:**
```json
{
  "status": "In Transit",
  "location": "Memphis, TN",
  "description": "Package arrived at sorting facility"
}
```

**Valid statuses:** `Picked Up`, `In Transit`, `Out for Delivery`, `Delivered`, `Delayed`, `Exception`

**Side Effects (all within one request):**
1. Updates `orders.status`; sets `actual_delivery = NOW()` if status is `Delivered`
2. Inserts a `shipment_events` row with mapped `event_type`
3. Inserts a `notifications` row with mapped `notification_type`
4. Sends an email via Azure Communication Services to the business `contact_email`
5. Returns the refreshed order (same as `GET /api/orders/{id}`)

**Status → Event Type Mapping:**
| Order Status | Shipment Event Type |
|-------------|-------------------|
| Picked Up | Package Picked Up |
| In Transit | In Transit |
| Out for Delivery | Out for Delivery |
| Delivered | Delivered |
| Delayed | Delay Reported |
| Exception | Exception |

**Status → Notification Type Mapping:**
| Order Status | Notification Type |
|-------------|-----------------|
| Delivered | Delivery Confirmed |
| Out for Delivery | Out for Delivery |
| Delayed | Delay Alert |
| Exception | Exception Alert |
| *(others)* | Status Update |

### Businesses

#### `GET /api/businesses` — List businesses (paginated)

**Query Parameters:** `page` (default 1), `limit` (default 10, max 100)

**Response:**
```json
{
  "businesses": [
    {
      "id": "uuid",
      "name": "Acme Corp",
      "account_number": "ACC-0001-A1B2C3",
      "address": "123 Main St, City, ST",
      "contact_email": "ops@acme.com",
      "phone": "+1-555-123-4567",
      "created_at": "2026-01-15T10:00:00+00"
    }
  ],
  "total": 300,
  "page": 1,
  "limit": 10
}
```

#### `GET /api/businesses/{id}` — Get business detail with aggregated stats

**Response:** Business fields plus:
- `total_orders` (int) — all orders for this business
- `active_shipments` (int) — orders NOT in `Delivered` or `Exception` status
- `unread_notifications` (int) — unread notification count
- `recent_orders` (array) — last 10 orders for this business

### Notifications

#### `GET /api/notifications` — List notifications (paginated, filterable)

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Default 1 |
| `limit` | int | Default 10, max 100 |
| `businessId` | UUID | Filter by business |
| `read` | boolean | Filter by read state (`true`/`false`) |

**Response:**
```json
{
  "notifications": [
    {
      "id": "uuid",
      "order_id": "uuid",
      "business_id": "uuid",
      "type": "Delay Alert",
      "message": "Tracking #TRK...: status changed to Delayed.",
      "is_read": false,
      "created_at": "2026-04-05T14:00:00+00",
      "tracking_number": "TRK...",
      "origin": "City, ST",
      "destination": "City, ST"
    }
  ],
  "total": 500,
  "page": 1,
  "limit": 10
}
```

#### `PATCH /api/notifications/{id}/read` — Mark single notification as read

**Response:** The updated notification object.

#### `PATCH /api/notifications/read-all` — Mark all notifications as read

**Request Body (optional):**
```json
{ "businessId": "uuid" }
```
If `businessId` is provided, only marks that business's unread notifications. Otherwise marks all.

**Response:** `{ "updated": 42 }`

### Insights

#### `GET /api/insights` — Delivery performance analytics

**Response:**
```json
{
  "avg_delivery_time_by_service": [
    { "service_type": "FedEx Overnight", "avg_hours": 28.5 },
    { "service_type": "FedEx Express", "avg_hours": 52.1 }
  ],
  "on_time_percentage": 87.3,
  "delivery_volume_30d": [
    { "date": "2026-03-10", "count": 45 },
    { "date": "2026-03-11", "count": 38 }
  ],
  "top_routes": [
    { "origin": "New York, NY", "destination": "Los Angeles, CA", "count": 120 }
  ],
  "delay_breakdown": [
    { "reason": "Weather", "count": 55 },
    { "reason": "Address Issue", "count": 30 }
  ]
}
```

**Computation Details:**
- **avg_delivery_time_by_service:** Average hours between `created_at` and `actual_delivery` for delivered orders, grouped by `service_type`.
- **on_time_percentage:** Percentage of delivered orders where `actual_delivery <= estimated_delivery`.
- **delivery_volume_30d:** Daily count of deliveries for the last 30 days (uses `generate_series` to fill zero-count days).
- **top_routes:** Top 5 origin→destination pairs by shipment count.
- **delay_breakdown:** Categorizes delay/exception events by keyword matching on `shipment_events.description` (Weather, Address Issue, Customs Hold, Volume Surge, Vehicle Breakdown) or by `event_type` fallback. Top 5 reasons.

---

## Email Service (Azure Communication Services)

**File:** `backend/src/Services/EmailService.php`

### Configuration
- Parses `AZURE_EMAIL_CONNECTION_STRING` to extract `endpoint` and `accesskey`
- Uses `AZURE_EMAIL_FROM_ADDRESS` as the sender

### Authentication
- HMAC-SHA256 signature over `POST\n{path}\n{date};{host};{contentHash}`
- Headers: `x-ms-date`, `x-ms-content-sha256`, `Authorization`, `Repeatability-Request-ID`, `Repeatability-First-Sent`
- API version: `2021-10-01-preview`

### Email Content
Sends to the business's `contact_email` with:
- **Subject:** `FedEx Update: Tracking #{tracking_number} — {newStatus}`
- **Plain text:** Formatted summary with tracking number, route, new status, description, timestamp
- **HTML:** FedEx-branded email with purple (#4D148C) header bar, FedEx orange (#FF6200) accent, tabular shipment details

### Trigger
Called from `OrderController::updateOrderStatus()`. Email failures are caught and logged but do not fail the HTTP response (non-blocking).

---

## Frontend Application

### Global Layout (`AppLayoutComponent`)

**Persistent shell with sidebar + header + content area.**

#### Sidebar Navigation
| Route | Icon | Label |
|-------|------|-------|
| `/businesses` | 🏢 | Businesses |
| `/orders` | 📋 | Orders |
| `/insights` | 📊 | Insights |
| `/update-status` | ✏️ | Update Status |

#### Header
- **Title:** "FedEx Notification Service"
- **Business Selector:** Dropdown populated from `GET /api/businesses?limit=100`. Selecting a business filters all pages globally via a `BehaviorSubject` in `BusinessService`. "All Businesses" option clears the filter.
- **Notification Bell:** Badge shows unread count (caps at "99+"). Dropdown shows 5 most recent unread notifications with relative timestamps. Clicking a notification navigates to the related order. Footer links to `/notifications`.

#### Routing
| Path | Component | Loading |
|------|-----------|---------|
| `/` | Redirects to `/businesses` | — |
| `/businesses` | `BusinessesComponent` | Lazy |
| `/orders` | `OrderListComponent` | Lazy |
| `/orders/:id` | `OrderDetailComponent` | Lazy |
| `/insights` | `InsightsComponent` | Lazy |
| `/update-status` | `UpdateStatusComponent` | Lazy |
| `/notifications` | `NotificationListComponent` | Lazy |
| `**` | Redirects to `/businesses` | — |

All routes use Angular's `withComponentInputBinding()` for route parameter binding.

### Page: Businesses (`/businesses`)

**Functionality:**
- Paginated table of all registered business accounts (10 per page)
- Columns: Business Name, Account #, Address, Contact Email, Phone, Actions
- "View Orders →" button sets the global business filter and navigates to `/orders?businessId={id}`
- Pagination controls (Prev/Next) with "X–Y of Z" display

**API calls:** `GET /api/businesses?page={n}&limit=10`

### Page: Orders (`/orders`)

**Functionality:**
- Paginated, filterable table of all orders (10 per page)
- **Filters:** Status dropdown, Service Type dropdown, free-text search (tracking number, origin, destination)
- Respects the global business selector from the header
- Accepts `?businessId=` query param (e.g., from Businesses page) to auto-set filter
- Columns: Tracking #, Business (truncated ID), Origin, Destination, Status (color badge), Service, Weight, Est. Delivery
- Clicking a row navigates to `/orders/{id}`
- Pagination controls

**Status Badge Colors (CSS classes):**
- `badge-picked-up`, `badge-in-transit`, `badge-out-for-delivery`, `badge-delivered`, `badge-delayed`, `badge-exception`

**API calls:** `GET /api/orders?page={n}&limit=10&businessId=...&status=...&serviceType=...&search=...`

### Page: Order Detail (`/orders/:id`)

**Functionality:**
- Breadcrumb: Orders > {tracking_number}
- **Header Card:** Tracking number (large), status badge, service type, weight
- **Shipment Details Card:** Origin, Destination, Estimated Delivery, Actual Delivery, Last Updated, Business Name, Account #
- **Shipment Timeline Card:** Chronological list of all shipment events (newest first) showing datetime, event type, location, description
- "← Back to Orders" button

**API calls:** `GET /api/orders/{id}`, `GET /api/businesses/{business_id}`

### Page: Insights (`/insights`)

**Functionality:**
- **On-Time Delivery Rate:** Large percentage display with color coding:
  - ≥90% → Green (#155724) — "Excellent performance"
  - ≥70% → Yellow (#856404) — "Acceptable — room to improve"
  - <70% → Red (#721c24) — "Below target — action required"
- **Avg Delivery Time by Service Type:** Horizontal bar chart (Chart.js) showing average hours per service type
- **Delivery Volume (Last 30 Days):** Line chart with area fill showing daily delivery counts
- **Delay Breakdown:** Doughnut chart showing categorized delay reasons
- **Top Routes by Volume:** Table showing top 5 origin→destination pairs with shipment counts

**Chart Colors:** FedEx purple (#4D148C), FedEx orange (#FF6200), plus Bootstrap-style accents.

**API calls:** `GET /api/insights`

### Page: Update Status (`/update-status`)

**Functionality:**
- **Step 1 — Order Lookup:** Text input for tracking number. Searches via the orders list API and finds an exact match (normalizing spaces). Shows error if not found.
- **Step 2 — Order Summary:** Displays tracking #, current status badge, route, service type, estimated delivery.
- **Step 3 — Status Transition:** Shows only valid next statuses as clickable buttons (e.g., "In Transit → Out for Delivery").
- **Step 4 — Additional Fields:** Location text input (pre-filled with origin), Description text input.
- **Step 5 — Submit:** Calls `PATCH /api/orders/{id}/status`. Shows success message with old→new status. If order is in terminal state (`Delivered` with no transitions), shows "No further transitions available."
- **Cache Invalidation:** After a successful update, all order/stats caches in `OrderService` are cleared.

**Status Transition Rules (frontend-enforced):**
| Current Status | Allowed Next Statuses |
|---------------|----------------------|
| Picked Up | In Transit |
| In Transit | Out for Delivery, Delayed, Exception |
| Out for Delivery | Delivered, Delayed, Exception |
| Delayed | In Transit, Out for Delivery, Exception |
| Exception | In Transit, Out for Delivery, Delivered |
| Delivered | *(none — terminal state)* |

**API calls:** `GET /api/orders?search={tracking}&limit=20`, `PATCH /api/orders/{id}/status`

### Page: Notifications (`/notifications`)

**Functionality:**
- **Tab Filter:** All / Unread / Read tabs
- **Mark All as Read** button (visible when unread notifications exist)
- Paginated notification list (10 per page)
- Each notification shows: icon (based on type), message text, relative timestamp, unread dot indicator
- Clicking a notification marks it as read and navigates to the related order detail

**Notification Icons:**
| Type keyword | Icon |
|-------------|------|
| delivery | 📦 |
| delay | ⏰ |
| exception | ⚠️ |
| status | 🔄 |
| pick | 🚚 |
| *(default)* | 🔔 |

**API calls:** `GET /api/notifications?businessId=...&read=...&page={n}&limit=10`, `PATCH /api/notifications/{id}/read`, `PATCH /api/notifications/read-all`

### Frontend Services

All services use in-memory caching via `Map` + `shareReplay(1)` for GET requests. Cache is invalidated on mutations.

#### `OrderService`
- `getOrders(filters)` — cached by serialized filter params
- `getOrderById(id)` — cached by ID
- `getOrderStats(businessId?)` — cached by business ID
- `updateOrderStatus(id, payload)` — invalidates all caches on success
- Normalizes `by_status` wrapper from stats response
- Maps `events` → `shipment_events` for backwards compatibility

#### `BusinessService`
- `getBusinesses(page, limit)` — cached by page:limit key
- `getBusinessById(id)` — cached by ID
- `getSelectedBusinessId()` / `setSelectedBusinessId(id)` — global business filter via `BehaviorSubject`

#### `NotificationService`
- `getNotifications(filters)` — cached by serialized params; normalizes `is_read` to boolean
- `markAsRead(id)` — clears cache
- `markAllAsRead(businessId?)` — clears cache
- `getUnreadCount(businessId?)` — derived from `getNotifications` with `read=false`

#### `InsightsService`
- `getDeliveryInsights()` — cached globally (single request); normalizes all numeric fields

### Frontend Environment

- **Development:** `apiUrl: 'http://localhost:8000'` (proxied through `proxy.conf.json` for `ng serve`)
- **Production:** `apiUrl: ''` (relative URLs, expects backend at same origin)

---

## Infrastructure & Deployment

### Docker

**Dockerfile** (backend only):
- Base: `php:8.3-cli-alpine`
- Installs: `libpq-dev`, `pdo`, `pdo_pgsql` extensions
- Copies Composer from official image
- Exposes port 8000
- CMD: `composer install && php -S 0.0.0.0:8000 -t public`

**docker-compose.yml:**
- Single `backend` service
- Mounts repo root as `/app`
- Reads `.env` file for environment variables
- Maps port 8000:8000

### Local Development (without Docker)

```bash
# Backend
cd backend && composer install && php -S 0.0.0.0:8000 -t public

# Frontend
cd frontend && npm install && npx ng serve --host 0.0.0.0
```

The Angular dev server proxies `/api` to `http://localhost:8000` via `proxy.conf.json`.

---

## Data Seeding

**File:** `migrations/seed_large_dataset.sql`

Creates a realistic demo dataset:
- **300 businesses** with randomized names (prefix + suffix + number), account numbers, addresses across 30 US cities, emails, phone numbers
- **10,000 orders** distributed across businesses with randomized:
  - Origin/destination (distinct cities)
  - Service type (weighted: 35% Ground, 27% Express, 12% Overnight, 15% 2Day, 11% International)
  - Created dates spanning last 120 days
  - Estimated delivery based on service type
- **3–8 shipment events per order** following a realistic lifecycle (always starts with "Package Picked Up", middle events randomized, final event determines order status)
- **1 notification per shipment event** with appropriate types and randomized read/unread state
- Final order status distribution: ~68% Delivered, ~12% Out for Delivery, ~10% Delayed, ~6% Exception, ~4% In Transit

**Usage:**
```bash
psql "$POSTGRES_CONNECTION_STRING?sslmode=require" -v ON_ERROR_STOP=1 -f migrations/seed_large_dataset.sql
```

> ⚠️ The seed script **TRUNCATES all tables** before inserting.

---

## Testing

### Backend (PHPUnit)

```bash
cd backend && ./vendor/bin/phpunit
```

- **Bootstrap** (`tests/bootstrap.php`): Sets dummy `$_ENV` values for `POSTGRES_CONNECTION_STRING`, `AZURE_EMAIL_CONNECTION_STRING`, `AZURE_EMAIL_FROM_ADDRESS` so controller/service constructors don't fail.
- **Test files:**
  - `EmailServiceTest.php` — Tests email service construction and signature building
  - `NotificationControllerTest.php` — Tests notification CRUD operations
  - `OrderControllerTest.php` — Tests order listing, detail, status updates
- Tests use `Database::setTestInstance(PDO $pdo)` to inject a mock/test PDO connection.

### Frontend (Vitest)

```bash
cd frontend && npm test
```

- Uses `@angular/build:unit-test` builder with Vitest
- Test files: `*.spec.ts` alongside components

---

## Environment Variables & Secrets

| Variable | Purpose |
|----------|---------|
| `POSTGRES_CONNECTION_STRING` | Full PostgreSQL connection URL (e.g., `postgresql://user:pass@host:5432/dbname`) |
| `AZURE_EMAIL_CONNECTION_STRING` | Azure Communication Services connection string (contains `endpoint` and `accesskey`) |
| `AZURE_EMAIL_FROM_ADDRESS` | Sender email address for notifications |
| `AZURE_APP_ID` | Azure service principal app ID (for `az login`) |
| `AZURE_PASSWORD` | Azure service principal password |
| `AZURE_TENANT_ID` | Azure AD tenant ID |

The `.env` file is loaded by `vlucas/phpdotenv` from the repo root (two directories above `backend/public/index.php`).

---

## Known Constraints & Modernization Notes

### Current Limitations

1. **No authentication/authorization.** All API endpoints are publicly accessible. No user sessions, JWT, or API keys.
2. **No WebSocket or real-time push.** Notifications are pull-based — the frontend polls on page load and navigation.
3. **CORS allows all origins** (`Access-Control-Allow-Origin: *`). No origin restriction.
4. **No rate limiting** on any endpoints.
5. **PHP built-in web server** is used for serving — not production-grade (no process management, no worker pool).
6. **No database migrations runner.** SQL files in `migrations/` must be applied manually via `psql`.
7. **Email is synchronous** within the HTTP request. The `updateOrderStatus` endpoint blocks briefly for the email HTTP call (15s timeout), though failures are caught.
8. **In-memory frontend caching** (via `shareReplay`) means stale data can appear after external changes until navigation triggers a fresh fetch. Mutations do clear caches.
9. **No pagination cursor/keyset.** Uses OFFSET-based pagination which degrades at scale.
10. **No soft deletes.** CASCADE deletes propagate through all related records.
11. **Single-tenant.** No multi-tenancy or organizational isolation.
12. **Frontend status transitions are only enforced client-side.** The backend accepts any valid status regardless of current state.
13. **No health check endpoint.** No `/healthz` or `/ready` for orchestration probes.
14. **Docker setup is backend-only.** No containerized frontend build or combined deployment.
15. **No CI/CD pipeline** defined in the repository.

### Data Model Observations for Modernization

- UUIDs used throughout (good for distributed systems)
- PostgreSQL-specific features heavily used: enums, `FILTER` clauses, `generate_series`, `gen_random_uuid()`, custom triggers
- `actual_delivery` is stored as `DATE` (no time component), while `created_at`/`updated_at` are `TIMESTAMPTZ`
- The `shipment_events.description` field is used for keyword-based delay categorization in insights — a dedicated `delay_reason` enum might be cleaner
- Business contact emails were bulk-set to a single email (migration 006) for demo purposes
