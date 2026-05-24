#!/bin/bash

###############################################################################
# update.sh - Atualiza aplicação Django com mudanças do Git
#
# Executa:
# - git pull
# - pip install -r requirements.txt (atualizar dependências)
# - python manage.py migrate
# - python manage.py collectstatic
# - systemctl restart gunicorn
# - systemctl restart nginx
###############################################################################

set -e  # Exit on any error

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log file
LOG_FILE="$PROJECT_DIR/update.log"

log_message() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log_message "\n${BLUE}=================================================================================${NC}"
log_message "${BLUE}Update da Aplicação Django - $TIMESTAMP${NC}"
log_message "${BLUE}=================================================================================${NC}"

# Verificar se é root (opcional, mas recomendado para restart dos serviços)
if [[ $EUID -ne 0 ]]; then
   log_message "${YELLOW}⚠ Este script deve ser executado como root para restart dos serviços${NC}"
   log_message "${YELLOW}  Use: sudo $0${NC}"
   # Não sair, apenas avisar
fi

# 1. Git Pull
log_message "\n${YELLOW}[1/6] Fazendo git pull...${NC}"
cd "$PROJECT_DIR"
if git pull 2>&1 | tee -a "$LOG_FILE"; then
    log_message "${GREEN}✓ Git pull realizado com sucesso${NC}"
else
    log_message "${RED}✗ Erro ao fazer git pull${NC}"
    exit 1
fi

# 2. Ativar venv e atualizar dependências
log_message "\n${YELLOW}[2/6] Ativando virtual environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    log_message "${RED}✗ Virtual environment não encontrado em $VENV_DIR${NC}"
    exit 1
fi

source "$VENV_DIR/bin/activate"
log_message "${GREEN}✓ Virtual environment ativado${NC}"

# 3. Atualizar dependências Python
log_message "\n${YELLOW}[3/6] Atualizando dependências Python...${NC}"
if pip install -r "$PROJECT_DIR/requirements.txt" 2>&1 | tee -a "$LOG_FILE"; then
    log_message "${GREEN}✓ Dependências atualizadas${NC}"
else
    log_message "${RED}✗ Erro ao atualizar dependências${NC}"
    exit 1
fi

# 4. Django Migrations
log_message "\n${YELLOW}[4/6] Executando Django migrations...${NC}"
cd "$PROJECT_DIR"
if python manage.py migrate 2>&1 | tee -a "$LOG_FILE"; then
    log_message "${GREEN}✓ Migrations aplicadas${NC}"
else
    log_message "${RED}✗ Erro ao executar migrations${NC}"
    exit 1
fi

# 5. Django Collect Static
log_message "\n${YELLOW}[5/6] Coletando arquivos estáticos...${NC}"
if python manage.py collectstatic --noinput 2>&1 | tee -a "$LOG_FILE"; then
    log_message "${GREEN}✓ Arquivos estáticos coletados${NC}"
else
    log_message "${RED}✗ Erro ao coletar estáticos${NC}"
    exit 1
fi

# 6. Restart serviços
log_message "\n${YELLOW}[6/6] Reiniciando serviços...${NC}"

if [[ $EUID -eq 0 ]]; then
    # Restart Gunicorn
    log_message "${BLUE}Reiniciando Gunicorn...${NC}"
    if systemctl restart gunicorn 2>&1 | tee -a "$LOG_FILE"; then
        log_message "${GREEN}✓ Gunicorn reiniciado${NC}"
    else
        log_message "${RED}✗ Erro ao reiniciar Gunicorn${NC}"
        exit 1
    fi

    # Restart Nginx
    log_message "${BLUE}Testando e reiniciando Nginx...${NC}"
    if nginx -t 2>&1 | tee -a "$LOG_FILE" && systemctl restart nginx 2>&1 | tee -a "$LOG_FILE"; then
        log_message "${GREEN}✓ Nginx reiniciado${NC}"
    else
        log_message "${RED}✗ Erro ao reiniciar Nginx${NC}"
        exit 1
    fi

    # Reiniciar WhatsApp Service (se houver)
    if systemctl is-active --quiet whatsapp-service; then
        log_message "${BLUE}Reiniciando WhatsApp Service...${NC}"
        if systemctl restart whatsapp-service 2>&1 | tee -a "$LOG_FILE"; then
            log_message "${GREEN}✓ WhatsApp Service reiniciado${NC}"
        else
            log_message "${YELLOW}⚠ Aviso ao reiniciar WhatsApp Service${NC}"
        fi
    fi
else
    log_message "${YELLOW}⚠ Não foi possível reiniciar os serviços (execute como root)${NC}"
    log_message "${YELLOW}  Execute manualmente:${NC}"
    log_message "    sudo systemctl restart gunicorn"
    log_message "    sudo systemctl restart nginx"
fi

log_message "\n${GREEN}=================================================================================${NC}"
log_message "${GREEN}✓ Update concluído com sucesso!${NC}"
log_message "${GREEN}=================================================================================${NC}"

# Verificar status dos serviços
if [[ $EUID -eq 0 ]]; then
    log_message "\n${BLUE}Status dos serviços:${NC}"
    systemctl status gunicorn --no-pager | grep -E "Active|Since" | sed 's/^/  /'
    systemctl status nginx --no-pager | grep -E "Active|Since" | sed 's/^/  /'
fi

log_message "\n${YELLOW}Log completo em: $LOG_FILE${NC}\n"
