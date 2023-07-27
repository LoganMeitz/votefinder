import re
import bbcode
from datetime import datetime

from bs4 import BeautifulSoup
from votefinder.main.models import (Game, GameDay, Player, PlayerState,
                                    Post)

from votefinder.main import BNRApi, PostParser


class BNRPageParser:
    def __init__(self):
        self.pageNumber = 0
        self.maxPages = 0
        self.gameName = ''
        self.posts = []
        self.players = []
        self.gamePlayers = []
        self.votes = []
        self.user = None
        self.api = BNRApi.BNRApi()

    def add_game(self, threadid, state):
        self.new_game = True
        self.state = state
        return self.download_and_update(threadid)

    def download_and_update(self, threadid, page=1):
        thread = self.api.get_thread(threadid, page)

        game = self.parse_page(thread, threadid)
        if not game:
            return None

        return game

    def update(self, game):
        self.new_game = False
        page = game.current_page
        if game.current_page < game.max_pages:
            page = game.current_page + 1

        return self.download_and_update(game.thread_id, page)

    def parse_page(self, thread, threadid):
        self.pageNumber = thread['pagination']['current_page']
        self.maxPages = thread['pagination']['last_page']
        self.gameName = re.compile(r'\[.*?\]').sub('', thread['thread']['title']).strip()

        posts = thread['posts']
        if not posts:
            return None

        mod = None
        for post_node in posts:
            new_post = self.read_post_values(post_node)  # TODO
            if new_post:
                if not mod:
                    mod = new_post.author

                new_post.page_number = self.pageNumber
                self.posts.append(new_post)
        if self.new_game and self.state == 'pregame':
            day_number = 0
        else:
            day_number = 1
            self.state = 'started'

        game, game_created = Game.objects.get_or_create(thread_id=threadid,
                                                        defaults={'moderator': mod, 'name': self.gameName,
                                                                  'current_page': 1, 'max_pages': 1, 'state': self.state,
                                                                  'added_by': self.user, 'current_day': day_number, 'home_forum': 'bnr'})

        if game_created:
            player_state, created = PlayerState.objects.get_or_create(game=game, player=mod,
                                                                      defaults={'moderator': True})
        else:
            self.gamePlayers = [player.player for player in game.all_players()]

        game.max_pages = self.maxPages
        game.current_page = self.pageNumber
        game.name = self.gameName
        post_parser = PostParser.PostParser()
        for post in self.posts:
            post.game = game
            post.save()
            post_parser.read_votes(post, self.gamePlayers, self.players)
            if post.author not in self.players:
                self.players.append(post.author)
            cur_player = post.author
            cur_player.last_post = datetime.now()
            cur_player.total_posts += 1
            cur_player.save()

        if self.new_game or game.state == 'pregame':
            default_state = 'alive'
        else:
            default_state = 'spectator'

        for player in self.players:
            player_state, created = PlayerState.objects.get_or_create(game=game, player=player,
                                                                      defaults={default_state: True})

        if game_created:
            gameday = GameDay(game=game, day_number=day_number, start_post=self.posts[0])
            gameday.save()

        game.save()
        return game

    def find_or_create_player(self, playername, playeruid):
        player, created = Player.objects.get_or_create(bnr_uid=playeruid,
                                                       defaults={'name': playername})

        if player.name != playername:
            player.name = playername
            player.save()

        return player

    def read_post_values(self, node):
        post_id = node['post_id']
        if post_id == '':
            return None

        try:
            post = Post.objects.get(post_id=post_id, game__home_forum='bnr')
            return None
        except Post.DoesNotExist:
            post = Post()

        post.post_id = post_id
        post.avatar = node['User']['avatar_urls']['o']

        body = node['message']
        bbcode_parser = bbcode.Parser()
        bbcode_parser.add_simple_formatter('user', '%(value)s')  # noqa: WPS323 this is as per the bbcode_parser docs
        bbcode_parser.add_simple_formatter('img', '<img src="%(value)s" />', replace_links=False)  # noqa: WPS323 this is as per the bbcode_parser docs
        post.bodySoup = BeautifulSoup(bbcode_parser.format(body))
        for quote in post.bodySoup.findAll('blockquote'):
            quote.name = 'div'
            quote['class'] = 'quote well'
        [img.replaceWith(f'<div class="embedded-image not-loaded" data-image="{img["src"]}">Click to load image...</div>') for img in post.bodySoup.find_all('img')]  # noqa: WPS428 false positive
        post.body = post.bodySoup.prettify(formatter=None)
        post.timestamp = datetime.fromtimestamp(node['post_date'])

        author_string = node['User']['username']
        author_string = re.sub(r'<.*?>', '', author_string)
        author_string = re.sub(r'&\w+?;', '', author_string).strip()
        author_uid = node['User']['user_id']

        post.author = self.find_or_create_player(author_string, author_uid)

        return post
