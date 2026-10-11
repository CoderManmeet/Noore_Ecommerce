"""
Safe serializer base classes.

DRF's `Meta.depth` auto-expands every foreign key into a serializer with fields='__all__'.
For the custom User model that exposed password hashes, OTPs and reset tokens on public
endpoints. SafeDepthModelSerializer replaces any depth-expanded User with PublicUserSerializer
and makes every further nested level safe as well.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.utils.field_mapping import get_nested_relation_kwargs

from core.display_name import display_name_for_user, public_display_name

User = get_user_model()

PUBLIC_USER_FIELDS = ("id", "username", "full_name", "display_name")


class PublicUserSerializer(serializers.ModelSerializer):
    """
    Minimal, non-sensitive view of a user, safe to embed in public responses.

    `full_name` and `username` are stored fields and may hold the account's email address
    (`User.save()` uses the email as the fallback name). Both are passed through
    `core.display_name` here so no public response can carry an email address, and
    `display_name` is what callers should render.
    """

    full_name = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = PUBLIC_USER_FIELDS
        read_only_fields = PUBLIC_USER_FIELDS

    def get_full_name(self, obj):
        return display_name_for_user(obj)

    def get_username(self, obj):
        return public_display_name(getattr(obj, "username", None))

    def get_display_name(self, obj):
        return display_name_for_user(obj)


class SafeDepthModelSerializer(serializers.ModelSerializer):
    def build_nested_field(self, field_name, relation_info, nested_depth):
        related_model = relation_info.related_model
        field_kwargs = get_nested_relation_kwargs(relation_info)
        if issubclass(related_model, User):
            return PublicUserSerializer, field_kwargs

        class NestedSerializer(SafeDepthModelSerializer):
            class Meta:
                model = related_model
                depth = nested_depth - 1
                fields = "__all__"

        return NestedSerializer, field_kwargs