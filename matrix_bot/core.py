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
from datetime import datetime

import requests

from lxml.html import builder as E

from bs4 import BeautifulSoup
from nio import AsyncClient, MatrixRoom, InviteEvent, RoomMessageText

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

    async def send_room_text(self, room, content):
        self.client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={
                "body": content,
                "msgtype": "m.text"
            })

    async def send_room_html(self, room, content):
        await self.client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={
                "body": re.sub('<[^<]+?>', '', content),
                "msgtype": "m.text",
                "format": "org.matrix.custom.html",
                "formatted_body": content,
            })

    async def send_room_content(self, room, msgtype, url, name, extra):
        await self.client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={
                "body": name,
                "msgtype": msgtype,
                "url": url,
                "info": extra,
            })

    async def send_room_image(self, room, url, name, extra):
        await self.send_room_content(room=room, msgtype="m.image", url=url, name=name, extra=extra)

    async def send_room_file(self, room, url, name, extra):
        await self.send_room_content(room=room, msgtype="m.file", url=url, name=name, extra=extra)

    async def on_room_message(self, room, event):
        if event.sender == self.user_id:
            return

        age = datetime.now().timestamp() * 1000 - event.server_timestamp
        if age > 5000:
            return

        for module in self.modules:
            try:
                await module.handle_room_message(self, room, event)
            except Exception as e:
                if self.debug:
                    msg = E.PRE(traceback.format_exc())
                    html_data = lxml.html.tostring(msg).decode('utf-8')
                    await self.send_room_html(room=room, content=html_data)
                else:
                    await self.send_room_text(room=room, content="There was an error.")

    async def on_invite(self, room, event):
        self.client.join(room.room_id)


    async def run(self):
        base_url = self.config['main']['base_url']
        self.user_id = self.config['main']['user_id']
        password = self.config['main']['password']
        device_id = self.config['main']['device_id']

        self.client = AsyncClient(homeserver=base_url, user=self.user_id)
        self.client.add_event_callback(self.on_invite, InviteEvent)
        self.client.add_event_callback(self.on_room_message, RoomMessageText)

        await self.client.login(password=password, device_name=device_id)
        await self.client.sync_forever(timeout=30000)
