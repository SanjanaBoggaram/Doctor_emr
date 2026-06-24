from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class PatientRegistrationForm(UserCreationForm):
    """New-patient signup. `username` is the chosen Patient ID."""

    full_name = forms.CharField(max_length=200, label="Full Name")

    class Meta:
        model = User
        fields = ("username", "full_name", "phone")
        labels = {
            "username": "Choose a Patient ID (e.g. your phone number)",
            "phone": "Phone (optional)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = False
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PATIENT
        full_name = self.cleaned_data["full_name"].strip()
        # Map the single "full name" onto Django's first/last name fields.
        parts = full_name.split(" ", 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
        if commit:
            user.save()
        return user
