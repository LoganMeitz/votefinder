import json as simplejson
import math
import random
import re
import requests
import urllib
from datetime import datetime, timedelta
from math import ceil

from pytz import common_timezones, timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connections
from django.db.models import Max, Min, Q  # noqa: WPS347
from django.http import (HttpResponse, HttpResponseForbidden,
                         HttpResponseNotFound, HttpResponseRedirect)
from django.shortcuts import get_list_or_404, get_object_or_404, render, redirect
from django.template.context_processors import csrf
from PIL import Image, ImageDraw, ImageFont
from votefinder.main.models import (AddCommentForm, AddFactionForm, AddPlayerForm,  # noqa: WPS235
                                    Alias, BlogPost, Comment, Game, GameDay,
                                    GameFaction, GameStatusUpdate, Player,
                                    PlayerState, Post, Theme, UserProfile, Vote,
                                    VotecountTemplate, VotecountTemplateForm)

from votefinder.main import (SAForumPageDownloader, SAGameListDownloader, SAPageParser,
                             VoteCounter, VotecountFormatter, BNRGameListDownloader,
                             BNRPageParser, BNRApi)


def check_mod(request, game):
    try:
        return (game.is_user_mod(request.user) or request.user.is_superuser)
    except AttributeError:
        return False


def index(request):
    active_game_list = Game.objects.select_related().filter(state='started').order_by('name')
    pregame_list = Game.objects.select_related().filter(state='pregame').order_by('name')

    big_games = [this_game for this_game in active_game_list if this_game.is_big]
    mini_games = [this_game for this_game in active_game_list if not this_game.is_big]
    posts = BlogPost.objects.all().order_by('-timestamp')[:5]

    game_count = Game.objects.count()
    post_count = Post.objects.count()
    vote_count = Vote.objects.count()
    player_count = Player.objects.count()
    context = {'pregame_games': pregame_list, 'big_games': big_games, 'mini_games': mini_games,
               'total': len(big_games) + len(mini_games), 'posts': posts,
               'game_count': game_count, 'post_count': post_count, 'vote_count': vote_count,
               'player_count': player_count}
    return render(request, 'index.html', context)


@login_required
def add(request):
    default_url = 'http://forums.somethingawful.com/showthread.php?threadid=3069667'
    return render(request, 'add.html', {'defaultUrl': default_url})


@login_required
def add_game(request):
    return_status = {'success': True, 'message': 'Success!', 'url': ''}
    if request.method == 'POST':
        threadid = request.POST.get('threadid')
        state = request.POST.get('addState')
        home_forum = request.POST.get('home_forum')
        if state in {'started', 'pregame'}:
            try:
                game = Game.objects.get(thread_id=threadid, home_forum=home_forum)
                return_status['url'] = game.get_absolute_url()
            except Game.DoesNotExist:
                if home_forum == 'bnr':
                    page_parser = BNRPageParser.BNRPageParser()
                elif home_forum == 'sa':
                    page_parser = SAPageParser.SAPageParser()
                else:
                    return_status['success'] = False
                    return_status['message'] = "Couldn't determine the parent forum or unsupported parent forum. Sorry!"
                    return HttpResponse(simplejson.dumps(return_status), content_type='application/json')
                page_parser.user = request.user
                game = page_parser.add_game(threadid, state)
                if game:
                    return_status['url'] = game.get_absolute_url()
                    game.status_update(f'A new game was created by {game.moderator.name}!')

                    if game.home_forum == 'sa':
                        message_data = {'content': f'{game.moderator.name} has opened {game.name}. Thread link: https://forums.somethingawful.com/showthread.php?threadid={game.thread_id}', 'username': 'Votefinder Game Announcement'}
                        session = requests.Session()
                        session.post(f'https://discordapp.com/api/webhooks/{settings.VF_SA_DISCORD_CHANNEL}/{settings.VF_SA_DISCORD_WEBHOOK}', data=message_data)  # TODO issue 198
                else:
                    return_status['success'] = False
                    return_status['message'] = "Couldn't download or parse the forum thread.  Sorry!"
        else:
            return_status['success'] = False
            return_status['message'] = "Couldn\'t validate the starting game state. Please contact support."
    else:
        return_status['success'] = False
        return_status['message'] = 'Form was submitted incorrectly. Please use the add game page.'
    return HttpResponse(simplejson.dumps(return_status), content_type='application/json')


@login_required
def game_list(request, page):
    downloader = SAGameListDownloader.SAGameListDownloader()
    downloader.get_game_list(f'http://forums.somethingawful.com/forumdisplay.php?forumid=103&pagenumber={page}')
    bnr = BNRGameListDownloader.BNRGameListDownloader()
    bnr.get_game_list(page)
    downloader.GameList.extend(bnr.GameList)
    return HttpResponse(simplejson.dumps(downloader.GameList), content_type='application/json')


