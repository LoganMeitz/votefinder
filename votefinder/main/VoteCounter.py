import math
import random

from votefinder.main.models import GameDay, ExecutionMessage, Player, Vote

from votefinder.main import SAForumPageDownloader, VotecountFormatter, BNRApi


class VoteCounter:
    def __init__(self):
        self.results = {}  # noqa: WPS110
        self.currentVote = {}
        self.votesFound = False
        self.no_execute_player = None
        self.voteLog = []
        self.show_only_active_votes = False

    def run(self, game):
        gameday = game.days.select_related().last()

        try:
            votes = Vote.objects.select_related().filter(game=game, ignored=False, manual=False,
                                                         post__id__gte=gameday.start_post.id).order_by('id')
            manual_votes = Vote.objects.select_related().filter(game=game, ignored=False, manual=True,
                                                                post__id__gte=gameday.start_post.id).order_by('id')
            self.votesFound = True
        except Vote.DoesNotExist:
            return None

        self.livingPlayers = Player.objects.select_related().filter(games__in=game.living_players())
        self.game = game
        self.voteLog = []

        for single_player in self.livingPlayers:
            self.results[single_player] = {'count': 0, 'votes': []}
            self.currentVote[single_player] = None

        for single_vote in votes:
            if single_vote.author in self.livingPlayers and self.target_is_valid(single_vote):
                if single_vote.unvote:
                    self.handle_unvote(single_vote)
                else:
                    self.handle_vote(single_vote)

        # ensure manual votes are applied after all real votes
        for single_manual_vote in manual_votes:
            if self.target_is_valid(single_manual_vote):
                if single_manual_vote.unvote:
                    self.handle_unvote(single_manual_vote)
                else:
                    self.handle_vote(single_manual_vote)

        self.run_notify(game, gameday)

        return self.build_result_list()

    def get_votelog(self):
        return self.voteLog

    def run_notify(self, game, gameday):
        gameday = GameDay.objects.get(id=gameday.id)  # reload to prevent double posts from 2 threads updating at once
        if gameday.notified:
            return

        to_execute = int(math.floor(len(game.living_players()) / 2.0) + 1)
        executed = filter(lambda key: self.results[key]['count'] >= to_execute, self.results)
        list_executed = list(executed)  # exhausts iterator - py3
        if len(list_executed) == 1:
            executee = list_executed[0]
            gameday.notified = True
            gameday.save()
            if game.post_executions:
                game.status_update(f'{executee.name} was executed on day {gameday.day_number}!')
                self.post_execute_message(game, executee.name)

    def post_execute_message(self, game, name):
        message = random.choice(ExecutionMessage.objects.all()).text  # noqa: S311
        vc_formatter = VotecountFormatter.VotecountFormatter(game)
        vc_formatter.go()
        message = f'{message}\n\n'
        message += vc_formatter.get_bbcode()
        if game.home_forum == 'sa':
            message = f':redhammer: {message}'
            dl = SAForumPageDownloader.SAForumPageDownloader()
        elif game.home_forum == 'bnr':
            dl = BNRApi.BNRApi()
        dl.reply_to_thread(game.thread_id, message.format(name))

    def build_result_list(self):
        resultlist = []
        for key, votes_by_player in self.results.items():
            resultlist.append({'target': key, 'count': votes_by_player['count'], 'votes': votes_by_player['votes']})

        resultlist.sort(key=lambda sorter: sorter['count'], reverse=True)

        return resultlist

    def target_is_valid(self, vote):
        if vote.no_execute and self.no_execute_player is None:
            self.no_execute_player = Player.objects.get(sa_uid=-1)
            self.results[self.no_execute_player] = {'count': 0, 'votes': []}

        return vote.unvote or vote.no_execute or (vote.target in self.livingPlayers)

    def handle_vote(self, vote):
        if not vote.manual and self.player_is_voting(vote.author):
            self.handle_unvote(vote)

        if vote.no_execute:
            vote.target = self.no_execute_player

        self.add_vote_to_player(vote.target, vote.author, False, vote.post.page_number, vote.post.post_id,  # noqa: WPS425
                                vote.post.timestamp)
        self.currentVote[vote.author] = vote.target

    def add_vote_to_player(self, target, author, unvote, page, postid, timestamp):
        result_item = self.results[target]
        if unvote:
            result_item['count'] -= 1
            text = f'{author} unvotes'
        else:
            result_item['count'] += 1
            text = f'{author} votes {target}'

        self.voteLog.append({'timestamp': timestamp, 'player': target.name, 'count': result_item['count'], 'text': text})
        if self.game.home_forum == 'sa':
            result_item['votes'].append({'unvote': unvote, 'enabled': True, 'author': author,
                                        'url': f'https://forums.somethingawful.com/showthread.php?threadid={self.game.thread_id}&pagenumber={page}#post{postid}'})
        elif self.game.home_forum == 'bnr':
            result_item['votes'].append({'unvote': unvote, 'enabled': True, 'author': author,
                                        'url': f'https://breadnroses.net/threads/{self.game.thread_id}/post-{postid}'})

    def handle_unvote(self, vote):
        current_vote = self.player_is_voting(vote.author)
        if current_vote:
            self.disable_current_vote(vote.author, current_vote)
            self.add_vote_to_player(current_vote, vote.author, True, vote.post.page_number, vote.post.post_id,  # noqa: WPS425
                                    vote.post.timestamp)
        self.currentVote[vote.author] = None

    def disable_current_vote(self, player, target):
        for vote in self.results[target]['votes']:
            if vote['author'] == player and vote['unvote'] is False and vote['enabled']:
                vote['enabled'] = False
                return

    def player_is_voting(self, player):
        if player in self.currentVote.keys():
            return self.currentVote[player]
        return None
