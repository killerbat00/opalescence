# -*- coding: utf-8 -*-

"""
Command Line Interface for Opalescence
"""

import asyncio
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

    def __init__(self, interval: float = 1.25):
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

            tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            self.active_tasks = len(tasks)
            print(f"{self.lag} lag. {self.active_tasks} running tasks.")


def handle_exception(_, context):
    exc = context.get("exception", context["message"])
    print(f"Unhandled exception {type(exc).__name__}")
    asyncio.create_task(shutdown())


async def shutdown(raised_sig=None):
    if raised_sig:
        print(f"Received signal {raised_sig.name}. Shutting down.")
    else:
        print(f"Shutting down. Not due to a signal.")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _download(torrent_fp, dest_fp):
    print(f"Downloading {torrent_fp.name} to {dest_fp}")

    loop = asyncio.get_event_loop()
    loop.set_debug(__debug__)

    client = Client()
    monitor = Monitor()

    for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            s, lambda x=s: asyncio.create_task(shutdown(x))
        )
    loop.set_exception_handler(handle_exception)

    def print_stats(t):
        print(f"{t.name} progress: {t.pct_complete}% "
              f"\t({t.present}/{t.total_size} bytes)"
              f"\t{t.num_peers} peers."
              f"\t{t.average_speed} KB/s average"
              f"\t{round(loop.time() - t.download_started)}s elapsed.")

    add_results = client.add_torrent(torrent_fp=torrent_fp, destination=dest_fp)
    if not add_results:
        print(f"Unable to add download {torrent_fp}")
        raise SystemExit
    torrent, complete_event = add_results

    client.start()
    monitor.start()
    try:
        while not complete_event.is_set():
            msg = None
            if not client._running:
                msg = "Client stopped."
            if torrent.status in [DownloadStatus.Errored, DownloadStatus.Stopped]:
                msg = f"{torrent.name} {torrent.status}."

            print_stats(torrent)

            if msg:
                print(msg)
                break
            await asyncio.sleep(1)
        else:
            print(f"{torrent.name} complete!")

    finally:
        print_stats(torrent)
        client.stop()
