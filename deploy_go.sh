#!/bin/bash

# deploy_go.sh - Compila o whatsapp_service localmente para Linux e faz o upload para a produção

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_IP=""
SERVER_USER=""
SSH_KEY=""

# Obter configurações do servidor do arquivo .env local se existir
if [ -f "$PROJECT_DIR/.env" ]; then
    SERVER_IP=$(grep -E "^SERVER_IP=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    SERVER_USER=$(grep -E "^SERVER_USER=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    SSH_KEY=$(grep -E "^SSH_KEY=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
fi

# Validar se as informações necessárias foram fornecidas no .env
if [ -z "$SERVER_IP" ]; then
    printf "%bErro: A variável SERVER_IP não está definida no seu arquivo .env local.%b\n" "${RED}" "${NC}"
    exit 1
fi

if [ -z "$SERVER_USER" ]; then
    printf "%bErro: A variável SERVER_USER não está definida no seu arquivo .env local.%b\n" "${RED}" "${NC}"
    exit 1
fi

# Tentar encontrar a chave padrão do GCP se nenhuma chave foi definida no .env
if [ -z "$SSH_KEY" ]; then
    # Expandir o path ~ para o diretório home real do usuário
    GCP_KEY="${HOME}/.ssh/google_compute_engine"
    if [ -f "$GCP_KEY" ]; then
        SSH_KEY="$GCP_KEY"
    fi
fi

# Configurar opções de chave privada para ssh/scp se houver uma chave definida
SSH_OPTS=""
if [ -n "$SSH_KEY" ]; then
    # Se a chave contiver ~ local, precisamos expandi-la
    SSH_KEY="${SSH_KEY/#\~/$HOME}"
    if [ -f "$SSH_KEY" ]; then
        SSH_OPTS="-i $SSH_KEY"
        printf "Usando chave SSH: %s\n" "$SSH_KEY"
    else
        printf "%bAviso: A chave SSH especificada não foi encontrada em %s.%b\n" "${YELLOW}" "$SSH_KEY" "${NC}"
    fi
fi

printf "\n%b[1/3] Compilando whatsapp_service para Linux (amd64)...%b\n" "${YELLOW}" "${NC}"
cd "$PROJECT_DIR/whatsapp_service"

# Configurar variáveis de ambiente do Go para compilação cruzada (Cross-Compilation)
env GOOS=linux GOARCH=amd64 go build -o whatsapp_service_linux main.go

if [ $? -eq 0 ]; then
    printf "%b✓ Compilado com sucesso! (whatsapp_service_linux)%b\n" "${GREEN}" "${NC}"
else
    printf "%b✗ Falha na compilação do Go.%b\n" "${RED}" "${NC}"
    exit 1
fi

printf "\n%b[2/3] Enviando binário para o servidor (${SERVER_USER}@${SERVER_IP})...%b\n" "${YELLOW}" "${NC}"
# Enviar via SCP
scp $SSH_OPTS whatsapp_service_linux "${SERVER_USER}@${SERVER_IP}:~/cenourinhas/whatsapp_service/whatsapp_service"

if [ $? -eq 0 ]; then
    printf "%b✓ Upload concluído com sucesso.%b\n" "${GREEN}" "${NC}"
else
    printf "%b✗ Falha no envio via SCP. Verifique suas chaves SSH ou IP.%b\n" "${RED}" "${NC}"
    rm -f whatsapp_service_linux
    exit 1
fi

# Limpar o arquivo local temporário
rm -f whatsapp_service_linux

printf "\n%b[3/3] Ajustando permissões e reiniciando o serviço na VM...%b\n" "${YELLOW}" "${NC}"
# Conectar via SSH para ajustar permissões, transferir a propriedade para www-data e reiniciar o serviço do whatsapp
ssh $SSH_OPTS -t "${SERVER_USER}@${SERVER_IP}" "sudo chmod 755 ~/cenourinhas/whatsapp_service/whatsapp_service && sudo chown www-data:www-data ~/cenourinhas/whatsapp_service/whatsapp_service && sudo systemctl restart whatsapp-service"

if [ $? -eq 0 ]; then
    printf "%b=================================================%b\n" "${GREEN}" "${NC}"
    printf "%b✓ Deploy do WhatsApp Service Concluído com Sucesso!%b\n" "${GREEN}" "${NC}"
    printf "%b=================================================%b\n" "${GREEN}" "${NC}"
else
    printf "%b✗ Falha ao reiniciar o serviço no servidor.%b\n" "${RED}" "${NC}"
    exit 1
fi
