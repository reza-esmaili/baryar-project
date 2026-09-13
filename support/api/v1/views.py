from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from support.models import (
    SupportDepartment,
    TicketTopic,
    Ticket,
    TicketTransfer,
    SupportAgent,
)

from .serializers import (
    SupportDepartmentSerializer,
    TicketTopicSerializer,
    TicketListSerializer,
    TicketDetailSerializer,
    TicketCreateSerializer,
    TicketReplySerializer,
    TicketTransferSerializer,
)

from support.search import filter_tickets
from support.services import auto_assign_agent
from support.views import get_panel_type, user_can_access_ticket, user_can_transfer_ticket


class DepartmentListAPIView(generics.ListAPIView):

    serializer_class = SupportDepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):

        panel_type = self.request.query_params.get("panel_type")

        qs = SupportDepartment.objects.filter(
            is_active=True
        )

        if panel_type:
            qs = qs.filter(panel_type=panel_type)

        return qs.order_by("name")


class TopicListAPIView(generics.ListAPIView):

    serializer_class = TicketTopicSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):

        department_id = self.request.query_params.get("department_id")

        qs = TicketTopic.objects.filter(
            is_active=True,
            department__is_active=True
        )

        if department_id:
            qs = qs.filter(department_id=department_id)

        return qs.order_by("title")


class TicketListAPIView(generics.ListAPIView):

    serializer_class = TicketListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):

        qs = Ticket.objects.filter(
            user=self.request.user
        ).select_related(
            "department",
            "topic",
        ).order_by("-updated_at", "-created_at")

        qs = filter_tickets(qs, self.request.query_params)

        return qs


class TicketCreateAPIView(generics.CreateAPIView):

    serializer_class = TicketCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):

        ticket = serializer.save()

        auto_assign_agent(ticket)


class TicketDetailAPIView(generics.RetrieveAPIView):

    serializer_class = TicketDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):

        return Ticket.objects.select_related(
            "department",
            "topic",
            "assigned_agent",
        ).prefetch_related(
            "messages"
        )

    def get_object(self):

        ticket = get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])
        panel_type = get_panel_type(self.request)

        if not user_can_access_ticket(self.request.user, ticket, panel_type):
            self.permission_denied(
                self.request,
                message="شما اجازه دسترسی به این تیکت را ندارید."
            )

        return ticket


class TicketReplyAPIView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):

        ticket = get_object_or_404(Ticket, pk=pk)
        panel_type = get_panel_type(request)

        if not user_can_access_ticket(request.user, ticket, panel_type):
            return Response(
                {"detail": "شما اجازه دسترسی به این تیکت را ندارید."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TicketReplySerializer(
            data=request.data,
            context={
                "request": request,
                "ticket": ticket
            }
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "پاسخ ثبت شد"},
            status=status.HTTP_201_CREATED
        )


class TicketTransferAPIView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):

        ticket = get_object_or_404(Ticket, pk=pk)
        panel_type = get_panel_type(request)

        try:
            agent = request.user.supportagent
        except SupportAgent.DoesNotExist:
            return Response(
                {"detail": "شما کارشناس نیستید"},
                status=status.HTTP_403_FORBIDDEN
            )

        if not user_can_transfer_ticket(request.user, ticket, panel_type):
            return Response(
                {"detail": "شما اجازه ارجاع این تیکت را ندارید."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TicketTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_department = serializer.validated_data["to_department"]

        TicketTransfer.objects.create(
            ticket=ticket,
            from_department=ticket.department,
            to_department=new_department,
            transferred_by=request.user,
            note=serializer.validated_data.get("note", "")
        )

        ticket.department = new_department
        ticket.assigned_agent = None
        ticket.status = Ticket.Status.OPEN
        ticket.unread_for_agent = True

        ticket.save(
            update_fields=[
                "department",
                "assigned_agent",
                "status",
                "unread_for_agent",
                "updated_at",
            ]
        )

        auto_assign_agent(ticket)

        return Response(
            {"detail": "تیکت منتقل شد"},
            status=status.HTTP_200_OK
        )
