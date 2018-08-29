import lxml.html
import re

from lxml.html import builder as E

from matrix_client.room import Room

class ValidationError(Exception):
    pass

class Command:
    def __init__(self, *args, **kwargs):
        self.aliases = []
        self.arguments = []
        self.prefix = kwargs.get('prefix', False)
        self.help = kwargs.get('help')
        self.callback = kwargs['callback']
        assert callable(self.callback)

        args = list(args)

        # get all aliases
        while args and isinstance(args[0], str):
            self.aliases.append(args.pop(0).lower())

        while args and isinstance(args[0], CommandArgument):
            self.arguments.append(args.pop(0))

        # we don't expect anything else after the callback
        assert len(args) == 0

        if self.prefix:
            assert len(self.arguments) == 1

    def get_help(self):
        arg_names = {}
        for i, arg in enumerate(self.arguments, start=1):
            arg_names['arg{}'.format(i)] = arg.get_help_name()

        return self.help.format(**arg_names)

    def run(self, event, line, room_, user_):
        stripped_line = line.strip()
        if self.prefix:
            for alias in self.aliases:
                if stripped_line.startswith(alias):
                    # cut off the prefix
                    stripped_line = stripped_line[len(alias):]
                    break
            else:
                # not an invocation of this command
                return False

            self.arguments[0].validator(stripped_line)
            self.callback(event=event, room_=room_, user_=user_, **{self.arguments[0].get_variable_name() : stripped_line})
            return

        words = stripped_line.split()
        first_word = words.pop(0).lower()
        if first_word not in self.aliases:
            # not an invocation of this command
            return False

        kwargs = {}
        for i, arg in enumerate(self.arguments):
            if len(words) <= i:
                if not arg.optional:
                    raise ValidationError("Missing argument '{}'".format(arg.name))

                kwargs[arg.get_variable_name()] = None
                continue

            if arg.multi_word:
                value = ' '.join(words[i:])
            else:
                value = words[i]

            try:
                arg.validator(value)
            except ValidationError as e:
                raise ValidationError("Bad argument '{}': {}".format(arg.name, e))

            kwargs[arg.get_variable_name()] = value

        self.callback(event=event, room_=room_, user_=user_, **kwargs)
        return True


class CommandArgument:
    def __init__(self, name, validator, optional, multi_word):
        self.name = name
        self.validator = validator
        self.optional = optional
        self.multi_word = multi_word

    def get_variable_name(self):
        return re.sub(r'[^a-zA-Z0-9_]', '_', self.name)

    def get_help_name(self):
        if self.optional:
            return '[{}]'.format(self.name)

        return '<{}>'.format(self.name)


def arg(name, validator, optional=False, multi_word=False):
    return CommandArgument(name, validator, optional, multi_word)


class MatrixBotModule:
    @staticmethod
    def create(cls, config):
        raise NotImplementedError()

    def __init__(self, config):
        self.config = config
        self.commands = []

        self.register_commands()

    def register_commands(self):
        pass

    def process(self, client, event):
        self.client = client

        if event['type'] == 'm.room.message':
            return self.handle_room_message(client, event)

    def handle_room_message(self, client, event):
        room_id = event['room_id']
        sender_id = event['sender']
        content = event['content']

        if content['msgtype'] != 'm.text':
            return

        data = content['body']
        room = Room(client, room_id)

        for command in self.commands:
            try:
                if command.run(event=event, line=data, room_=room, user_=None):
                    return True

            except ValidationError as e:
                room.send_text(str(e))
                return True


    def add_command(self, *args, **kwargs):
        self.commands.append(Command(*args, **kwargs))

    def show_help(self, event, room_, user_):
        table = E.TABLE(
            E.TR(
                E.TH("command"),
                E.TH("arguments"),
                E.TH("details")
            ),
        )
        html = E.DIV(
            E.P("Command list:"),
            table
        )

        for command in self.commands:
            table.append(E.TR(
                    E.TD(', '.join(command.aliases)),
                    E.TD('\xa0'.join(arg.get_help_name() for arg in command.arguments)),
                    E.TD(command.get_help())
                )
            )

        html_data = lxml.html.tostring(html, pretty_print=True).decode('utf-8')
        print(html_data)
        room_.send_html(html_data)
