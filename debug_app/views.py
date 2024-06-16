from django.shortcuts import render, redirect
from django.conf import settings
from votefinder.main.models import Game
# Create your views here.


def delete_game(request, game_id):
    game = Game.objects.get(id=game_id)
    game.delete()
    return redirect('/')