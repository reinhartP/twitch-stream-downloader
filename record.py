import logging
import requests
import os
import yaml
import time
import configparser
import json
import traceback
import subprocess
from timeit import default_timer as timer
from streamer import Streamer
from api import API as twitch
from discord_bot import Bot

logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("discord").setLevel(logging.ERROR)


class Record:
    def __init__(self):
        self.__current_directory = os.path.dirname(os.path.realpath(__file__))
        self.__config_path = os.path.join(self.__current_directory, "config.ini")
        self.__config = configparser.ConfigParser()
        self.__config.read(self.__config_path)
        self.__discord_webhook = self.__config["discord"]["webhook"]
        self.__verbosity = int(self.__config["default"]["verbosity"])
        logging.basicConfig(
            filename=os.path.join(self.__current_directory, "app.log"),
            format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.INFO,
        )

        self.__streamers = dict()
        self.__streamer_ids = dict()
        self.__forced_streamers = json.loads(
            self.__config["streamers"]["forced_streamers"]
        )
        self.__paused_streamers = json.loads(self.__config["streamers"]["paused"])
        self.__capture_directory = os.path.normpath(
            self.__config["default"]["capture_directory"]
        )
        self.__complete_directory = os.path.normpath(
            self.__config["default"]["complete_directory"]
        )
        self.__client_id = self.__config["twitchapi"]["client_id"]
        self.__client_secret = self.__config["twitchapi"]["client_secret"]
        self.__helix = twitch(
            self.__client_id,
            self.__client_secret,
            self.__config["twitchapi"]["bearer_token"],
            self.__config.getfloat("twitchapi", "expires"),
        )
        self.__bearer_token_expiration = self.__helix.get_bearer_token_expiration()
        self.__bearer_token = self.__helix.get_bearer_token()
        self.__restrict_games = self.__config.getboolean(
            "twitch_categories", "restrict"
        )
        self.__games = json.loads(self.__config["twitch_categories"]["games"])

        self.__online = []
        self.__offline = []
        self.__recording = []
        self.__create_streamers()
        self.__bot_enable = self.__config["discord"]["bot_enable"]
        if self.__bot_enable:
            self.__bot_token = self.__config["discord"]["bot_token"]
            self.__bot_channel_id = self.__config["discord"]["bot_channel_id"]
            self.__status_msg_id = self.__config["discord"]["status_msg_id"]
        self.__bot = Bot(
            bot_token=self.__bot_token,
            channel_id=self.__bot_channel_id,
            msg_id=self.__status_msg_id,
            embed_template={
                "title": "Status",
                "description": "**Recording**: {recording}\n\n**Online**: {online}\n\n**Offline**: {offline}\n\n**Paused**: {paused}",
                "color": 7506394,
            },
        )

    def __create_streamers(self):
        streamers = self.__load_streamers()
        streamer_ids = self.__get_streamers_id(streamers)
        for streamer in streamers:
            streamer_name = streamer.lower()
            self.__streamers[streamer_name] = Streamer(
                streamer_name,
                self.__capture_directory,
                streamer_ids.get(streamer_name),
                self.__complete_directory,
            )

    def __load_streamers(self):
        return json.loads(self.__config["streamers"]["streamers"])

    def __get_streamers_id(self, streamers):
        if time.time() > self.__bearer_token_expiration:
            self.__update_bearer_token()

        params = {"login": streamers}

        response = self.__helix.request(
            "GET", "https://api.twitch.tv/helix/users", params=params
        )

        streamers_with_id = dict()
        for streamer in response["data"]:
            streamers_with_id[streamer["login"]] = streamer["id"]
            self.__streamer_ids[streamer["id"]] = streamer["login"]
        return streamers_with_id

    def __update_discord(self):
        # self.__bot.set_statuses(self.__recording, self.__online, self.__offline)
        self.__paused_streamers.sort()
        self.__status_msg_id = self.__bot.update_discord(
            recording=self.__bot.format_discord_list(self.__recording),
            online=self.__bot.format_discord_list(self.__online),
            offline=self.__bot.format_discord_list(self.__offline),
            paused=self.__bot.format_discord_list(self.__paused_streamers),
        )
        self.__config["discord"]["status_msg_id"] = self.__status_msg_id
        self.__update_config()

    def __read_config(self):
        logger.debug("updating streamers from file")
        self.__config.read(self.__config_path)
        try:
            self.__verbosity = self.__config.getint("default", "verbosity")
            self.__max_file_size = self.__config.getfloat("default", "max_file_size")
            self.__paused_streamers = json.loads(self.__config["streamers"]["paused"])
            streamers = json.loads(self.__config["streamers"]["streamers"])
            forced_streamers = json.loads(
                self.__config["streamers"]["forced_streamers"]
            )
            include = json.loads(self.__config.get("streamers", "include"))
            exclude = json.loads(self.__config["streamers"]["exclude"])
            force_include = json.loads(self.__config["streamers"]["force_include"])
            force_exclude = json.loads(self.__config["streamers"]["force_exclude"])
        except json.decoder.JSONDecodeError:
            print(
                "Error updating streamers. Make sure to encase streamer name in quotations."
            )
            return None
        if len(include) > 0:
            # add to self.__streamers
            streamer_ids = self.__get_streamers_id(include)
            for streamer in include:
                streamer_name = streamer.lower()
                if streamer_name not in self.__streamers:
                    streamers.append(streamer_name)
                    self.__streamers[streamer_name] = Streamer(
                        streamer_name,
                        self.__capture_directory,
                        streamer_ids.get(streamer_name),
                        self.__complete_directory,
                    )
        if len(exclude) > 0:
            # Remove from self.__streamers, streamers, and forced_streamers
            for streamer in exclude:
                streamer_name = streamer.lower()
                if streamer_name in self.__streamers:
                    try:
                        temp_streamer = self.__streamers.get(streamer_name)
                        if temp_streamer.get_recording_status() == True:
                            temp_streamer.stop_recording()
                        del self.__streamers[streamer_name]
                        streamers.remove(streamer_name)
                        forced_streamers.remove(streamer_name)
                        self.__forced_streamers.remove(streamer_name)
                    except ValueError:
                        pass
        if len(force_include) > 0:
            # add to self.__streamers and forced_streamers
            streamer_ids = self.__get_streamers_id(force_include)
            for streamer in force_include:
                streamer_name = streamer.lower()
                if streamer_name not in forced_streamers:
                    forced_streamers.append(streamer_name)
                    self.__forced_streamers.append(streamer_name)
                if streamer_name not in streamers:
                    streamers.append(streamer_name)
                    self.__streamers[streamer_name] = Streamer(
                        streamer_name,
                        self.__capture_directory,
                        streamer_ids.get(streamer_name),
                        self.__complete_directory,
                    )
        if len(force_exclude) > 0:
            # remove from self.__forced_streamers
            for streamer in force_exclude:
                streamer_name = streamer.lower()
                if streamer_name in forced_streamers:
                    forced_streamers.remove(streamer_name)
                if streamer_name in self.__forced_streamers:
                    self.__forced_streamers.remove(streamer_name)

        self.__config["streamers"]["streamers"] = json.dumps(streamers)
        self.__config["streamers"]["forced_streamers"] = json.dumps(forced_streamers)
        self.__config["streamers"]["include"] = json.dumps([])
        self.__config["streamers"]["exclude"] = json.dumps([])
        self.__config["streamers"]["force_include"] = json.dumps([])
        self.__config["streamers"]["force_exclude"] = json.dumps([])
        self.__update_config()

    def __update_config(self):
        with open(self.__config_path, "w") as f:
            self.__config.write(f)

    def __update_bearer_token(self):
        self.__bearer_token = self.__helix.get_bearer_token()
        self.__bearer_token_expiration = self.__helix.get_bearer_token_expiration()
        self.__config.read(self.__config_path)
        self.__config["twitchapi"]["expires"] = self.__bearer_token_expiration
        self.__config["twitchapi"]["bearer_token"] = self.__bearer_token
        self.__update_config()

    def __update_streamer_status(self):
        """
            Check which streamers are online. Querying the endpoint returns which streamers are live, if they are
            offline they aren't included in the response.
            If the streamer is online, mark them as online.
            If the streamer is offline, mark them as offline
        """
        if time.time() > self.__bearer_token_expiration:
            self.__update_bearer_token()

        streamers = list(self.__streamers.keys())

        params = {"user_login": streamers}
        response = self.__helix.request(
            "GET", "https://api.twitch.tv/helix/streams", params=params
        )

        try:
            # Go through streamers that are live
            if len(response["data"]) > 0:
                for streamer in response["data"]:
                    # get username from id
                    # twitch returns local name so it may return foreign characters
                    username = self.__streamer_ids[streamer["user_id"]]
                    if username not in self.__paused_streamers and (
                        self.__restrict_games is False
                        or streamer.get("game_id") in self.__games
                        or username in self.__forced_streamers
                    ):
                        self.__streamers[username].set_live_status(True)
                        streamers.remove(username)
            # set remaining streamers to offline
            for username in streamers:
                self.__streamers[username].set_live_status(False)
        except KeyError as e:
            print(f"keyerror {response}")
            print(e.args[0])
            time.sleep(30)

    def __handle_recording(self, streamer) -> int:
        """
            If the streamer is live, check if recording, if not then start recording
            If the streamer is offline, check if recording, if it is recording then stop recording
            Returns -1 if recording stopped, 0 if nothing happened, 1 if recording started, 2 if file size exceeded max(stop and start recording)
        """
        current_time = self.__get_current_time()
        streamer_name = streamer.get_name()

        live_status = streamer.get_live_status()
        recording_status = streamer.get_recording_status()
        logger.debug(
            f"{streamer_name:16} - live: {str(live_status):5} - recording: {str(recording_status)}"
        )
        if live_status == True and recording_status == False:
            # print(f"\n----------[{self.__get_current_time()}] {streamer_name} recording started----------\n")
            streamer.start_recording()
            self.__recording.append(streamer.get_name())
            return 1
        elif live_status == False and recording_status == True:
            # print(f"\n----------[{current_time}] {streamer_name} offline----------\n")
            streamer.stop_recording()
            self.__recording.remove(streamer.get_name())
            return -1
        elif recording_status == True and self.__check_file_size(streamer):
            print(
                f"\n----------[{current_time}] {streamer_name} file size exceeded. Restarting recording----------\n"
            )
            streamer.stop_recording()
            streamer.start_recording()
            return 2
        return 0

    def __check_file_size(self, streamer):
        try:
            file_size = os.stat(
                os.path.join(self.__capture_directory, streamer.get_filename())
            ).st_size
            logger.debug(f"{streamer.get_filename} is {file_size/(1024*1024)}MB")
            if self.__max_file_size != 0 and file_size < (
                1024 * 1024 * 1024 * self.__max_file_size
            ):
                return False
        except FileNotFoundError:
            # file was most likely deleted by user. return true which restarts recording
            logger.error(
                f"{streamer.get_filename()} not found. probably deleted by user"
            )
            pass
        return True

    def __find_differences_in_lists(self, bigger, smaller):
        """
            Finds what's different in the "bigger" list (bigger list can be the same size as smaller)
            [2,3,4] and [2,1,4] returns [3]
            [2,1,4] and [2,3,4] returns [1]
        """
        differences = []
        for element in bigger:
            if element not in smaller:
                differences.append(element)
        return differences

    def __format_list(self, list_to_format):
        output = ""
        for idx, element in enumerate(list_to_format):
            if idx > 0:
                output += ", "
            output += element
        return output

    def __get_changes(self, new, old):
        """
            Finds changes in lists to determine who went online/offline or started/stopped recording.

            Parameters:
            new (list): The most updated version of a list
            old (list): The previous version of a list
        """
        started = []
        stopped = []
        if len(new) < len(old):
            # streamers who went offline or stopped recording
            stopped = self.__find_differences_in_lists(old, new)
        elif len(new) > len(old):
            # streamers who went online or started recording
            started = self.__find_differences_in_lists(new, old)
        elif len(new) == len(old):
            # unlikely situtation. same amount of streamers go online and offline at the same time
            stopped = self.__find_differences_in_lists(old, new)
            started = self.__find_differences_in_lists(new, old)

        return started, stopped

    def __status_changes(self, online, offline, recording):
        """
            If online gets smaller than find out who went offline
            If online gets bigger than find out who went online
            If streamers gets bigger find out who was added
            if streamers gets smaller find out who was removed
        """
        went_online, went_offline = self.__get_changes(online, self.__online)
        started_recording, stopped_recording = self.__get_changes(
            recording, self.__recording
        )
        self.__online = online.copy()
        self.__offline = offline.copy()
        self.__recording = recording.copy()
        self.__update_discord()
        if (  # no changes
            len(went_online) == 0
            and len(went_offline) == 0
            and len(started_recording) == 0
            and len(stopped_recording) == 0
        ):
            return
        self.__print_status_changes(
            went_online, went_offline, started_recording, stopped_recording
        )

    def __print_status_changes(
        self, went_online, went_offline, started_recording, stopped_recording
    ):
        if len(went_online) > 0 and self.__verbosity < 2:
            print(
                f"\n----------[{self.__get_current_time()}] {self.__format_list(went_online)} went online----------\n"
            )
        if len(went_offline) > 0 and self.__verbosity < 2:
            print(
                f"\n----------[{self.__get_current_time()}] {self.__format_list(went_offline)} went offline----------\n"
            )
        if len(started_recording) > 0 and self.__verbosity < 2:
            print(
                f"\n----------[{self.__get_current_time()}] {self.__format_list(started_recording)} started recording----------\n"
            )
        if len(stopped_recording) > 0 and self.__verbosity < 2:
            print(
                f"\n----------[{self.__get_current_time()}] {self.__format_list(stopped_recording)} stopped recording----------\n"
            )
        print(f"recording: {self.__recording}")
        if self.__verbosity < 2:
            print(f"online:  {self.__online}")
        if self.__verbosity < 1:
            print(f"offline: {self.__offline}")

    def start(self):
        while True:
            temp_online = []
            temp_offline = []
            temp_recording = []
            self.__read_config()
            try:
                self.__update_streamer_status()
                for key, streamer in self.__streamers.items():
                    recording_status = self.__handle_recording(streamer)
                    if streamer.get_live_status() == True:
                        if streamer.get_recording_status() == True:
                            temp_recording.append(streamer.get_name())
                        temp_online.append(streamer.get_name())
                    elif streamer.get_name() not in self.__paused_streamers:
                        temp_offline.append(streamer.get_name())
                temp_online.sort()
                temp_offline.sort()
                temp_recording.sort()
                self.__status_changes(temp_online, temp_offline, temp_recording)
            except requests.exceptions.ConnectionError:
                logger.error("requests.exception.ConnectionError", exc_info=True)
                pass
            time.sleep(5)

    def cleanup(self):
        for key, streamer in self.__streamers.items():
            if streamer.get_recording_status() == True:
                streamer.stop_recording()

    def __get_current_time(self):
        return time.strftime("%H:%M:%S")

    def get_discord_Webhook(self):
        return self.__discord_webhook


if __name__ == "__main__":
    record = Record()
    try:
        record.start()
    except KeyboardInterrupt:
        print("program exiting. cleaning up...")
        record.cleanup()
    except:
        discord_webhook = record.get_discord_Webhook()
        if discord_webhook != "":
            body = {
                "username": "twitch_recorder_bot",
                "content": "fatal error caused script to exit.",
                "embeds": [
                    {
                        "title": "Error",
                        "description": f"{traceback.format_exc()}",
                        "color": 7506394,
                    },
                ],
            }
            try:
                requests.post(
                    discord_webhook,
                    headers={"Content-Type": "application/json"},
                    json=body,
                )
            except:
                logger.error("error occured while posting to discord.", exc_info=True)
                pass
        logger.fatal("fatal error occured.", exc_info=True)
        print("some error occurred. cleaning up before exiting")
        record.cleanup()
