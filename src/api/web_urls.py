from django.urls import path

from .web_views import (
    dashboard,
    payment_detail,
    payment_reconcile,
    payment_retry,
    payments_page,
    simulator_page,
    system_page,
)


urlpatterns = [
    path(
        "",
        dashboard,
        name="dashboard",
    ),

    path(
        "payments/",
        payments_page,
        name="payments",
    ),

    path(
        "payments/<int:payment_id>/",
        payment_detail,
        name="payment-detail",
    ),

    path(
        "payments/<int:payment_id>/reconcile/",
        payment_reconcile,
        name="payment-reconcile",
    ),

    path(
        "payments/<int:payment_id>/retry/",
        payment_retry,
        name="payment-retry",
    ),

    path(
        "simulator/",
        simulator_page,
        name="simulator",
    ),

    path(
        "system/",
        system_page,
        name="system",
    ),
]