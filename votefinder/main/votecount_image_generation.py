import re

from django.conf import settings

from votefinder.main import VotecountFormatter
from votefinder.main.models import Vote

from PIL import ImageDraw, ImageFont

def votecount_to_image(img, game, xpos=0, ypos=0, max_width=600):
    draw = ImageDraw.Draw(img)
    regular_font = ImageFont.truetype(settings.VF_REGULAR_FONT_PATH, 15)
    bold_font = ImageFont.truetype(settings.VF_BOLD_FONT_PATH, 15)

    # Reset game template to None to force use of the system default votecount template instead of whatever the game is actually set to
    game.template = None

    vc = VotecountFormatter.VotecountFormatter(game)
    vc.go(show_comment=False)

    split_vc = re.compile(r'\[.*?\]').sub('', vc.bbcode_votecount).split('\r\n')
    header_text = split_vc[0]  # Explicitly take the first and last elements in case of multiline templates
    footer_text = split_vc[-1]
    (header_x_size, header_y_size) = draw_wordwrap_text(draw, header_text, 0, 0, max_width, bold_font)
    draw.line([0, header_y_size - 2, header_x_size, header_y_size - 2], fill=(0, 0, 0, 255), width=2)
    ypos = 2 * header_y_size

    (vc_x_size, ypos) = draw_votecount_text(draw, vc, 0, ypos, max_width, regular_font, bold_font)
    ypos += header_y_size

    (x_size, ypos) = draw_wordwrap_text(draw, footer_text, 0, ypos, max_width, regular_font)

    votes = Vote.objects.select_related().filter(game=game, target=None, unvote=False, ignored=False, no_execute=False)
    if votes:
        ypos += header_y_size
        if len(votes) == 1:
            warning_text = 'Warning: There is currently 1 unresolved vote.  The votecount may be inaccurate.'
        else:
            warning_text = 'Warning: There are currently {} unresolved votes.  The votecount may be inaccurate.'.format(len(
                votes))

        (warning_x, ypos) = draw_wordwrap_text(draw, warning_text, 0, ypos, max_width, bold_font)
        x_size = max(x_size, warning_x)

    return (max(header_x_size, vc_x_size, x_size), ypos)


def draw_votecount_text(draw, vc, xpos, ypos, max_width, font, bold_font):
    votes_by_player = [voted_player for voted_player in vc.counted_votes if voted_player['count'] > 0]
    longest_name = 0
    divider_len_x, divider_len_y = draw.textsize(': ', font=font)
    max_x = 0
    if votes_by_player is None:  # No votes found
        text = 'No votes found in vc.counted_votes~'
        this_size_x, this_size_y = draw.textsize(text, font=bold_font)
        return draw_wordwrap_text(draw, text, 0, ypos, max_width, bold_font)
    for line in votes_by_player:
        text = '{} ({})'.format(line['target'].name, line['count'])
        this_size_x, this_size_y = draw.textsize(text, font=bold_font)
        line['size'] = this_size_x
        if this_size_x > longest_name:
            longest_name = this_size_x

    for line_again in votes_by_player:  # noqa: WPS426
        pct = float(line_again['count']) / vc.toexecute
        box_width = min(pct * longest_name, longest_name)
        draw.rectangle([longest_name - box_width, ypos, longest_name, this_size_y + ypos],
                       fill=(int(155 + (pct * 100)), 100, 100, 0))

        text = '{} ({})'.format(line_again['target'].name, line_again['count'])
        (x_size1, y_bottom1) = draw_wordwrap_text(draw, text, longest_name - line_again['size'], ypos, max_width, bold_font)

        (x_size2, y_bottom2) = draw_wordwrap_text(draw, ': ', x_size1, ypos, max_width, font)

        text = ', '.join(
            [vote['author'].name for vote in filter(lambda vote: vote['unvote'] is False and vote['enabled'], line_again['votes'])])
        (x_size3, y_bottom3) = draw_wordwrap_text(draw, text, x_size2 + divider_len_x, ypos, max_width, font)

        max_x = max(max_x, x_size3)
        ypos = max(y_bottom1, y_bottom2, y_bottom3)

    return (max_x, ypos)


def draw_wordwrap_text(draw, text, xpos, ypos, max_width, font):
    fill = (0, 0, 0, 0)
    used_width = 0
    max_width -= xpos
    space_width, space_height = draw.textsize(' ', font=font)

    text_size_x, text_size_y = draw.textsize(text, font=font)
    remaining = max_width
    output_text = []

    for word in text.split(None):
        word_width, word_height = draw.textsize(word, font=font)
        if word_width + space_width > remaining:
            output_text.append(word)
            remaining = max_width - word_width
        elif output_text:
            output = output_text.pop()
            output = '{} {}'.format(output, word)
            output_text.append(output)
            remaining = remaining - (word_width + space_width)
        else:
            output_text.append(word)
            remaining = remaining - (word_width + space_width)

    for text_element in output_text:
        cur_width, cur_height = draw.textsize(text_element, font=font)
        if (cur_width > used_width):
            used_width = cur_width

        draw.text((xpos, ypos), text_element, font=font, fill=fill)
        ypos += text_size_y

    return used_width + xpos, ypos