from unittest.mock import Mock, patch

import pytest

from matrix_bot.modules.base import Command, MatrixBotModule, arg


@pytest.fixture
def TestModule():
    class TestModuleClass(MatrixBotModule):
        def register_commands(self):
            self.add_command(
                '!command1',
                callback=self.command1,
                help="do something with command1")

            self.add_command(
                '!command2',
                arg('name', self.validate_name),
                callback=self.command2,
                help="do something with command2 and {arg1}")

            self.add_command(
                '!command3', '!c3',
                arg('name', self.validate_name),
                arg('optional', self.validate_optional, optional=True),
                callback=self.command3,
                help="do something with command3 and {arg1} and {arg2}")

            self.add_command(
                '\\',
                arg('command', self.validate_command),
                callback=self.command4,
                prefix=True,
                help="do something with prefix command4")

        def validate_name(self, value):
            pass

        def validate_optional(self, value):
            pass

        def validate_command(self, value):
            pass

        def command1(event, **kwargs):
            pass

        def command2(event, name, **kwargs):
            pass

        def command3(event, name, optional, **kwargs):
            pass

        def command4(event, command, **kwargs):
            pass

    return TestModuleClass

def test_command_creation():
    def validate_foo_bar():
        pass

    def validate_optional():
        pass

    def callback(event, foo_bar, optional, **kwargs):
        pass

    command = Command(
        '!command', '!c',
        arg('foo-bar', validate_foo_bar),
        arg('optional', validate_optional, optional=True),
        callback=callback,
        help="do something with command and {arg1} and {arg2}")

    assert command.aliases == ['!command', '!c']
    assert command.arguments[0].name == 'foo-bar'
    assert command.arguments[0].get_variable_name() == 'foo_bar'
    assert command.arguments[0].validator == validate_foo_bar
    assert command.arguments[0].optional == False
    assert command.arguments[1].name == 'optional'
    assert command.arguments[1].get_variable_name() == 'optional'
    assert command.arguments[1].validator == validate_optional
    assert command.arguments[1].optional == True
    assert command.callback == callback
    assert command.prefix == False


def test_module_with_commands(TestModule):
    test_module = TestModule({})
    # TODO: test some more features

async def test_module_show_help(TestModule):
    test_module = TestModule({})
    room = Mock()
    bot = Mock()
    await test_module.show_help(bot=bot, event={}, room=room, user=None)

    expected_html = """\
<div>
<p>Command list:</p>
<table>
<tr>
<th>command</th>
<th>arguments</th>
<th>details</th>
</tr>
<tr>
<td>!command1</td>
<td></td>
<td>do something with command1</td>
</tr>
<tr>
<td>!command2</td>
<td>&lt;name&gt;</td>
<td>do something with command2 and &lt;name&gt;</td>
</tr>
<tr>
<td>!command3, !c3</td>
<td>&lt;name&gt;&#160;[optional]</td>
<td>do something with command3 and &lt;name&gt; and [optional]</td>
</tr>
<tr>
<td>\</td>
<td>&lt;command&gt;</td>
<td>do something with prefix command4</td>
</tr>
</table>
</div>
"""
    bot.send_room_html.assert_called_with(bot, expected_html)
