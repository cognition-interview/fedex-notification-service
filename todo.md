# FedEx Notification Service — TODO

Simulated on-premise FedEx app: order tracking dashboard with notifications.

- [ ] Global requirement: entire app (all pages, components, copy, and interactions) must follow FedEx format/brand conventions consistently

---

## 1. Project Setup

- [ ] Initialize Angular project (`ng new fedex-notification-service`)
- [ ] Initialize PHP backend with Composer (`composer init`)
- [ ] Install PHP dependencies: `slim/slim` (routing), `slim/psr7`, `php-dotenv/vlucas-phpdotenv`
- [ ] Set up PostgreSQL connection via PDO using `POSTGRES_CONNECTION_STRING` from `.env`
- [ ] Configure project structure: `frontend/`, `backend/` (PHP), `migrations/`
- [ ] Set up PHP built-in server for dev (`php -S localhost:8000 -t backend/public`)
- [ ] Add CORS middleware for Angular dev server
- [ ] Add scripts for dev, build, seed, and test

---

## 2. Database & Models

### `initDatabase()` — `backend/src/Database.php`
- [ ] Create `Database` class with PDO singleton connection (reads `POSTGRES_CONNECTION_STRING` from `.env`)
- [ ] Tables defined in `migrations/` — run in order:
  - `001_create_businesses.sql` — `businesses` (uuid pk, name, account_number, address, contact_email, phone)
  - `002_create_orders.sql` — `orders` (uuid pk, business_id fk, tracking_number, origin, destination, status enum, weight_lbs, service_type enum, estimated_delivery, actual_delivery)
  - `003_create_shipment_events.sql` — `shipment_events` (uuid pk, order_id fk, event_type enum, location, description, occurred_at)
  - `004_create_notifications.sql` — `notifications` (uuid pk, order_id fk, business_id fk, type enum, message, is_read, created_at)
  - `005_updated_at_trigger.sql` — auto-update `orders.updated_at` via PostgreSQL trigger
- [ ] Add `Database::runMigrations()` to execute all `.sql` files in `migrations/` sequentially

### `seedDatabase()` — `backend/scripts/seed.php`
- [ ] Create `Seeder` class in `backend/src/Seeder.php`
- [ ] `Seeder::seedBusinesses()` — generate 5-8 fake businesses, all with `contact_email = 'gb555@cornell.edu'`
- [ ] `Seeder::seedOrders()` — generate 50-100 orders across businesses with varied statuses (Picked Up, In Transit, Out for Delivery, Delivered, Delayed, Exception)
- [ ] `Seeder::seedShipmentEvents()` — generate 3-8 shipment events per order (realistic scan history)
- [ ] `Seeder::seedNotifications()` — generate notifications for status changes, delays, and deliveries
- [ ] Use realistic city names, timestamps spanning last 30 days, and FedEx-style tracking numbers (e.g., `7489xxxxxxxxxxxx`)
- [ ] Run via `php backend/scripts/seed.php` (loads `.env` via phpdotenv)

---

## 3. Backend — PHP API Routes (Slim Framework)

### Router setup — `backend/public/index.php`
- [ ] Bootstrap Slim app, register middleware (CORS, JSON content-type)
- [ ] Register route groups: `/api/orders`, `/api/businesses`, `/api/notifications`, `/api/insights`
- [ ] Register `PATCH /api/orders/{id}/status` route → `OrderController::updateOrderStatus`

### `OrderController` — `backend/src/Controllers/OrderController.php`

#### `OrderController::getOrders($request, $response)`
- [ ] `GET /api/orders` — list orders with filtering and pagination
- [ ] Support query params: `businessId`, `status`, `fromDate`, `toDate`, `page`, `limit`
- [ ] Use PDO prepared statements with dynamic WHERE clauses

#### `OrderController::getOrderById($request, $response, $args)`
- [ ] `GET /api/orders/{id}` — single order with full shipment event history
- [ ] JOIN `shipment_events` table, return nested JSON

#### `OrderController::getOrderStats($request, $response)`
- [ ] `GET /api/orders/stats` — aggregate counts by status, avg delivery time, on-time percentage
- [ ] Use SQL `COUNT`, `AVG`, `GROUP BY` queries

