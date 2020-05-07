# Twitch-Stream-Downloader

Automatically archive live Twitch streams.

## Instructions

- Install `streamlink` so it can be run from command line
- Install requests `pip install requests`
- Either copy and rename or just rename the example config files (remove .example extension) and fill in your Twitch client-id and client-secret in `config.ini`
    - Fill in Discord webhook if you want a notification when the script unexpectedly exits.
    - Can also setup a Discord bot to show who is currently recording. It updates an embed in Discord with who is recording/online and offline. You currently have to manually setup the Discord channel and create a message you can edit with the bot. Then copy the channel id and message id into the config along with the bot token you created on Discord's dev portal.
- Run with `python record.py"`

- ***(optional) Setup Discord Bot***
    - [You have to setup the bot](https://discordpy.readthedocs.io/en/latest/discord.html) and create the Discord channel you want the bot in
    - Copy your bot token and id of the Discord channel into the config file

## Problems/Edge Cases

- This is a really rare situation but it's possible for a streamer to be live but not show up in any directories on Twitch(game category, following list) and they also don't show up as live on the Twitch API. This script won't detect the streamer as live since it relies on the API
    - A possible solution to this is to use streamlink to check if a stream is available, but this significantly increases the time it takes to check if a streamer is live (fractions of a second to a few seconds per streamer)

## Background Info
I originally used a similarly working script that I modified to look at what category the streamer is in but because of a few things Twitch has done the tool is no longer viable. So then I decided to make this because I wanted a tool to not only archive Twitch streams but also be able to limit what categories are archived since I mostly just wanted to archive if a streamer was in a non-gaming category. 
