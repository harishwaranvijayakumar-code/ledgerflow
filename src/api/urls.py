from django.urls import path

from .views import create_payment


urlpatterns = [
    path("payments/", create_payment, name="create-payment"),
]