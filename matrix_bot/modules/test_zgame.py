import configparser
import os
import pytest

from unittest.mock import ANY, Mock, patch, AsyncMock

from . import zgame as zgame_module
from matrix_bot.modules import base


@pytest.fixture
def root_dir():
    return os.path.abspath(os.path.join(__file__, "../../.."))

@pytest.fixture
def room_id():
    return '!test-room:matrix.thialfihar.org'

@pytest.fixture
def zgame_config(root_dir):
    config = configparser.ConfigParser()
    config.read_string("""
[zgame]
session_dir = {root}/test-data/zgame-sessions
save_dir = {root}/test-data/zgame-savegames

[zgame/make-it-good]
name = Make It Good
file = {root}/test-data/MakeItGood.zblorb
command_prefix = \\n

[zgame/anchor]
name = Anchorhead
file = {root}/test-data/anchor.z8

[zgame/h2g2]
name = Hitchhiker's Guide To The Galaxy
file = {root}/test-data/hhgg.z3
 """.format(root=root_dir))

    return config


@pytest.fixture
def zgame(zgame_config):
    return zgame_module.ZGameModule.create(zgame_config)


@pytest.fixture
def event():
    event = AsyncMock()
    event.sender = '@thi:matrix.thialfihar.org'
    event.source = {
        'content': {'body': '', 'msgtype': 'm.text'},
    }

    return event

@pytest.fixture
def bot():
    return AsyncMock()


@pytest.fixture
def room(room_id):
    room = AsyncMock()
    room.room_id = room_id
    return room


def test_default_dfrotz_path(root_dir):
    dfrotz_path = zgame_module.ZGameModule.get_default_dfrotz_path()
    expected_path = os.path.abspath(os.path.join(root_dir, "bin/dfrotz"))
    assert dfrotz_path == expected_path


def test_zgame_config_parsing(zgame, root_dir):
    assert set(zgame.games.keys()) == {'make-it-good', 'anchor', 'h2g2'}

    assert zgame.games['make-it-good']['name'] == "Make It Good"
    assert zgame.games['make-it-good']['file'] == os.path.join(root_dir, "test-data/MakeItGood.zblorb")


@pytest.mark.asyncio
async def test_zgame_list(zgame, bot, room, event):
    event.source['content']['body'] = '!zlist'
    await zgame.handle_room_message(bot=bot, room=room, event=event)

    bot.send_room_html.assert_called_with(room, """\
<table>
<tr>
<th>id</th>
<th>name</th>
</tr>
<tr>
<td>anchor</td>
<td>Anchorhead</td>
</tr>
<tr>
<td>h2g2</td>
<td>Hitchhiker's Guide To The Galaxy</td>
</tr>
<tr>
<td>make-it-good</td>
<td>Make It Good</td>
</tr>
</table>
""")


@pytest.mark.asyncio
async def test_zgame_start_without_game_id(zgame, bot, room, event):
    event.source['content']['body'] = '!zstart'
    await zgame.handle_room_message(bot=bot, room=room, event=event)

    bot.send_room_text.assert_called_with(room, "Missing argument 'game-id'")


@pytest.mark.asyncio
async def test_zgame_start_with_unknown_game_id(zgame, bot, room, event):
    event.source['content']['body'] = '!zstart foobar'
    await zgame.handle_room_message(bot=bot, room=room, event=event)

    bot.send_room_text.assert_called_with(room, "Bad argument 'game-id': Unknown game-id 'foobar'")


