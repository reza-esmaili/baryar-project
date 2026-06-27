from django.urls import path
from . import views

app_name = "support_api_v1"

urlpatterns = [

    path(
        "departments/",
        views.DepartmentListAPIView.as_view(),
        name="department-list"
    ),

    path(
        "topics/",
        views.TopicListAPIView.as_view(),
        name="topic-list"
    ),

    path(
        "tickets/",
        views.TicketListAPIView.as_view(),
        name="ticket-list"
    ),

    path(
        "tickets/create/",
        views.TicketCreateAPIView.as_view(),
        name="ticket-create"
    ),

    path(
        "tickets/<int:pk>/",
        views.TicketDetailAPIView.as_view(),
        name="ticket-detail"
    ),

    path(
        "tickets/<int:pk>/reply/",
        views.TicketReplyAPIView.as_view(),
        name="ticket-reply"
    ),

    path(
        "tickets/<int:pk>/transfer/",
        views.TicketTransferAPIView.as_view(),
        name="ticket-transfer"
    ),
]
