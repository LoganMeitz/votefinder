from django.conf import settings
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.utils.feedgenerator import Atom1Feed
from votefinder.main.models import BlogPost, Game, GameStatusUpdate


class LatestRss(Feed):
    title = 'Votefinder Updates'
    link = f'https://{settings.VF_PRIMARY_DOMAIN}/'
    author_name = 'Votefinder Team'
    feed_url = f'{link}rss'
    description = 'Changes and updates to the Votefinder site.'
    guid = '/'

    def items(self):  # noqa: WPS110
        return BlogPost.objects.all().order_by('-timestamp')[:5]

    def item_title(self, item):  # noqa: WPS110
        return item.title

    def item_description(self, item):  # noqa: WPS110
        return item.text

    def item_link(self, item):  # noqa: WPS110
        return f'https://{settings.VF_PRIMARY_DOMAIN}/'

    def item_pubdate(self, item):  # noqa: WPS110
        return item.timestamp


class LatestAtom(LatestRss):
    feed_type = Atom1Feed
    subtitle = LatestRss.description


class GameStatusRss(Feed):
    title = 'Votefinder Game Status Updates'
    link = f'https://{settings.VF_PRIMARY_DOMAIN}/'
    author_name = 'Votefinder Team'
    feed_url = f'{link}game_status'
    description = 'Game status updates for games tracked by Votefinder.'
    guid = '/'

    def items(self):  # noqa: WPS110
        return GameStatusUpdate.objects.all().order_by('-id')[:5]

    def item_title(self, item):  # noqa: WPS110
        if item.game:
            return f'[{item.game.name}] {item.message}'
        return item.message

    def item_description(self, item):  # noqa: WPS110
        return item.message

    def item_link(self, item):  # noqa: WPS110
        return item.url

    def item_pubdate(self, item):  # noqa: WPS110
        return item.timestamp


class GameStatusAtom(GameStatusRss):
    feed_type = Atom1Feed
    subtitle = GameStatusRss.description


class SpecificGameStatusRss(Feed):
    title = 'Votefinder Game Status Updates'
    link = f'https://{settings.VF_PRIMARY_DOMAIN}/'
    author_name = 'Votefinder Team'
    feed_url = '{}game_status'.format(link)
    description = 'Game status updates for games tracked by Votefinder.'
    guid = '/'
    game = None

    def get_object(self, request, slug):
        self.game = get_object_or_404(Game, slug=slug)
        return self.game

    def items(self):  # noqa: WPS110
        return GameStatusUpdate.objects.filter(game=self.game).order_by('-id')[:5]

    def item_title(self, item):  # noqa: WPS110
        if item.game:
            return '[{}] {}'.format(item.game.name, item.message)
        return item.message

    def item_description(self, item):  # noqa: WPS110
        return item.message

    def item_link(self, item):  # noqa: WPS110
        return item.url

    def item_pubdate(self, item):  # noqa: WPS110
        return item.timestamp


class SpecificGameStatusAtom(SpecificGameStatusRss):
    feed_type = Atom1Feed
    subtitle = GameStatusRss.description