def test_zgame_convert_to_html(zgame):
    data = """\
   Broken Top Boulevard, Outside No. 15                                                                                                Time:  2:26 pm
   - in the black chevy
                                                                                                           [For a closer description of something, EXAMINE it.]
.
     MAKE IT GOOD
        By Jon Ingold

     -- Release 13 / Serial number 090921 / Inform v6.21 Library 6/10

  Broken Top Boulevard, Outside No. 15 (in the black chevy)
  The boulevard through the windscreen is lined with ash trees, thick trunks casting shadows and gnarled roots mangling up the sidewalk. You're sat in your car,
  parked too high up the kerb; just outside the gate to No. 15. Just an ordinary house. With a body inside.

  "Homicide. One Jack Draginam, accountant. Married, no kids. Stabbed. Yadda yadda, blah blah. We got the call from the maid - geez, who has a maid? Apparently
  she wanted to stress there's a lot of blood."

  "Oh, Inspector. Word is, if you don't crack this one, you're out of a job."

  The glove compartment is closed. Sat on the passenger seat is a whiskey bottle.

> > """
    html_data = zgame.convert_to_html(data, "test-room")
    expected_html_data = """\
<div title="[For a closer description of something, EXAMINE it.]">
<div class="location">Broken Top Boulevard, Outside No. 15 (in the black chevy)</div>
<div class="score">Time:  2:26 pm</div>
<p>&#160;  MAKE IT GOOD<br>&#160; &#160; &#160; By Jon Ingold</p>
<p>&#160;  -- Release 13 / Serial number 090921 / Inform v6.21 Library 6/10</p>
<p>The boulevard through the windscreen is lined with ash trees, thick trunks casting shadows and gnarled roots mangling up the sidewalk. You're sat in your car,
parked too high up the kerb; just outside the gate to No. 15. Just an ordinary house. With a body inside.</p>
<p>"Homicide. One Jack Draginam, accountant. Married, no kids. Stabbed. Yadda yadda, blah blah. We got the call from the maid - geez, who has a maid? Apparently
she wanted to stress there's a lot of blood."</p>
<p>"Oh, Inspector. Word is, if you don't crack this one, you're out of a job."</p>
<p>The glove compartment is closed. Sat on the passenger seat is a whiskey bottle.</p>
</div>
"""

    assert html_data == expected_html_data


def test_zgame_convert_to_html_no_status_line(zgame):
    data = """\
You're not holding your gown.

> """
    html_data = zgame.convert_to_html(data, "test-room")
    expected_html_data = """\
<div><p>You're not holding your gown.</p></div>
"""

    assert html_data == expected_html_data


@pytest.mark.skip
@pytest.mark.asyncio
async def test_zgame_start_make_it_good(zgame, bot, room, event):
    event.source['content']['body'] = '!zstart make-it-good'
    zgame.sessions = {}

    await zgame.handle_room_message(bot=bot, room=room, event=event)

    assert zgame.sessions == {room.room_id: 'make-it-good'}

def test_zgame_h2g2_list_convert(zgame):
    data = """\
 Bedroom                                                                                                                          Score: 0        Moves: 13

You have:
  a splitting headache
  no tea
  your gown (being worn)

> """

    html_data = zgame.convert_to_html(data, "test-room")
    expected_html_data = """\
<div>
<div class="location">Bedroom</div>\n<div class="score">Score: 0        Moves: 13</div>
<p>You have:<br>&#160; a splitting headache<br>&#160; no tea<br>&#160; your gown (being worn)</p>
</div>
"""

    assert html_data == expected_html_data


@pytest.mark.asyncio
async def test_zgame_zdirect_on(zgame, bot, room, event):
    event.source['content']['body'] = '!zdirect on'

    zgame.direct_mode = {}

    await zgame.handle_room_message(bot=bot, room=room, event=event)

    assert zgame.direct_mode == {room.room_id: {event.sender}}


@pytest.mark.asyncio
async def test_zgame_zdirect_off_1(zgame, bot, room, event):
    event.source['content']['body'] = '!zdirect off'

    zgame.direct_mode = {}

    await zgame.handle_room_message(bot=bot, room=room, event=event)

    assert zgame.direct_mode == {}


@pytest.mark.asyncio
async def test_zgame_zdirect_off_2(zgame, bot, room, event):
    event.source['content']['body'] = '!zdirect off'

    zgame.direct_mode = {room.room_id: {event.sender}}

    await zgame.handle_room_message(bot=bot, room=room, event=event)

    assert zgame.direct_mode == {room.room_id: set()}


@pytest.mark.asyncio
async def test_zgame_room_message_direct_command(zgame, bot, room, event):
    event.source['content']['body'] = 'examine'

    zgame.direct_mode = {room.room_id: event.sender}

    zgame.zcommand = AsyncMock()

    await zgame.handle_room_message(bot=bot, room=room, event=event)

    zgame.zcommand.assert_called_with(bot=bot, event=event, command='examine', room=ANY, user=ANY)
