from django.urls import path, re_path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

app_name = 'blogai'

urlpatterns = [
    # Auth
    path('auth/login/', views.api_login, name='api_login'),
    path('auth/signup/', views.api_signup, name='api_signup'),
    path('auth/logout/', views.api_logout, name='api_logout'),
    path('auth/user/', views.get_user_data, name='get_user_data'),
    path('auth/user/update/', views.update_user_profile, name='update_user_profile'),

    # Blog logic
    path('all-blogs/', views.api_blog_list, name='api_blog_list'),
    path('blog-details/<int:pk>/', views.api_blog_details, name='api_blog_details'),
    path('generate-blog/', views.generate_blog, name='generate_blog'),
    path('blogs/<int:pk>/delete/', views.api_blog_delete, name='api_blog_delete'),
]

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]