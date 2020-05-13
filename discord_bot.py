import requests
import discord
import time


class Bot:
    def __init__(self, bot_token, channel_id, msg_id, embed_template):
        self.__bot_token = bot_token
        self.__headers = {"Authorization": "Bot {token}".format(token=self.__bot_token)}
        self.__channel_id = channel_id
        self.__msg_id = msg_id
        self.__embed_template = embed_template
        self.__client = discord.Client()
        self.on_ready = self.__client.event(self.on_ready)

    def init_bot(self):
        self.__client.run(self.__bot_token)

    async def on_ready(self):
        print("Logged in as")
        print(self.__client.user.name)
        print(self.__client.user.id)
        print("------")
        self.__new_msg()
        await self.__client.close()

    def format_discord_list(self, list_to_format):
        return "`" + str(list_to_format) + "`"

    def __get_formatted_embed(self, **kwargs):
        return {
            "title": self.__embed_template["title"],
            "description": self.__embed_template["description"].format(**kwargs),
            "color": self.__embed_template["color"],
        }

    def __new_msg(self):
        # If the response is unathorized then that usually means the bot hasn't connected to a gateway.
        # If that happens then we initialize the bot with discord.py
        response = requests.post(
            f"https://discordapp.com/api/channels/{self.__channel_id}/messages",
            headers=self.__headers,
            json={"embed": self.__embed},
        )
        response = response.json()
        if response.get("message") == "Unauthorized":
            init_bot()
        else:
            return response.get("id")
        return None

    def update_discord(self, **kwargs):
        self.__embed = self.__get_formatted_embed(**kwargs)
        response = requests.patch(
            f"https://discordapp.com/api/channels/{self.__channel_id}/messages/{self.__msg_id}",
            headers=self.__headers,
            json={"embed": self.__embed},
        )
        if response.status_code == 403 or response.status_code == 404:
            id = self.__new_msg()
            return id
        return self.__msg_id