def game(request, slug):
    game = get_object_or_404(Game, slug=slug)
    players = game.players.select_related().all()
    form = AddPlayerForm()
    try:
        comment = Comment.objects.get(game=game)
        comment_form = AddCommentForm(initial={'comment': comment.comment})
    except Comment.DoesNotExist:
        comment_form = AddCommentForm()
    faction_form = AddFactionForm()
    moderators = [ps.player for ps in game.moderators()]
    templates = VotecountTemplate.objects.select_related().filter(Q(creator__in=moderators) | Q(shared=True))
    updates = GameStatusUpdate.objects.filter(game=game).order_by('-timestamp')

    gameday = game.days.select_related().last()

    # detecting games that are missing posts
    if gameday is None:
        context = {'game': game, 'players': players, 'moderator': check_mod(request, game), 'form': form,
                   'comment_form': comment_form, 'broken': True}
        return render(request, 'game_broken.html', context)

    manual_votes = Vote.objects.filter(game=game, manual=True, post__id__gte=gameday.start_post.id).order_by('id')

    if game.deadline:
        tz = timezone(game.timezone)
        tzone = tz.zone
        deadline = timezone(settings.TIME_ZONE).localize(game.deadline).astimezone(tz)
    else:
        deadline = timezone(game.timezone).localize(datetime.now() + timedelta(days=3))
        tzone = game.timezone

    if request.user.is_authenticated:
        try:
            player_state = PlayerState.objects.get(game=game, player=request.user.profile.player)
        except UserProfile.DoesNotExist:
            player_state = False
        except PlayerState.DoesNotExist:
            player_state = False
    else:
        player_state = False

    post_vc_button = bool(check_mod(request, game) and (game.last_vc_post is None or datetime.now() - game.last_vc_post >= timedelta(minutes=60) or (game.deadline and game.deadline - datetime.now() <= timedelta(minutes=60))))
    context = {'game': game, 'players': players, 'moderator': check_mod(request, game), 'form': form,
               'comment_form': comment_form, 'gameday': gameday, 'post_vc_button': post_vc_button,
               'nextDay': gameday.day_number + 1, 'deadline': deadline, 'templates': templates,
               'manual_votes': manual_votes, 'timezone': tzone, 'common_timezones': common_timezones,
               'updates': updates, 'playerstate': player_state, 'faction_form': faction_form, 'broken': False}
    return render(request, 'game.html', context)


