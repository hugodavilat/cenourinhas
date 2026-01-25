from django.contrib import admin
from .models import Presente, Pagamento


@admin.register(Presente)
class PresenteAdmin(admin.ModelAdmin):
    list_display = ['id', 'nome', 'valor', 'criado_em']
    search_fields = ['nome', 'descricao']
    list_filter = ['criado_em']
    fields = ['nome', 'descricao', 'valor', 'imagem_url', 'criado_em', 'atualizado_em']
    readonly_fields = ['criado_em', 'atualizado_em']


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ['id', 'presente', 'valor', 'status', 'mp_payment_id', 'criado_em']
    search_fields = ['mp_payment_id', 'nome_pagador', 'email_pagador']
    list_filter = ['status', 'criado_em']
    fields = ['presente', 'valor', 'status', 'mp_payment_id', 'nome_pagador', 'email_pagador', 'criado_em', 'atualizado_em']
    readonly_fields = ['criado_em', 'atualizado_em']
    
    def has_delete_permission(self, request):
        return False  # Evitar exclusão de registros de pagamento

    def has_add_permission(self, request):
        return False  # Pagamentos não devem ser adicionados manualmente
