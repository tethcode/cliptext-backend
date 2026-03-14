from rest_framework import serializers
from .models import BlogPost, PasswordResetToken
from django.contrib.auth.models import User
from django.utils import timezone

class BlogPostSerializer(serializers.ModelSerializer):
    # 'source' maps the field to the correct model relationship
    profile_pic = serializers.ImageField(source='user.profile.image', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = BlogPost
        fields = [
            'id', 
            'youtube_title', 
            'youtube_link', 
            'generated_content', 
            'created_at', 
            'profile_pic', 
            'username'
        ]

class ForgotPasswordSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()

    def validate(self, data):
        try:
            user = User.objects.get(username=data['username'], email=data['email'])
            data['user'] = user
        except User.DoesNotExist:
            raise serializers.ValidationError("No user found with this username and email.")
        return data


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(min_length=8, write_only=True)

    def validate(self, data):
        try:
            reset_token = PasswordResetToken.objects.get(token=data["token"])
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Invalid token.")

        if reset_token.expires_at < timezone.now():
            reset_token.delete()
            raise serializers.ValidationError("Token has expired.")

        data["reset_token"] = reset_token
        return data

    def save(self):
        reset_token = self.validated_data["reset_token"]
        user = reset_token.user

        user.set_password(self.validated_data["password"])
        user.save()

        reset_token.delete()