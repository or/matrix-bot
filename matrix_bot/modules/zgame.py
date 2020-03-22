#!/usr/bin/env python3
import html
import json
import logging
import lxml.html
import os
import random
import re
import requests
import shutil
import string
import time

from datetime import datetime
from fcntl import fcntl, F_GETFL, F_SETFL
from lxml.html import builder as E
from subprocess import Popen, PIPE, STDOUT

from matrix_bot.modules.base import MatrixBotModule, arg, ValidationError

class ZGameModule(MatrixBotModule):
    COMMAND_PREFIX = '\\'

    @staticmethod
    def create(config):
        if 'zgame' in config:
            return ZGameModule(config)

        return None

    def __init__(self, config):
        super(ZGameModule, self).__init__(config)
        self.executable = self.config['zgame'].get('dfrotz_bin', ZGameModule.get_default_dfrotz_path())
        self.session_dir = self.config['zgame']['session_dir']
        self.save_dir = self.config['zgame']['save_dir']
        self.games = {}
        for section in self.config.sections():
            if not section.startswith('zgame/'):
                continue

            game_id = section[len('zgame/'):]
            data = self.config[section]
            data['id'] = game_id
            self.games[game_id] = data

        self.sessions = {}
        self.status_line_cache = {}
        self.load_sessions()
        self.direct_mode = {}

    async def handle_room_message(self, bot, room, event):
        print("here")
        if await super().handle_room_message(bot=bot, room=room, event=event):
            return
        print("here2")

        content = event.source['content']
        if content['msgtype'] != 'm.text':
            return

        room_id = room.room_id
        sender_id = event.sender
        command = content['body'].strip()

        if command.startswith(self.COMMAND_PREFIX) or command.startswith('!'):
            # let the normal zcommand handle it
            return

        if sender_id in self.direct_mode.get(room_id, set()):
            self.zcommand(bot=bot, event=event, command=command, room=room, user=None)

    def register_commands(self):
        self.add_command(
            '!zhelp', '!zh',
            callback=self.show_help,
            help="show help")

        self.add_command(
            '!zlist',
            callback=self.zlist,
            help="list all installed games and their IDs")

        self.add_command(
            '!zstart',
            arg('game-id', self.validate_game_id),
            callback=self.zstart,
            help="start a new session of game {arg1}, replaces the current session")

        self.add_command(
            '!zsave', '!zs',
            arg('name', self.validate_savegame_name),
            arg('overwrite', self.validate_overwrite, optional=True),
            callback=self.zsave,
            help="save current session to {arg1}, if it already exists, then {arg2} must be specified")

        self.add_command(
            '!zload', '!zl',
            arg('game-id', self.validate_game_id),
            arg('name', self.validate_savegame_name),
            callback=self.zload,
            help="load a new save game of game <game-id>, replacing the current session")

        self.add_command(
            '!zlistsaves', '!zls',
            arg('game-id', self.validate_game_id),
            callback=self.zlistsaves,
            help="list saved games for game {arg1}")

        self.add_command(
            '!zdownload', '!zd',
            arg('game-id', self.validate_game_id),
            arg('name', self.validate_savegame_name),
            callback=self.zdownload,
            help="download savegame {arg2} for game {arg1}")

        self.add_command(
            '!zcontinue', '!zc',
            arg('game-id', self.validate_game_id),
            callback=self.zcontinue,
            help="continue the last session of game <game-id> that was played, if there is one")

        self.add_command(
            '!zdirect',
            arg('mode', self.validate_direct_mode),
            callback=self.zdirect,
            help="set direct mode for yourself to <on> or <off>, if it is on, then the '{}' prefix is not needed".format(self.COMMAND_PREFIX))

        self.add_command(
            self.COMMAND_PREFIX,
            arg('command', self.validate_command),
            callback=self.zcommand,
            prefix=True,
            help="send commands to the game itself, e.g.: \\look around")

    def validate_savegame_name(self, value):
        if not re.match(r'^[a-zA-Z0-9-]+$', value):
            raise ValidationError("Filename '{}' should only contain a-z, A-Z, 0-9 or - ".format(value))

    def validate_game_id(self, value):
        if value not in self.games:
            raise ValidationError("Unknown game-id '{}'".format(value))

    def validate_overwrite(self, value):
        if value.lower() != 'overwrite':
            raise ValidationError("invalid value '{}', only 'overwrite' is accepted".format(value))

    def validate_direct_mode(self, value):
        if value.lower() not in ['on', 'off']:
            raise ValidationError("invalid value '{}', only 'on' or 'off' are accepted".format(value))

    def validate_command(self, value):
        pass

    async def zlist(self, bot, event, room, user):
        html = E.TABLE()
        html.append(E.TR(E.TH('id'), E.TH('name')))
        for unused_id, game in sorted(self.games.items(), key=lambda x: x[1]['name']):
            html.append(E.TR(E.TD(game['id']), E.TD(game['name'])))

        html_data = lxml.html.tostring(html, pretty_print=True).decode('utf-8')
        await bot.send_room_html(room, html_data)

    async def zstart(self, bot, event, game_id, room, user):
        room_id = room.room_id
        game = self.games[game_id]

        p = self.start_frotz(game)
        self.send_prefix(p, game)

        data = self.send_data_to_process(p, '\n')
        html_data = self.convert_to_html(data, room_id)

        self.save_game(p, room_id, game_id)
        self.quit_game(p)

        await bot.send_room_html(room, html_data)

    async def zsave(self, bot, event, name, overwrite, room, user):
        room_id = room.room_id

        if overwrite == 'overwrite':
            overwrite = True
        else:
            overwrite = False

        if room_id not in self.sessions:
            await bot.send_room_text(room, "No session to save")

        game_id = self.sessions[room_id]
        game = self.games[game_id]

        target_path = os.path.join(self.save_dir, ZGameModule.escape_room_id(room_id), game_id, name)
        if os.path.exists(target_path) and not overwrite:
            await bot.send_room_text(room, "Save file '{}' exists, pick another one or specify 'overwrite' as last argument".format(name))
            return

        os.makedirs(os.path.abspath(os.path.join(target_path, os.pardir)), exist_ok=True)
        shutil.copy(self.get_session_file(room_id, game_id), target_path)
        await bot.send_room_text(room, "Saved to file '{}' for game '{}'".format(name, game_id))

    async def zload(self, bot, event, game_id, name, room, user):
        room_id = room.room_id
        game = self.games[game_id]

        if not re.match(r'^[a-zA-Z0-9-]+$', name):
            await bot.send_room_text(room, "Filename '{}' should only contain a-z, A-Z, 0-9 or - ".format(name))
            return

        target_path = os.path.join(self.save_dir, ZGameModule.escape_room_id(room_id), game_id, name)
        if not os.path.exists(target_path):
            await bot.send_room_text(room, "Save file '{}' doesn't exist".format(name))
            return

        p = self.start_frotz(game)
        self.send_prefix(p, game)
        self.send_data_to_process(p, '\n')
        data = self.load_game(p, room_id, game_id, name)
        if data is None:
            await bot.send_room_text(room, "No session found for game-id '{}'".format(game_id))
            return

        html_data = self.convert_to_html(data, room_id)

        self.save_game(p, room_id, game_id)
        self.quit_game(p)

        await bot.send_room_html(room, html_data)

    async def zdownload(self, bot, event, game_id, name, room, user):
        room_id = room.room_id
        game = self.games[game_id]

        if not re.match(r'^[a-zA-Z0-9-]+$', name):
            await bot.send_room_text(room, "Filename '{}' should only contain a-z, A-Z, 0-9 or - ".format(name))
            return

        target_path = os.path.join(self.save_dir, ZGameModule.escape_room_id(room_id), game_id, name)
        if not os.path.exists(target_path):
            await bot.send_room_text(room, "Save file '{}' doesn't exist".format(name))
            return

        file_url = self.client.upload(open(target_path, 'rb').read(), "application/octet-stream")
        await bot.send_room_file(
            room=room,
            url=file_url,
            name=game_id + '-' + name,
            mimetype="application/octet-stream")

    async def zlistsaves(self, bot, event, game_id, room, user):
        room_id = room.room_id

        specific_savegame_dir = os.path.join(self.save_dir, ZGameModule.escape_room_id(room_id), game_id)
        os.makedirs(specific_savegame_dir, exist_ok=True)
        filenames = [
            (f, os.path.getmtime(os.path.join(specific_savegame_dir, f)))
            for f in os.listdir(specific_savegame_dir)
            if os.path.isfile(os.path.join(specific_savegame_dir, f))
        ]
        print(specific_savegame_dir, filenames)
        filenames.sort(key=lambda x: x[1])
        html = E.TABLE()
        if not filenames:
            await bot.send_room_text(room, "No savegames for '{}' in this room".format(game_id))
            return

        for f, s in filenames:
            timestamp = datetime.fromtimestamp(s)
            html.append(E.TR(E.TD(timestamp.isoformat(' ')), E.TD(f)))

        html_data = lxml.html.tostring(html, pretty_print=True).decode('utf-8')
        await bot.send_room_html(room, html_data)

    async def zcontinue(self, bot, event, game_id, room, user):
        room_id = room.room_id
        game = self.games[game_id]

        p = self.start_frotz(game)
        self.send_prefix(p, game)
        self.send_data_to_process(p, '\n')
        data = self.restore_game(p, room_id, game_id)
        if data is None:
            await bot.send_room_text(room, "No session found for game-id '{}'".format(game_id))
            return

        html_data = self.convert_to_html(data, room_id)

        self.save_game(p, room_id, game_id)
        self.quit_game(p)

        await bot.send_room_html(room, html_data)

    async def zdirect(self, bot, event, mode, room, user):
        room_id = room.room_id
        sender_id = event.sender
        if mode.lower() == 'on':
            if room_id not in self.direct_mode:
                self.direct_mode[room_id] = set()

            self.direct_mode[room_id].add(sender_id)
            await bot.send_room_text(room, "Direct mode enabled")

        else:
            if sender_id in self.direct_mode.get(room_id, set()):
                self.direct_mode[room_id].remove(sender_id)

            await bot.send_room_text(room, "Direct mode disabled, '{}' is required for commands".format(self.COMMAND_PREFIX))

    async def zcommand(self, bot, event, command, room, user):
        room_id = room.room_id

        if room_id not in self.sessions:
            await bot.send_room_text(room, room, "No active session, use !zstart to start a game")
            return

        game_id = self.sessions[room_id]
        game = self.games[game_id]

        p = self.start_frotz(game)
        self.send_prefix(p, game)
        self.send_data_to_process(p, '\n')
        self.restore_game(p, room_id, game_id)

        command = command + '\n'
        data = self.send_data_to_process(p, command)
        html_data = self.convert_to_html(data, room_id)

        # send a hash and anew line in case we're stuck in a follow-up prompt
        # to clarify, which would case the save to fail
        # a hash also won't advance the time or move counter
        self.send_data_to_process(p, '#\n')

        self.save_game(p, room_id, game_id)
        self.quit_game(p)

        await bot.send_room_html(room, html_data)

    # most things below this line probably can be refactored into a frotz module

    @staticmethod
    def get_default_dfrotz_path():
        return os.path.abspath(os.path.join(__file__, "../../../bin/dfrotz"))

    @staticmethod
    def read_stdout_from_process(process):
        data = os.read(process.stdout.fileno(), 100000)
        data = data.decode('utf-8')
        print('---')
        print(data)
        print('---')
        return data

    @staticmethod
    def read_stderr_from_process(process):
        try:
            data = os.read(process.stderr.fileno(), 100000)
        except BlockingIOError:
            return ''

        data = data.decode('utf-8')
        print('---stderr---')
        print(data)
        print('---stderr---')
        return data

    @staticmethod
    def escape_room_id(room_id):
        return re.sub(r'[^a-zA-Z0-9._-]', '_', room_id)

    @staticmethod
    def get_temporary_filename():
        filename = ''
        while len(filename) < 32:
            filename += random.choice(string.ascii_lowercase + string.digits)

        return '/tmp/' + filename

    @staticmethod
    def count_leading_spaces(s):
        for i in range(len(s)):
            if s[i] != ' ':
                return i

    @staticmethod
    def add_text(element, text):
        children = element.getchildren()
        if children:
            last_element = children[-1]
            if last_element.tail:
                last_element.tail += '\n' + text
            else:
                last_element.tail = text

        else:
            if element.text:
                element.text += '\n' + text
            else:
                element.text = text

    @staticmethod
    def remove_trailing_brs(element):
        children = element.getchildren()
        for child in children:
            ZGameModule.remove_trailing_brs(child)

        if children:
            last_child = children[-1]
            if last_child.tag == 'br' and not last_child.tail:
                element.remove(last_child)

    def convert_to_html(self, data, room_id):
        if room_id not in self.status_line_cache:
            self.status_line_cache[room_id] = {}

        data = data.rstrip('> \n\r')
        data = data.replace('</i><i>', '')
        data = data.replace('</b><b>', '')
        lines = data.split('\n')

        main_div = E.DIV()

        first_line_chunks = re.split('    +', lines[0], 1)
        if len(first_line_chunks) > 1:
            lines.pop(0)
            location, score = first_line_chunks
            location = location.strip()
            location_full = location
            score = score.strip()

            # Make It Good uses " - ..." on the second line as extension of the
            # location in the status line
            if lines:
                line = lines[0].strip()
                if line.startswith('- '):
                    lines.pop(0)
                    location_full = location + ' (' + line[2:] + ')'

            if location_full != self.status_line_cache[room_id].get('location', ''):
                main_div.append(E.DIV(E.CLASS('location'), location_full))

            if score != self.status_line_cache[room_id].get('score', ''):
                main_div.append(E.DIV(E.CLASS('score'), score))
        else:
            location = None
            location_full = None
            score = None

        self.status_line_cache[room_id]['location'] = location_full
        self.status_line_cache[room_id]['score'] = score

        base_leading_spaces = min(self.count_leading_spaces(s) for s in lines if s.strip(". "))

        current = main_div
        for raw_line in lines:
            line = raw_line.strip()
            if line == '.':
                line = ''

            line_without_tags = re.sub(r'</?[bi]>', '', line)
            if location and line_without_tags.startswith(location):
                continue

            if line.startswith('[') and line.endswith(']'):
                current.attrib['title'] = line
                continue

            if current.tag != 'p' and not line:
                continue

            if current.tag != 'p' or not line:
                current = E.P()
                main_div.append(current)

            fixed_line = raw_line
            if base_leading_spaces > 0 and fixed_line.startswith(" " * base_leading_spaces):
                fixed_line = fixed_line[base_leading_spaces:]

            fixed_line = fixed_line.replace("  ", "\xa0 ")

            self.add_text(current, fixed_line)

            if fixed_line and len(fixed_line) < 50:
                br = E.BR()
                current.append(br)

        self.remove_trailing_brs(main_div)

        html_data = lxml.html.tostring(main_div, pretty_print=True).decode('utf-8')
        html_data = html_data.replace("&lt;i&gt;", '<i>')
        html_data = html_data.replace("&lt;/i&gt;", '</i>')
        html_data = html_data.replace("&lt;b&gt;", '<b>')
        html_data = html_data.replace("&lt;/b&gt;", '</b>')

        return html_data

    def update_status_line_cache(self, room_id, new_status_line_cache):
        if room_id not in self.status_line_cache:
            self.status_line_cache[room_id] = {}

        self.status_line_cache[room_id].update(new_status_line_cache)

    def start_frotz(self, game):
        command = [self.executable, '-w', '100000', '-h', '100000', game['file']]
        print('running:', ' '.join(command))
        p = Popen(command, stdout=PIPE, stdin=PIPE, stderr=PIPE)

        # set the O_NONBLOCK flag of p.stdout file descriptor:
        flags = fcntl(p.stdout.fileno(), F_GETFL) # get current p.stdout flags
        fcntl(p.stdout.fileno(), F_SETFL, flags | os.O_NONBLOCK)

        # set the O_NONBLOCK flag of p.stderr file descriptor:
        flags = fcntl(p.stderr.fileno(), F_GETFL) # get current p.stderr flags
        fcntl(p.stderr.fileno(), F_SETFL, flags | os.O_NONBLOCK)

        time.sleep(0.1)
        data = self.read_stderr_from_process(p)
        if data:
            raise Exception(data)

        return p

    def send_prefix(self, process, game):
        prefix = game.get('command_prefix', '').replace(r'\\', '\\').replace(r'\n', '\n')
        if not prefix:
            return ''

        return self.send_data_to_process(process, prefix)

    def send_options(self, process, game):
        return self.send_data_to_process(process, r'\lt\cm\w')

    def send_data_to_process(self, process, data):
        print("sending: '{}'".format(data))
        process.stdin.write(data.encode('utf-8'))
        process.stdin.flush()
        time.sleep(0.1)
        return ZGameModule.read_stdout_from_process(process)

    def get_session_file(self, room_id, game_id):
        file_path = os.path.join(self.session_dir, ZGameModule.escape_room_id(room_id), game_id)
        os.makedirs(os.path.abspath(os.path.join(file_path, os.pardir)), exist_ok=True)
        return file_path

    def save_game(self, process, room_id, game_id):
        self.sessions[room_id] = game_id
        session_file = self.get_session_file(room_id, game_id)

        temp_file = ZGameModule.get_temporary_filename()
        payload = "save\n{}\n".format(temp_file)
        self.send_data_to_process(process, payload)
        statinfo = os.stat(temp_file)
        # only overwrite old file if the save didn't fail
        if statinfo.st_size != 0:
            shutil.move(temp_file, session_file)

        self.save_sessions()

    def restore_game(self, process, room_id, game_id):
        session_file = self.get_session_file(room_id, game_id)
        if not os.path.exists(session_file):
            return None

        temp_file = ZGameModule.get_temporary_filename()
        shutil.copy(session_file, temp_file)
        self.send_data_to_process(process, "restore\n")
        return self.send_data_to_process(process, temp_file + '\n')

    def load_game(self, process, room_id, game_id, filename):
        saved_file = os.path.join(self.save_dir, ZGameModule.escape_room_id(room_id), game_id, filename)

        temp_file = ZGameModule.get_temporary_filename()
        shutil.copy(saved_file, temp_file)
        payload = "restore\n{}\n".format(temp_file)

        return self.send_data_to_process(process, payload)

    def get_sessions_manifest_file(self):
        return os.path.join(self.session_dir, 'sessions')

    def save_sessions(self):
        with open(self.get_sessions_manifest_file(), 'w') as f:
            json.dump(self.sessions, f)

    def load_sessions(self):
        file_path = self.get_sessions_manifest_file()
        if not os.path.exists(file_path):
            self.sessions = {}
            return

        with open(file_path, 'r') as f:
            self.sessions = json.load(f)

    def quit_game(self, process):
        process.kill()
