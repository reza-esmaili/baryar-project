from rest_framework import serializers
from support.models import (
    SupportDepartment,
    TicketTopic,
    Ticket,
    TicketMessage,
    TicketTransfer,
)
from django.contrib.auth import get_user_model

User = get_user_model()


class SupportDepartmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = SupportDepartment
        fields = [
            "id",
            "name",
            "panel_type",
            "sla_response_minutes",
            "sla_resolve_minutes",
        ]


class TicketTopicSerializer(serializers.ModelSerializer):

    class Meta:
        model = TicketTopic
        fields = [
            "id",
            "title",
            "department",
        ]


class TicketMessageSerializer(serializers.ModelSerializer):

    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = [
            "id",
            "sender",
            "sender_name",
            "message",
            "attachment",
            "created_at",
        ]

    def get_sender_name(self, obj):
        return str(obj.sender)


class TicketListSerializer(serializers.ModelSerializer):

    department_name = serializers.CharField(source="department.name", read_only=True)
    topic_title = serializers.CharField(source="topic.title", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "number",
            "subject",
            "priority",
            "status",
            "department",
            "department_name",
            "topic",
            "topic_title",
            "created_at",
            "updated_at",
            "unread_for_user",
        ]


class TicketDetailSerializer(serializers.ModelSerializer):

    department_name = serializers.CharField(source="department.name", read_only=True)
    topic_title = serializers.CharField(source="topic.title", read_only=True)

    messages = TicketMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "number",
            "subject",
            "priority",
            "status",
            "department",
            "department_name",
            "topic",
            "topic_title",
            "assigned_agent",
            "messages",
            "created_at",
            "updated_at",
        ]


class TicketCreateSerializer(serializers.ModelSerializer):

    message = serializers.CharField(write_only=True)
    attachment = serializers.FileField(required=False)

    class Meta:
        model = Ticket
        fields = [
            "department",
            "topic",
            "subject",
            "priority",
            "message",
            "attachment",
        ]

    def create(self, validated_data):

        message = validated_data.pop("message")
        attachment = validated_data.pop("attachment", None)

        user = self.context["request"].user

        ticket = Ticket.objects.create(
            user=user,
            unread_for_agent=True,
            unread_for_user=False,
            status=Ticket.Status.OPEN,
            **validated_data,
        )

        TicketMessage.objects.create(
            ticket=ticket,
            sender=user,
            message=message,
            attachment=attachment,
        )

        return ticket


class TicketReplySerializer(serializers.ModelSerializer):

    class Meta:
        model = TicketMessage
        fields = [
            "message",
            "attachment",
        ]

    def create(self, validated_data):

        ticket = self.context["ticket"]
        user = self.context["request"].user

        message = TicketMessage.objects.create(
            ticket=ticket,
            sender=user,
            **validated_data,
        )

        if ticket.user == user:
            ticket.unread_for_agent = True
            ticket.unread_for_user = False
            ticket.status = Ticket.Status.OPEN
        else:
            ticket.unread_for_user = True
            ticket.unread_for_agent = False
            ticket.status = Ticket.Status.ANSWERED

        ticket.save(
            update_fields=[
                "unread_for_user",
                "unread_for_agent",
                "status",
                "updated_at",
            ]
        )

        return message


class TicketTransferSerializer(serializers.ModelSerializer):

    class Meta:
        model = TicketTransfer
        fields = [
            "to_department",
            "note",
        ]
