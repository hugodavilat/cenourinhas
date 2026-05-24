#!/bin/bash

###############################################################################
# new_server.sh - Setup completo para novo servidor Django em produção
# 
# Este script configura um servidor Linux zero do zero com:
# - Python 3 e venv
# - Dependências do requirements.txt
# - Gunicorn e Nginx
# - Golang e whatsapp_service
# - Arquivo .env com variáveis dummy
###############################################################################

set -e  # Exit on any error

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configurações
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
GUNICORN_SOCKET="/run/gunicorn.sock"
DJANGO_SETTINGS="core.settings"
GO_VERSION="1.23"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Servidor Django Produção${NC}"
echo -e "${GREEN}========================================${NC}"

# Verificar se é root (ou sudo)
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Este script deve ser executado como root (sudo)${NC}"
   exit 1
fi

# 1. Update do sistema
echo -e "\n${YELLOW}[1/10] Atualizando pacotes do sistema...${NC}"
apt-get update
# apt-get upgrade -y # Comentado para evitar atualizar pacotes gigantes desnecessários (como google-cloud-cli) em VMs pequenas

# 2. Instalar Python 3 e dependências de build
echo -e "\n${YELLOW}[2/10] Instalando Python 3 e ferramentas de build...${NC}"
apt-get install -y python3 python3-pip python3-venv python3-dev
apt-get install -y build-essential libssl-dev libffi-dev

# 3. Instalar PostgreSQL client (se usar BD remoto)
echo -e "\n${YELLOW}[3/10] Instalando PostgreSQL client...${NC}"
apt-get install -y postgresql-client

# 4. Criar virtual environment
echo -e "\n${YELLOW}[4/10] Criando Python virtual environment...${NC}"
if [ -d "$VENV_DIR" ]; then
    echo "Venv já existe, pulando..."
else
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip setuptools wheel
fi

# Ativar venv
source "$VENV_DIR/bin/activate"

# 5. Instalar Python dependencies
echo -e "\n${YELLOW}[5/10] Instalando dependências Python...${NC}"
pip install -r "$PROJECT_DIR/requirements.txt"

# 6. Instalar Gunicorn
echo -e "\n${YELLOW}[6/10] Instalando Gunicorn...${NC}"
pip install gunicorn

# 7. Instalar Nginx
echo -e "\n${YELLOW}[7/10] Instalando Nginx...${NC}"
apt-get install -y nginx
systemctl enable nginx

# 8. Instalar Golang
echo -e "\n${YELLOW}[8/10] Instalando Golang...${NC}"
apt-get install -y wget
ARCH=$(uname -m)
if [ "$ARCH" == "x86_64" ]; then
    GO_ARCH="amd64"
elif [ "$ARCH" == "aarch64" ]; then
    GO_ARCH="arm64"
else
    GO_ARCH="$ARCH"
fi

if ! command -v go &> /dev/null; then
    cd /tmp
    wget -q "https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
    tar -C /usr/local -xzf "go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
    rm "go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
    export PATH="$PATH:/usr/local/go/bin"
    echo 'export PATH="$PATH:/usr/local/go/bin"' >> /etc/profile.d/golang.sh
fi

# 9. Instalar whatsapp_service
echo -e "\n${YELLOW}[9/10] Compilando whatsapp_service (Go)...${NC}"
export PATH="$PATH:/usr/local/go/bin"
cd "$PROJECT_DIR/whatsapp_service"
go mod download
go build -o whatsapp_service main.go
chmod +x whatsapp_service

# 10. Criar arquivo .env com variáveis dummy
echo -e "\n${YELLOW}[10/10] Criando arquivo .env com variáveis dummy...${NC}"
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "Arquivo .env já existe, criando backup..."
    cp "$PROJECT_DIR/.env" "$PROJECT_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"
fi

cat > "$PROJECT_DIR/.env" << 'EOF'
# Django Settings
DJANGO_DEBUG=False
DJANGO_SECRET_KEY="CHANGE-THIS-TO-A-RANDOM-SECRET-KEY-IN-PRODUCTION"
URL_SITE="https://www.cenourinhas.com.br"

