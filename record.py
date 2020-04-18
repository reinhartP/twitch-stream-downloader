import logging
import requests
import os
import yaml
import time
import configparser
import json
import traceback
from streamer import Streamer
from api import API as twitch

logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class Record:
    def __init__(self):
        self.__current_directory = os.path.dirname(os.path.realpath(__file__))
        self.__config_path = os.path.join(self.__current_directory, "config.ini")
        self.__config = configparser.ConfigParser()
        self.__config.read(self.__config_path)
        self.__discord_webhook = self.__config["default"]["discord_webhook"]
        logging.basicConfig(
            filename=os.path.join(self.__current_directory, "app.log"),
            format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.WARNING,
        )

        self.__streamers = dict()
        self.__streamer_ids = dict()
        self.__forced_streamers = []
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
        self.__load_streamers()

    def __load_streamers(self):
        streamers = json.loads(self.__config["streamers"]["streamers"])
        self.__forced_streamers = json.loads(
            self.__config["streamers"]["forced_streamers"]
        )
        streamer_ids = self.__get_streamers_id(streamers)
        for streamer in streamers:
            streamer_name = streamer.lower()
            self.__streamers[streamer_name] = Streamer(
                streamer_name,
                self.__capture_directory,
                streamer_ids.get(streamer_name),
                self.__complete_directory,
            )

    def __update_streamers(self):
        logging.info("updating streamers from file")
        self.__config.read(self.__config_path)
        try:
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
            """
                Remove from self.__streamers
                Remove from streamers
                Remove from forced_streamers
            """
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

        params = {"user_login": self.__streamers}

        response = self.__helix.request(
            "GET", "https://api.twitch.tv/helix/streams", params=params
        )

        current_time = self.__get_current_time()

        try:
            streamers = list(self.__streamers.keys())
            if len(response["data"]) > 0:
                for streamer in response["data"]:  # go through online streamers
                    username = self.__streamer_ids[streamer["user_id"]]
                    if (
                        self.__restrict_games == False
                        or streamer.get("game_id") in self.__games
                        or username in self.__forced_streamers
                    ):
                        self.__streamers[username].set_live_status(True)
                        streamers.remove(username)
                for streamer in streamers:
                    self.__streamers[streamer].set_live_status(False)
            else:
                for streamer in streamers:
                    self.__streamers[streamer].set_live_status(False)
        except KeyError as e:
            print(f"keyerror {response}")
            print(e.args[0])
            time.sleep(30)

    def __check_recording(self, streamer) -> int:
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
            print(f"[{current_time}] {streamer_name} recording started")
            streamer.start_recording()
            return 1
        elif live_status == False and recording_status == True:
            print(f"[{current_time}] {streamer_name} offline")
            streamer.stop_recording()
            return -1
        elif recording_status == True and self.__check_file_size(streamer):
            print(
                f"[{current_time}] {streamer_name} file size exceeded. Restarting recording."
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
            if file_size > (1024 * 1024 * 1024 * 8.25):
                return True
        except FileNotFoundError:
            # file was most likely deleted by user. return false which restarts recording
            logger.error(f"{streamer.get_filename} not found. probably deleted by user")
            pass
        return False

    def __find_differences_in_lists(self, bigger, smaller):
        differences = []
        for element in bigger:
            if element not in smaller:
                differences.append(element)
        return differences

    def __status_changes(self, online, offline):
        """
            If online gets smaller than find out who went offline
            If online gets bigger than find out who went online
            If streamers gets bigger find out who was added
            if streamers gets smaller find out who was removed
        """
        online_or_offline = "online"
        if len(online) < len(self.__online):
            # differences are streamers who went offline
            online_or_offline = "offline"
            differences = self.__find_differences_in_lists(self.__online, online)
        elif len(online) > len(self.__online):
            # differences are streamers who went online
            differences = self.__find_differences_in_lists(online, self.__online)
        else:
            return 0

        changed_streamers = ""
        for idx, difference in enumerate(differences):
            if idx > 0:
                changed_streamers += ", "
            changed_streamers += difference
        self.__online = online.copy()
        self.__offline = offline.copy()
        print(
            f"\n----------[{self.__get_current_time()}] {changed_streamers} went {online_or_offline}----------\n"
        )
        print(f"online:  {online}")
        print(f"offline: {offline}")

    def start(self):
        while True:
            temp_online = []
            temp_offline = []
            self.__update_streamers()
            try:
                self.__update_streamer_status()
                for key, streamer in self.__streamers.items():
                    recording_status = self.__check_recording(streamer)
                    if streamer.get_live_status() == True:
                        temp_online.append(streamer.get_name())
                    else:
                        temp_offline.append(streamer.get_name())
                temp_online.sort()
                temp_offline.sort()
                self.__status_changes(temp_online, temp_offline)
            except ConnectionError as e:
                logger.error("fatal error occured.", exc_info=True)
                pass

            time.sleep(15)

    def cleanup(self):
        for key, streamer in self.__streamers.items():
            if streamer.get_recording_status() == True:
                streamer.stop_recording()

    def __get_current_time(self):
        return time.strftime("%H:%M:%S")

    def get_discord_Webhook(self):
        return self.__discord_webhook


if __name__ == "__main__":
    logger.info("program start")
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
            requests.post(
                discord_webhook, headers={"Content-Type": "application/json"}, json=body
            )
        logger.fatal("fatal error occured.", exc_info=True)
        print("some error occurred. cleaning up before exiting")
        record.cleanup()
