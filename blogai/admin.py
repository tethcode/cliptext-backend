from django.contrib import admin
from .models import BlogPost, Profile

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('youtube_title', 'user', 'created_at')
    search_fields = ('youtube_title', 'generated_content')
    list_filter = ('created_at', 'user')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bio', 'has_profile_pic')
    search_fields = ('user__username', 'bio')

    def has_profile_pic(self, obj):
        return bool(obj.profile_pic)
    has_profile_pic.boolean = True  # Shows a nice checkmark icon