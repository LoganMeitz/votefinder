import math
import re
from datetime import datetime

from pytz import timezone

from django.conf import settings
from django.utils.dateformat import format
from django.utils.timesince import timeuntil
from votefinder.main.models import Comment, VotecountTemplate

from votefinder.main import VoteCounter


class VotecountFormatter:
    def __init__(self, game):
        self.empty_tick = ''
        self.tick = ''

        self.vc = VoteCounter.VoteCounter()
        self.game = game

    def go(self, show_comment=True):
        self.counted_votes = self.vc.run(self.game)

        game_template = self.game.template
        if game_template is None:
            game_template = VotecountTemplate.objects.get(system_default=True)

        gameday = self.game.days.select_related().last()
        living_players = [ps.player for ps in self.game.living_players()]
        alive = len(living_players)
        if self.game.deadline:
            tz = timezone(self.game.timezone)
            dl = timezone(settings.TIME_ZONE).localize(self.game.deadline).astimezone(tz)
            deadline = format(dl, r'F dS, Y \a\t P ') + dl.tzname()
            until_deadline = timeuntil(self.game.deadline, datetime.now())
            until_deadline = until_deadline.replace('\u00A0', ' ')
        else:
            deadline = ''
            until_deadline = ''

        self.toexecute = self.to_execute(alive)
        detail_level = game_template.detail_level
        self.tick = game_template.full_tick
        self.empty_tick = game_template.empty_tick
        comments = Comment.objects.filter(game=self.game).order_by('-timestamp') if show_comment else ''

        votecount_lines = []
        for votecount_by_player in self.counted_votes:
            if votecount_by_player['count'] == 0 and game_template.hide_zero_votes:
                continue

            if votecount_by_player['votes']:
                votelist = []
                for vote in votecount_by_player['votes']:
                    thisvote = None
                    if vote['unvote']:
                        if detail_level == 3:
                            thisvote = ''.join(
                                [game_template.before_unvote, str(vote['author'].name), game_template.after_unvote])
                    elif vote['enabled']:
                        thisvote = ''.join([game_template.before_vote, str(vote['author'].name), game_template.after_vote])
                    elif detail_level >= 2:
                        thisvote = ''.join(
                            [game_template.before_unvoted_vote, str(vote['author'].name), game_template.after_unvoted_vote])

                    if thisvote:
                        votelist.append(thisvote.replace('{{url}}', vote['url']))

                if votelist:
                    this_line = game_template.single_line.replace('{{target}}', str(votecount_by_player['target'].name)).replace(
                        '{{count}}', str(votecount_by_player['count'])).replace('{{votelist}}', ', '.join(votelist))
                    votecount_lines.append(
                        this_line.replace('{{ticks}}', self.build_ticks(votecount_by_player['count'], self.toexecute)))

        self.not_voting_list = sorted(
            filter(lambda player: self.vc.currentVote[player] is None and player in living_players, self.vc.currentVote),
            key=lambda player: player.name.lower())
        temp_not_voting = game_template.single_line.replace('{{target}}', 'Not Voting').replace('{{count}}', str(
            len(self.not_voting_list))).replace('{{ticks}}', self.build_ticks(0, self.toexecute))

        temp_overall = game_template.overall.replace('{{votecount}}', '\n'.join(votecount_lines))
        temp_overall = temp_overall.replace('{{deadline}}', game_template.deadline_exists if self.game.deadline else game_template.deadline_not_set)
        temp_overall = temp_overall.replace('{{notvoting}}', temp_not_voting.replace('{{votelist}}', ', '.join(
            map(lambda not_voting_player: not_voting_player.name, self.not_voting_list))))

        if comments:
            temp_overall += '\n \n' + '\n \n'.join([comment.comment for comment in comments])  # noqa: WPS336

        self.bbcode_votecount = temp_overall.replace('{{deadline}}', str(deadline)).replace('{{timeuntildeadline}}', until_deadline).replace('{{day}}', str(gameday.day_number)).replace('{{tolynch}}', str(self.toexecute)).replace('{{alive}}', str(alive))

        self.html_votecount = self.convert_bbcode_to_html(self.bbcode_votecount)

    def to_execute(self, count):
        return int(math.floor(count / 2.0) + 1)

    def build_ticks(self, ticked, total):
        return ''.join(
            [f'[img]{self.empty_tick if iterator < (total - ticked) else self.tick}[/img]' for iterator in range(0, total)])

    def convert_bbcode_to_html(self, bbcode):
        bbcode_votecount = bbcode

        html_votecount = bbcode_votecount.replace('\n', '<br />\n').replace('[b]', '<b>').replace('[/b]', '</b>').replace('[i]', '<i>')
        html_votecount = html_votecount.replace('[/i]', '</i>').replace('[u]', '<u>').replace('[/u]', '</u>').replace('[super]', '<sup>')
        html_votecount = html_votecount.replace('[/super]', '</sup>').replace('[sub]', '<sub>').replace('[/sub]', '</sub>').replace('[s]', '<del>')
        html_votecount = html_votecount.replace('[/s]', '</del>').replace('[list]', '<list>').replace('[/list]', '</list><br/>').replace('[*]', '<li>')

        html_votecount = re.compile(r'\[img\](.*?)\[/img\]', re.I | re.S).sub(r'<img src="\1">', html_votecount)
        html_votecount = re.compile(r'\[url=(.*?)\](.*?)\[/url\]', re.I | re.S).sub(r'<u><a href="\1">\2</a></u>', html_votecount)

        return html_votecount  # noqa: WPS331 more confusing without the variable, promise
