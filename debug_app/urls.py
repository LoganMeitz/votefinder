from django.urls import path, re_path

from debug_app import views

urlpatterns = [
    path('delete/<game_id>', views.delete_game),
    path('hammer/<game_id>', views.post_hammer)
]