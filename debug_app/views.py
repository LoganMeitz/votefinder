from django.shortcuts import render, redirect
from django.conf import settings
from votefinder.main.models import Game
from votefinder.main import VoteCounter
# Create your views here.


def delete_game(request, game_id):
    game = Game.objects.get(id=game_id)
    game.delete()
    return redirect('/')

def post_hammer(request, game_id):
    game = Game.objects.get(id=game_id)
    vc = VoteCounter.VoteCounter()
    vc.post_execute_message(game, "Test Hammer")
    return redirect(f'/game/{game.slug}')