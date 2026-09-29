from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("messages/", views.MessagesHomeView.as_view(), name="home"),
    path("messages/c/<slug:slug>/", views.ChannelView.as_view(), name="channel"),
    path("messages/dm/<str:username>/", views.DirectMessageView.as_view(), name="direct"),
]
