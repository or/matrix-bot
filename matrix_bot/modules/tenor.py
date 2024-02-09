#!/usr/bin/env python3
import json
import logging
import random
from io import BytesIO

import requests

from matrix_bot.modules.base import MatrixBotModule, arg


class TenorModule(MatrixBotModule):
    @staticmethod
    def create(config):
        if "tenor" in config and "api_key" in config["tenor"]:
            return TenorModule(config)

        return None

    def register_commands(self):
        self.add_command(
            "!tenor",
            "!ten",
            "!gif",
            ".gif",
            arg("search", self.validate_search, multi_word=True),
            callback=self.search_tenor,
            help="search tenor",
        )

    def validate_search(self, value):
        pass

    async def search_tenor(self, bot, event, search, room, user):
        search = search.replace(" ", "+")
        response = requests.get(
            "https://api.tenor.com/v1/search",
            params=dict(
                api_key=self.config["tenor"]["api_key"],
                limit=20,
                media_filter="minimal",
                q=search,
            ),
        )
        results = json.loads(response.content.decode("utf-8"))

        if "results" not in results:
            await bot.send_room_text(room, "It appears something went wrong.")
            return

        if not results["results"]:
            await bot.send_room_text(room, "That doesn't exist.")
            return

        match = random.choice(results["results"])
        url = match["media"][0]["gif"]["url"]
        height = match["media"][0]["gif"]["dims"][1]
        width = match["media"][0]["gif"]["dims"][0]
        size = match["media"][0]["gif"]["size"]
        image_response = requests.get(url)
        mimetype = image_response.headers.get("Content-Type")

        title = match["title"].strip()
        if not title:
            title = (
                match["itemurl"]
                .strip("/")
                .split("/")[-1]
                .rstrip("0123456789")
                .rstrip("-")
            )

        if not title:
            title = "no-title"

        def data_provider(_x, _y):
            return BytesIO(image_response.content)

        response, error = await bot.client.upload(
            data_provider, content_type="image/gif"
        )
        if error:
            print(error)
            await bot.send_room_text(room, "Something went wrong.")
            return

        image_url = response.content_uri
        await bot.send_room_image(
            room=room,
            url=image_url,
            name=title + ".gif",
            extra=dict(mimetype=mimetype, h=height, w=width, size=size),
        )
