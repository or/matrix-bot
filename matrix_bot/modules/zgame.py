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

from matrix_client.room import Room

from matrix_bot.modules.base import MatrixBotModule

class ZGameModule(MatrixBotModule):
    @staticmethod
    def create(config):
        if 'zgame' in config:
            return ZGameModule(config)

        return None

    @staticmethod
    def get_default_dfrotz_path():
        return os.path.abspath(os.path.join(__file__, "../../../bin/dfrotz"))

    def convert_to_html(self, data, room_id):
        if room_id not in self.status_line_cache:
            self.status_line_cache[room_id] = {}

        data = data.rstrip('> \n\r')
        lines = data.split('\n')

        main_div = E.DIV()

        first_line_chunks = re.split('    +', lines[0], 1)
        if len(first_line_chunks) > 1:
            lines.pop(0)
            location, score = first_line_chunks
            location = location.strip()
            score = score.strip()

            # Make It Good uses " - ..." on the second line as extension of the
            # location in the status line
            if lines:
                line = lines[0].strip()
                if line.startswith('- '):
                    lines.pop(0)
                    location = location + ' (' + line[2:] + ')'

            if location != self.status_line_cache[room_id].get('location', ''):
                main_div.append(E.DIV(E.CLASS('location'), location))

            if score != self.status_line_cache[room_id].get('score', ''):
                main_div.append(E.DIV(E.CLASS('score'), score))
        else:
            location = None
            score = None

        self.status_line_cache[room_id]['location'] = location
        self.status_line_cache[room_id]['score'] = score

        current = main_div
        for raw_line in lines:
            line = raw_line.strip()
            if line == '.':
                line = ''

            if location and line.startswith(location):
                continue

            if line.startswith('[') and line.endswith(']'):
                current.attrib['title'] = line
                continue

            if line.startswith('- '):
                if current.tag != 'ul':
                    current = E.UL()
                    main_div.append(current)

                current.append(E.LI(line[2:]))
                continue

            elif current.tag == 'ul':
                current = main_div
                continue

            if raw_line.startswith('    '):
                if current.tag != 'pre':
                    current = E.PRE()
                    main_div.append(current)

                if current.text:
                    current.text += '\n' + raw_line
                else:
                    current.text = raw_line

                continue

            elif line and current.tag == 'pre':
                current = main_div

            if not line:
                if current.tag == 'pre':
                    continue

            if current.tag != 'p' and not line:
                continue

            if current.tag != 'p' or not line:
                current = E.P()
                main_div.append(current)

            if current.text:
                current.text += '\n' + line
            else:
                current.text = line

        return lxml.html.tostring(main_div, pretty_print=True).decode('utf-8')

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

    def update_status_line_cache(self, room_id, new_status_line_cache):
        if room_id not in self.status_line_cache:
            self.status_line_cache[room_id] = {}

        self.status_line_cache[room_id].update(new_status_line_cache)

    def process(self, client, event):
        if event['type'] != 'm.room.message':
            return

        room_id = event['room_id']
        sender_id = event['sender']
        content = event['content']

        if content['msgtype'] != 'm.text':
            return

        words = [word.strip() for word in content['body'].split() if word.strip()]
        if not words:
            return

        room = Room(client, room_id)

        command = words[0].lower()
        if command in ['!zlist', '!zl']:
            html = E.TABLE()
            html.append(E.TR(E.TH('id'), E.TH('name')))
            for unused_id, game in sorted(self.games.items(), key=lambda x: x[1]['name']):
                html.append(E.TR(E.TD(game['id']), E.TD(game['name'])))

            html_data = lxml.html.tostring(html, pretty_print=True).decode('utf-8')
            room.send_html(html_data)

        elif command in ['!zhelp', '!zh']:
            html = E.DIV(
                E.P("Command list:"),
                E.TABLE(
                    E.TR(
                        E.TH("command"),
                        E.TH("arguments"),
                        E.TH("details")
                    ),
                    E.TR(
                        E.TD("!zhelp, !zh"),
                        E.TD(""),
                        E.TD("this help")
                    ),
                    E.TR(
                        E.TD("!zlist, !zl"),
                        E.TD(""),
                        E.TD("list all installed games and their IDs")
                    ),
                    E.TR(
                        E.TD("!zstart, !zs"),
                        E.TD("<game-id>"),
                        E.TD("start a new session of game <game-id>, replaces the current session")
                    ),
                    E.TR(
                        E.TD("!zsave"),
                        E.TD("<name>\xa0[overwrite]"),
                        E.TD("save current session to <name>, if it already exists, then [overwrite] must be specified")
                    ),
                    E.TR(
                        E.TD("!zload, !zl"),
                        E.TD("<game-id>\xa0<name>"),
                        E.TD("load a new save game of game <game-id>, replacing the current session")
                    ),
                    E.TR(
                        E.TD("!zcontinue, !zc"),
                        E.TD("<game-id>"),
                        E.TD("continue the last session of game <game-id> that was played, if there is one")
                    ),
                    E.TR(
                        E.TD("\\"),
                        E.TD("<commands>"),
                        E.TD("send commands to the game itself, e.g.: \look around")
                    ),
                )
            )
            html_data = lxml.html.tostring(html, pretty_print=True).decode('utf-8')
            room.send_html(html_data)

        elif command in ['!zstart', '!zs']:
            if len(words) < 2:
                room.send_text("Use: !zstart <game-id>")
                return

            game_id = words[1].lower()
            if game_id not in self.games:
                room.send_text("Unknown game-id '{}'".format(game_id))
                return

            game = self.games[game_id]

            p = self.start_frotz(game)
            self.send_prefix(p, game)

            data = self.send_data_to_process(p, '\n')
            html_data = self.convert_to_html(data, room_id)

            self.save_game(p, room_id, game_id)
            self.quit_game(p)

            room.send_html(html_data)

        elif command in ['!zcontinue', '!zc']:
            if len(words) < 2:
                room.send_text("Use: !zcontinue <game-id>")
                return

            game_id = words[1].lower()
            if game_id not in self.games:
                room.send_text("Unknown game-id '{}'".format(game_id))
                return

            game = self.games[game_id]

            p = self.start_frotz(game)
            self.send_prefix(p, game)
            self.send_data_to_process(p, '\n')
            data = self.restore_game(p, room_id, game_id)
            if data is None:
                room.send_text("No session found for game-id '{}'".format(game_id))
                return

            html_data = self.convert_to_html(data, room_id)

            self.save_game(p, room_id, game_id)
            self.quit_game(p)

            room.send_html(html_data)

        elif command in ['!zsave']:
            if len(words) < 2:
                room.send_text("Use: !zsave <save-name> [overwrite]")
                return

            filename = words[1]
            if not re.match(r'^[a-zA-Z0-9-]+$', filename):
                room.send_text("Filename '{}' should only contain a-z, A-Z, 0-9 or - ".format(filename))
                return

            overwrite = False
            if len(words) > 2 and words[2].lower() != 'overwrite':
                room.send_text("Can't understand argument '{}', should be 'overwrite'".format(words[2]))
                return

            elif len(words) > 2 and words[2].lower() == 'overwrite':
                overwrite = True

            if room_id not in self.sessions:
                room.send_text("No session to save")
                return

            game_id = self.sessions[room_id]
            game = self.games[game_id]

            target_path = os.path.join(self.save_dir, ZGameModule.escape_room_id(room_id), game_id, filename)
            if os.path.exists(target_path) and not overwrite:
                room.send_text("Save file '{}' exists, pick another one or specify 'overwrite' as third argument".format(filename))
                return

            os.makedirs(os.path.abspath(os.path.join(target_path, os.pardir)), exist_ok=True)
            shutil.copy(self.get_session_file(room_id, game_id), target_path)
            room.send_text("Saved to file '{}' for game '{}'".format(filename, game_id))

        elif command in ['!zload', '!zl']:
            if len(words) < 3:
                room.send_text("Use: !zload <game-id> <save-name>")
                return

            game_id = words[1].lower()
            if game_id not in self.games:
                room.send_text("Unknown game-id '{}'".format(game_id))
                return

            game = self.games[game_id]

            filename = words[2]
            if not re.match(r'^[a-zA-Z0-9-]+$', filename):
                room.send_text("Filename '{}' should only contain a-z, A-Z, 0-9 or - ".format(filename))
                return

            target_path = os.path.join(self.save_dir, ZGameModule.escape_room_id(room_id), game_id, filename)
            if not os.path.exists(target_path):
                room.send_text("Save file '{}' doesn't exist".format(filename))
                return

            p = self.start_frotz(game)
            self.send_prefix(p, game)
            self.send_data_to_process(p, '\n')
            data = self.restore_game(p, room_id, game_id)
            if data is None:
                room.send_text("No session found for game-id '{}'".format(game_id))
                return

            html_data = self.convert_to_html(data, room_id)

            self.save_game(p, room_id, game_id)
            self.quit_game(p)

            room.send_html(html_data)

        elif command in ['!zlistsaves', '!zlistsave', '!zls']:
            if len(words) < 2:
                room.send_text("Use: !zlistsaves <game-id>")
                return

            game_id = words[1].lower()
            if game_id not in self.games:
                room.send_text("Unknown game-id '{}'".format(game_id))
                return

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
                room.send_text("No savegames for '{}' in this room".format(game_id))
                return

            for f, s in filenames:
                timestamp = datetime.fromtimestamp(s)
                html.append(E.TR(E.TD(timestamp.isoformat(' ')), E.TD(f)))

            html_data = lxml.html.tostring(html, pretty_print=True).decode('utf-8')
            room.send_html(html_data)

        elif command.startswith('\\'):
            full_command = ' '.join(words)[1:]
            if not full_command:
                room.send_text("Use: \<command>")
                return

            if room_id not in self.sessions:
                room.send_text("No active session, use !zstart to start a game")
                return

            game_id = self.sessions[room_id]
            game = self.games[game_id]

            p = self.start_frotz(game)
            self.send_prefix(p, game)
            self.send_data_to_process(p, '\n')
            self.restore_game(p, room_id, game_id)

            command = full_command + '\n'
            data = self.send_data_to_process(p, command)
            html_data = self.convert_to_html(data, room_id)

            self.save_game(p, room_id, game_id)
            self.quit_game(p)

            room.send_html(html_data)

    def start_frotz(self, game):
        p = Popen([self.executable, '-w', '100000', '-h', '100000', game['file']],
                    stdout=PIPE, stdin=PIPE, stderr=PIPE)

        # set the O_NONBLOCK flag of p.stdout file descriptor:
        flags = fcntl(p.stdout, F_GETFL) # get current p.stdout flags
        fcntl(p.stdout, F_SETFL, flags | os.O_NONBLOCK)

        return p

    def send_prefix(self, process, game):
        prefix = game.get('command_prefix', '').replace(r'\\', '\\').replace(r'\n', '\n')
        if not prefix:
            return ''

        return self.send_data_to_process(process, prefix)

    def send_options(self, process, game):
        return self.send_data_to_process(process, r'\lt\cm\w')

    def send_data_to_process(self, process, data):
        print("sending:", data)
        process.stdin.write(data.encode('utf-8'))
        process.stdin.flush()
        time.sleep(0.1)
        return ZGameModule.read_stdout_from_process(process)

    @staticmethod
    def read_stdout_from_process(process):
        data = os.read(process.stdout.fileno(), 100000)
        data = data.decode('utf-8')
        print('---')
        print(data)
        print('---')
        return data

    @staticmethod
    def escape_room_id(room_id):
        return re.sub(r'[^a-zA-Z0-9._-]', '_', room_id)

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

    @staticmethod
    def get_temporary_filename():
        filename = ''
        while len(filename) < 32:
            filename += random.choice(string.ascii_lowercase + string.digits)

        return '/tmp/' + filename
