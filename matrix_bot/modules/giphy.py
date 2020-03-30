#!/usr/bin/env python3
import json
import logging
import random
from io import BytesIO

import requests

from matrix_bot.modules.base import MatrixBotModule, arg


class GiphyModule(MatrixBotModule):
    @staticmethod
    def create(config):
        if 'giphy' in config and 'api_key' in config['giphy']:
            return GiphyModule(config)

        return None

    def register_commands(self):
        self.add_command(
            '!giphy',
            arg('search', self.validate_search, multi_word=True),
            callback=self.search_giphy,
            help="search giphy")

    def validate_search(self, value):
        pass

    async def search_giphy(self, bot, event, search, room, user):
        search = search.replace(' ', '+')
        response = requests.get("https://api.giphy.com/v1/gifs/search",
                                params=dict(api_key=self.config['giphy']['api_key'],
                                            limit=100,
                                            lang='en',
                                            fmt='json',
                                            q=search))
        results = json.loads(response.content.decode('utf-8'))
        match = random.choice(results['data'])
        title = match['title']
        url = match['images']['original']['url']
        height = match['images']['original']['height']
        width = match['images']['original']['width']
        size = match['images']['original']['size']
        image_response = requests.get(url)
        mimetype = image_response.headers.get('Content-Type')
        def data_provider(_x, _y):
            return BytesIO(image_response.content)

        response, error = await bot.client.upload(data_provider,
                                                  content_type="image/gif")
        if error:
            print(error)
            await bot.send_room_text(room, "Something went wrong.")
            return

        image_url = response.content_uri
        await bot.send_room_image(
            room,
            url=image_url,
            name=title,
            extra=dict(
                mimetype=mimetype,
                h=height,
                w=width,
                size=size))
