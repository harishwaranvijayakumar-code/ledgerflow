from django.urls import path

from .views import (
    create_payment,
    reconcile_payment_view,
    retry_payment_view,
)


urlpatterns = [
    path(
        "payments/",
        create_payment,
        name="create-payment",
    ),
    path(
        "payments/<int:payment_id>/reconcile/",
        reconcile_payment_view,
        name="reconcile-payment",
    ),
    path(
        "payments/<int:payment_id>/retry/",
        retry_payment_view,
        name="retry-payment",
    ),
]