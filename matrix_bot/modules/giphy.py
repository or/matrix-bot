#!/usr/bin/env python3
import json

import logging

import requests

from matrix_client.room import Room

from matrix_bot.modules.base import MatrixBotModule, arg

class GiphyModule(MatrixBotModule):
    @staticmethod
    def create(config):
        if 'giphy' in config and 'api_key' in config['giphy']:
            return GiphyModule(config)

        return None

    def register_commands(self):
        self.add_command(
            '!giphy', '!gif',
            arg('search', self.validate_search, multi_word=True),
            callback=self.search_giphy,
            help="search giphy")

    def validate_search(self, value):
        pass

    def search_giphy(self, event, search, room_, user_):
        search = search.replace(' ', '+')
        response = requests.get("https://api.giphy.com/v1/gifs/search",
                                params=dict(api_key=self.config['giphy']['api_key'],
                                            limit=1,
                                            lang='en',
                                            fmt='json',
                                            q=search))
        results = json.loads(response.content.decode('utf-8'))
        match = results['data'][0]
        title = match['title']
        url = match['images']['original']['url']
        height = match['images']['original']['height']
        width = match['images']['original']['width']
        size = match['images']['original']['size']
        image_response = requests.get(url)
        mimetype = image_response.headers.get('Content-Type')
        image_url = self.client.upload(image_response.content, "image/gif")
        room_.send_image(url=image_url,
                         name=title,
                         mimetype=mimetype,
                         h=height,
                         w=width,
                         size=size)
