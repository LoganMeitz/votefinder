import re

from django.conf import settings

from votefinder.main import VotecountFormatter
from votefinder.main.models import Vote

from PIL import ImageDraw, ImageFont, Image

regular_font = ImageFont.truetype(settings.VF_REGULAR_FONT_PATH, 15)

bold_font = ImageFont.truetype(settings.VF_BOLD_FONT_PATH, 15)

def votecount_to_image(game):
    img = Image.new('RGB', (800, 1024), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Reset game template to None to force use of the system default votecount template instead of whatever the game is actually set to
    game.template = None

    # Generate text for image by... getting the BBCode the bot would post
    # normally, then processing it
    # there's a better way to do this but, for now, I'd rather not touch it
    vc = VotecountFormatter.VotecountFormatter(game)
    vc.go(show_comment=False)

    split_vc = re.compile(r'\[.*?\]').sub('', vc.bbcode_without_images()).split('\r\n')
    header_text = split_vc[0]  # Explicitly take the first and last elements in case of multiline templates
    footer_text = split_vc[-1]

    for l in split_vc:
        # print(l.split())
        # current_y = 0
        # draw.multiline_text((0, current_y), l, fill=(0,0,0), font=regular_font)
        # left, top, right, bottom = draw.multiline_textbbox((0, current_y), l, font=regular_font)
        # current_y += bottom - top

        draw.multiline_text((0, 0), l, fill=(0,0,0), font=regular_font)


    # Actual image creation follows

    max_width = 800

    

    return img