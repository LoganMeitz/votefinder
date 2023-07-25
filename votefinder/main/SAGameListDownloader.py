import re

from bs4 import BeautifulSoup
from votefinder.main.models import Game

from votefinder.main import SAForumPageDownloader


class SAGameListDownloader():
    def __init__(self):
        self.GameList = []
        self.downloader = SAForumPageDownloader.SAForumPageDownloader()

    def get_game_list(self, page):
        game_raw_html = self.download_list(page)
        if not game_raw_html:
            return False

        if not self.parse_game_list(game_raw_html):
            return False

        return True

    def download_list(self, page):
        return self.downloader.download(
            f'https://forums.somethingawful.com/forumdisplay.php?forumid=103&pagenumber={page}')

    def parse_game_list(self, game_raw_html):
        soup = BeautifulSoup(game_raw_html, 'html.parser')

        for thread in soup.find_all('a', 'thread_title'):
            if thread.text.lower().find('mafia') != -1:
                matcher = re.compile(r'threadid=(?P<threadid>\d+)').search(thread['href'])
                thread_id = matcher.group('threadid')
                game = {'name': thread.text, 'url': thread['href'], 'threadid': thread_id, 'home_forum': 'sa', 'tracked': self.is_game_tracked(thread_id)}
                self.GameList.append(game)

        return True

    def is_game_tracked(self, thread_id):
        try:
            Game.objects.all().get(thread_id=thread_id)
            return True
        except Game.DoesNotExist:
            pass  # noqa: WPS420

        return False
