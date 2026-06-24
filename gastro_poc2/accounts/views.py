from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from emr.models import PatientProfile

from .forms import PatientRegistrationForm


class AppLoginView(LoginView):
    """Single login form for both patients and doctors (role decides redirect)."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.is_doctor:
            return reverse_lazy("emr:doctor_dashboard")
        return reverse_lazy("emr:patient_chat")


def register(request):
    if request.user.is_authenticated:
        return redirect("emr:home")

    if request.method == "POST":
        form = PatientRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Every patient gets an EMR profile seeded with blank sections.
            PatientProfile.objects.create(
                user=user,
                full_name=form.cleaned_data["full_name"].strip(),
            )
            login(request, user)
            messages.success(request, "Account created — welcome!")
            return redirect("emr:patient_chat")
    else:
        form = PatientRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("accounts:login")
