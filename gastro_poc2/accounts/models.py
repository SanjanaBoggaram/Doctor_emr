from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user. `username` doubles as the patient ID (e.g. a phone number).
    Passwords are hashed by Django's auth system — no more plaintext.
    """

    class Role(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    phone = models.CharField(max_length=30, blank=True)

    @property
    def is_patient(self) -> bool:
        return self.role == self.Role.PATIENT

    @property
    def is_doctor(self) -> bool:
        return self.role == self.Role.DOCTOR or self.is_staff

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.username} ({self.role})"
