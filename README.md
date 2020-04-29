# Twitch-Stream-Downloader

Automatically archive live Twitch streams.

## Instructions

- Install `streamlink`
- Install requests `pip install requests`
- Either copy and rename or just rename the example config files (remove .example extension) and fill in your Twitch client-id and client-secret in `config.ini`
    - Can fill in Discord webhook if you want a notification when the script unexpectedly exits.
    - Can also setup a Discord bot to show who is currently recording. It updates an embed in Discord with who is recording/online and offline. You currently have to manually setup the Discord channel and create a message you can edit with the bot. Then copy the channel id and message id into the config along with the bot token you created on Discord's dev portal.
- Run with `python record.py"`

- ***(optional) Setup Discord Bot***
    - [You have to setup the bot](https://discordpy.readthedocs.io/en/latest/discord.html) and create the Discord channel you want the bot in
    - Copy your bot token and id of the Discord channel into the config file

## Problems/Edge Cases

- There was a situation where a streamer was online but they weren't showing up in any directories on the site(game category, following list) and they weren't showing up as live on the Twitch API. This script won't detect the streamer as live since it relies on the Twitch API.

## Background Info
I decided to make this because all of the other tools I've seen that automatically archive Twitch streams use streamlink to determine when a stream goes live. This is a problem for me since, for some channels, I only want to download the stream if they are playing a certain game. Although in this script, the games you want to record apply to all streamers except the forced streamers. I was using an older version of a tool which was still querying the Twitch API to determine if a streamer was live. I modified the tool to also check what category the streamer is under but the tool used ffmpeg to record the streams which would have ads at the beginning of the recording and that would mess up the audio for some channels. 