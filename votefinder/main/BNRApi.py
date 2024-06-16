import requests

import simplejson as json
from django.conf import settings


class BNRApi():
    def __init__(self):
        if not settings.VF_BNR_API_KEY:
            raise BNRApiKeyError
        self.session = requests.Session()
        self.api_key = settings.VF_BNR_API_KEY
        self.session.headers.update({'XF-API-Key': self.api_key})
        # review if necessary

    def download(self, page):
        page_data = self.perform_download(page)
        if page_data is None:
            return None
        return page_data

    def get_thread(self, threadid, page=1):
        thread = self.session.get(f'https://breadnroses.net/api/threads/{threadid}?with_posts=true&page={page}')
        return json.loads(thread.text)

    def get_games(self, page=1):
        games = self.session.get(f'https://breadnroses.net/api/forums/35?with_threads=true&page={page}')
        return json.loads(games.text)

    def perform_download(self, page):
        try:
            page_request = self.session.get(page)
            return page_request.text
        except BaseException:
            return None

    def reply_to_thread(self, thread, message):  # TODO
        post_url = 'https://breadnroses.net/api/posts/'

        inputs = {'thread_id': thread, 'message': message}

        self.session.post(post_url, data=inputs)

    def get_user_by_name(self, username):
        user = self.session.get(f'https://breadnroses.net/api/users/find-name?username={username}')
        users = json.loads(user.text)
        return users['exact']

    def get_user_by_id(self, uid):
        user = self.session.get(f'https://breadnroses.net/api/users/{uid}')
        user_json = json.loads(user.text)
        return user_json['user']

class BNRApiKeyError(Exception):
    def __init__(self):
        self.message = "You're missing the BNR API key in your .env file."
    
    def __str__(self):
        return self.message

if __name__ == '__main__':
    dl = BNRApi()
    result = dl.get_thread(1012)  # noqa: WPS110
