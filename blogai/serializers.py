from rest_framework import serializers
from .models import BlogPost

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