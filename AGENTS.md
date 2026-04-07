# AGENTS.md — FedEx Notification Service

> **Source-of-truth architecture document for the full system modernization and cloud migration.**
>
> | Attribute | Legacy (Current) | Target (New) |
> |---|---|---|
> | **Hosting** | On-premise | Azure-native (PaaS / serverless) |
> | **Backend** | PHP 7.x | Python 3.12+ (FastAPI) |
> | **Frontend** | Angular 12 | React 18+ (Vite, TypeScript) |
> | **Database** | MySQL 5.7 | Azure Database for PostgreSQL — Flexible Server |
> | **Queue / Bus** | Cron + database polling | Azure Service Bus |
> | **Email** | On-prem SMTP relay | Azure Communication Services (Email) |
> | **Auth** | LDAP / session cookies | Microsoft Entra ID (Azure AD) + MSAL |
> | **Observability** | Log files + Nagios | Azure Monitor / Application Insights |
> | **Secrets** | Config files on disk | Azure Key Vault (+ environment injection) |

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Agents & Services](#2-agents--services)
3. [End-to-End Workflows](#3-end-to-end-workflows)
4. [Interfaces & Contracts](#4-interfaces--contracts)
5. [Data Flow & Storage](#5-data-flow--storage)
6. [Failure Handling, Retries & Idempotency](#6-failure-handling-retries--idempotency)
7. [Scalability & Performance](#7-scalability--performance)
8. [Security & Access Control](#8-security--access-control)
9. [Observability](#9-observability)
10. [Migration Mapping](#10-migration-mapping)
11. [Environment & Configuration](#11-environment--configuration)
12. [Appendices](#12-appendices)

---

## 1. System Overview

The FedEx Notification Service is responsible for **ingesting shipment tracking events from FedEx**, **evaluating notification rules**, and **delivering multi-channel notifications** (email, SMS, webhook) to customers, internal operations teams, and downstream systems.

### 1.1 High-Level Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌────────────────────┐
│  FedEx Track API │─────▶│  Ingestion Agent  │─────▶│  Azure Service Bus  │
│  (Webhooks/Poll) │      │  (FastAPI)        │      │  (Topics & Queues)  │
└─────────────────┘      └──────────────────┘      └────────┬───────────┘
                                                            │
                         ┌──────────────────────────────────┼──────────────────────┐
                         │                                  │                      │
                         ▼                                  ▼                      ▼
              ┌─────────────────┐              ┌─────────────────┐     ┌─────────────────────┐
              │  Event Processor │              │ Notification     │     │  Analytics Sink      │
              │  Agent           │              │ Delivery Agent   │     │  (Event Archival)    │
              │  (Azure Function)│              │ (Azure Function) │     │  (Azure Function)    │
              └────────┬────────┘              └────────┬────────┘     └─────────────────────┘
                       │                                │
                       ▼                                ▼
              ┌─────────────────┐              ┌─────────────────┐
              │  PostgreSQL      │              │  Azure Comms     │
              │  (State + Rules) │              │  Services (Email)│
              └─────────────────┘              └─────────────────┘

              ┌─────────────────────────────────────────────┐
              │  Admin Dashboard (React SPA)                 │
              │  ── Notification templates, rules, analytics │
              └─────────────────────────────────────────────┘
```

### 1.2 Core Capabilities

| Capability | Description |
|---|---|
| **Shipment event ingestion** | Receive real-time and polled tracking updates from FedEx Track API v2 |
| **Rule-based routing** | Evaluate configurable rules to decide which notifications fire for which events |
| **Multi-channel delivery** | Send notifications via email (Azure Communication Services), SMS, and outbound webhooks |
| **Template management** | Version-controlled, parameterized notification templates with Jinja2 rendering |
| **Preference management** | Per-recipient and per-account notification preferences and opt-out handling |
| **Audit & compliance** | Immutable audit log of every notification decision and delivery attempt |
| **Admin dashboard** | React-based UI for managing templates, rules, recipients, and reviewing delivery analytics |

---

## 2. Agents & Services

Each agent is a **deployable, independently scalable unit** with clearly defined inputs, outputs, and responsibilities.

### 2.1 Ingestion Agent

| Property | Value |
|---|---|
| **Runtime** | FastAPI application on Azure Container Apps |
| **Trigger** | FedEx webhook push **and** scheduled polling (fallback) |
| **Output** | Publishes raw `ShipmentEvent` messages to Azure Service Bus topic `shipment-events` |
| **Data store** | PostgreSQL — `ingestion_log` table (deduplication + audit) |

#### Responsibilities

1. **Webhook receiver** — Expose `POST /api/v1/webhooks/fedex` endpoint that accepts FedEx Track API v2 push notifications. Validate the `X-FedEx-Signature` HMAC header against the shared secret.
2. **Polling fallback** — A scheduled Azure Function (`ingestion-poller`) calls the FedEx Track API every 5 minutes for shipments that have not received a webhook update within the configured SLA window (default: 15 min). This covers webhook delivery failures.
3. **Deduplication** — Each incoming event is assigned a deterministic `event_fingerprint` (SHA-256 of `tracking_number + event_timestamp + status_code`). Before publishing, the agent performs an upsert against `ingestion_log`. If the fingerprint already exists, the event is acknowledged but not re-published.
4. **Normalization** — Raw FedEx payloads vary across API versions and event types. The ingestion agent transforms every payload into a canonical `ShipmentEvent` schema (see [§4.1](#41-shipmentevent-schema)) before publishing.
5. **Back-pressure signaling** — If the Service Bus topic reports throttling (HTTP 429), the agent buffers events in-memory (bounded queue, max 10 000) and applies exponential back-off with jitter (base 1 s, max 60 s).

#### Legacy (PHP) Equivalent

- `cron/fetch_tracking.php` — Polled FedEx SOAP API on a 10-minute cron interval.
- `api/webhook_handler.php` — Received push notifications; no signature validation; stored raw payloads in `raw_events` MySQL table.
- Deduplication relied on a MySQL `UNIQUE` index on `(tracking_number, event_code, event_timestamp)` — this caused silent drops when FedEx sent events with identical codes but different descriptions.

---

### 2.2 Event Processor Agent

| Property | Value |
|---|---|
| **Runtime** | Azure Functions (Python, consumption plan) |
| **Trigger** | Azure Service Bus topic subscription `shipment-events/sub-event-processor` |
| **Output** | Publishes `NotificationRequest` messages to Service Bus queue `notification-requests` |
| **Data store** | PostgreSQL — `notification_rules`, `recipient_preferences`, `processed_events` |

#### Responsibilities

1. **Rule evaluation** — Load active rules from `notification_rules` (cached in-memory with 60 s TTL). Each rule is expressed as a JSON predicate tree:
   ```json
   {
     "rule_id": "uuid",
     "name": "Delivery Exception Alert",
     "conditions": {
       "all": [
         {"field": "status_category", "op": "eq", "value": "EXCEPTION"},
         {"field": "ship_date_age_days", "op": "gte", "value": 2}
       ]
     },
     "channels": ["email", "webhook"],
     "template_id": "uuid",
     "priority": "high",
     "enabled": true
   }
   ```
   Rules are evaluated top-down by priority; **all matching rules fire** (not short-circuit).

2. **Recipient resolution** — For each matched rule, determine the recipient list:
   - Account-level recipients from `account_contacts` table.
   - Shipment-level overrides from the `ShipmentEvent.notification_overrides` field.
   - Filter out recipients who have opted out via `recipient_preferences`.

3. **Enrichment** — Attach additional context to the notification request:
   - Shipment details (origin, destination, estimated delivery, service type).
   - Account metadata (company name, branding configuration).
   - Historical context (previous events for the same tracking number).

4. **Throttle check** — Enforce per-recipient rate limits (default: max 5 notifications per tracking number per hour). Excess notifications are logged as `THROTTLED` but not delivered.

5. **Emit `NotificationRequest`** — Publish one message per recipient-channel pair to the `notification-requests` queue.

#### Legacy (PHP) Equivalent

- `services/RuleEngine.php` — Hardcoded PHP `if/else` chains; rules were not configurable without a code deployment.
- `services/RecipientResolver.php` — SQL queries with no caching; caused database hotspots under load.
- No throttle mechanism existed; a FedEx API hiccup once sent 40 000 duplicate emails in 12 minutes.

---

### 2.3 Notification Delivery Agent

| Property | Value |
|---|---|
| **Runtime** | Azure Functions (Python, consumption plan) |
| **Trigger** | Azure Service Bus queue `notification-requests` |
| **Output** | Delivery status written to PostgreSQL `delivery_log`; dead-letter on permanent failure |
| **External services** | Azure Communication Services (Email), Twilio (SMS), outbound webhooks |

#### Responsibilities

1. **Template rendering** — Load the referenced template from `notification_templates` (cached, 5 min TTL). Render using Jinja2 with the context from the `NotificationRequest` payload.
   - Templates support conditional blocks, loops, and localization keys.
   - HTML email templates include a plain-text fallback auto-generated via `html2text`.

2. **Channel dispatch** — Route to the appropriate delivery provider:

   | Channel | Provider | Mechanism |
   |---|---|---|
   | **Email** | Azure Communication Services | `azure-communication-email` SDK; connection string from `AZURE_EMAIL_CONNECTION_STRING` |
   | **SMS** | Twilio | REST API via `twilio` Python SDK |
   | **Webhook** | Customer-configured endpoints | HTTP POST with HMAC-SHA256 signature in `X-Notification-Signature` header |

3. **Delivery tracking** — Each delivery attempt is logged in `delivery_log` with:
   - `delivery_id` (UUID v4)
   - `notification_request_id` (correlation)
   - `channel`, `recipient`, `status` (`PENDING`, `SENT`, `DELIVERED`, `BOUNCED`, `FAILED`)
   - `provider_message_id` (for provider-side lookup)
   - `attempt_number`, `next_retry_at`

4. **Retry with back-off** — On transient failures (5xx, timeout, rate-limit):
   - Retry up to **3 times** with exponential back-off (delays: 30 s, 120 s, 480 s).
   - On exhaustion, move the message to the Service Bus dead-letter queue and mark as `FAILED`.
   - Permanent failures (4xx except 429) are immediately dead-lettered.

5. **Bounce / feedback processing** — A separate timer-triggered function (`delivery-feedback-poller`) polls Azure Communication Services for delivery status updates (bounces, complaints) every 2 minutes and updates `delivery_log`.

#### Legacy (PHP) Equivalent

- `services/Mailer.php` — Used PHPMailer against an on-prem SMTP relay. No retry logic; failures were silently logged to a text file.
- `services/SmsGateway.php` — Thin wrapper around a legacy SMPP gateway. SMS was unreliable and often delayed by hours.
- No webhook delivery existed.
- No centralized delivery log; delivery status was scattered across multiple log files.

---

### 2.4 Template Management Service

| Property | Value |
|---|---|
| **Runtime** | FastAPI (part of the core API, same Container App as Ingestion Agent) |
| **Data store** | PostgreSQL — `notification_templates`, `template_versions` |
| **Access** | Admin Dashboard (React) via REST API |

#### Responsibilities

1. **CRUD operations** — Create, read, update, and soft-delete notification templates.
2. **Versioning** — Every edit creates a new row in `template_versions`. Active notifications reference a specific `version_id`, ensuring in-flight notifications are not affected by template edits.
3. **Preview & validation** — `POST /api/v1/templates/{id}/preview` renders a template with sample data and returns the output. Jinja2 syntax errors are caught and returned as structured validation errors.
4. **Localization** — Templates support `{{ t("key") }}` calls that resolve against a locale-specific string table stored in `template_translations`.
5. **Asset management** — Email templates can reference image assets (logos, banners) uploaded via `POST /api/v1/templates/assets`. Assets are stored in Azure Blob Storage and served via CDN.

#### Legacy (PHP) Equivalent

- Templates were PHP files with inline HTML and embedded `<?php ?>` blocks. Changes required a deployment.
- No versioning; a bad template edit immediately affected all in-flight notifications.
- No preview capability; testing required sending a real email.

---

### 2.5 Preferences & Recipient Service

| Property | Value |
|---|---|
| **Runtime** | FastAPI (part of the core API) |
| **Data store** | PostgreSQL — `recipients`, `recipient_preferences`, `account_contacts` |

#### Responsibilities

1. **Recipient management** — CRUD for recipient records (name, email, phone, webhook URL).
2. **Preference management** — Per-recipient, per-channel, per-event-category opt-in/opt-out settings.
3. **Unsubscribe handling** — One-click unsubscribe links (RFC 8058) in emails resolve to `POST /api/v1/preferences/unsubscribe` which records the opt-out and returns a confirmation page.
4. **Bulk import/export** — CSV upload for bulk recipient management; async processing via Service Bus queue `recipient-imports`.
5. **GDPR / data subject requests** — `DELETE /api/v1/recipients/{id}` triggers a cascade soft-delete across all related tables and enqueues a data purge job.

#### Legacy (PHP) Equivalent

- `admin/recipients.php` — Server-rendered Angular forms with direct MySQL queries.
- No unsubscribe link support; recipients had to contact support to opt out.
- No GDPR compliance tooling.

---

### 2.6 Admin Dashboard (React SPA)

| Property | Value |
|---|---|
| **Runtime** | Static React 18 SPA deployed to Azure Static Web Apps |
| **Auth** | Microsoft Entra ID via MSAL.js; role-based access (`admin`, `operator`, `viewer`) |
| **API** | Communicates exclusively with the FastAPI backend via REST |

#### Key Screens & Features

| Screen | Description |
|---|---|
| **Dashboard Home** | KPI cards: notifications sent (24 h), delivery rate, bounce rate, active rules, pending retries |
| **Shipment Tracker** | Search by tracking number; view event timeline and notification history |
| **Notification Rules** | Visual rule builder; create/edit/enable/disable rules with a JSON predicate UI |
| **Templates** | WYSIWYG and code editor for email/SMS templates; live preview with sample data |
| **Recipients** | Searchable table of recipients; inline preference editing; bulk import |
| **Delivery Log** | Paginated, filterable log of all delivery attempts with status, timestamps, and provider IDs |
| **Analytics** | Charts for delivery volume over time, channel breakdown, failure reasons, rule hit rates |
| **Settings** | Account configuration, API key management, webhook signing secret rotation |

#### Legacy (Angular) Equivalent

- Angular 12 SPA served by Apache on the same on-prem server as the PHP backend.
- Authentication was PHP session-based with LDAP integration.
- No role-based access control; all authenticated users had full admin access.
- Dashboard showed only total notification count; no delivery analytics.

---

### 2.7 Analytics & Archival Agent

| Property | Value |
|---|---|
| **Runtime** | Azure Functions (Python, consumption plan) |
| **Trigger** | Azure Service Bus topic subscription `shipment-events/sub-analytics` |
| **Output** | Azure Blob Storage (Parquet files); PostgreSQL `analytics_aggregates` |

#### Responsibilities

1. **Event archival** — Write raw `ShipmentEvent` payloads to Azure Blob Storage in Parquet format, partitioned by `date/account_id`. Retention: 7 years (compliance).
2. **Aggregate computation** — Maintain pre-computed aggregates (hourly, daily) in `analytics_aggregates` for fast dashboard queries.
3. **Data export** — Scheduled export of notification delivery metrics to Azure Data Lake for BI tooling.

#### Legacy Equivalent

- No archival; old events were deleted by a weekly MySQL cron job after 90 days.
- No aggregate tables; dashboard queries ran directly against production MySQL.

---

## 3. End-to-End Workflows

### 3.1 Webhook-Driven Notification Flow

```
 FedEx Track API
       │
       │ POST /api/v1/webhooks/fedex
       ▼
 ┌─────────────┐   validate signature    ┌─────────────┐
 │  Ingestion   │ ──────────────────────▶ │  Normalize   │
 │  Agent       │   deduplicate           │  & Publish   │
 └─────────────┘                          └──────┬──────┘
                                                  │
                            Service Bus topic: shipment-events
                                                  │
                         ┌────────────────────────┼────────────────────┐
                         ▼                        ▼                    ▼
                ┌─────────────────┐    ┌─────────────────┐   ┌──────────────┐
                │ Event Processor  │    │ Analytics Sink   │   │ (Future       │
                │ Agent            │    │ Agent            │   │  subscribers) │
                └────────┬────────┘    └─────────────────┘   └──────────────┘
                         │
                  evaluate rules
                  resolve recipients
                  check throttle
                         │
              Service Bus queue: notification-requests
                         │
                         ▼
                ┌─────────────────┐
                │ Notification     │
                │ Delivery Agent   │
                └────────┬────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          ┌───────┐ ┌───────┐ ┌──────────┐
          │ Email │ │  SMS  │ │ Webhook  │
          │ (ACS) │ │(Twilio│ │ (HTTP)   │
          └───────┘ └───────┘ └──────────┘
                         │
                    delivery_log
                    (PostgreSQL)
```

**Step-by-step:**

1. FedEx sends a webhook POST to the Ingestion Agent.
2. The agent validates the HMAC signature (`X-FedEx-Signature`).
3. The agent computes the `event_fingerprint` and checks `ingestion_log` for duplicates.
4. If new, the event is normalized into a `ShipmentEvent` and published to the `shipment-events` Service Bus topic.
5. The Event Processor subscription receives the event.
6. Active rules are evaluated against the event; all matching rules produce notification intents.
7. For each intent, recipients are resolved, preferences checked, and throttle limits enforced.
8. One `NotificationRequest` per recipient-channel pair is published to the `notification-requests` queue.
9. The Notification Delivery Agent picks up each request, renders the template, and dispatches via the appropriate channel.
10. Delivery status is written to `delivery_log`.
11. On transient failure, the message is retried (up to 3×); on permanent failure, it is dead-lettered.

### 3.2 Polling Fallback Flow

```
 Timer trigger (every 5 min)
       │
       ▼
 ┌──────────────────┐
 │ Ingestion Poller  │
 │ (Azure Function)  │
 └────────┬─────────┘
          │
   Query shipments with
   no webhook update > 15 min
          │
   Call FedEx Track API v2
   GET /track/v2/shipments
          │
   (same pipeline from step 3 onwards)
```

### 3.3 Template Editing Flow

1. Admin opens the Templates screen in the React dashboard.
2. Admin selects a template and edits it in the code editor or WYSIWYG editor.
3. Admin clicks "Preview" → `POST /api/v1/templates/{id}/preview` renders the template with sample data.
4. Admin clicks "Save" → `PUT /api/v1/templates/{id}` creates a new `template_versions` row.
5. The previous version remains active for any in-flight notifications; new notifications pick up the latest version.

### 3.4 Recipient Unsubscribe Flow

1. Recipient clicks the one-click unsubscribe link in an email.
2. Browser sends `POST /api/v1/preferences/unsubscribe?token=<signed_jwt>`.
3. The API validates the JWT (signed with a per-environment secret), extracts the recipient ID and channel.
4. A row is inserted/updated in `recipient_preferences` with `opted_out = true`.
5. A confirmation page is returned.
6. Subsequent notification requests for this recipient-channel pair are filtered out by the Event Processor Agent.

---

## 4. Interfaces & Contracts

### 4.1 `ShipmentEvent` Schema

The canonical internal event schema, published to Service Bus:

```json
{
  "event_id": "uuid-v4",
  "event_fingerprint": "sha256-hex",
  "tracking_number": "794644790132",
  "carrier": "FEDEX",
  "status_code": "DL",
  "status_category": "DELIVERED",
  "status_description": "Delivered - Left at front door",
  "event_timestamp": "2025-01-15T14:32:00Z",
  "location": {
    "city": "Memphis",
    "state": "TN",
    "country": "US",
    "postal_code": "38118"
  },
  "shipment": {
    "origin": { "city": "Seattle", "state": "WA", "country": "US" },
    "destination": { "city": "Memphis", "state": "TN", "country": "US" },
    "service_type": "FEDEX_GROUND",
    "ship_date": "2025-01-12",
    "estimated_delivery": "2025-01-15",
    "weight_kg": 2.3,
    "package_count": 1
  },
  "account_id": "uuid",
  "notification_overrides": {
    "recipients": ["ops-team@example.com"],
    "channels": ["email"]
  },
  "raw_payload": { "...FedEx original JSON..." },
  "ingested_at": "2025-01-15T14:32:05Z"
}
```

### 4.2 `NotificationRequest` Schema

Published to the `notification-requests` queue:

```json
{
  "request_id": "uuid-v4",
  "event_id": "uuid-v4 (correlation)",
  "rule_id": "uuid",
  "template_id": "uuid",
  "template_version_id": "uuid",
  "channel": "email",
  "priority": "high",
  "recipient": {
    "id": "uuid",
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "phone": null,
    "webhook_url": null
  },
  "context": {
    "tracking_number": "794644790132",
    "status_description": "Delivered - Left at front door",
    "account_name": "Acme Corp",
    "branding": {
      "logo_url": "https://cdn.example.com/acme-logo.png",
      "primary_color": "#003366"
    },
    "event_history": [
      { "timestamp": "2025-01-12T09:00:00Z", "description": "Picked up" },
      { "timestamp": "2025-01-13T06:00:00Z", "description": "In transit - Memphis hub" },
      { "timestamp": "2025-01-15T14:32:00Z", "description": "Delivered" }
    ]
  },
  "created_at": "2025-01-15T14:32:07Z"
}
```

### 4.3 REST API Endpoints

All endpoints are served by the FastAPI backend under `/api/v1/`. Authentication is via Bearer JWT (Entra ID).

#### Webhook & Ingestion

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/webhooks/fedex` | HMAC signature | FedEx webhook receiver |

#### Notifications

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/notifications` | Bearer JWT | List notifications with filters (status, date, tracking number) |
| `GET` | `/notifications/{id}` | Bearer JWT | Get notification detail including delivery attempts |
| `POST` | `/notifications/resend` | Bearer JWT (admin) | Manually resend a failed notification |

#### Templates

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/templates` | Bearer JWT | List all templates |
| `GET` | `/templates/{id}` | Bearer JWT | Get template with current version |
| `POST` | `/templates` | Bearer JWT (admin) | Create a new template |
| `PUT` | `/templates/{id}` | Bearer JWT (admin) | Update template (creates new version) |
| `DELETE` | `/templates/{id}` | Bearer JWT (admin) | Soft-delete a template |
| `POST` | `/templates/{id}/preview` | Bearer JWT | Render template with sample data |
| `POST` | `/templates/assets` | Bearer JWT (admin) | Upload an image asset |

#### Recipients & Preferences

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/recipients` | Bearer JWT | List recipients with search/filter |
| `POST` | `/recipients` | Bearer JWT (admin) | Create a recipient |
| `PUT` | `/recipients/{id}` | Bearer JWT (admin) | Update a recipient |
| `DELETE` | `/recipients/{id}` | Bearer JWT (admin) | GDPR-compliant soft-delete + purge |
| `GET` | `/recipients/{id}/preferences` | Bearer JWT | Get notification preferences |
| `PUT` | `/recipients/{id}/preferences` | Bearer JWT | Update preferences |
| `POST` | `/preferences/unsubscribe` | Signed JWT (email link) | One-click unsubscribe |
| `POST` | `/recipients/import` | Bearer JWT (admin) | Bulk import via CSV |

#### Rules

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/rules` | Bearer JWT | List notification rules |
| `GET` | `/rules/{id}` | Bearer JWT | Get rule detail |
| `POST` | `/rules` | Bearer JWT (admin) | Create a rule |
| `PUT` | `/rules/{id}` | Bearer JWT (admin) | Update a rule |
| `DELETE` | `/rules/{id}` | Bearer JWT (admin) | Soft-delete a rule |

#### Analytics

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/analytics/summary` | Bearer JWT | Dashboard KPIs (24 h window) |
| `GET` | `/analytics/delivery-volume` | Bearer JWT | Time-series delivery volume |
| `GET` | `/analytics/failure-reasons` | Bearer JWT | Breakdown of failure categories |
| `GET` | `/analytics/rule-hits` | Bearer JWT | Rule evaluation hit rates |

#### Health & Ops

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Liveness probe (returns `200 OK`) |
| `GET` | `/health/ready` | None | Readiness probe (checks DB + Service Bus connectivity) |
| `GET` | `/metrics` | Internal | Prometheus-format metrics |

### 4.4 Service Bus Topics & Queues

| Resource | Type | Publishers | Subscribers | Message TTL |
|---|---|---|---|---|
| `shipment-events` | Topic | Ingestion Agent | Event Processor, Analytics Sink | 24 h |
| `shipment-events/sub-event-processor` | Subscription | — | Event Processor Agent | — |
| `shipment-events/sub-analytics` | Subscription | — | Analytics Agent | — |
| `notification-requests` | Queue | Event Processor Agent | Notification Delivery Agent | 4 h |
| `notification-requests/$deadletter` | Dead-letter queue | (auto) | Manual / alert-driven review | 14 d |
| `recipient-imports` | Queue | API (bulk import) | Import Worker | 1 h |

### 4.5 Outbound Webhook Contract

When a notification rule specifies the `webhook` channel, the Delivery Agent sends:

```http
POST {customer_webhook_url}
Content-Type: application/json
X-Notification-Signature: sha256=<hmac_hex>
X-Notification-Id: <delivery_id>
X-Notification-Timestamp: <iso8601>

{
  "event": "notification.delivered",
  "tracking_number": "794644790132",
  "status": "DELIVERED",
  "status_description": "Delivered - Left at front door",
  "timestamp": "2025-01-15T14:32:00Z",
  "notification_id": "uuid",
  "metadata": { ... }
}
```

Customers must respond with `2xx` within 10 seconds. Non-2xx or timeout → retry.

---

## 5. Data Flow & Storage

### 5.1 PostgreSQL Schema (Azure Database for PostgreSQL — Flexible Server)

Connection: `POSTGRES_CONNECTION_STRING` environment variable.

#### Core Tables

```sql
-- Ingestion & deduplication
CREATE TABLE ingestion_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_fingerprint VARCHAR(64) UNIQUE NOT NULL,
    tracking_number VARCHAR(40) NOT NULL,
    status_code     VARCHAR(20) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    raw_payload     JSONB NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          VARCHAR(20) NOT NULL  -- 'webhook' | 'poll'
);
CREATE INDEX idx_ingestion_tracking ON ingestion_log (tracking_number, event_timestamp DESC);

-- Notification rules
CREATE TABLE notification_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    conditions  JSONB NOT NULL,
    channels    TEXT[] NOT NULL,
    template_id UUID REFERENCES notification_templates(id),
    priority    VARCHAR(10) NOT NULL DEFAULT 'normal',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);

-- Notification templates
CREATE TABLE notification_templates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    channel     VARCHAR(20) NOT NULL,  -- 'email' | 'sms' | 'webhook'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);

CREATE TABLE template_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id     UUID NOT NULL REFERENCES notification_templates(id),
    version_number  INT NOT NULL,
    subject         TEXT,             -- email only
    body_html       TEXT,             -- email only
    body_text       TEXT,             -- email/sms
    body_json       JSONB,            -- webhook
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID NOT NULL,    -- user ID from Entra ID
    UNIQUE (template_id, version_number)
);

CREATE TABLE template_translations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_version_id UUID NOT NULL REFERENCES template_versions(id),
    locale          VARCHAR(10) NOT NULL,  -- e.g., 'en-US', 'es-MX'
    strings         JSONB NOT NULL,
    UNIQUE (template_version_id, locale)
);

-- Recipients & preferences
CREATE TABLE recipients (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  UUID NOT NULL,
    name        VARCHAR(200),
    email       VARCHAR(320),
    phone       VARCHAR(20),
    webhook_url TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);

CREATE TABLE recipient_preferences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id    UUID NOT NULL REFERENCES recipients(id),
    channel         VARCHAR(20) NOT NULL,
    event_category  VARCHAR(40),         -- NULL = all categories
    opted_out       BOOLEAN NOT NULL DEFAULT false,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (recipient_id, channel, event_category)
);

CREATE TABLE account_contacts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  UUID NOT NULL,
    recipient_id UUID NOT NULL REFERENCES recipients(id),
    role        VARCHAR(40) NOT NULL DEFAULT 'default',
    UNIQUE (account_id, recipient_id)
);

-- Processed events & delivery log
CREATE TABLE processed_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL,     -- from ShipmentEvent
    rule_id         UUID NOT NULL REFERENCES notification_rules(id),
    recipient_id    UUID NOT NULL REFERENCES recipients(id),
    channel         VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL,  -- 'QUEUED' | 'THROTTLED'
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_processed_events_event ON processed_events (event_id);

CREATE TABLE delivery_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_request_id UUID NOT NULL,
    event_id                UUID NOT NULL,
    channel                 VARCHAR(20) NOT NULL,
    recipient_id            UUID NOT NULL REFERENCES recipients(id),
    status                  VARCHAR(20) NOT NULL,  -- PENDING|SENT|DELIVERED|BOUNCED|FAILED
    provider_message_id     VARCHAR(200),
    attempt_number          INT NOT NULL DEFAULT 1,
    next_retry_at           TIMESTAMPTZ,
    error_message           TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_delivery_log_status ON delivery_log (status, next_retry_at);
CREATE INDEX idx_delivery_log_tracking ON delivery_log (event_id, channel);

-- Analytics aggregates
CREATE TABLE analytics_aggregates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_start    TIMESTAMPTZ NOT NULL,
    period_type     VARCHAR(10) NOT NULL,  -- 'hourly' | 'daily'
    account_id      UUID,
    channel         VARCHAR(20) NOT NULL,
    total_sent      INT NOT NULL DEFAULT 0,
    total_delivered INT NOT NULL DEFAULT 0,
    total_bounced   INT NOT NULL DEFAULT 0,
    total_failed    INT NOT NULL DEFAULT 0,
    total_throttled INT NOT NULL DEFAULT 0,
    UNIQUE (period_start, period_type, account_id, channel)
);
```

### 5.2 Azure Blob Storage

| Container | Purpose | Retention | Format |
|---|---|---|---|
| `event-archive` | Raw ShipmentEvent archive | 7 years | Parquet, partitioned by `date/account_id` |
| `template-assets` | Email template images (logos, banners) | Indefinite | PNG, JPG, SVG |
| `import-uploads` | Bulk recipient CSV uploads | 30 days | CSV |
| `export-data` | Scheduled data exports for BI | 90 days | Parquet / CSV |

### 5.3 Data Flow Diagram

```
FedEx API ──▶ Ingestion Agent ──▶ ingestion_log (PG)
                   │
                   ▼
           Service Bus: shipment-events
                   │
          ┌────────┴────────┐
          ▼                 ▼
   Event Processor    Analytics Sink
          │                 │
          ▼                 ▼
  notification_rules   event-archive (Blob)
  processed_events     analytics_aggregates (PG)
  recipient_preferences
          │
          ▼
   Service Bus: notification-requests
          │
          ▼
   Notification Delivery Agent
          │
          ▼
     delivery_log (PG)
          │
          ▼
   Azure Comms / Twilio / Webhook
```

---

## 6. Failure Handling, Retries & Idempotency

### 6.1 Idempotency Model

Every operation is designed to be **safely retryable**:

| Component | Idempotency Key | Mechanism |
|---|---|---|
| Ingestion Agent | `event_fingerprint` (SHA-256) | Upsert to `ingestion_log`; duplicate → ack without re-publish |
| Event Processor | `event_id + rule_id + recipient_id` | Check `processed_events` before emitting `NotificationRequest` |
| Delivery Agent | `notification_request_id + attempt_number` | Unique constraint on `delivery_log`; duplicate → skip |
| Template updates | `template_id + version_number` | Unique constraint; concurrent edits get a conflict error |

### 6.2 Retry Strategies

| Component | Retryable Errors | Max Retries | Back-off | Dead-letter |
|---|---|---|---|---|
| Ingestion → Service Bus | 429, 500, 503, timeout | 5 | Exponential (1 s base, 60 s max, jitter) | In-memory buffer overflow → alert |
| Event Processor | DB connection error, Service Bus publish failure | 3 | Service Bus built-in retry | DLQ after 3 attempts |
| Notification Delivery | Provider 5xx, 429, timeout | 3 | 30 s → 120 s → 480 s | DLQ; status → `FAILED` |
| Webhook delivery | Non-2xx, timeout (10 s) | 3 | 30 s → 120 s → 480 s | DLQ; status → `FAILED` |

### 6.3 Dead-Letter Queue Processing

Dead-lettered messages are:
1. Logged with full context to Application Insights (custom event `notification.deadlettered`).
2. Visible in the Admin Dashboard under **Delivery Log → Failed**.
3. Manually retriable via `POST /api/v1/notifications/resend` (re-enqueues to `notification-requests`).
4. Retained for 14 days, then auto-purged.

### 6.4 Circuit Breaker

The Notification Delivery Agent implements a **circuit breaker** per channel-provider:

| State | Condition | Behavior |
|---|---|---|
| **Closed** | Failure rate < 50% in 60 s window | Normal operation |
| **Open** | Failure rate ≥ 50% (min 10 requests) | All requests fast-fail for 120 s; alert fired |
| **Half-open** | After 120 s cool-down | Allow 1 probe request; success → Closed, failure → Open |

### 6.5 Poison Message Handling

Messages that cause unhandled exceptions (e.g., malformed JSON, missing required fields) are:
1. Caught by a global exception handler in each agent.
2. Logged with the full message body and stack trace.
3. Moved to the dead-letter queue with `deadletter_reason = "poison_message"`.
4. An alert is fired to the `#notifications-ops` channel (see [§9 Observability](#9-observability)).

---

## 7. Scalability & Performance

### 7.1 Scaling Model

| Component | Scaling Method | Min | Max | Scale Trigger |
|---|---|---|---|---|
| Ingestion Agent (Container App) | HTTP-based autoscaling | 1 | 10 | Concurrent HTTP requests > 100 |
| Event Processor (Azure Function) | Event-driven (Service Bus) | 0 | 50 | Queue depth + message age |
| Notification Delivery (Azure Function) | Event-driven (Service Bus) | 0 | 100 | Queue depth |
| Analytics Sink (Azure Function) | Event-driven (Service Bus) | 0 | 20 | Queue depth |
| PostgreSQL | Vertical (Flexible Server tier) | 2 vCores | 16 vCores | Manual / scheduled |
| Admin Dashboard (Static Web App) | Azure CDN | N/A | N/A | Globally distributed |

### 7.2 Performance Targets

| Metric | Target | Measurement |
|---|---|---|
| Webhook ingestion latency (p99) | < 200 ms | Time from HTTP request receipt to Service Bus publish |
| End-to-end notification latency (p95) | < 30 s | Time from event ingestion to email delivery |
| Email delivery throughput | 10 000 / min | Sustained rate during peak |
| Rule evaluation time (p99) | < 50 ms | Per event, across all active rules |
| Dashboard API response time (p95) | < 500 ms | For paginated list queries |
| System availability | 99.9% | Monthly uptime SLA |

### 7.3 Performance Optimizations

1. **Rule caching** — Active rules are loaded from PostgreSQL into an in-memory cache with a 60 s TTL. Rules are fetched in a single query with `WHERE enabled = true AND deleted_at IS NULL`.
2. **Template caching** — Compiled Jinja2 templates are cached with a 5-minute TTL, keyed by `template_version_id`.
3. **Batch Service Bus operations** — The Ingestion Agent batches up to 100 messages per Service Bus send call during high-throughput periods.
4. **Connection pooling** — All PostgreSQL connections use `asyncpg` with a pool size of 10–50 (configurable per service).
5. **Read replicas** — Dashboard analytics queries are routed to a PostgreSQL read replica to avoid impacting the transactional workload.
6. **Pagination** — All list API endpoints use cursor-based pagination (keyset pagination on `created_at, id`) to avoid `OFFSET` performance degradation.

---

## 8. Security & Access Control

### 8.1 Authentication

| Layer | Mechanism | Details |
|---|---|---|
| **Admin Dashboard** | Microsoft Entra ID (MSAL.js) | OAuth 2.0 Authorization Code flow with PKCE; tenant: `AZURE_TENANT_ID` |
| **API (internal)** | Bearer JWT | Tokens issued by Entra ID; validated by FastAPI middleware (`python-jose`) |
| **FedEx Webhook** | HMAC-SHA256 | Shared secret; signature in `X-FedEx-Signature` header |
| **Unsubscribe links** | Signed JWT | Short-lived (24 h), single-use tokens signed with a per-environment secret |
| **Service Bus** | Managed Identity | Container Apps and Functions authenticate to Service Bus via Azure Managed Identity |
| **PostgreSQL** | Connection string | Stored in Azure Key Vault, injected as `POSTGRES_CONNECTION_STRING` |

### 8.2 Authorization (RBAC)

Roles are defined as Entra ID App Roles and enforced by the FastAPI backend:

| Role | Permissions |
|---|---|
| `admin` | Full CRUD on all resources; user management; resend notifications; rotate keys |
| `operator` | Read all resources; create/edit rules and templates; resend notifications |
| `viewer` | Read-only access to dashboard, logs, and analytics |

Role assignment is managed in the Azure Portal (Enterprise Applications → Users and groups).

### 8.3 Data Protection

| Measure | Implementation |
|---|---|
| **Encryption at rest** | Azure-managed keys (AES-256) for PostgreSQL, Blob Storage, Service Bus |
| **Encryption in transit** | TLS 1.2+ enforced on all endpoints; HSTS enabled on the dashboard |
| **PII handling** | Recipient PII (email, phone, name) is stored in PostgreSQL only; archived events in Blob Storage are PII-stripped |
| **Secret management** | All secrets stored in Azure Key Vault; referenced via environment variables (`AZURE_EMAIL_CONNECTION_STRING`, `AZURE_EMAIL_FROM_ADDRESS`, etc.) |
| **Audit logging** | All admin actions (template edits, rule changes, manual resends) are logged with user ID and timestamp in `admin_audit_log` |
| **Network isolation** | PostgreSQL and Service Bus are accessible only via Azure Virtual Network; no public endpoints |
| **CORS** | Dashboard origin whitelisted; API rejects other origins |

### 8.4 Compliance

| Requirement | How Addressed |
|---|---|
| **GDPR** | Recipient deletion cascades through all tables; data purge job clears Blob Storage; unsubscribe mechanism |
| **CAN-SPAM** | All emails include a one-click unsubscribe link and physical mailing address |
| **SOC 2** | Audit log retention (1 year); access reviews via Entra ID; encryption at rest and in transit |
| **Data retention** | Configurable per data type (see Blob Storage retention table in §5.2) |

---

## 9. Observability

### 9.1 Logging

| Component | Sink | Format |
|---|---|---|
| All agents | Azure Application Insights | Structured JSON (`trace_id`, `span_id`, `level`, `message`, `context`) |
| Ingestion Agent | stdout (Container Apps) | Auto-collected by Azure Monitor |
| Azure Functions | Built-in integration | Auto-collected by Application Insights |

**Correlation**: Every request is assigned a `trace_id` (W3C Trace Context) that propagates through Service Bus message properties, enabling end-to-end tracing from ingestion to delivery.

### 9.2 Metrics

Exposed via Application Insights custom metrics and Prometheus `/metrics` endpoint:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `ingestion.events.received` | Counter | `source` (webhook/poll) | Total events received |
| `ingestion.events.deduplicated` | Counter | — | Events dropped as duplicates |
| `ingestion.events.published` | Counter | — | Events successfully published to Service Bus |
| `processor.rules.evaluated` | Counter | `rule_id` | Rule evaluation count |
| `processor.rules.matched` | Counter | `rule_id` | Rule match count |
| `processor.notifications.throttled` | Counter | `recipient_id` | Throttled notification count |
| `delivery.attempts` | Counter | `channel`, `status` | Delivery attempt outcomes |
| `delivery.latency_seconds` | Histogram | `channel` | Time from NotificationRequest creation to delivery |
| `delivery.circuit_breaker.state` | Gauge | `channel` | 0=closed, 1=open, 2=half-open |
| `api.request.duration_seconds` | Histogram | `method`, `path`, `status` | API response time |
| `api.request.count` | Counter | `method`, `path`, `status` | API request count |

### 9.3 Alerts

Configured in Azure Monitor Action Groups:

| Alert | Condition | Severity | Action |
|---|---|---|---|
| **High failure rate** | `delivery.attempts{status=FAILED}` > 100 in 5 min | Sev 1 | PagerDuty + Slack `#notifications-ops` |
| **Circuit breaker open** | `delivery.circuit_breaker.state` = 1 for any channel | Sev 1 | PagerDuty + Slack |
| **DLQ depth** | Dead-letter queue depth > 50 | Sev 2 | Slack `#notifications-ops` |
| **Ingestion lag** | No events published in 15 min during business hours | Sev 2 | Slack `#notifications-ops` |
| **API error rate** | 5xx rate > 5% over 5 min | Sev 2 | Slack `#notifications-ops` |
| **Database CPU** | PostgreSQL CPU > 80% for 10 min | Sev 3 | Slack `#infra` |
| **Function cold starts** | Cold start rate > 20% | Sev 3 | Slack `#notifications-ops` |

### 9.4 Dashboards

Pre-built Azure Monitor workbooks:

1. **Operations Dashboard** — Real-time view of ingestion rate, processing pipeline health, delivery success rate, and DLQ depth.
2. **Delivery Analytics** — Historical trends of delivery volume, channel breakdown, failure reasons, and bounce rates.
3. **Performance Dashboard** — Latency percentiles (p50, p95, p99) for each pipeline stage; function execution times; database query performance.
4. **Incident Dashboard** — Circuit breaker state history, alert timeline, and DLQ message inspector.

### 9.5 Distributed Tracing

End-to-end trace flow:

```
[Ingestion Agent]          trace_id: abc123, span: ingestion
       │
       ▼ Service Bus (trace_id in message properties)
       │
[Event Processor]          trace_id: abc123, span: processing
       │
       ▼ Service Bus (trace_id propagated)
       │
[Notification Delivery]    trace_id: abc123, span: delivery
       │
       ▼ Azure Comms / Twilio
       │
[Delivery Feedback]        trace_id: abc123, span: feedback
```

Traces are queryable in Application Insights via:
```kusto
traces
| where customDimensions.trace_id == "abc123"
| order by timestamp asc
```

---

## 10. Migration Mapping

### 10.1 Component-by-Component Mapping

| Legacy Component | Technology | New Component | Technology | Migration Notes |
|---|---|---|---|---|
| `cron/fetch_tracking.php` | PHP + cron | Ingestion Poller | Azure Function (timer) | Replace SOAP with REST (FedEx Track API v2); add dedup |
| `api/webhook_handler.php` | PHP | Ingestion Agent | FastAPI (Container App) | Add HMAC validation, schema normalization |
| `services/RuleEngine.php` | PHP (hardcoded) | Event Processor Agent | Azure Function + JSON rules | Extract rules from code into `notification_rules` DB table |
| `services/RecipientResolver.php` | PHP + MySQL | Preferences Service | FastAPI + PostgreSQL | Add caching, opt-out support, GDPR compliance |
| `services/Mailer.php` | PHPMailer + SMTP | Notification Delivery Agent | Azure Function + ACS | Add retry logic, delivery tracking, bounce processing |
| `services/SmsGateway.php` | PHP + SMPP | Notification Delivery Agent | Azure Function + Twilio | Replace SMPP with REST API; add delivery tracking |
| N/A (did not exist) | — | Webhook delivery | Azure Function + HTTP client | New capability |
| `templates/*.php` | PHP inline HTML | Template Management Service | FastAPI + Jinja2 + PostgreSQL | Extract templates to DB; add versioning, preview, localization |
| `admin/*.php` + Angular SPA | PHP + Angular 12 | Admin Dashboard | React 18 + Static Web App | Full rewrite; add RBAC, analytics, rule builder |
| MySQL `raw_events` table | MySQL 5.7 | `ingestion_log` | PostgreSQL (Flexible Server) | Schema redesign; add fingerprint-based dedup |
| MySQL `email_log` table | MySQL 5.7 | `delivery_log` | PostgreSQL (Flexible Server) | Unified log across all channels; add retry tracking |
| Apache + mod_php | On-prem | Azure Container Apps | Azure PaaS | Containerized; auto-scaling; managed TLS |
| Log files + Nagios | On-prem | Application Insights + Azure Monitor | Azure PaaS | Structured logging; distributed tracing; alerting |
| LDAP auth | On-prem | Microsoft Entra ID | Azure | RBAC with app roles; MSAL.js + JWT |
| Config files on disk | On-prem | Azure Key Vault | Azure | Secrets injected as env vars; no plaintext on disk |

### 10.2 Data Migration Strategy

#### Phase 1: Schema Migration

1. Provision Azure Database for PostgreSQL — Flexible Server.
2. Apply the schema from [§5.1](#51-postgresql-schema-azure-database-for-postgresql--flexible-server) using Alembic migrations.
3. Validate schema with empty data.

#### Phase 2: Historical Data Migration

| Source Table (MySQL) | Target Table (PostgreSQL) | Transformation |
|---|---|---|
| `raw_events` | `ingestion_log` | Compute `event_fingerprint`; convert timestamps to UTC; store raw payload as JSONB |
| `email_log` | `delivery_log` | Map status codes; generate UUIDs; normalize timestamps |
| `recipients` | `recipients` | Validate email format; normalize phone to E.164 |
| `email_templates` (files) | `notification_templates` + `template_versions` | Parse PHP templates; convert to Jinja2 syntax; create initial version |
| `notification_rules` (code) | `notification_rules` | Extract hardcoded rules from PHP; express as JSON predicates |
| N/A | `recipient_preferences` | Initialize with all `opted_out = false`; import any known opt-outs from support tickets |

#### Phase 3: Parallel Run

1. Run both legacy and new systems in parallel for 2 weeks.
2. Ingestion Agent receives all events; legacy system continues operating.
3. Compare notification outputs (new system in shadow mode — logs but does not deliver).
4. Validate delivery rates, template rendering, and rule matching align within 1% tolerance.

#### Phase 4: Cutover

1. Update FedEx webhook URL to point to the new Ingestion Agent.
2. Disable legacy cron jobs.
3. Monitor for 48 hours with heightened alerting thresholds.
4. Decommission legacy system after 30-day stabilization period.

### 10.3 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FedEx webhook URL change causes event loss | Medium | High | Maintain polling fallback for 30 days post-cutover |
| Template rendering differences (PHP → Jinja2) | High | Medium | Automated visual regression tests on all templates during parallel run |
| Performance regression under load | Medium | High | Load test with 10× peak volume before cutover |
| Data migration integrity issues | Medium | High | Row-count reconciliation + checksum validation per table |
| Entra ID auth disrupts admin access | Low | High | Pre-provision all admin accounts; maintain break-glass local admin |

---

## 11. Environment & Configuration

### 11.1 Required Environment Variables

| Variable | Description | Source |
|---|---|---|
| `AZURE_APP_ID` | Entra ID application (client) ID | Azure Key Vault |
| `AZURE_TENANT_ID` | Entra ID tenant ID | Azure Key Vault |
| `AZURE_PASSWORD` | Service principal client secret | Azure Key Vault |
| `AZURE_EMAIL_CONNECTION_STRING` | Azure Communication Services connection string | Azure Key Vault |
| `AZURE_EMAIL_FROM_ADDRESS` | Verified sender email address for ACS | Azure Key Vault |
| `POSTGRES_CONNECTION_STRING` | PostgreSQL connection string | Azure Key Vault |
| `FEDEX_API_KEY` | FedEx Track API v2 key | Azure Key Vault |
| `FEDEX_API_SECRET` | FedEx Track API v2 secret | Azure Key Vault |
| `FEDEX_WEBHOOK_SECRET` | Shared secret for webhook HMAC validation | Azure Key Vault |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Azure Key Vault |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Azure Key Vault |
| `TWILIO_FROM_NUMBER` | Twilio sender phone number | Azure Key Vault |
| `SERVICE_BUS_CONNECTION_STRING` | Azure Service Bus connection string | Managed Identity (preferred) or Key Vault |
| `BLOB_STORAGE_CONNECTION_STRING` | Azure Blob Storage connection string | Managed Identity (preferred) or Key Vault |
| `UNSUBSCRIBE_JWT_SECRET` | Secret for signing unsubscribe tokens | Azure Key Vault |
| `APP_ENVIRONMENT` | `development` / `staging` / `production` | App configuration |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | App configuration |

### 11.2 Infrastructure (Azure Resources)

| Resource | SKU / Tier | Purpose |
|---|---|---|
| Azure Container Apps Environment | Consumption | Hosts Ingestion Agent / API |
| Azure Functions App (consumption) | Consumption | Event Processor, Delivery Agent, Analytics Sink |
| Azure Database for PostgreSQL | Flexible Server, General Purpose (2–16 vCores) | Primary data store |
| Azure Service Bus | Standard tier | Message broker |
| Azure Communication Services | Pay-as-you-go | Email delivery |
| Azure Blob Storage | Standard LRS | Event archive, template assets |
| Azure Static Web Apps | Free / Standard | Admin Dashboard hosting |
| Azure Key Vault | Standard | Secret management |
| Azure Application Insights | Pay-as-you-go | Observability |
| Azure Monitor | Included | Alerting and dashboards |
| Azure CDN | Standard | Template asset delivery |
| Azure Virtual Network | Standard | Network isolation for PG + Service Bus |

### 11.3 Local Development

```bash
# Prerequisites
python 3.12+
node 20+
docker & docker-compose

# Backend
cd backend/
cp .env.example .env  # Fill in local dev values
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend/
npm install
npm run dev  # Vite dev server on :5173

# Local infrastructure
docker-compose up -d  # PostgreSQL, Azurite (Storage emulator), Service Bus emulator
```

---

## 12. Appendices

### Appendix A: FedEx Status Code Mapping

| FedEx Code | Category | Description | Notification Priority |
|---|---|---|---|
| `PU` | `PICKED_UP` | Package picked up | Normal |
| `IT` | `IN_TRANSIT` | In transit | Low |
| `OD` | `OUT_FOR_DELIVERY` | Out for delivery | Normal |
| `DL` | `DELIVERED` | Delivered | Normal |
| `DE` | `EXCEPTION` | Delivery exception | High |
| `SE` | `EXCEPTION` | Shipment exception | High |
| `CA` | `CANCELLED` | Shipment cancelled | High |
| `HL` | `HELD` | Package held at location | Normal |
| `RS` | `RETURNED` | Return to shipper | High |

### Appendix B: Notification Template Variables

Available in all templates via Jinja2 context:

| Variable | Type | Description |
|---|---|---|
| `tracking_number` | `str` | FedEx tracking number |
| `status` | `str` | Human-readable status description |
| `status_category` | `str` | Normalized category (DELIVERED, EXCEPTION, etc.) |
| `event_timestamp` | `datetime` | When the event occurred |
| `origin` | `dict` | Origin location (city, state, country) |
| `destination` | `dict` | Destination location (city, state, country) |
| `estimated_delivery` | `date` | Estimated delivery date |
| `service_type` | `str` | FedEx service type |
| `account_name` | `str` | Customer account name |
| `branding.logo_url` | `str` | Account logo URL |
| `branding.primary_color` | `str` | Account brand color |
| `event_history` | `list[dict]` | Timeline of all events for this shipment |
| `unsubscribe_url` | `str` | One-click unsubscribe link |
| `tracking_url` | `str` | FedEx tracking page URL |
| `t(key)` | `function` | Localization lookup |

### Appendix C: Service Bus Message Properties

Custom properties set on all Service Bus messages for routing and tracing:

| Property | Type | Description |
|---|---|---|
| `trace_id` | `str` | W3C Trace Context trace ID |
| `event_id` | `str` | ShipmentEvent UUID |
| `tracking_number` | `str` | FedEx tracking number |
| `account_id` | `str` | Account UUID |
| `status_category` | `str` | Normalized status category |
| `priority` | `str` | `low` / `normal` / `high` |
| `source` | `str` | `webhook` / `poll` |
| `published_at` | `str` | ISO 8601 timestamp |

### Appendix D: Error Codes

API error responses follow RFC 7807 (Problem Details):

```json
{
  "type": "https://api.notifications.example.com/errors/validation",
  "title": "Validation Error",
  "status": 422,
  "detail": "Field 'conditions' is required",
  "instance": "/api/v1/rules",
  "errors": [
    {"field": "conditions", "message": "This field is required"}
  ]
}
```

| Error Type | HTTP Status | Description |
|---|---|---|
| `validation` | 422 | Request body validation failed |
| `not_found` | 404 | Resource does not exist or is soft-deleted |
| `conflict` | 409 | Duplicate resource or version conflict |
| `unauthorized` | 401 | Missing or invalid Bearer token |
| `forbidden` | 403 | Insufficient role permissions |
| `rate_limited` | 429 | API rate limit exceeded (100 req/min per user) |
| `internal` | 500 | Unexpected server error |

---

*Last updated: 2025-01-15 | Maintainer: Notification Platform Team*
