from django.urls import path

from . import views

app_name = "emr"

urlpatterns = [
    path("", views.home, name="home"),
    # Patient
    path("onboarding/", views.onboarding, name="onboarding"),
    path("chat/", views.patient_chat, name="patient_chat"),
    path("chat/send/", views.chat_send, name="chat_send"),
    path("chat/reset/", views.chat_reset, name="chat_reset"),
    path("record/", views.emr_view, name="emr_view"),
    path("visits/", views.visit_list, name="visit_list"),
    # Doctor
    path("doctor/", views.doctor_dashboard, name="doctor_dashboard"),
    path("doctor/visit/<int:visit_id>/", views.visit_update, name="visit_update"),
]
