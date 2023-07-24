from votefinder.main.models import Game

from votefinder.main import BNRApi


class BNRGameListDownloader():
    def __init__(self):
        self.GameList = []
        self.downloader = BNRApi.BNRApi()

    def get_game_list(self, page):
        forum_page = self.download_list(page)
        if not forum_page:
            return False

        if not self.parse_game_list(forum_page):
            return False

        return True

    def download_list(self, page):
        return self.downloader.get_games(page)

    def parse_game_list(self, forum_page):
        threads = forum_page['threads']
        for thread in threads:
            thread_title = thread['title']
            if thread_title.lower().find('mafia') != -1 and thread_title.lower().find('werewolf') != 1:
                game = {'name': thread_title, 'url': f'https://breadnroses.net/threads/{thread["thread_id"]}', 'home_forum': 'bnr', 'threadid': thread['thread_id'], 'tracked': self.is_game_tracked(thread['thread_id'])}
                self.GameList.append(game)

        return True

    def is_game_tracked(self, threadid):
        try:
            Game.objects.all().get(thread_id=threadid)
            return True
        except Game.DoesNotExist:
            pass  # noqa: WPS420

        return False
