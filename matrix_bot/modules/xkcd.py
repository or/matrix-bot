#!/usr/bin/env python3
import json
import logging
import random
import re

import requests
from bs4 import BeautifulSoup

from matrix_bot.modules.base import MatrixBotModule, arg


class XkcdModule(MatrixBotModule):
    @staticmethod
    def create(config):
        if (
            "google" in config
            and "api_key" in config["google"]
            and "cx" in config["google"]
        ):
            return XkcdModule(config)

        return None

    def register_commands(self):
        self.add_command(
            "!xkcd",
            arg("search", self.validate_search, multi_word=True),
            callback=self.search_xkcd,
            help="search giphy",
        )

    def validate_search(self, value):
        pass

    def search_xkcd(self, event, search, room_, user_):
        search = search.replace(" ", "+")
        search_response = requests.get(
            "https://www.googleapis.com/customsearch/v1/",
            params=dict(
                key=self.config["google"]["api_key"],
                cx=self.config["google"]["cx"],
                q="site:xkcd.com " + search,
            ),
        )
        results = json.loads(search_response.content.decode("utf-8"))
        print(search_response.content)
        links = []
        for item in results["items"]:
            link = item["link"]
            mo = re.match(r"https://xkcd.com/\d+/?", link)
            if mo:
                links.append(link)

        if not links:
            return

        found_xkcd_link = random.choice(links)
        xkcd_response = requests.get(found_xkcd_link)
        print(xkcd_response.content)
        soup = BeautifulSoup(xkcd_response.content, "html.parser")
        transcript = soup.find(id="transcript").string
        comic = soup.find(id="comic")
        if not comic:
            return

        imgs = comic.find_all("img")
        if not imgs:
            return

        img = imgs[0]

        alt_text = img.get("title")
        img_url = img.get("src")

        if img_url.startswith("//"):
            img_url = "https://xkcd.com" + img_url[1:]

        elif not img_url.startswith("http"):
            img_url = found_xkcd_link + img_url

        image_response = requests.get(img_url)
        mimetype = image_response.headers.get("Content-Type")
        image_url = self.client.upload(image_response.content, "image/gif")
        room_.send_image(
            url=image_url,
            name=alt_text,
            mimetype=mimetype,
            size=len(image_response.content),
        )