#### `OrderController::updateOrderStatus($request, $response, $args)`
- [ ] `PATCH /api/orders/{id}/status` — update order status
- [ ] Accept body: `{ "status": "Delivered", "location": "Memphis, TN", "description": "..." }`
- [ ] Validate `status` is a valid `order_status` enum value; return 422 on invalid
- [ ] Update `orders.status` and `orders.updated_at` via PDO prepared statement
- [ ] Insert a new row into `shipment_events` to record the scan (event_type derived from new status)
- [ ] Trigger a `notifications` row inline for each status update event (same request/transaction, linked to order + business)
- [ ] Do not rely on background jobs/queues for notification creation
- [ ] If status changed, call `EmailService::sendStatusUpdateEmail()` to notify the business
- [ ] Return updated order object with 200, or 404 if order not found

### `EmailService` — `backend/src/Services/EmailService.php`

#### `EmailService::sendStatusUpdateEmail($order, $business, $newStatus)`
- [ ] Read `AZURE_EMAIL_CONNECTION_STRING` and `AZURE_EMAIL_FROM_ADDRESS` from `.env`
- [ ] Parse endpoint and access key from `AZURE_EMAIL_CONNECTION_STRING` (format: `endpoint=https://...;accesskey=...`)
- [ ] Build HMAC-SHA256 request signature for Azure authentication header
- [ ] POST to `{endpoint}/emails:send?api-version=2021-10-01-preview` with JSON body:
  ```json
  {
    "senderAddress": "<AZURE_EMAIL_FROM_ADDRESS>",
    "recipients": { "to": [{ "address": "<business.contact_email>" }] },
    "content": {
      "subject": "FedEx Update: Tracking #{{tracking_number}} — {{newStatus}}",
      "plainText": "Your shipment status has changed to {{newStatus}}. Tracking: {{tracking_number}}, Route: {{origin}} → {{destination}}.",
      "html": "<p>...</p>"
    }
  }
  ```
- [ ] Use PHP `curl` (via `curl_init`) to make the HTTP request
- [ ] On successful send, insert a row into `notifications` table (`type = 'Status Update'`, `is_read = false`)
- [ ] Log errors but do not block the status update response if email fails

### `BusinessController` — `backend/src/Controllers/BusinessController.php`

#### `BusinessController::getBusinesses($request, $response)`
- [ ] `GET /api/businesses` — list all businesses

#### `BusinessController::getBusinessById($request, $response, $args)`
- [ ] `GET /api/businesses/{id}` — single business with summary stats (order count, active shipments)

### `NotificationController` — `backend/src/Controllers/NotificationController.php`

#### `NotificationController::getNotifications($request, $response)`
- [ ] `GET /api/notifications` — list notifications with filtering
- [ ] Support query params: `businessId`, `read`, `page`, `limit`

#### `NotificationController::markNotificationRead($request, $response, $args)`
- [ ] `PATCH /api/notifications/{id}/read` — mark single notification as read
- [ ] Use PDO `UPDATE` with prepared statement

#### `NotificationController::markAllNotificationsRead($request, $response)`
- [ ] `PATCH /api/notifications/read-all` — mark all as read for a business
- [ ] Accept `businessId` in request body

### `InsightsController` — `backend/src/Controllers/InsightsController.php`

#### `InsightsController::getDeliveryInsights($request, $response)`
- [ ] `GET /api/insights` — delivery timeline analytics
- [ ] Calculate: avg transit time by route, on-time %, delays by service type
- [ ] Use SQL aggregation queries with optional `businessId` and date range filters

---

## 4. Frontend — Angular Components

### Theme & Layout

