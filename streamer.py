import time
import subprocess
import os
import logging

logger = logging.getLogger(__name__)


class Streamer:
    def __init__(self, name: str, capture_path: str, id: int, complete_path: str):
        self.__name = name
        self.__capture_path = capture_path
        self.__complete_path = complete_path
        self.__id = id
        self.__live = False
        self.__recording = False
        self.__process = None
        self.__filename = None
        logger.debug(f"Created Streamer object for {name}")

    def start_recording(self):
        file_time = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.__filename = f"twitch_{self.__name}_{file_time}.ts"
        self.__process = subprocess.Popen(
            [
                "streamlink",
                "-o",
                f"{os.path.join(self.__capture_path, self.__filename)}",
                "--twitch-disable-hosting",
                "--twitch-disable-reruns",
                "--twitch-disable-ads",
                "--force",
                f"twitch.tv/{self.__name}",
                "best",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.__recording = True
        logger.debug(
            f"Started recording for {self.__name} ({self.__process.pid}) - {self.__filename}"
        )

    def stop_recording(self):
        self.__process.terminate()
        self.__process = None
        self.__recording = False
        time.sleep(2)
        try:
            os.rename(
                os.path.join(self.__capture_path, self.__filename),
                os.path.join(self.__complete_path, self.__filename),
            )
        except FileNotFoundError:
            logger.error(f"{self.__filename} not found. probably deleted by user")
            pass

        logger.debug(f"Stopped recording for {self.__name} - {self.__filename}")

        self.__filename = None

    def __get_current_time(self) -> str:
        return time.strftime("%H:%M:%S")

    def check_recording_process(self):
        """
            Check if the recording process has exited
        """
        if self.__process is not None and self.__process.poll() is not None:
            # recording process has exited, most likely streamer went offline and api hasn't updated yet
            logger.info(
                f"{self.__name} - {self.__filename} recording process has exited."
            )
            self.stop_recording()

    def set_live_status(self, status: bool):
        self.__live = status

    def get_live_status(self):
        return self.__live

    def get_recording_status(self):
        return self.__recording

    def get_process(self):
        return self.__process

    def get_name(self) -> str:
        return self.__name

    def get_filename(self) -> str:
        return self.__filename

    def get_id(self) -> int:
        return self.__id
