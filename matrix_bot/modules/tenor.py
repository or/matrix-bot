#!/usr/bin/env python3
import json
import logging
import random
import requests

from matrix_client.room import Room

from matrix_bot.modules.base import MatrixBotModule, arg

class TenorModule(MatrixBotModule):
    @staticmethod
    def create(config):
        if 'tenor' in config and 'api_key' in config['tenor']:
            return TenorModule(config)

        return None

    def register_commands(self):
        self.add_command(
            '!tenor', '!ten', '!gif', '.gif',
            arg('search', self.validate_search, multi_word=True),
            callback=self.search_tenor,
            help="search tenor")

    def validate_search(self, value):
        pass

    def search_tenor(self, event, search, room_, user_):
        search = search.replace(' ', '+')
        response = requests.get("https://api.tenor.com/v1/search",
                                params=dict(api_key=self.config['tenor']['api_key'],
                                            limit=20,
                                            media_filter='minimal',
                                            q=search))
        results = json.loads(response.content.decode('utf-8'))

        title = 'Sir'
        if ('users' in self.config
                and 'female' in self.config['users']
                and event['sender'] in self.config['users']['female'].split()):
            title = 'Miss'

        if 'results' not in results:
            room_.send_text(f"It appears something went wrong, {title}.")
            return

        if not results['results']:
            room_.send_text(f"That doesn't exist, {title}.")
            return

        match = random.choice(results['results'])
        title = match['title']
        url = match['media'][0]['gif']['url']
        height = match['media'][0]['gif']['dims'][1]
        width = match['media'][0]['gif']['dims'][0]
        size = match['media'][0]['gif']['size']
        image_response = requests.get(url)
        mimetype = image_response.headers.get('Content-Type')
        image_url = self.client.upload(image_response.content, "image/gif")
        room_.send_image(url=image_url,
                         name=title,
                         mimetype=mimetype,
                         h=height,
                         w=width,
                         size=size)
