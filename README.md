# Cenourinhas

## Overview

This repository implements the wedding site and backend for the Cenourinhas wedding.
It is built with Django and includes:

- Wedding website pages and RSVP flow
- Guest management and extra guests
- Mercado Pago gift/payment integration
- WhatsApp OTP login and WhatsApp messaging
- A Gemini-based virtual assistant for WhatsApp
- A Go-based WhatsApp service using `whatsmeow`
- Production helper scripts for server setup and deployment

## Repository structure

- `assistant/`
  - Virtual assistant integration.
  - `assistant.ai` receives WhatsApp messages from the Go service and calls Gemini/OpenRouter.
  - `assistant.tools` defines domain-specific tools for confirming presence, listing gifts, and generating payments.
  - `assistant.models.ConversationMessage` stores WhatsApp conversation context.

- `core/`
  - Main Django app.
  - `core.models` defines `Guest`, `ExtraGuest`, `Presente`, `Pagamento`, `SiteContent`, and WhatsApp batch models.
  - `core.views` handles site pages, payment links, Mercado Pago webhooks, admin dashboard, and WhatsApp mass messaging.
  - `core.settings` loads environment settings and configures Mercado Pago, Gemini/OpenRouter and WhatsApp service URL.
  - `core.urls` defines public pages, admin pages, OTP routes, webhook routes, and the WhatsApp Gemini API endpoint.

- `otp/`
  - OTP login flow using phone numbers.
  - Phone normalization and WhatsApp OTP sending logic.
  - Routes for `/otp/` views and templates.

- `whatsapp_service/`
  - Go service that connects to WhatsApp using `whatsmeow`.
  - Handles QR login, sends OTPs, sends text/images/PDFs, receives incoming WhatsApp messages and forwards them to Django.
  - Configured to run on `http://localhost:8081` by default.

- `templates/`, `static/`, `media/`
  - Django templates and static assets used by the wedding website.

- `manage.py`
  - Django command entrypoint.

- `requirements.txt`
  - Python dependencies for the Django app.

- `new_server.sh`
  - Full production server setup script for a fresh Ubuntu/Debian VM.

- `update.sh`
  - Update script for an existing production deployment.

- `deploy_go.sh`
  - Builds the Go WhatsApp service inside Docker and uploads it to production.

- `verify_setup.py`
  - Quick local sanity check for environment variables and required Django/Mercado Pago integration files.

## Environment variables

The Django app is configured through `.env` and `dotenv`.
Create a `.env` file at the project root with at least the following values:

- `DJANGO_DEBUG=False` or `True` for development.
- `DJANGO_SECRET_KEY="<random-secret-key>"`
- `URL_SITE="https://www.cenourinhas.com.br"`
- `ADMINS="+5511999999999,+5511888888888"` (comma-separated admin WhatsApp numbers)
- `MP_ACCESS_TOKEN="<your-mercadopago-access-token>"`
- `GEMINI_API_KEY="<your-gemini-api-key>"`
- `OPEN_ROUTER_API_KEY="<your-openrouter-api-key>"`
- `WHATSAPP_SERVER_URL="http://localhost:8081"`

Optional variables used by deployment helpers:

- `DJANGO_WEBHOOK_URL="http://127.0.0.1:8000/api/whatsapp/gemini"`
  - Used by the Go WhatsApp service to forward inbound messages to Django.
  - The Go service defaults to the same local endpoint if this variable is not set.
- `SERVER_IP`, `SERVER_USER`, `SSH_KEY`
  - Used by `deploy_go.sh` to deploy the compiled WhatsApp service to the production server.
  - `SSH_KEY` can point to your private key path; if unset, the script may use `~/.ssh/google_compute_engine`.

### Notes

- The default database in `core/settings.py` is SQLite (`db.sqlite3`).
- If you use a different database in production, update `core/settings.py` accordingly.
- Keep `.env` secret and never commit it to version control.

## Local development setup

1. Create and activate a Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` with the variables listed above.

4. Run migrations and collect static files:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

5. Run the app locally:

```bash
python manage.py runserver
```

6. (Optional) Run setup verification:

```bash
python verify_setup.py
```

### If you want WhatsApp features locally

- Run the Go WhatsApp service:

```bash
cd whatsapp_service
go run main.go
```

- Or use `deploy_go.sh` with Docker to compile a Linux binary.

## New VM / production deployment

The repository includes `new_server.sh` to bootstrap a new Ubuntu/Debian VM.
It performs:

- system package update and required build tools
- Python 3 environment creation and dependency installation
- Gunicorn and Nginx installation
- `.env` file creation with dummy values
- Django migrations and static collection
- Creation of `gunicorn.service` and `whatsapp-service.service`
- Nginx site configuration for the Django app

Run it as root on the new server:

```bash
sudo ./new_server.sh
```

After the script finishes:

- Edit `./.env` with your real production credentials.
- Confirm Nginx config and domain names in `/etc/nginx/sites-available/django_app`.
- Start services:

```bash
sudo systemctl start gunicorn
sudo systemctl start whatsapp-service
sudo systemctl restart nginx
```

- Check status:

```bash
sudo systemctl status gunicorn
sudo systemctl status whatsapp-service
sudo systemctl status nginx
```

- For WhatsApp QR login output:

```bash
sudo journalctl -u whatsapp-service -f
```

## Deploying the Go WhatsApp service in production

Use `deploy_go.sh` to compile the Go service inside Docker and deploy the binary to the server.
It expects these variables in your local `.env` file:

- `SERVER_IP` - remote server address
- `SERVER_USER` - SSH user
- `SSH_KEY` - optional SSH private key path

The script:

1. builds `whatsapp_service/main.go` as a static Linux binary inside Docker
2. uploads the binary to the remote server via SCP
3. moves the binary into `~/cenourinhas/whatsapp_service/whatsapp_service`
4. sets permissions and restarts `whatsapp-service`

Run it locally from the project root:

```bash
./deploy_go.sh
```

## `update.sh` explained

`update.sh` is the production update script for an existing deployment. It:

- runs `git pull`
- activates the local Python virtual environment
- installs Python dependencies from `requirements.txt`
- runs `python manage.py migrate`
- runs `python manage.py collectstatic --noinput`
- restarts `gunicorn` and `nginx`
- optionally restarts `whatsapp-service` if it is active

Run it as root when updating production:

```bash
sudo ./update.sh
```

## Important Django commands

Useful commands for local development and migrations:

- `python manage.py makemigrations`
- `python manage.py makemigrations core assistant otp`
- `python manage.py migrate`
- `python manage.py createsuperuser`
- `python manage.py collectstatic --noinput`
- `python manage.py runserver`
- `python manage.py shell`
- `python manage.py check`
- `python manage.py test`

## What the site does

- Public wedding site pages with gift/present list and personalized RSVP.
- Guest login via WhatsApp OTP through `otp/` and the Go WhatsApp service.
- Guest and extra guest tracking, confirmation status for both wedding days.
- Payment creation using Mercado Pago and webhook handling for status updates.
- Admin dashboard for managing guests, gifts, payments, site content and WhatsApp batches.
- WhatsApp assistant integration: incoming WhatsApp messages are forwarded from the Go service to Django, where Gemini (and OpenRouter fallback) can handle user intent and call tools.

## Notes

- `core/settings.py` currently uses SQLite and loads environment variables with `dotenv`.
- The WhatsApp service communicates with Django via `WHATSAPP_SERVER_URL`.
- The assistant can use either Gemini or OpenRouter for AI responses depending on API keys.
- `verify_setup.py` helps validate local configuration before starting.

Prod: www.cenourinhas.com.br
