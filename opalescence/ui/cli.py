# -*- coding: utf-8 -*-

"""
Command Line Interface for Opalescence
"""

import asyncio
import functools
import signal
from pathlib import Path

from opalescence.btlib.client import Client
from opalescence.btlib.torrent import DownloadStatus


def download(args) -> None:
    """
    Main entrypoint for the CLI.
    Downloads a .torrent file

    :param args: .torrent filepath argparse.Namespace object
    """
    torrent_fp: Path = args.torrent_file
    dest_fp: Path = args.destination

    if not torrent_fp.exists():
        print("Torrent filepath does not exist.")
        raise SystemExit
    if dest_fp.exists() and dest_fp.is_file():
        print(f"Destination filepath is not a directory.")
        raise SystemExit
    if not dest_fp.exists():
        try:
            print(f"Destination filepath does not exist. Creating {dest_fp}")
            dest_fp.mkdir(parents=True)
        except Exception:
            print(f"Unable to create filepath {dest_fp}")

    asyncio.run(_download(torrent_fp, dest_fp))


class Monitor:
    lag: float = 0
    active_tasks: int = 0

    def __init__(self, interval: float = 0.25):
        self._interval = interval

    def start(self):
        loop = asyncio.get_running_loop()
        loop.create_task(self._monitor(loop))

    async def _monitor(self, loop):
        while loop.is_running():
            start = loop.time()
            await asyncio.sleep(self._interval)
            time_sleeping = loop.time() - start
            self.lag = time_sleeping - self._interval

            tasks = [t for t in asyncio.Task.all_tasks(loop) if not t.done()]
            self.active_tasks = len(tasks)


async def _download(torrent_fp, dest_fp):
    print(f"Downloading {torrent_fp.name} to {dest_fp}")

    loop = asyncio.get_event_loop()
    loop.set_debug(__debug__)
    client = Client()

    def signal_received(s):
        print(f"{s} received. Shutting down...")
        client.stop()

    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame),
                                functools.partial(signal_received, signame))

    def print_stats(t):
        print(f"{t.name} progress: {t.pct_complete}% "
              f"\t({t.present}/{t.total_size} bytes)"
              f"\t{t.num_peers} peers."
              f"\t{t.average_speed} KB/s average"
              f"\t{round(asyncio.get_event_loop().time() - t.download_started)}s elapsed.")

    client.add_torrent(torrent_fp=torrent_fp, destination=dest_fp)
    try:
        client.start()
        q = False
        while not q:
            for torrent in client.downloading:
                if torrent.status == DownloadStatus.Completed:
                    print(f"{torrent.name} complete.")
                    print_stats(torrent)
                    q = True
                    break

                if torrent.status == DownloadStatus.Errored:
                    print(f"{torrent.name} error.")
                    q = True
                    break

                if torrent.status == DownloadStatus.Stopped:
                    print(f"{torrent.name} stopped.")
                    q = True
                    break

                if not client._running:
                    print("Client stopped.")
                    q = True
                    break

                print_stats(torrent)
            if not q:
                await asyncio.sleep(1)
    finally:
        client.stop()
