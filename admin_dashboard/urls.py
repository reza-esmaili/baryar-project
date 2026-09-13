from django.urls import path
from . import views
from . import views_lookup
from . import views_rates
from . import views_documents
from . import views_import
from . import views_ajax

app_name = "admin_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("settings/", views.settings_hub, name="settings_hub"),

    # ─── Phase 1: users, forwarders, orders, tickets ───────────────────────
    path("users/", views.user_list, name="user_list"),
    path("users/add/", views.user_create, name="user_create"),
    path("users/<int:user_id>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),

    path("forwarders/", views.forwarder_list, name="forwarder_list"),
    path("forwarders/add/", views.forwarder_create, name="forwarder_create"),
    path("forwarders/<int:company_id>/edit/", views.forwarder_edit, name="forwarder_edit"),
    path(
        "forwarders/<int:company_id>/branches/add/",
        views.forwarder_branch_form,
        name="forwarder_branch_add",
    ),
    path(
        "forwarders/<int:company_id>/branches/<int:branch_id>/edit/",
        views.forwarder_branch_form,
        name="forwarder_branch_edit",
    ),
    path(
        "forwarders/<int:company_id>/branches/<int:branch_id>/toggle-active/",
        views.forwarder_branch_toggle_active,
        name="forwarder_branch_toggle_active",
    ),
    path(
        "forwarders/<int:company_id>/staff/add/",
        views.forwarder_staff_form,
        name="forwarder_staff_add",
    ),
    path(
        "forwarders/<int:company_id>/staff/<int:staff_id>/edit/",
        views.forwarder_staff_form,
        name="forwarder_staff_edit",
    ),
    path(
        "forwarders/<int:company_id>/staff/<int:staff_id>/toggle-active/",
        views.forwarder_staff_toggle_active,
        name="forwarder_staff_toggle_active",
    ),
    path("forwarders/<int:company_id>/", views.forwarder_detail, name="forwarder_detail"),
    path(
        "forwarders/<int:company_id>/documents/<int:doc_id>/review/",
        views.review_identity_document,
        name="review_identity_document",
    ),

    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:order_id>/edit/", views.order_edit, name="order_edit"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),

    path("tickets/", views.ticket_list, name="ticket_list"),
    path("tickets/<int:ticket_id>/", views.ticket_detail, name="ticket_detail"),

    # ─── Phase 2: generic lookup tables ─────────────────────────────────────
    path("lookups/<str:key>/", views_lookup.lookup_list, name="lookup_list"),
    path("lookups/<str:key>/add/", views_lookup.lookup_form, name="lookup_add"),
    path("lookups/<str:key>/<int:pk>/edit/", views_lookup.lookup_form, name="lookup_edit"),
    path("lookups/<str:key>/<int:pk>/toggle-active/", views_lookup.lookup_toggle_active, name="lookup_toggle_active"),
    path("lookups/<str:key>/<int:pk>/delete/", views_lookup.lookup_delete, name="lookup_delete"),

    # ─── Phase 2: rates + cargo type hierarchy ──────────────────────────────
    path("rates/", views_rates.rate_list, name="rate_list"),
    path("rates/add/", views_rates.rate_form, name="rate_add"),
    path("rates/<int:pk>/edit/", views_rates.rate_form, name="rate_edit"),
    path("rates/<int:pk>/delete/", views_rates.rate_delete, name="rate_delete"),
    path("rates/<int:pk>/", views_rates.rate_detail, name="rate_detail"),
    path("cargo-types/", views_rates.cargo_type_hub, name="cargo_type_hub"),
    path("cargo-types/<int:category_id>/subcategories/", views_rates.cargo_subcategory_hub, name="cargo_subcategory_hub"),

    # ─── Phase 2: document rules ─────────────────────────────────────────────
    path("document-rules/", views_documents.document_rule_list, name="document_rule_list"),
    path("document-rules/add/", views_documents.document_rule_form, name="document_rule_add"),
    path("document-rules/<int:pk>/edit/", views_documents.document_rule_form, name="document_rule_edit"),
    path(
        "additional-document-requests/",
        views_documents.additional_document_request_list,
        name="additional_document_request_list",
    ),

    # ─── Phase 2: excel importers ────────────────────────────────────────────
    path("cargo-types/import/", views_import.import_cargo_types, name="cargo_type_import"),
    path("lookups/provinces/import/", views_import.import_provinces, name="province_import"),
    path("lookups/countries/import/", views_import.import_countries, name="country_import"),

    # ─── ajax cascading dropdowns ────────────────────────────────────────────
    path("ajax/cities/", views_ajax.ajax_cities, name="ajax_cities"),
    path("ajax/destination-cities/", views_ajax.ajax_destination_cities, name="ajax_destination_cities"),
    path("ajax/destination-ports/", views_ajax.ajax_destination_ports, name="ajax_destination_ports"),
    path("ajax/cargo-types/", views_ajax.ajax_cargo_types, name="ajax_cargo_types"),
]
