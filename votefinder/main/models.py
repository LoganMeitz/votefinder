import re
from datetime import datetime, timedelta
from enum import Enum

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.forms import ModelForm
from django.template.defaultfilters import slugify

DETAIL_LEVEL_CHOICES = (
    (1, 'Brief'),
    (2, 'Medium'),
    (3, 'Detailed'),
)


def get_root_user():
    return User.objects.get_or_create(username='root')[0]


def get_default_player():
    return Player.objects.get_or_create(name='votefinder')[0]


def slugify_uniquely(potential_slug, model, slugfield='slug'):
    suffix = 1
    maximum_slug_length = 45
    actual_slug = slugify(potential_slug)[:maximum_slug_length]
    base = slugify(potential_slug)[:maximum_slug_length]
    while True:
        if suffix > 1:
            actual_slug = '-'.join([base, str(suffix)])
        if not model.objects.filter(**{slugfield: actual_slug}).count():
            return actual_slug
        suffix += 1


class Player(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    sa_uid = models.IntegerField(unique=True, db_index=True, null=True)
    bnr_uid = models.IntegerField(unique=True, null=True, db_index=True)
    slug = models.SlugField()
    last_post = models.DateTimeField(null=True, blank=True)
    total_posts = models.IntegerField(default=0)

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        return '/player/{}'.format(self.slug)

    def save(self, *args, **kwargs):
        if not self.id:
            self.slug = slugify_uniquely(self.name, self.__class__)
        super().save(*args, **kwargs)

    def current_games(self):
        return PlayerState.objects.filter(player=self, spectator=False, game__state='started')

    def closed_games(self):
        return PlayerState.objects.filter(player=self, game__state='closed')

    def pronouns(self):
        return UserProfile.objects.get(player=self).pronouns


class VotecountTemplate(models.Model):
    creator = models.ForeignKey(Player, editable=False, on_delete=models.SET(get_default_player))
    name = models.CharField(max_length=256)
    shared = models.BooleanField(default=False)
    system_default = models.BooleanField(editable=False, default=False)

    overall = models.TextField()
    single_line = models.CharField(max_length=256)
    deadline_exists = models.CharField(max_length=256)
    deadline_not_set = models.CharField(max_length=256)
    before_vote = models.CharField(max_length=256, blank=True)
    after_vote = models.CharField(max_length=256, blank=True)
    before_unvote = models.CharField(max_length=256, blank=True)
    after_unvote = models.CharField(max_length=256, blank=True)
    before_unvoted_vote = models.CharField(max_length=256, blank=True)
    after_unvoted_vote = models.CharField(max_length=256, blank=True)
    detail_level = models.IntegerField(choices=DETAIL_LEVEL_CHOICES, default=3)
    hide_zero_votes = models.BooleanField(default=False)
    full_tick = models.CharField(max_length=256, default='https://{}/t.png'.format(settings.VF_PRIMARY_DOMAIN))
    empty_tick = models.CharField(max_length=256, default='https://{}/te.png'.format(settings.VF_PRIMARY_DOMAIN))

    def __str__(self):
        if self.system_default:
            return 'DEFAULT: {} [by {}]'.format(self.name, self.creator)
        elif self.shared:
            return 'SHARED: {} [by {}]'.format(self.name, self.creator)
        return '{} [by {}]'.format(self.name, self.creator)


class Game(models.Model):
    name = models.CharField(max_length=255)
    thread_id = models.IntegerField(db_index=True)
    moderator = models.ForeignKey(Player, related_name='moderatingGames', on_delete=models.SET(get_default_player))
    last_updated = models.DateTimeField(auto_now=True)
    max_pages = models.IntegerField()
    current_page = models.IntegerField()
    slug = models.SlugField()
    locked_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=32)
    deadline = models.DateTimeField(null=True, blank=True)
    template = models.ForeignKey(VotecountTemplate, null=True, blank=True, on_delete=models.SET_DEFAULT, default=2)
    added_by = models.ForeignKey(User, on_delete=models.SET(get_root_user))
    timezone = models.CharField(max_length=128, default='US/Eastern')
    post_executions = models.BooleanField(default=False)
    ecco_mode = models.BooleanField(default=False)
    last_vc_post = models.DateTimeField(null=True, blank=True)
    is_big = models.BooleanField(default=False)
    current_day = models.IntegerField(default=0)
    living_count = models.IntegerField(default=0)
    players_count = models.IntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True, blank=True)
    home_forum = models.CharField(max_length=10, default='sa')

    def update_counts(self):
        self.players_count = self.count_players()
        self.living_count = len(self.living_players())
        self.is_big = bool(self.players_count > 16)

        days = self.days.order_by('-id')
        if days:
            self.current_day = days[0].day_number

    def status_update(self, message):
        self.status_update_noncritical(message)

    def status_update_noncritical(self, message):
        status_update = GameStatusUpdate(game=self, message=message)
        status_update.save()

    def is_locked(self):
        if self.locked_at is None or datetime.now() - self.locked_at > timedelta(minutes=1):
            return False
        return True

    def lock(self, *args, **kwargs):
        self.locked_at = datetime.now()
        super().save(*args, **kwargs)  # noqa: WPS613

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.id:
            filtered_name = re.compile(r'[:\.-].+').sub('', self.name.lower())
            filtered_name = filtered_name.replace('mini-mafia', '')
            filtered_name = filtered_name.replace('mafia', '')
            filtered_name = filtered_name.replace('mini', '')
            if filtered_name.strip() == '':
                self.slug = slugify_uniquely(self.name.strip(), self.__class__)
            else:
                self.slug = slugify_uniquely(filtered_name.strip(), self.__class__)
        self.locked_at = None
        self.update_counts()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return '/game/{}'.format(self.slug)

    def count_players(self):
        return self.players.filter(spectator=False, moderator=False).count()

    def all_players(self):
        return sorted(self.players.select_related().filter(spectator=False, moderator=False),
                      key=lambda player: player.player.name.lower())

    def living_players(self):
        return sorted(self.players.select_related().filter(alive=True), key=lambda player: player.player.name.lower())

    def dead_players(self):
        return sorted(self.players.select_related().filter(alive=False, moderator=False, spectator=False),
                      key=lambda player: player.player.name.lower())

    def spectators(self):
        return sorted(self.players.select_related().filter(spectator=True), key=lambda player: player.player.name.lower())

    def moderators(self):
        return sorted(self.players.select_related().filter(moderator=True), key=lambda player: player.player.name.lower())

    def is_player_mod(self, player):
        try:
            user_state = PlayerState.objects.get(game=self, player=player)
            if user_state.moderator:
                return True
        except PlayerState.DoesNotExist:
            pass  # noqa: WPS420
        return False

    def is_user_mod(self, user):
        if user.is_superuser:
            return True
        elif user.is_authenticated:
            return self.is_player_mod(user.profile.player)
        return False

    def winning_faction(self):
        return self.factions.get(winning=True)

    class Meta:
        unique_together = ('thread_id', 'home_forum')