# Admin Numbers (WhatsApp)
ADMINS="+5511999999999,+5511888888888"

# MercadoPago
MP_ACCESS_TOKEN="YOUR_MERCADOPAGO_ACCESS_TOKEN_HERE"

# AI APIs
GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
OPEN_ROUTER_API_KEY="YOUR_OPEN_ROUTER_API_KEY_HERE"

# WhatsApp Service
WHATSAPP_SERVER_URL="http://localhost:8081"
EOF

chmod 600 "$PROJECT_DIR/.env"
echo -e "${GREEN}✓ Arquivo .env criado. EDITE COM SUAS CREDENCIAIS!${NC}"

# Django setup
echo -e "\n${YELLOW}Executando Django migrations...${NC}"
cd "$PROJECT_DIR"
python manage.py migrate
python manage.py collectstatic --noinput

# Setup systemd services
echo -e "\n${YELLOW}Criando systemd service para Gunicorn...${NC}"

cat > /etc/systemd/system/gunicorn.service << EOF
[Unit]
Description=Gunicorn Django App
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$VENV_DIR/bin/gunicorn \
    --workers 3 \
    --bind unix:$GUNICORN_SOCKET \
    --access-logfile - \
    --error-logfile - \
    $DJANGO_SETTINGS.wsgi
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo -e "\n${YELLOW}Criando systemd service para WhatsApp Service...${NC}"

cat > /etc/systemd/system/whatsapp-service.service << EOF
[Unit]
Description=WhatsApp Service (Go)
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$PROJECT_DIR/whatsapp_service
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/whatsapp_service/whatsapp_service
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Setup Nginx
echo -e "\n${YELLOW}Configurando Nginx...${NC}"

cat > /etc/nginx/sites-available/django_app << EOF
upstream gunicorn {
    server unix:$GUNICORN_SOCKET fail_timeout=0;
}

server {
    listen 80;
    listen [::]:80;
    server_name www.cenourinhas.com.br cenourinhas.com.br;

    client_max_body_size 20M;

    location /static/ {
        alias $PROJECT_DIR/static/;
    }

    location /media/ {
        alias $PROJECT_DIR/media/;
    }

    location / {
        proxy_pass http://gunicorn;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }
}
EOF

# Enable Nginx site
if [ -L /etc/nginx/sites-enabled/django_app ]; then
    rm /etc/nginx/sites-enabled/django_app
fi
ln -s /etc/nginx/sites-available/django_app /etc/nginx/sites-enabled/django_app

# Remover site default
rm -f /etc/nginx/sites-enabled/default

# Test Nginx config
nginx -t

# Reload systemd
systemctl daemon-reload
systemctl enable gunicorn
systemctl enable whatsapp-service

# Criar diretórios necessários
mkdir -p "$PROJECT_DIR/staticfiles"
mkdir -p "$PROJECT_DIR/media"

# Permissões
chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"
chmod 600 "$PROJECT_DIR/.env"

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Setup Completo!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Próximos passos:${NC}"
echo "1. Edite o arquivo .env com suas credenciais reais:"
echo "   sudo nano $PROJECT_DIR/.env"
echo ""
echo "2. Configure seu domínio no Nginx:"
echo "   sudo nano /etc/nginx/sites-available/django_app"
echo "   (atualize os caminhos de static/ e media/)"
echo ""
echo "3. Inicie os serviços:"
echo "   sudo systemctl start gunicorn"
echo "   sudo systemctl start whatsapp-service"
echo "   sudo systemctl restart nginx"
echo ""
echo "4. Verifique o status:"
echo "   sudo systemctl status gunicorn"
echo "   sudo systemctl status whatsapp-service"
echo "   sudo systemctl status nginx"
echo ""
echo "5. Para ler o QR code do WhatsApp:"
echo "   sudo journalctl -u whatsapp-service -f"
echo ""
