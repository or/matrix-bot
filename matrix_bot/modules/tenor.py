#!/usr/bin/env python3
import json
import logging
import random
import requests
from io import BytesIO

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

    async def search_tenor(self, bot, event, search, room, user):
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
                and event.sender in self.config['users']['female'].split()):
            title = 'Miss'

        if 'results' not in results:
            await bot.send_room_text(f"It appears something went wrong, {title}.")
            return

        if not results['results']:
            await bot.send_room_text(f"That doesn't exist, {title}.")
            return

        match = random.choice(results['results'])
        title = match['title']
        url = match['media'][0]['gif']['url']
        height = match['media'][0]['gif']['dims'][1]
        width = match['media'][0]['gif']['dims'][0]
        size = match['media'][0]['gif']['size']
        image_response = requests.get(url)
        mimetype = image_response.headers.get('Content-Type')

        def data_provider(_x, _y):
            return BytesIO(image_response.content)

        response, error = await bot.client.upload(data_provider,
                                                  content_type="image/gif")
        if error:
            print(error)
            await bot.send_room_text("Something went wrong.")
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