class FactionType(Enum):
    town = 'Town'
    scum = 'Scum'
    third = 'Third Party'
    cult = 'Cult'


class GameFaction(models.Model):
    game = models.ForeignKey(Game, related_name='factions', on_delete=models.CASCADE)
    faction_name = models.CharField(max_length=255)
    faction_type = models.CharField(max_length=5, choices=[(faction, faction.value) for faction in FactionType])
    winning = models.BooleanField(default=False)


class Comment(models.Model):
    player = models.ForeignKey(Player, on_delete=models.SET(get_root_user))
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    comment = models.CharField(max_length=4096, blank=True, null=True)

    def __str__(self):
        return '{}: {}'.format(self.player, self.comment[:100])


class PlayerState(models.Model):
    game = models.ForeignKey(Game, related_name='players', on_delete=models.CASCADE)
    player = models.ForeignKey(Player, related_name='games', on_delete=models.CASCADE)
    spectator = models.BooleanField(default=False)
    alive = models.BooleanField(default=False)
    moderator = models.BooleanField(default=False)
    faction = models.ManyToManyField(GameFaction)

    def set_moderator(self):
        self.spectator = False
        self.moderator = True
        self.alive = False

    def set_alive(self):
        self.spectator = False
        self.moderator = False
        self.alive = True

    def set_dead(self):
        self.spectator = False
        self.moderator = False
        self.alive = False

    def set_spectator(self):
        self.spectator = True
        self.moderator = False
        self.alive = False

    def state(self):
        if self.moderator:
            return 'Moderator'
        elif self.spectator:
            return 'Spectator'
        elif self.alive:
            return 'Alive'
        return 'Dead'

    def __str__(self):
        return '{} [{}]'.format(self.player, self.state())

    class Meta:
        unique_together = ('game', 'player')


