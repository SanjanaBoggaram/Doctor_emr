from django.contrib import admin

from .models import PatientProfile, Visit


class VisitInline(admin.TabularInline):
    model = Visit
    extra = 0
    fields = ("visit_code", "chief_complaint", "diagnosis", "created_at")
    readonly_fields = ("visit_code", "created_at")
    show_change_link = True


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "patient_id", "created_at", "updated_at")
    search_fields = ("full_name", "user__username")
    inlines = [VisitInline]


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("visit_code", "patient", "chief_complaint", "created_at")
    list_filter = ("created_at",)
    search_fields = ("patient__full_name", "chief_complaint", "diagnosis")
    readonly_fields = ("created_at",)
