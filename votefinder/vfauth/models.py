import re
import urllib

from django import forms
from django.contrib.auth.models import User
from votefinder.main.BNRApi import BNRApi
from votefinder.main.SAForumPageDownloader import SAForumPageDownloader
from votefinder.main.models import Player, UserProfile


class CreateUserForm(forms.Form):
    login = forms.CharField(label='Username', min_length=3)
    email = forms.EmailField(label='Email')
    password = forms.CharField(widget=forms.PasswordInput, min_length=5,
                               label='New Password')
    confirm = forms.CharField(widget=forms.PasswordInput, min_length=5,
                              label='Confirm Password')

    def clean_login(self):
        login = self.cleaned_data['login']
        try:
            existing_user = User.objects.all().get(username=login)
            raise forms.ValidationError(f'A user by the name {existing_user.username} already exists.')
        except User.DoesNotExist:
            pass  # noqa: WPS420
        return login

    def clean_confirm(self):
        password1 = self.cleaned_data['password']
        password2 = self.cleaned_data['confirm']
        if password1 != password2:
            raise forms.ValidationError("The two password fields don't match.")
        return password2


class LinkProfileForm(forms.Form):
    login = forms.CharField(label='Username', min_length=3)
    home_forum = forms.ChoiceField(choices=[('sa', 'Something Awful'), ('bnr', 'Bread & Roses')])

    def clean_login(self):
        login = self.cleaned_data['login']
        home_forum = self.data['home_forum']

        if self.required_key:
            if home_forum == 'sa':
                downloader = SAForumPageDownloader()
                page_data = downloader.download(
                    f'https://forums.somethingawful.com/member.php?action=getinfo&username={urllib.parse.quote_plus(login)}')

                if page_data is None:
                    raise forms.ValidationError(f'There was a problem downloading the profile for the SA user {login}.')

                if page_data.find(str(self.required_key)) == -1:
                    raise forms.ValidationError(f"Unable to find the correct key ({self.required_key}) in {login}'s SA profile")
                else:
                    matcher = re.compile(r'userid=(?P<userid>\d+)').search(page_data)
                    if matcher:
                        self.userid = matcher.group('userid')
                        try:
                            existing_player = Player.objects.all().get(sa_uid=self.userid)
                            existing_userprofile = UserProfile.objects.all().get(player=existing_player)  # noqa: F841
                            raise forms.ValidationError(f'{existing_player.name} is already registered to a user profile. Do you have another Votefinder account?')
                        except Player.DoesNotExist:
                            pass  # noqa: WPS420
                        except UserProfile.DoesNotExist:
                            raise forms.ValidationError(f'Votefinder is already aware of {existing_player.name} as an unclaimed player profile. Claim it from their <a href="/player/{existing_player.slug}">profile page</a>.')
                        matcher = re.compile(r'\<dt class="author"\>(?P<login>.+?)\</dt\>').search(page_data)
                        if matcher:
                            login = matcher.group('login')
                    else:
                        raise forms.ValidationError(
                            f'Unable to find the userID of {login}.  Please talk to the site admin.')
            elif home_forum == 'bnr':
                api = BNRApi()
                user_profile = api.get_user_by_name(urllib.parse.quote_plus(login))
                if user_profile is None:
                    raise forms.ValidationError(f'There was a problem downloading the profile for the BNR user {login}.')
                if user_profile['location'] == str(self.required_key):
                    if user_profile['user_id']:
                        self.userid = user_profile['user_id']
                        try:
                            existing_player = Player.objects.all().get(bnr_uid=self.userid)
                            raise forms.ValidationError(f'{existing_player.name} is already registered with that user ID. Has your forum name changed?')
                        except Player.DoesNotExist:
                            pass  # noqa: WPS420
                        login = user_profile['username']
                    else:
                        raise forms.ValidationError(
                            f'Unable to find the userID of {login}.  Please talk to the site admin.')
                else:
                    raise forms.ValidationError(f"Unable to find the correct key ({self.required_key}) in {login}'s BNR profile")

        return login
