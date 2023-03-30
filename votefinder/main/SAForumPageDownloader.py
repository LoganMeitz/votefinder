import re

import requests

from bs4 import BeautifulSoup
from django.conf import settings
from votefinder.main.models import Game


class SAForumPageDownloader():
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        # we must set this, SA blocks the default UA

    def download(self, page):
        page_data = self.perform_download(page)

        if page_data is None:
            return None
        elif not self.needs_to_login(page_data):
            return page_data
        elif self.login_to_forum():
            page_data = self.perform_download(page)

            if not self.needs_to_login(page_data):
                return page_data
            return None
        return None

    def log_login_attempt(self):
        game = Game.objects.get(id=228)
        game.status_update('Trying to re-login to forums.  PM Alli if this happens a lot.')

    def login_to_forum(self):
        page_text = ''

        self.log_login_attempt()

        page_request = self.session.post('https://forums.somethingawful.com/account.php',
                                         data={'action': 'login', 'username': settings.VF_SA_USER,
                                               'password': settings.VF_SA_PASS, 'secure_login': ''})
        page_text = page_request.text

        if self.is_logged_in_correctly(page_text):
            return True
        return False

    def needs_to_login(self, page_data):
        if re.search(re.compile(r'\*\*\* LOG IN \*\*\*'), page_data) is None:
            return False
        return True

    def is_logged_in_correctly(self, page_data):
        if not page_data:
            raise ValueError('Login failed, no data in response from login attempt')
        if re.search(re.compile(r'Login with username and password'), page_data) is None:
            return True
        return False

    def perform_download(self, page):
        try:
            page_request = self.session.get(page)
            return page_request.text
        except BaseException:
            return None

    def reply_to_thread(self, thread, message):
        get_url = 'https://forums.somethingawful.com/newreply.php?action=newreply&threadid={}'.format(thread)
        post_url = 'https://forums.somethingawful.com/newreply.php?action=newreply'

        page_data = self.download(get_url)
        if page_data is None:
            return False  # Could not retrieve anything from the page.

        soup = BeautifulSoup(page_data, 'html.parser')

        inputs = {'message': message}
        for input_element in soup.find_all('input', {'value': True}):
            inputs[input_element['name']] = input_element['value']

        if not inputs['disablesmilies']:
            return False  # Thread is locked.
        inputs.pop('disablesmilies')
        inputs.pop('preview')

        self.session.post(post_url, data=inputs)


if __name__ == '__main__':
    dl = SAForumPageDownloader()
    result = dl.download('https://forums.somethingawful.com/showthread.php?threadid=3552086')  # noqa: WPS110
