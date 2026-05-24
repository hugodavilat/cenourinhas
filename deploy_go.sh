#!/bin/bash

# deploy_go.sh - Compila o whatsapp_service localmente para Linux e faz o upload para a produção

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_IP=""
SERVER_USER="hugo"

# Tentar obter o IP do servidor do arquivo .env local se existir
if [ -f "$PROJECT_DIR/.env" ]; then
    SERVER_IP=$(grep -E "^SERVER_IP=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
fi

if [ -z "$SERVER_IP" ]; then
    echo -e "${YELLOW}Digite o IP ou domínio do seu servidor GCP:${NC} "
    read -r SERVER_IP
fi

if [ -z "$SERVER_IP" ]; then
    echo -e "${RED}Erro: O IP do servidor é obrigatório.${NC}"
    exit 1
fi

echo -e "\n${YELLOW}[1/3] Compilando whatsapp_service para Linux (amd64)...${NC}"
cd "$PROJECT_DIR/whatsapp_service"

# Configurar variáveis de ambiente do Go para compilação cruzada (Cross-Compilation)
env GOOS=linux GOARCH=amd64 go build -o whatsapp_service_linux main.go

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Compilado com sucesso! (whatsapp_service_linux)${NC}"
else
    echo -e "${RED}✗ Falha na compilação do Go.${NC}"
    exit 1
fi

echo -e "\n${YELLOW}[2/3] Enviando binário para o servidor (${SERVER_USER}@${SERVER_IP})...${NC}"
# Enviar via SCP
scp whatsapp_service_linux "${SERVER_USER}@${SERVER_IP}:~/cenourinhas/whatsapp_service/whatsapp_service"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Upload concluído com sucesso.${NC}"
else
    echo -e "${RED}✗ Falha no envio via SCP. Verifique suas chaves SSH ou IP.${NC}"
    rm -f whatsapp_service_linux
    exit 1
fi

# Limpar o arquivo local temporário
rm -f whatsapp_service_linux

echo -e "\n${YELLOW}[3/3] Ajustando permissões e reiniciando o serviço na VM...${NC}"
# Conectar via SSH para ajustar permissões, transferir a propriedade para www-data e reiniciar o serviço do whatsapp
ssh -t "${SERVER_USER}@${SERVER_IP}" "sudo chmod 755 ~/cenourinhas/whatsapp_service/whatsapp_service && sudo chown www-data:www-data ~/cenourinhas/whatsapp_service/whatsapp_service && sudo systemctl restart whatsapp-service"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}=================================================${NC}"
    echo -e "${GREEN}✓ Deploy do WhatsApp Service Concluído com Sucesso!${NC}"
    echo -e "${GREEN}=================================================${NC}"
else
    echo -e "${RED}✗ Falha ao reiniciar o serviço no servidor.${NC}"
    exit 1
fi
