from django.urls import path

from .web_views import (
    dashboard,
    payment_detail,
    payments_page,
    simulator_page,
    system_page,
)


urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("payments/", payments_page, name="payments"),
    path(
        "payments/<int:payment_id>/",
        payment_detail,
        name="payment-detail",
    ),
    path("simulator/", simulator_page, name="simulator"),
    path("system/", system_page, name="system"),
]