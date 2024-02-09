#!/usr/bin/env python3
import asyncio
import configparser
import logging

from matrix_bot.core import MatrixBot

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    config = configparser.ConfigParser()
    config.read("config.cfg")

    bot = MatrixBot(config)
    asyncio.get_event_loop().run_until_complete(bot.run())
