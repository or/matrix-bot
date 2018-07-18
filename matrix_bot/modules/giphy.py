#!/usr/bin/env python3
import json

import logging

import requests

from matrix_client.room import Room

from matrix_bot.modules.base import MatrixBotModule

class GiphyModule(MatrixBotModule):
    @staticmethod
    def create(config):
        if 'giphy' in config and 'api_key' in config['giphy']:
            return GiphyModule(config)

        return None

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

        if words[0].lower() in ['!giphy', '!gif']:
            response = requests.get("https://api.giphy.com/v1/gifs/search",
                                    params=dict(api_key=self.config['giphy']['api_key'],
                                                limit=1,
                                                lang='en',
                                                fmt='json',
                                                q='+'.join(words[1:])))
            results = json.loads(response.content.decode('utf-8'))
            match = results['data'][0]
            title = match['title']
            url = match['images']['original']['url']
            height = match['images']['original']['height']
            width = match['images']['original']['width']
            size = match['images']['original']['size']
            image_response = requests.get(url)
            mimetype = image_response.headers.get('Content-Type')
            image_url = client.upload(image_response.content, "image/gif")
            room.send_image(url=image_url,
                            name=title,
                            mimetype=mimetype,
                            h=height,
                            w=width,
                            size=size)
