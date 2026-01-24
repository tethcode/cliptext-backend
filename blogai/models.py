import os
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver

# --- Your existing model ---
class BlogPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    youtube_title = models.CharField(max_length=300)
    youtube_link = models.URLField()
    generated_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.youtube_title

# --- New Profile model ---
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_pic = models.ImageField(upload_to='profiles/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)

    def __str__(self):
        return f'{self.user.username} Profile'

# --- Signals ---

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

# 1. Delete file from filesystem when Profile object is deleted
@receiver(post_delete, sender=Profile)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    if instance.profile_pic:
        if os.path.isfile(instance.profile_pic.path):
            os.remove(instance.profile_pic.path)

# 2. Delete old file from filesystem when photo is updated or removed
@receiver(pre_save, sender=Profile)
def auto_delete_file_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return False

    try:
        old_file = sender.objects.get(pk=instance.pk).profile_pic
    except sender.DoesNotExist:
        return False

    new_file = instance.profile_pic
    if not old_file == new_file:
        if old_file and os.path.isfile(old_file.path):
            os.remove(old_file.path)