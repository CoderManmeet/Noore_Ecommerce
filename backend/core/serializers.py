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

User = get_user_model()

PUBLIC_USER_FIELDS = ("id", "username", "full_name")


class PublicUserSerializer(serializers.ModelSerializer):
    """Minimal, non-sensitive view of a user, safe to embed in public responses."""

    class Meta:
        model = User
        fields = PUBLIC_USER_FIELDS
        read_only_fields = PUBLIC_USER_FIELDS


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