#### `setupFedExTheme()`
- [ ] Configure FedEx brand colors: purple (#4D148C), orange (#FF6200), white, gray
- [ ] Use old-school/corporate styling (no rounded corners, minimal shadows, structured grid layout)
- [ ] Add FedEx logo to header
- [ ] Set up global styles (fonts, buttons, tables, cards)

#### `AppLayoutComponent`
- [ ] Sidebar navigation with exactly 4 pages: `Businesses`, `Orders`, `Insights`, `Update Order Status`
- [ ] Top header bar with FedEx logo, business selector dropdown, notification bell icon

### Businesses

#### `BusinessesComponent`
- [ ] Show businesses list/table
- [ ] Add action on each business: "View Orders"
- [ ] Clicking "View Orders" should navigate to Orders page and pre-apply `businessId` filter in query params

### Orders

#### `OrderListComponent`
- [ ] Paginated table with columns: Tracking #, Origin, Destination, Status, Service Type, Date
- [ ] Filter bar supports all filters: `businessId`, `status`, `fromDate`, `toDate`, `trackingNumber` search, `page`, `limit`
- [ ] Read filters from URL query params on load (including redirected `businessId` from Businesses page)
- [ ] Keep filters synced to URL query params when changed
- [ ] Status badges with color coding (green=delivered, blue=in transit, red=exception, yellow=delayed)

#### `OrderDetailComponent`
- [ ] Order header (tracking number, status, service type, weight)
- [ ] Shipment timeline: vertical event list with timestamps, locations, and descriptions
- [ ] Origin → Destination summary with estimated vs actual delivery

### Insights

#### `InsightsComponent`
- [ ] Leave this page blank for now (placeholder component only)

### Update Order Status

#### `UpdateOrderStatusComponent`
- [ ] UI to select/order lookup and move status only from previous state → next allowed state
- [ ] Do not allow backward transitions to previous states
- [ ] On successful status update, trigger and surface the new notification in UI state
- [ ] Allowed forward flow:
  - `Picked Up` → `In Transit`
  - `In Transit` → `Out for Delivery` | `Delayed` | `Exception`
  - `Out for Delivery` → `Delivered` | `Delayed` | `Exception`
  - `Delayed` → `In Transit` | `Out for Delivery` | `Exception`
  - `Exception` → `In Transit` | `Out for Delivery` | `Delivered`
  - `Delivered` → no next state
- [ ] Disable/hide invalid transition options in UI and enforce same rule in backend validation

---

## 5. Frontend — Services

### `OrderService`
- [ ] `getOrders(filters)` — call `GET /api/orders`
- [ ] `getOrderById(id)` — call `GET /api/orders/:id`
- [ ] `getOrderStats()` — call `GET /api/orders/stats`

### `BusinessService`
- [ ] `getBusinesses()` — call `GET /api/businesses`
- [ ] `getBusinessById(id)` — call `GET /api/businesses/:id`

### `NotificationService`
- [ ] `getNotifications(filters)` — call `GET /api/notifications`
- [ ] `markAsRead(id)` — call `PATCH /api/notifications/:id/read`
- [ ] `markAllAsRead(businessId)` — call `PATCH /api/notifications/read-all`

### `InsightsService`
- [ ] `getDeliveryInsights(filters)` — call `GET /api/insights`

---

## 6. Tests (target: 20-30% coverage)

### Backend Tests (PHPUnit) — `backend/tests/`
- [ ] Install PHPUnit via Composer (`composer require --dev phpunit/phpunit`)
- [ ] `OrderControllerTest::testGetOrders()` — returns filtered list, pagination works
- [ ] `OrderControllerTest::testGetOrderById()` — returns order with events, 404 for missing
- [ ] `OrderControllerTest::testGetOrderStats()` — returns correct aggregate counts
- [ ] `OrderControllerTest::testUpdateOrderStatus()` — valid status updates order + inserts shipment event
- [ ] `OrderControllerTest::testUpdateOrderStatusInvalid()` — invalid status returns 422
- [ ] `EmailServiceTest::testSendStatusUpdateEmail()` — mock Azure curl call, assert correct JSON payload shape and auth header
- [ ] `NotificationControllerTest::testGetNotifications()` — filters by read/unread and business
- [ ] `NotificationControllerTest::testMarkNotificationRead()` — toggles read status
- [ ] `InsightsControllerTest::testGetDeliveryInsights()` — returns calculated metrics

### Frontend Tests
- [ ] `DashboardComponent` — renders summary cards with data
- [ ] `OrderListComponent` — renders table rows, filters apply
- [ ] `OrderDetailComponent` — renders shipment timeline
- [ ] `NotificationListComponent` — renders notifications, mark-read works
- [ ] `InsightsComponent` — renders charts with data

---

## 7. Operational

- [ ] Seed script runnable via `php backend/scripts/seed.php`
- [ ] Dev server script: starts PHP built-in server (`php -S localhost:8000`) + Angular dev server (`ng serve`)
- [ ] `composer.json` with autoload PSR-4 config (`FedEx\\` → `backend/src/`)
- [ ] Add `.env` to `.gitignore`
- [ ] README with setup instructions (PHP version, Composer, Angular CLI, Supabase connection string)
