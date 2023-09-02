from django.conf import settings

from votefinder.main import VotecountFormatter

from PIL import ImageDraw, ImageFont, Image

regular_font = ImageFont.truetype(settings.VF_REGULAR_FONT_PATH, 15)
bold_font = ImageFont.truetype(settings.VF_BOLD_FONT_PATH, 15)

# dummy Image/ImageDraw objects to use so we can access
# ImageDraw.multiline_textbbox before actually creating an image
# there's gotta be a way to access that method otherwise but I can't seem to
# find it
dummy_img = Image.new('RGB', (0,0), (255, 255, 255))
dummy_draw = ImageDraw.Draw(dummy_img)

def votecount_to_image(game):

    # get the gamestate object
    vc = VotecountFormatter.VotecountFormatter(game)
    vc.go(show_comment=False)
    game_state = vc.game_state

    # we're going to compose the votecount image out of several smaller
    # images - one for each player, plus one for the game title and one for
    # the deadline/other information 

    # keys are player names, values are a list - the first item in the
    # list is the image of the player name/their votes received, and the
    # second is an image of the received votes - these will be joined together
    # into one image for composition later
    # without knowing how tall the list of votes will be, it is hard to place
    # them in one image to start
    # I want to keep the player image/votes image together so they're easier to
    # iterate over later
    # note: python dictionaries are *generally* assumed to be in insertion order
    # but this isn't guaranteed - there may be a better way to do this
    votecounts = {}

    # going over each of the players who have received votes to generate
    # names/received votes - we need this to determine the maximum width
    # available for the names that come afterwards
    max_player_name_width = draw_votecount_names(game_state, votecounts)

    # now we'll generate the actual list of voting players
    draw_vote_list(game_state, votecounts, max_player_name_width)

    # split the votecounts dictionary into a list of tuples - index 0 of the
    # tuple is the name of the voted player, index 1 is the list of votes

    vote_images = []
    total_height = 0

    for v in votecounts.values():
        vote_images.append((v[0], v[1]))
        total_height += v[1].height

    header_text = f"Votecount for Day {game_state['gameday']}"

    footer_text = f"With {game_state['players']} alive, it's {game_state['to_execute']} votes to execute."
    if game_state['deadline'] != '':
        footer_text += f"\nThe current deadline is {game_state['deadline']} - that's in about {game_state['until_deadline']}."


    header_height = dummy_draw.multiline_textbbox(
            (0,0),
            header_text,
            font=regular_font
        )[3]

    footer_height = dummy_draw.multiline_textbbox(
            (0,0),
            footer_text,
            font=regular_font
        )[3]

    # the 32 here gives 16 pixels of space around the votes
    total_height = total_height + header_height + footer_height + 32

    # Actual image creation follows
    # the +16s are to create a margin around the image, so the text doesn't
    # butt right up to the edge
    img = Image.new('RGB', (816, total_height + 16), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # cursor values to keep track of where we should be drawing on our image
    cursor_x = 8
    cursor_y = 8

    draw.text((cursor_x, cursor_y), header_text, fill=(0,0,0), font=bold_font)
    cursor_y += header_height + 16

    for name, votes in vote_images:
        name_offset = max_player_name_width - name.width
        img.paste(name, (cursor_x + name_offset, cursor_y))
        img.paste(votes, (cursor_x + max_player_name_width, cursor_y))
        cursor_y += votes.height

    cursor_y += 16
    draw.text((cursor_x, cursor_y), footer_text, fill=(0,0,0), font=bold_font)

    return img

# generates images of the player name plus their received votes, plus
# returns widest player name, for generation of the vote list image
def draw_votecount_names(game_state, votecounts):
    
    # going to store the widest player name plus votes received so far so we
    # can use it later when building other elements
    max_player_name_width = 0

    for votecount in [x for x in game_state['votecounts_by_player'] if x['votes_received'] != 0]:

        # figure maximum width of generated text and create image for it
        text = f'{votecount["player_name"]} ({votecount["votes_received"]}): '
        _, _, right, bottom = dummy_draw.textbbox((0,0), text=text, font=bold_font)
        img = Image.new('RGB', (right, bottom), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((0,0), text=text, font=regular_font, fill=(0,0,0))

        # add image to votecounts
        votecounts[votecount['player_name']] = [img, None]        

        # keep track of largest name found
        max_player_name_width = max(max_player_name_width, right)

    # print(votecounts)
    return max_player_name_width

def draw_vote_list(game_state, votecounts, max_player_name_width):
    max_width = 800 - max_player_name_width

    for votecount in [x for x in game_state['votecounts_by_player'] if x['votes_received'] != 0]:

        player_names = [
            n['author'] for n in votecount['votes'] if
            n['enabled'] == True and n['unvote'] == False
        ]

        # testing: adding extra names
        # don't forget to delete these when you're done
        player_names.append('aaaaaa')
        player_names.append('bbbbbb')
        player_names.append('cccccccccccccc')
        player_names.append('dddd ddddd ddddddd')
        player_names.append('eeeeeeeeeeeee eeeeeeeeeeee')
        player_names.append('ff ff ff')
        player_names.append('gggg ggg ggggg')

        # print("appended all extra names")

        player_names_text = player_names[0]

        _, _, _, text_height = dummy_draw.multiline_textbbox(
                (0,0),
                player_names[0],
                font=regular_font
            )
        # not sure if this needs stroke width
        for p in player_names[1:len(player_names)]:
            # print(f'appending {p} to image for {votecount["player_name"]}')
            _, _, right, bottom = dummy_draw.multiline_textbbox(
                (0,0),
                player_names_text + f', {p}',
                font=regular_font
            )
            # print(f'bounding box: {left, top, right, bottom}')
            if right > max_width:
                # print(f'new bottom is {text_height}')
                text_height += bottom
                # print(f'{right} > {max_width} when adding {p}')
                player_names_text += f',\n{p}'
            else:
                player_names_text += f', {p}'
            
            # print(player_names_text)
            

        # the + 4 to text height is to insure things like the tails of 
        # characters like 'g' don't accidentally get cropped - there might be
        # a better way of doing this
        votes_image = Image.new('RGB', (max_width, text_height + 4), (255, 255, 255))
        votes_draw = ImageDraw.Draw(votes_image)
        votes_draw.multiline_text(
                (0,0),
                player_names_text,
                fill=(0, 0, 0),
                font=regular_font
            )

        votecounts[votecount['player_name']][1] = votes_image

        # votes_image.show()
        
        # print(f"{votecount['player_name']} votes: {player_names}")