class Alias(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    alias = models.CharField(max_length=255)

    def __str__(self):
        return self.alias

    class Meta:  # noqa: WPS306
        verbose_name_plural = 'Aliases'


class Post(models.Model):
    post_id = models.IntegerField(db_index=True)
    timestamp = models.DateTimeField()
    author = models.ForeignKey(Player, related_name='posts', on_delete=models.SET(get_default_player))
    author_search = models.CharField(max_length=256)
    body = models.TextField()
    avatar = models.CharField(max_length=256, null=True)
    page_number = models.IntegerField()
    game = models.ForeignKey(Game, related_name='posts', on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['post_id', 'game'], name='unique_postid_game'),
        ]

    def __str__(self):
        return '{} at {}'.format(self.author.name, self.timestamp)


class Vote(models.Model):
    post = models.ForeignKey(Post, related_name='votes', db_index=True, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, related_name='votes', db_index=True, on_delete=models.CASCADE)
    author = models.ForeignKey(Player, related_name='votes', on_delete=models.CASCADE)
    target = models.ForeignKey(Player, related_name='target_of_votes', null=True, on_delete=models.CASCADE)
    target_string = models.CharField(max_length=256)
    unvote = models.BooleanField(default=False)
    ignored = models.BooleanField(default=False)
    manual = models.BooleanField(default=False)
    no_execute = models.BooleanField(default=False)

    def __str__(self):
        if self.unvote:
            return '{} unvotes'.format(self.author)
        return '{} votes {}'.format(self.author, self.target_string)


class GameStatusUpdate(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    message = models.CharField(max_length=1024)
    url = models.CharField(max_length=255)

    def save(self, *args, **kwargs):
        if not self.id:
            if self.game.home_forum == 'sa':
                post_url = 'https://forums.somethingawful.com/showthread.php?goto=post&postid={}'.format(self.game.posts.all().order_by('-id')[0].post_id)
            elif self.game.home_forum == 'bnr':
                post_url = 'https://breadnroses.net/threads/{}/post-{}'.format(self.game.thread_id, self.game.posts.all().order_by('-id')[0].post_id)
            try:
                if url is None:
                    self.url = post_url
                else:
                    self.url = url
            except NameError:
                self.url = post_url

        super().save(*args, **kwargs)


class BlogPost(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return '/'


class Theme(models.Model):
    name = models.CharField(max_length=10, default='default')

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE)
    user = models.OneToOneField(User, related_name='profile', on_delete=models.CASCADE)
    registered = models.DateTimeField(auto_now_add=True)
    theme = models.ForeignKey(Theme, on_delete=models.SET_DEFAULT, default=1)
    pronouns = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.player.name


class GameDay(models.Model):
    game = models.ForeignKey(Game, related_name='days', db_index=True, on_delete=models.CASCADE)
    day_number = models.IntegerField(default=1)
    start_post = models.ForeignKey(Post, on_delete=models.CASCADE)
    notified = models.BooleanField(default=False)

    def __str__(self):
        return 'Day {} of {}'.format(self.day_number, self.game)


class CookieStore(models.Model):
    cookie = models.TextField()


class AddPlayerForm(forms.Form):
    name = forms.CharField()
    forum = forms.CharField()

    def clean_name(self):
        name = self.cleaned_data['name']
        forum = self.data.get('forum')
        try:
            if forum == 'sa':
                self.player = Player.objects.filter(sa_uid__isnull=False).get(name=name)
            elif forum == 'bnr':
                self.player = Player.objects.filter(bnr_uid__isnull=False).get(name=name)
        except Player.DoesNotExist:
            raise forms.ValidationError('No player by that name.')

        return self.player.name


class AddFactionForm(forms.Form):
    choices = (
        ('town', 'Town'),
        ('scum', 'Scum'),
        ('third', 'Third Party'),
        ('cult', 'Cult'),
    )
    faction_name = forms.CharField()
    faction_type = forms.ChoiceField(choices=choices)


class AddCommentForm(forms.Form):
    comment = forms.CharField(widget=forms.widgets.Textarea(), required=False)


class VotecountTemplateForm(ModelForm):
    class Meta:
        model = VotecountTemplate
        fields = '__all__'


class ExecutionMessage(models.Model):
    text = models.CharField(max_length=512)

    def __str__(self):
        return self.text
