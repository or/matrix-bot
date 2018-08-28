#!/usr/bin/env python3
import html
import json
import logging
import os
import re
import requests
import shutil
import string
import tempfile
import time
import lxml.html

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

    @staticmethod
    def convert_to_html(data):
        # print(data)
        data = data.rstrip('> \n\r')
        lines = data.split('\n')
        status_line = lines.pop(0)
        location, score = re.split('    +', status_line, 1)
        location = location.strip()
        score = score.strip()

        main_div = E.DIV()
        main_div.append(E.DIV(E.CLASS('location'), location))
        main_div.append(E.DIV(E.CLASS('score'), score))

        current = main_div
        for raw_line in lines:
            line = raw_line.strip()
            if line == '.':
                line = ''

            if line.startswith(location):
                continue

            if line.startswith('[') and line.endswith(']'):
                current = main_div
                hint = E.DIV(E.CLASS('hint'), line)
                current.append(hint)
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
        self.load_sessions()

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
            html_data = "<table>\n"
            html_data += "  <tr><th>id</th><th>name</th></tr>\n"
            for unused_id, game in sorted(self.games.items(), key=lambda x: x[1]['name']):
                html_data += "  <tr><td>{id}</td><td>{name}</td></tr>\n".format(**game)
            html_data += "</table>"
            room.send_html(html_data)
            return

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
            html_data = ZGameModule.convert_to_html(data)

            self.save_game(p, room_id, game_id)
            self.quit_game(p)

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
            html_data = ZGameModule.convert_to_html(data)

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

    def get_session_file(self, room_id, game_id):
        escaped_room_id = re.sub(r'[^a-zA-Z0-9._-]', '_', room_id)
        file_path = os.path.join(self.session_dir, escaped_room_id, game_id)
        os.makedirs(os.path.abspath(os.path.join(file_path, os.pardir)), exist_ok=True)
        return file_path

    def save_game(self, process, room_id, game_id):
        self.sessions[room_id] = game_id
        session_file = self.get_session_file(room_id, game_id)

        temp_file = ZGameModule.get_temporary_filename()
        # file definitely exists, so add "y\n" to overwrite it
        payload = "save\n{}\ny\n".format(temp_file)
        self.send_data_to_process(process, payload)
        statinfo = os.stat(temp_file)
        # only overwrite old file if the save didn't fail
        if statinfo.st_size != 0:
            shutil.move(temp_file, session_file)

        self.save_sessions()

    def restore_game(self, process, room_id, game_id):
        session_file = self.get_session_file(room_id, game_id)

        temp_file = ZGameModule.get_temporary_filename()
        shutil.copy(session_file, temp_file)
        payload = "restore\n{}\n".format(temp_file)

        self.send_data_to_process(process, payload)

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
        pid, file_path = tempfile.mkstemp()
        os.close(pid)
        return file_path
