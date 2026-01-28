"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('presente/', views.presente, name='presente'),
    path('pagamento/<int:presente_id>/', views.iniciar_pagamento, name='iniciar_pagamento'),
    path('pagamento/sucesso/', views.pagamento_sucesso, name='pagamento_sucesso'),
    path('pagamento/erro/', views.pagamento_erro, name='pagamento_erro'),
    path('pagamento/pendente/', views.pagamento_pendente, name='pagamento_pendente'),
    path('webhook/mercadopago/', views.webhook_mercadopago, name='webhook_mercadopago'),
    path("otp/", include("otp.urls")),
    path('admin/', admin.site.urls),

    # Custom admin dashboard and CRUD
    path('wedding-admin/', views.wedding_admin_dashboard, name='wedding_admin'),
    path('wedding-admin/presente/add/', views.admin_add_presente, name='admin_add_presente'),
    path('wedding-admin/presente/<int:pk>/edit/', views.admin_edit_presente, name='admin_edit_presente'),
    path('wedding-admin/presente/<int:pk>/delete/', views.admin_delete_presente, name='admin_delete_presente'),
    path('wedding-admin/pagamento/<int:pk>/edit/', views.admin_edit_pagamento, name='admin_edit_pagamento'),
    path('wedding-admin/pagamento/<int:pk>/delete/', views.admin_delete_pagamento, name='admin_delete_pagamento'),
    path('wedding-admin/guest/add/', views.admin_add_guest, name='admin_add_guest'),
    path('wedding-admin/guest/<int:pk>/edit/', views.admin_edit_guest, name='admin_edit_guest'),
    path('wedding-admin/guest/<int:pk>/delete/', views.admin_delete_guest, name='admin_delete_guest'),
    path('wedding-admin/guest/<int:main_guest_id>/extra/add/', views.admin_add_extra_guest, name='admin_add_extra_guest'),
    path('wedding-admin/extra/<int:pk>/edit/', views.admin_edit_extra_guest, name='admin_edit_extra_guest'),
    path('wedding-admin/extra/<int:pk>/delete/', views.admin_delete_extra_guest, name='admin_delete_extra_guest'),
    path('confirmacao/', views.confirmacao_familia, name='confirmacao_familia'),
]
