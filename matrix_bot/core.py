#!/usr/bin/env python3
import configparser
import inspect
import json
import logging
import lxml.html
import os.path
import re
import sys
import time
import traceback

import requests

from lxml.html import builder as E

from bs4 import BeautifulSoup
from matrix_client.api import MatrixRequestError
from matrix_client.client import MatrixClient
from matrix_client.room import Room

from matrix_bot.modules.base import MatrixBotModule
from matrix_bot import modules

def read_base64_file(filename):
    """Read a base64 file, dropping any CR/LF characters"""
    with open(filename, "rb") as f:
        return f.read().replace(b"\r\n", b"")


class MatrixBot:
    def __init__(self, config):
        self.config = config
        self.modules = []
        if self.config['main'].get('debug', '').lower() == 'true':
            self.debug = True
        else:
            self.debug = False

        for key, value in modules.__dict__.items():
            if inspect.isclass(value) and issubclass(value, MatrixBotModule):
                print("loading {}...".format(value))
                m = value.create(config)
                if m:
                    self.modules.append(m)


    def on_event(self, event):
        print(event)
        if event['type'] == 'm.room.message':
            self.on_room_message(room_id=event['room_id'],
                                 sender_id=event['sender'],
                                 content=event['content'],
                                 event=event)

        for module in self.modules:
            try:
                module.process(self.client, event)
            except Exception as e:
                room = Room(self.client, event['room_id'])
                if self.debug:
                    msg = E.PRE(traceback.format_exc())
                    html_data = lxml.html.tostring(msg).decode('utf-8')
                    room.send_html(html_data)
                else:
                    room.send_text("There was an error.")

    def on_room_message(self, room_id, sender_id, content, event):
        pass


    def on_invite(self, room_id, event):
        self.client.join_room(room_id)


    def run(self):
        base_url = self.config['main']['base_url']
        user_id = self.config['main']['user_id']
        password = self.config['main']['password']
        device_id = self.config['main']['device_id']

        self.client = MatrixClient(base_url=base_url)
        self.client.login(user_id, password, device_id=device_id)

        self.client.add_invite_listener(self.on_invite)
        self.client.add_listener(self.on_event)
        self.client.start_listener_thread()

        while True:
            time.sleep(0.5)
