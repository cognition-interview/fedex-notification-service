# Update Order Status — Azure Function App (Python)

Standalone Python Azure Function App that implements the `PATCH /api/orders/{order_id}/status` endpoint.

## What it does

1. Validates the incoming status value
2. Updates `orders.status` (sets `actual_delivery` when Delivered)
3. Inserts a `shipment_events` row with the mapped event type
4. Inserts a `notifications` row with the mapped notification type
5. Sends a branded email via Azure Communication Services
6. Returns the refreshed order (same shape as `GET /api/orders/{id}`)

## Prerequisites

- Python 3.10+
- [Azure Functions Core Tools v4](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)

## Setup

```bash
cd azure-functions

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
```

## Configuration

Copy the provided `local.settings.json` and fill in the values:

| Setting | Description |
|---------|-------------|
| `POSTGRES_CONNECTION_STRING` | Full PostgreSQL connection URL (e.g. `postgresql://user:pass@host:5432/dbname`) |
| `AZURE_EMAIL_CONNECTION_STRING` | Azure Communication Services connection string |
| `AZURE_EMAIL_FROM_ADDRESS` | Sender email address for notifications |

## Running locally

```bash
source .venv/bin/activate
func start
```

The function will be available at `http://localhost:7071/api/orders/{order_id}/status`.

### Example request

```bash
curl -X PATCH http://localhost:7071/api/orders/<ORDER_UUID>/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "In Transit",
    "location": "Memphis, TN",
    "description": "Package arrived at sorting facility"
  }'
```

### Valid statuses

`Picked Up`, `In Transit`, `Out for Delivery`, `Delivered`, `Delayed`, `Exception`

## Running tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Tests use mocked database and email connections — no external services required.

## Project structure

```
azure-functions/
├── function_app.py          # Main function implementation
├── host.json                # Azure Functions host configuration
├── requirements.txt         # Production dependencies
├── requirements-dev.txt     # Dev dependencies (includes pytest)
├── local.settings.json      # Local environment config (git-ignored)
├── .funcignore              # Files excluded from deployment
└── tests/
    ├── __init__.py
    └── test_function_app.py # Unit tests (23 tests)
```
