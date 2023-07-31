import math
import re
from datetime import datetime

from pytz import timezone

from django.conf import settings
from django.utils.dateformat import format
from django.utils.timesince import timeuntil
from django.template import Template, Context

from votefinder.main.models import Comment, VotecountTemplate

from votefinder.main import VoteCounter


class VotecountFormatter:
    def __init__(self, game):
        self.empty_tick = ''
        self.tick = ''

        self.vc = VoteCounter.VoteCounter()
        self.game = game

    def go(self, show_comment=True):
        # Pull together all data needed to determine vote state for game
        self.counted_votes = self.vc.run(self.game)

        self.game_template = self.game.template
        if self.game_template is None:
            self.game_template = VotecountTemplate.objects.get(system_default=True)

        self.gameday = self.game.days.select_related().last()
        living_players = [ps.player for ps in self.game.living_players()]

        if self.game.deadline:
            tz = timezone(self.game.timezone)
            dl = timezone(settings.TIME_ZONE).localize(self.game.deadline).astimezone(tz)
            deadline = format(dl, r'F dS, Y \a\t P ') + dl.tzname()
            until_deadline = timeuntil(self.game.deadline, datetime.now())
            until_deadline = until_deadline.replace('\u00A0', ' ')
        else:
            deadline = ''
            until_deadline = ''

        self.to_execute = int(math.floor(len(living_players)/ 2.0) + 1)
        self.detail_level = self.game_template.detail_level
        self.tick = self.game_template.full_tick
        self.empty_tick = self.game_template.empty_tick
        self.comments = Comment.objects.filter(game=self.game).order_by('-timestamp') if show_comment else ''

        self.not_voting_list = sorted(
            filter(lambda player: self.vc.currentVote[player] is None and player in living_players, self.vc.currentVote),
            key=lambda player: player.name.lower())

        self.game_state = {
            'gameday': self.gameday.day_number,
            'players': len(living_players),
            'to_execute': self.to_execute,
            'votecounts_by_player': [],
            'not_voting': [x.name for x in self.not_voting_list],
            'deadline': deadline,
            'until_deadline': until_deadline
        }

        for vc in self.counted_votes:
            new_player = {'player_name': vc['target'].name, 'votes_received': int(vc['count']), 'votes': []}
            for vote in vc['votes']:
                vote['author'] = vote['author'].name
                new_player['votes'].append(vote)
            if len(new_player['votes']) == 0 and self.game_template.hide_zero_votes:
                continue
            else:
                self.game_state['votecounts_by_player'].append(new_player)

    def get_bbcode(self):
        game_template = Template(self.game_template.overall)
        
        # Get together individual votecount lines
        votecount = ""
        template_single_line = Template(self.game_template.single_line + "\n")
        for x in self.game_state['votecounts_by_player']:
            votelist = []
            for vote in x['votes']:
                if vote['unvote'] == True:
                    votelist.append(f"[s]{vote['author']}[/s]")
                elif vote['enabled'] == True:
                    votelist.append(f"[url={vote['url']}]{vote['author']}[/url]")
                else:
                    votelist.append(f"{vote['author']}")

            votelist_string = ', '.join(votelist)

            ticks = (f"[img]{self.game_template.empty_tick}[/img]" * (self.to_execute - x['votes_received'])) + f"[img]{self.game_template.full_tick}[/img]" * x['votes_received']

            votecount += template_single_line.render(context = Context({'ticks': ticks,'target': x['player_name'], 'count': x['votes_received'], 'votelist': votelist_string}))

        # Figure out deadline
        if self.game_state['deadline'] == '':
            deadline = self.game_template.deadline_not_set
        else:
            deadline = Template(self.game_template.deadline_exists).render(Context({
                'deadline': self.game_state['deadline'],
                'timeuntildeadline': self.game_state['until_deadline']
            }))

        return game_template.render(context = Context({
            'day': self.game_state['gameday'],
            'votecount': votecount,
            'notvoting': f"Not voting: {', '.join(self.game_state['not_voting'])}" if len(self.game_state['not_voting']) != 0 else '',
            'alive': self.game_state['players'],
            'tolynch': self.game_state['to_execute'],
            'deadline': deadline
        }))

    def get_html(self):

        # game_template = Template("{% autoescape off %}" + self.game_template.overall + "{% endautoescape %}")

        game_template = Template(self.game_template.overall)
        
        # Get together individual votecount lines
        votecount = ""
        # template_single_line = Template(self.game_template.single_line + "\n")

        template_single_line = Template("{% autoescape off %}" + self.game_template.single_line + "{% endautoescape %}" + "\n")

        for x in self.game_state['votecounts_by_player']:
            votelist = []
            for vote in x['votes']:
                if vote['unvote'] == True:
                    votelist.append(f"<del>{vote['author']}</del>")
                elif vote['enabled'] == True:
                    votelist.append(f"<u><a href='{vote['url']}'>{vote['author']}</a></u>")
                else:
                    votelist.append(f"{vote['author']}")

            votelist_string = ', '.join(votelist)

            ticks = (f"<img src='{self.game_template.empty_tick}'/>" * (self.to_execute - x['votes_received'])) + f"<img src='{self.game_template.full_tick}'/>" * x['votes_received']

            votecount += template_single_line.render(context = Context({'ticks': ticks,'target': x['player_name'], 'count': x['votes_received'], 'votelist': votelist_string}))

        # Figure out deadline
        if self.game_state['deadline'] == '':
            deadline = self.game_template.deadline_not_set
        else:
            deadline = Template(self.game_template.deadline_exists).render(Context({
                'deadline': self.game_state['deadline'],
                'timeuntildeadline': self.game_state['until_deadline']
            }))

        return game_template.render(context = Context({
            'day': self.game_state['gameday'],
            'votecount': votecount,
            'notvoting': f"Not voting: {', '.join(self.game_state['not_voting'])}" if len(self.game_state['not_voting']) != 0 else '',
            'alive': self.game_state['players'],
            'tolynch': self.game_state['to_execute'],
            'deadline': deadline
        }))