def update(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if game.is_locked():
        return HttpResponse(simplejson.dumps(
            {'success': False, 'message': 'Someone else is updating that game right now.  Please wait.'}),
            content_type='application/json')
    else:
        game.lock()
    try:
        if game.home_forum == 'bnr':
            page_parser = BNRPageParser.BNRPageParser()
        elif game.home_forum == 'sa':
            page_parser = SAPageParser.SAPageParser()
        new_game = page_parser.update(game)
        if new_game:
            return HttpResponse(
                simplejson.dumps({'success': True, 'curPage': new_game.current_page, 'maxPages': new_game.max_pages}),
                content_type='application/json')
        game.save()
        return HttpResponse(simplejson.dumps({'success': False, 'message': 'There was a problem either downloading or parsing the forum page.  Please try again later.'}),
                            content_type='application/json')
    except BaseException:
        game.save()
        raise


@login_required
def profile(request):
    player = request.user.profile.player
    games = player.games.select_related().all()
    themes = Theme.objects.all()
    context = {'player': player, 'games': games, 'profile': request.user.profile, 'themes': themes,
               'show_delete': True}
    return render(request, 'profile.html', context)


@login_required
def update_user_profile(request):
    if request.method == 'POST':
        profile = request.user.profile
        profile.theme = Theme.objects.get(id=request.POST['theme_id'])
        profile.pronouns = request.POST['pronouns']
        profile.discord_username = request.POST['discord_username']
        profile.save()
    return redirect('/profile')


def player(request, slug):
    try:
        player = get_object_or_404(Player, slug=slug)
        games = player.games.select_related().all()
    except Player.DoesNotExist:
        return HttpResponseNotFound
    show_claim = False
    try:
        aliases = Alias.objects.filter(player=player)
    except Alias.DoesNotExist:
        pass  # noqa: WPS420
    try:
        profile = UserProfile.objects.get(player=player)
        pronouns = profile.pronouns
        discord = profile.discord_username
    except UserProfile.DoesNotExist:
        pronouns = None
        discord = None
        if request.user.is_authenticated and ((player.bnr_uid is not None and player.sa_uid is None and request.user.profile.player.bnr_uid is None) or (player.sa_uid is not None and player.bnr_uid is None and request.user.profile.player.sa_uid is None)):
            show_claim = True

    show_delete = False
    if request.user.is_superuser or (request.user.is_authenticated and request.user.profile.player == player):
        show_delete = True

    return render(request, 'player.html',
                  {'player': player, 'games': games, 'aliases': aliases, 'show_delete': show_delete, 'pronouns': pronouns, 'show_claim': show_claim, 'discord': discord})


@login_required
def claim_player(request, playerid):
    player = get_object_or_404(Player, id=playerid)
    if ((player.bnr_uid is not None and player.sa_uid is None and request.user.profile.player.bnr_uid is None) or (player.sa_uid is not None and player.bnr_uid is None and request.user.profile.player.sa_uid is None)) and not UserProfile.objects.filter(player=player).exists():
        # Eligible to claim!
        if request.method == 'POST':
            validated = False
            csrf_resp = {}
            csrf_resp.update(csrf(request))
            if request.session['claim_key']:
                if player.sa_uid is not None:
                    downloader = SAForumPageDownloader.SAForumPageDownloader()
                    page_data = downloader.download(
                        f'https://forums.somethingawful.com/member.php?action=getinfo&userid={player.sa_uid}')

                    if page_data is None:
                        messages.add_message(request, messages.ERROR, f'There was a problem downloading the profile for the SA user {player.sa_uid}.')

                    if page_data.find(str(request.session['claim_key'])) == -1:
                        messages.add_message(request, messages.ERROR, f"Unable to find the correct key ({request.session['claim_key']}) in {player.sa_uid}'s SA profile")
                    else:
                        validated = True
                elif player.bnr_uid is not None:
                    api = BNRApi.BNRApi()
                    user_profile = api.get_user_by_id(player.bnr_uid)
                    if user_profile is None:
                        messages.add_message(request, messages.ERROR, f'There was a problem downloading the profile for the BNR user {player.bnr_uid}.')
                    if user_profile['location'] == str(request.session['claim_key']):
                        validated = True
                    else:
                        messages.add_message(request, messages.ERROR, f"Unable to find the correct key ({request.session['claim_key']}) in {player.bnr_uid}'s BNR profile")
                if validated:
                    # TODO make this into a queued job via Rabbit or Celery or something - https://buildwithdjango.com/blog/post/celery-progress-bars/ - I don't need progress bars but a come back later'd be nice
                    Game.objects.filter(moderator=player).update(moderator=request.user.profile.player)
                    PlayerState.objects.filter(player=player).update(player=request.user.profile.player)
                    Alias.objects.filter(player=player).update(player=request.user.profile.player)
                    Post.objects.filter(author=player).update(author=request.user.profile.player)
                    Vote.objects.filter(target=player).update(target=request.user.profile.player)
                    Vote.objects.filter(author=player).update(author=request.user.profile.player)
                    if player.sa_uid is not None:
                        request.user.profile.player.sa_uid = player.sa_uid
                    elif player.bnr_uid is not None:
                        request.user.profile.player.bnr_uid = player.bnr_uid
                    player.delete()
                    request.user.profile.player.save()
                    messages.add_message(request, messages.SUCCESS, f'<strong>Done!</strong> You have successfully claimed {player.name}.')
                    return HttpResponseRedirect('/profile')
                return HttpResponseRedirect(f'/player/{player.slug}')
            return HttpResponseNotFound
        claim_key = random.randint(10000000, 99999999)  # noqa: S311
        request.session['claim_key'] = claim_key  # see auth/views.py. yes, i'm stealing it, just without a form afterwards
        return render(request, 'claim_player.html', {'player': player, 'claim_key': claim_key})


def player_id(request, playerid):
    player = get_object_or_404(Player, id=playerid)
    return HttpResponseRedirect(player.get_absolute_url())


@login_required
def player_state(request, gameid, playerid, state):
    game = get_object_or_404(Game, id=gameid)
    player = get_object_or_404(Player, id=playerid)
    current_state = get_object_or_404(PlayerState, game=game, player=player)

    if not check_mod(request, game) or game.moderator == player:
        return HttpResponseNotFound

    if state == 'dead':
        current_state.set_dead()
        game.status_update(f'{player.name} died.')
    elif state == 'alive':
        current_state.set_alive()
    elif state == 'spectator':
        current_state.set_spectator()
    elif state == 'mod':
        current_state.set_moderator()
    else:
        return HttpResponseNotFound

    current_state.save()
    current_state.game.save()  # updated cached values

    return HttpResponse(simplejson.dumps({'success': True}))


def player_list(request):
    player_list = []
    try:
        for player in Player.objects.filter(name__icontains=request.GET['term']):
            player_list.append(player.name)
    except Player.DoesNotExist:
        pass  # noqa: WPS420

    return HttpResponse(simplejson.dumps(player_list), content_type='application/json')


@login_required
def add_player(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if request.method != 'POST' or not check_mod(request, game):
        return HttpResponseNotFound

    csrf_resp = {}
    csrf_resp.update(csrf(request))
    form = AddPlayerForm(request.POST)
    if form.is_valid():
        current_state, created = PlayerState.objects.get_or_create(player=form.player, game=game)
        if not current_state.moderator:
            current_state.set_alive()
            current_state.save()
            game.save()  # updated cached totals
        if created:
            messages.add_message(request, messages.SUCCESS, f'<strong>{form.player}</strong> was added to the game.')
        else:
            messages.add_message(request, messages.SUCCESS,
                                 f'<strong>{form.player}</strong> was already in the game, but they have been set to alive.')
    else:
        messages.add_message(request, messages.ERROR,
                             f'Unable to find a player named <strong>{form.data["name"]}</strong>.')

    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def add_faction(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if request.method != 'POST' or not check_mod(request, game):
        return HttpResponseNotFound
    csrf_resp = {}
    csrf_resp.update(csrf(request))
    form = AddFactionForm(request.POST)
    if form.is_valid():
        current_faction, created = GameFaction.objects.get_or_create(game=game, faction_name=form.cleaned_data['faction_name'], faction_type=form.cleaned_data['faction_type'])
        if created:
            messages.add_message(request, messages.SUCCESS, f'<strong>{current_faction.faction_name}</strong> was created!')
        else:
            messages.add_message(request, messages.ERROR, 'Something went wrong, and the faction could not be added.')
    else:
        messages.add_message(request, messages.ERROR, 'Invalid form submission, please review.')
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def delete_faction(request, factionid):
    faction = get_object_or_404(GameFaction, id=factionid)
    if not check_mod(request, faction.game):
        return HttpResponseNotFound
    faction.delete()
    return HttpResponseRedirect(faction.game.get_absolute_url())


@login_required
def delete_spectators(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if not check_mod(request, game):
        return HttpResponseNotFound

    for player in game.spectators():
        PlayerState.delete(player)

    messages.add_message(request, messages.SUCCESS, 'All spectators were deleted from the game.')
    return HttpResponseRedirect(game.get_absolute_url())


def votecount(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    try:
        votes = Vote.objects.select_related().filter(game=game, target=None, unvote=False, ignored=False, no_execute=False)
        if votes:
            players = sorted(game.all_players(), key=lambda player: player.player.name.lower())
            return render(request, 'unresolved.html',
                          {'game': game, 'votes': votes, 'players': players})
    except Vote.DoesNotExist:
        pass  # noqa: WPS420

    vc_formatter = VotecountFormatter.VotecountFormatter(game)
    vc_formatter.go()

    post_vc_button = bool(check_mod(request, game) and (game.last_vc_post is None or datetime.now() - game.last_vc_post >= timedelta(
        minutes=60) or (game.deadline and game.deadline - datetime.now() <= timedelta(minutes=60))))
    context = {'post_vc_button': post_vc_button,
               'html_votecount': vc_formatter.html_votecount,
               'bbcode_votecount': vc_formatter.bbcode_votecount}
    return render(request, 'votecount.html', context)


def resolve(request, voteid, resolution):
    vote = get_object_or_404(Vote, id=voteid)
    votes = Vote.objects.filter(game=vote.game, target_string__iexact=vote.target_string, target=None, unvote=False,
                                ignored=False)

    if resolution == '-1':
        vote.ignored = True
        vote.save()
    elif resolution == '-2':
        vote.no_execute = True
        vote.save()
    else:
        player = get_object_or_404(Player, id=int(resolution))
        for this_vote in votes:
            this_vote.target = player
            this_vote.save()

        alias, created = Alias.objects.get_or_create(player=player, alias=vote.target_string)
        if created:
            alias.save()

    key = f'{vote.game.slug}-vc-image'
    cache.delete(key)

    new_votes = Vote.objects.filter(game=vote.game, target_string__iexact=vote.target_string, target=None, unvote=False,
                                    ignored=False, no_execute=False)

    refresh = bool(len(votes) != 1 or not new_votes)
    return HttpResponse(simplejson.dumps({'success': True, 'refresh': refresh}))


def posts(request, gameid, page):
    game = get_object_or_404(Game, id=gameid)
    posts = game.posts.select_related().filter(page_number=page).order_by('id')
    page = int(page)
    gameday = game.days.select_related().last()
    context = {'game': game, 'posts': posts,
               'prevPage': page - 1, 'nextPage': page + 1, 'page': page,
               'pageNumbers': range(1, game.current_page + 1),
               'currentDay': gameday.day_number, 'nextDay': gameday.day_number + 1, 'moderator': check_mod(request, game)}
    return render(request, 'posts.html', context)


@login_required
def start_game(request, gameid, day):
    game = get_object_or_404(Game, id=gameid)
    if game.state != 'pregame' or not check_mod(request, game):
        return HttpResponseNotFound
    game.state = 'started'
    game.save()
    game.status_update('The game has started!')
    if day == '1':
        return new_day(request, gameid, day)
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def add_comment(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if request.method != 'POST' or not check_mod(request, game):
        return HttpResponseNotFound

    csrf_resp = {}
    csrf_resp.update(csrf(request))
    form = AddCommentForm(request.POST)
    if form.is_valid():
        comments = Comment.objects.filter(game=game)
        if comments:
            comments.delete()

        if len(form.cleaned_data['comment']) > 1:
            comment = Comment(comment=form.cleaned_data['comment'], player=request.user.profile.player, game=game)
            comment.save()
            game.status_update_noncritical(
                f'{request.user.profile.player} added a comment: {form.cleaned_data["comment"]}')

        messages.add_message(request, messages.SUCCESS, 'Your comment was added successfully.')
    else:
        messages.add_message(request, messages.ERROR, 'Unable to add your comment.  Was it empty?')
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def delete_comment(request, commentid):
    comment = get_object_or_404(Comment, id=commentid)
    if not check_mod(comment.game):
        return HttpResponseNotFound

    url = comment.game.get_absolute_url()
    Comment.delete(comment)
    messages.add_message(request, messages.SUCCESS, 'The comment was deleted successfully.')
    return HttpResponseRedirect(url)


@login_required
def deadline(request, gameid, month, day, year, hour, minute, ampm, tzname):
    game = get_object_or_404(Game, id=gameid)
    if game.state != 'started' or not check_mod(request, game):
        return HttpResponseNotFound

    hour = int(hour)
    if ampm == 'AM' and hour == 12:
        hour = hour - 12
    if ampm == 'PM' and hour < 12:
        hour = hour + 12

    prev_deadline = game.deadline
    dl = timezone(tzname).localize(datetime(int(year), int(month), int(day), int(hour), int(minute)))
    game.timezone = tzname
    game.deadline = dl.astimezone(timezone(settings.TIME_ZONE)).replace(tzinfo=None)
    game.save()

    if not prev_deadline:
        game.status_update_noncritical(
            f'A deadline has been set for {dl.strftime("%A, %B %d at %I:%M %p ") + dl.tzname()}.')  # noqa: WPS323 time formatting

    messages.add_message(request, messages.SUCCESS, 'The deadline was set successfully.')
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def close_game(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if request.method != 'POST' or not check_mod(request, game):
        return HttpResponseNotFound
    faction = None
    if int(request.POST.get('winning_faction')) > 0:
        faction = GameFaction.objects.get(id=request.POST.get('winning_faction'))
        faction.winning = True
        faction.save()
    game.state = 'closed'
    game.save()
    if faction is not None:
        game.status_update(f'The game is over. {faction.faction_name} has won.')
    else:
        game.status_update('The game is over.')

    messages.add_message(request, messages.SUCCESS,
                         'The game was <strong>closed</strong>!  Make sure to add it to the wiki!')

    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def reopen_game(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if game.state != 'closed' or not check_mod(request, game):
        return HttpResponseNotFound

    game.state = 'started'
    game.save()

    game.status_update('The game is re-opened!')

    messages.add_message(request, messages.SUCCESS, 'The game was <strong>re-opened</strong>!')

    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def new_day(request, gameid, day):
    game = get_object_or_404(Game, id=gameid)
    post = game.posts.all().order_by('-id')[:1][0]
    return start_day(request, day, post.id)


@login_required
def replace(request, gameid, clear, outgoing, incoming):
    game = get_object_or_404(Game, id=gameid)
    if game.state != 'started' or not check_mod(request, game):
        return HttpResponseNotFound

    player_out = get_object_or_404(Player, id=outgoing)
    try:
        player_in = Player.objects.get(name__iexact=urllib.parse.unquote(incoming))
    except Player.DoesNotExist:
        messages.add_message(request, messages.ERROR, f'No player by the name <strong>{incoming}</strong> was found!')
        return HttpResponseRedirect(game.get_absolute_url())

    clear_votes = bool(clear == 'true')

    try:
        player_state = PlayerState.objects.get(game=game, player=player_out)
    except PlayerState.DoesNotExist:
        messages.add_message(request, messages.ERROR, f'The player <strong>{player_out}</strong> is not in that game!')

    try:
        new_player_state = PlayerState.objects.get(game=game, player=player_in)
        if new_player_state.spectator:
            new_player_state.delete()
        else:
            messages.add_message(request, messages.ERROR,
                                 f'The player <strong>{player_in}</strong> is already in that game!')
            return HttpResponseRedirect(game.get_absolute_url())
    except PlayerState.DoesNotExist:
        pass  # noqa: WPS420

    player_state.player = player_in
    player_state.save()
    votes_affected = 0

    vote_list = game.votes.filter(Q(author=player_out) | Q(target=player_out))
    votes_affected = len(vote_list)

    if clear_votes:
        vote_list.delete()
    else:
        for vote in vote_list:
            if vote.author == player_out:
                vote.author = player_in
            else:
                vote.target = player_in
            vote.save()

    game.status_update_noncritical(f'{player_out} is replaced by {player_in}.')

    messages.add_message(request, messages.SUCCESS,
                         f'Success! <strong>{player_out}</strong> was replaced by <strong>{player_in}</strong>.  {votes_affected} votes were affected.')

    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def start_day(request, day, postid):
    post = get_object_or_404(Post, id=postid)
    if post.game.state != 'started' or not check_mod(request, post.game):
        return HttpResponseNotFound

    gameday, created = GameDay.objects.get_or_create(game=post.game, day_number=day, defaults={'start_post': post})
    if not created:
        gameday.start_post = post
    gameday.save()

    post.game.deadline = None
    post.game.save()

    post.game.status_update(f'Day {day} has begun!')

    messages.add_message(request, messages.SUCCESS,
                         f'Success! <strong>Day {gameday.day_number}</strong> will now begin with post ({post.post_id}) by {post.author}.')

    return HttpResponseRedirect(post.game.get_absolute_url())


@login_required
def templates(request):
    templates = VotecountTemplate.objects.filter(creator=request.user.profile.player)
    return render(request, 'templates.html', {'templates': templates})


@login_required
def create_template(request):
    if request.method == 'GET':
        try:
            system_default = VotecountTemplate.objects.get(system_default=True)
        except VotecountTemplate.DoesNotExist:
            system_default = VotecountTemplate()

        system_default.name = 'My New Template'
        return render(request, 'template_edit.html', {'form': VotecountTemplateForm(instance=system_default)})

    csrf_resp = {}
    csrf_resp.update(csrf(request))
    form = VotecountTemplateForm(request.POST)
    if form.is_valid():
        new_temp = form.save(commit=False)
        new_temp.creator = request.user.profile.player
        new_temp.save()

        messages.add_message(request, messages.SUCCESS,
                             f'Success! The template <strong>{new_temp.name}</strong> was saved.')
        return HttpResponseRedirect('/templates')
    return render(request, 'template_edit.html', {'form': form})


@login_required
def edit_template(request, templateid):
    old_temp = get_object_or_404(VotecountTemplate, id=templateid)
    if not request.user.is_superuser and old_temp.creator != request.user.profile.player:
        return HttpResponseNotFound

    if request.method == 'GET':
        return render(request, 'template_edit.html',
                      {'form': VotecountTemplateForm(instance=old_temp), 'template': old_temp, 'edit': True})

    csrf_resp = {}
    csrf_resp.update(csrf(request))
    form = VotecountTemplateForm(request.POST)
    if form.is_valid():
        new_temp = form.save(commit=False)
        new_temp.id = old_temp.id  # noqa: WPS125
        new_temp.creator = old_temp.creator
        new_temp.system_default = old_temp.system_default
        new_temp.save()

        if old_temp.shared and not new_temp.shared:
            player = request.user.profile.player
            for game in Game.objects.filter(template=new_temp):
                if not game.is_player_mod(player):
                    game.template = None
                    game.save()

        messages.add_message(request, messages.SUCCESS,
                             f'Success! The template <strong>{new_temp.name}</strong> was saved.')
        return HttpResponseRedirect('/templates')
    return render(request, 'template_edit.html', {'form': form, 'template': old_temp, 'edit': True})


@login_required
def delete_template(request, templateid):
    template = get_object_or_404(VotecountTemplate, id=templateid)
    if not request.user.is_superuser and template.creator != request.user.profile.player:
        return HttpResponseNotFound

    if template.system_default:
        messages.add_message(request, messages.ERROR,
                             '<strong>Error!</strong> You cannot delete the system default template.')
        return HttpResponseRedirect('/templates')

    for this_game in Game.objects.filter(template=template):
        this_game.template = None
        this_game.save()

    template.delete()

    messages.add_message(request, messages.SUCCESS, 'Template was deleted!')
    return HttpResponseRedirect('/templates')


@login_required
def game_template(request, gameid, templateid):
    game = get_object_or_404(Game, id=gameid)
    template = get_object_or_404(VotecountTemplate, id=templateid)
    if not check_mod(request, game):
        return HttpResponseNotFound

    game.template = None if template.system_default else template
    game.save()

    messages.add_message(request, messages.SUCCESS,
                         f'<strong>Success!</strong> This game now uses the template <strong>{template.name}</strong>.')
    return HttpResponseRedirect(game.get_absolute_url())


def active_games(request):
    game_list = Game.objects.select_related().filter(state='started').order_by('name')

    big_games = [this_game for this_game in game_list if this_game.is_big]
    mini_games = [this_game for this_game in game_list if this_game.is_big is False]

    return render(request, 'wiki_games.html',
                  {'big_games': big_games, 'mini_games': mini_games})


def active_games_style(request, style):
    if style in {'default', 'verbose'}:
        game_list = Game.objects.select_related().filter(state='started').order_by('name')
        big_games = [this_game for this_game in game_list if this_game.is_big]
        mini_games = [this_game for this_game in game_list if not this_game.is_big]

        return render(request, 'wiki_games.html', {'big_games': big_games, 'mini_games': mini_games, 'style': style})
    elif style == 'closedmonthly':
        game_list = Game.objects.select_related().filter(state='closed').order_by('name').annotate(last_post=Max('posts__timestamp')).order_by(
            '-last_post')
        game_list = [this_game for this_game in game_list if datetime.now() - this_game.last_post < timedelta(days=31)]

        return render(request, 'wiki_closed_games.html', {'game_list': game_list})
    return HttpResponse('Style not supported')


def active_games_json(request):
    game_list = sorted(({'name': game.name, 'mod': game.moderator.name,
                        'url': f'http://forums.somethingawful.com/showthread.php?threadid={game.thread_id}'} for game in
                       Game.objects.select_related().filter(state='started')), key=lambda game_name: game['name'])

    return HttpResponse(simplejson.dumps(game_list), content_type='application/json')


def closed_games(request):
    game_list = Game.objects.select_related().filter(state='closed').order_by('name').annotate(last_post=Max('posts__timestamp'), first_post=Min('posts__timestamp'))
    return render(request, 'closed.html', {'games': game_list, 'total': len(game_list)})


@login_required
def add_vote(request, gameid, player, votes, target):
    game = get_object_or_404(Game, id=gameid)
    if game.state != 'started' or not check_mod(request, game):
        return HttpResponseNotFound

    gameday = game.days.select_related().last()
    vote = Vote(manual=True, post=gameday.start_post, game=game)
    if player == '-1':
        vote.author = Player.objects.get(sa_uid=0)  # anonymous
    else:
        vote.author = get_object_or_404(Player, id=player)

    if votes == 'unvotes':
        vote.unvote = True
    else:
        vote.target = get_object_or_404(Player, id=target)

    vote.save()
    messages.add_message(request, messages.SUCCESS, 'Success! A new manual vote was saved.')
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def add_vote_global(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if game.state != 'started' or not check_mod(request, game):
        return HttpResponseNotFound

    gameday = game.days.select_related().last()
    playerlist = get_list_or_404(PlayerState, game=game)
    for indiv_player in playerlist:
        target = get_object_or_404(Player, id=indiv_player.player_id)
        vote = Vote(manual=True, post=gameday.start_post, game=game, author=Player.objects.get(sa_uid=0), target=target)
        vote.save()
    messages.add_message(request, messages.SUCCESS, 'Success! A global hated vote has been added.')
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def delete_vote(request, voteid):
    vote = get_object_or_404(Vote, id=voteid)
    game = vote.game
    if game.state != 'started' or not check_mod(request, game):
        return HttpResponseNotFound

    vote.delete()
    messages.add_message(request, messages.SUCCESS, 'Success!  The vote was deleted.')
    return HttpResponseRedirect(game.get_absolute_url())


def draw_wordwrap_text(draw, text, xpos, ypos, max_width, font):
    fill = (0, 0, 0, 255)
    used_width = 0
    max_width -= xpos
    space_width, space_height = draw.textsize(' ', font=font)

    text_size_x, text_size_y = draw.textsize(text, font=font)
    remaining = max_width
    output_text = []

    for word in text.split(None):
        word_width, word_height = draw.textsize(word, font=font)
        if word_width + space_width > remaining:
            output_text.append(word)
            remaining = max_width - word_width
        elif output_text:
            output = output_text.pop()
            output = f'{output} {word}'
            output_text.append(output)
            remaining = remaining - (word_width + space_width)
        else:
            output_text.append(word)
            remaining = remaining - (word_width + space_width)

    for text_element in output_text:
        cur_width, cur_height = draw.textsize(text_element, font=font)
        if (cur_width > used_width):
            used_width = cur_width

        draw.text((xpos, ypos), text_element, font=font, fill=fill)
        ypos += text_size_y

    return used_width + xpos, ypos


def draw_votecount_text(draw, vc, xpos, ypos, max_width, font, bold_font):
    votes_by_player = [voted_player for voted_player in vc.counted_votes if voted_player['count'] > 0]
    longest_name = 0
    divider_len_x, divider_len_y = draw.textsize(': ', font=font)
    max_x = 0
    if votes_by_player is None:  # No votes found
        text = 'No votes found in vc.counted_votes~'
        this_size_x, this_size_y = draw.textsize(text, font=bold_font)
        return draw_wordwrap_text(draw, text, 0, ypos, max_width, bold_font)
    for line in votes_by_player:
        text = f'{line["target"].name} ({line["count"]})'
        this_size_x, this_size_y = draw.textsize(text, font=bold_font)
        line['size'] = this_size_x
        if this_size_x > longest_name:
            longest_name = this_size_x

    for line_again in votes_by_player:  # noqa: WPS426
        pct = float(line_again['count']) / vc.toexecute
        box_width = min(pct * longest_name, longest_name)
        draw.rectangle([longest_name - box_width, ypos, longest_name, this_size_y + ypos],
                       fill=(int(155 + (pct * 100)), 100, 100, int(pct * 255)))

        text = f'{line_again["target"].name} ({line_again["count"]})'
        (x_size1, y_bottom1) = draw_wordwrap_text(draw, text, longest_name - line_again['size'], ypos, max_width, bold_font)

        (x_size2, y_bottom2) = draw_wordwrap_text(draw, ': ', x_size1, ypos, max_width, font)

        text = ', '.join(
            [vote['author'].name for vote in filter(lambda vote: vote['unvote'] is False and vote['enabled'], line_again['votes'])])
        (x_size3, y_bottom3) = draw_wordwrap_text(draw, text, x_size2 + divider_len_x, ypos, max_width, font)

        max_x = max(max_x, x_size3)
        ypos = max(y_bottom1, y_bottom2, y_bottom3)

    return (max_x, ypos)


def votecount_to_image(img, game, xpos=0, ypos=0, max_width=600):
    draw = ImageDraw.Draw(img)
    regular_font = ImageFont.truetype(settings.VF_REGULAR_FONT_PATH, 15)
    bold_font = ImageFont.truetype(settings.VF_BOLD_FONT_PATH, 15)

    # Reset game template to None to force use of the system default votecount template instead of whatever the game is actually set to
    game.template = None

    vc = VotecountFormatter.VotecountFormatter(game)
    vc.go(show_comment=False)

    split_vc = re.compile(r'\[.*?\]').sub('', vc.bbcode_votecount).split('\r\n')
    header_text = split_vc[0]  # Explicitly take the first and last elements in case of multiline templates
    footer_text = split_vc[-1]
    (header_x_size, header_y_size) = draw_wordwrap_text(draw, header_text, 0, 0, max_width, bold_font)
    draw.line([0, header_y_size - 2, header_x_size, header_y_size - 2], fill=(0, 0, 0, 255), width=2)
    ypos = 2 * header_y_size

    (vc_x_size, ypos) = draw_votecount_text(draw, vc, 0, ypos, max_width, regular_font, bold_font)
    ypos += header_y_size

    (x_size, ypos) = draw_wordwrap_text(draw, footer_text, 0, ypos, max_width, regular_font)

    votes = Vote.objects.select_related().filter(game=game, target=None, unvote=False, ignored=False, no_execute=False)
    if votes:
        ypos += header_y_size
        if len(votes) == 1:
            warning_text = 'Warning: There is currently 1 unresolved vote.  The votecount may be inaccurate.'
        else:
            warning_text = f'Warning: There are currently {len(votes)} unresolved votes.  The votecount may be inaccurate.'

        (warning_x, ypos) = draw_wordwrap_text(draw, warning_text, 0, ypos, max_width, bold_font)
        x_size = max(x_size, warning_x)

    return (max(header_x_size, vc_x_size, x_size), ypos)


def check_update_game(game):
    if game.is_locked():
        return game
    else:
        game.lock()

    try:
        if game.home_forum == 'sa':
            page_parser = SAPageParser.SAPageParser()
        elif game.home_forum == 'bnr':
            page_parser = BNRPageParser.BNRPageParser()
        new_game = page_parser.update(game)
        if new_game:
            return new_game
        game.save()
        return game
    except BaseException:
        return game


def votecount_image(request, slug):
    game = get_object_or_404(Game, slug=slug)

    key = f'{slug}-vc-image'
    img_dict = cache.get(key)

    if img_dict is None:
        game = check_update_game(game)
        img = Image.new('RGBA', (800, 1024), (255, 255, 255, 0))
        (width, height) = votecount_to_image(img, game, 0, 0, 800)
        img = img.crop((0, 0, width, height))
        cache.set(key, {'size': img.size, 'data': img.tobytes()}, 120)
    else:
        img = Image.frombytes('RGBA', img_dict['size'], img_dict['data'])

    response = HttpResponse(content_type='image/png')
    img.save(response, 'PNG')  # transparency=(255, 255, 255))
    return response


def autoupdate(request):
    games = Game.objects.exclude(state='closed').order_by('-last_updated')
    for game in games:
        key = f'{game.slug}-vc-image'
        cache.delete(key)  # image will regenerate on next GET
        game = check_update_game(game)
        post = game.posts.order_by('-timestamp')[:1][0]

        if datetime.now() - post.timestamp > timedelta(days=6) and game.state == 'started':
            game.status_update('Closed automatically for inactivity.')
            game.state = 'closed'
            game.save()
    return HttpResponse('Ok')


def players(request):
    return players_page(request, 1)


def players_page(request, page):
    items_per_page = 3000
    page = int(page)

    if page < 1:
        return HttpResponseRedirect('/players')

    first_record = (page - 1) * items_per_page

    total_players = Player.objects.all().count()
    total_pages = int(ceil(float(total_players) / items_per_page))
    players = Player.objects.select_related().filter(Q(sa_uid__gt='0') | Q(bnr_uid__gt='0')).order_by('name').extra(select={
        'alive': 'select count(*) from main_playerstate join main_game on main_playerstate.game_id=main_game.id where main_playerstate.player_id=main_player.id and main_game.state = "started" and main_playerstate.alive=true',
        'total_games_played': 'select count(*) from main_playerstate where main_playerstate.player_id=main_player.id and main_playerstate.moderator=false and main_playerstate.spectator=false',
        'total_games_run': 'select count(*) from main_game where main_game.moderator_id=main_player.id'})[
        first_record: first_record + items_per_page]

    if not players:
        return HttpResponseRedirect('/players')

    for player in players:
        if player.total_games_played > 0:
            player.posts_per_game = player.total_posts / (float(player.total_games_played))
        else:
            player.posts_per_game = 0

    return render(request, 'players.html',
                  {'players': players, 'page': page, 'total_pages': total_pages})


@login_required
def delete_alias(request, aliasid):
    alias = get_object_or_404(Alias, id=aliasid)
    if not request.user.is_superuser and request.user.profile.player != alias.player:
        return HttpResponseForbidden

    messages.add_message(request, messages.SUCCESS, f'The alias <strong>{alias.alias}</strong> was deleted.')
    player = alias.player
    alias.delete()

    return HttpResponseRedirect(f'/player/{player.slug}')


@login_required
def sendpms(request, slug):
    game = get_object_or_404(Game, slug=slug)
    if game.state != 'started' or not check_mod(request, game):
        return HttpResponseForbidden

    return render(request, 'sendpms.html', {'game': game})


def post_histories(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    return render(request, 'post_histories.html', {'game': game})


@login_required
def post_executions(request, gameid, enabled):
    game = get_object_or_404(Game, id=gameid)
    if not check_mod(request, game):
        return HttpResponseForbidden

    if enabled == 'on':
        game.post_executions = True
        messages.add_message(request, messages.SUCCESS, 'Posting of voted executes for this game is now enabled!')
    else:
        game.post_executions = False
        messages.add_message(request, messages.SUCCESS, 'Posting of voted executes for this game is now disabled!')

    game.save()
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def ecco_mode(request, gameid, enabled):
    game = get_object_or_404(Game, id=gameid)
    if not check_mod(request, game):
        return HttpResponseForbidden

    if enabled == 'on':
        game.ecco_mode = True
        messages.add_message(request, messages.SUCCESS, 'Ecco Mode has been enabled for this game!')
    else:
        game.ecco_mode = False
        messages.add_message(request, messages.SUCCESS, 'Ecco Mode has been disabled for this game!')

    game.save()
    return HttpResponseRedirect(game.get_absolute_url())


@login_required
def post_vc(request, gameid):
    game = get_object_or_404(Game, id=gameid)
    if game.state != 'started' or not check_mod(request, game):
        return HttpResponseForbidden

    if game.last_vc_post is not None and datetime.now() - game.last_vc_post < timedelta(minutes=60) and (game.deadline and game.deadline - datetime.now() > timedelta(minutes=60)):
        messages.add_message(request, messages.ERROR, 'Votefinder has posted too recently in that game.')
    else:
        game.last_vc_post = datetime.now()
        game.save()

        game = check_update_game(game)

        vc_formatter = VotecountFormatter.VotecountFormatter(game)
        vc_formatter.go()
        if game.home_forum == 'sa':
            dl = SAForumPageDownloader.SAForumPageDownloader()
        elif game.home_forum == 'bnr':
            dl = BNRApi.BNRApi()
        dl.reply_to_thread(game.thread_id, vc_formatter.bbcode_votecount)
        messages.add_message(request, messages.SUCCESS, 'Votecount posted.')

    return HttpResponseRedirect(game.get_absolute_url())


def votechart_all(request, gameslug):
    game = get_object_or_404(Game, slug=gameslug)
    day = GameDay.objects.get(game=game, day_number=game.current_day)
    required_votes_to_execute = int(math.floor(len(game.living_players()) / 2.0) + 1)

    vc = VoteCounter.VoteCounter()
    vc.run(game)
    vote_log = vc.get_votelog()

    return render(request, 'votechart.html',
                  {'game': game, 'showAllPlayers': True, 'startDate': day.start_post.timestamp,
                   'now': datetime.now(), 'toExecute': required_votes_to_execute,
                   'votes': vote_log, 'numVotes': len(vote_log),
                   'players': [player.player.name for player in game.living_players()],
                   'allPlayers': [player.player for player in game.living_players()]},
                  )


def votechart_player(request, gameslug, playerslug):
    game = get_object_or_404(Game, slug=gameslug)
    player = get_object_or_404(Player, slug=playerslug)
    day = GameDay.objects.get(game=game, day_number=game.current_day)
    required_votes_to_execute = int(math.floor(len(game.living_players()) / 2.0) + 1)

    vc = VoteCounter.VoteCounter()
    vc.run(game)
    vote_log = [vote for vote in vc.get_votelog() if vote['player'] == player.name]

    return render(request, 'votechart.html',
                  {'game': game, 'showAllPlayers': False, 'startDate': day.start_post.timestamp,
                   'now': datetime.now(), 'toExecute': required_votes_to_execute,
                   'votes': vote_log, 'numVotes': len(vote_log),
                   'allPlayers': [player.player for player in game.living_players()],
                   'selectedPlayer': player.name,
                   'players': [player.name]},
                  )


def dictfetchall(cursor):
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]


def gamechart(request):
    cursor = connections['default'].cursor()
    cursor.execute(
        'select cast(timestamp as date) as date, count(1)/count(distinct(game_id)) as activity, count(distinct(author_Id)) as posters, count(distinct(game_id)) as games, count(1) as posts from main_post group by date order by date')
    gamedata_by_date = dictfetchall(cursor)

    return render(request, 'gamechart.html',
                  {'data': gamedata_by_date, 'dataLen': len(gamedata_by_date)},
                  )


def common_games(request, slug_a, slug_b):
    player_a = get_object_or_404(Player, slug=slug_a)
    player_b = get_object_or_404(Player, slug=slug_b)
    games_a = [state.game for state in PlayerState.objects.filter(player=player_a) if not (state.moderator or state.spectator)]
    games_b = [state.game for state in PlayerState.objects.filter(player=player_b) if not (state.moderator or state.spectator)]
    common_games = [game for game in games_a if game in games_b]

    context = {
        'player_a': player_a,
        'player_b': player_b,
        'games': common_games,
    }

    return render(request, 'common_games.html', context)
