import asyncio
import logging
from pathlib import Path
from typing import Optional, IO

from .metainfo import MetaInfoFile, FileItem
from .protocol.peer import PeerInfo, PeerConnection, Piece
from .protocol.piece_handler import FileWriter, PieceRequester
from .tracker import TrackerManager, TrackerConnectionError

logger = logging.getLogger(__name__)
MAX_PEER_CONNECTIONS = 5


class DownloadError(Exception):
    pass


class Complete(Exception):
    pass


class Download:
    """
    A torrent currently being downloaded by the Client.
    This wraps the tracker, requester, and peers into a single API.
    """

    def __init__(self, torrent: MetaInfoFile, destination: Path, local_peer: PeerInfo):
        self.client_info = local_peer
        self.present: Optional[list[Piece]] = None  # pieces we have
        self.missing: Optional[list[Piece]] = None  # pieces we are missing
        self.all_pieces: list[Piece] = []
        self.torrent: MetaInfoFile = torrent
        self.destination = destination
        self.stats = {"uploaded": 0, "downloaded": 0, "left": torrent.total_size, "started": 0.0}
        self.tracker = TrackerManager(self.client_info, torrent, self.stats)
        self.peer_q = asyncio.Queue()
        self.writer = FileWriter(torrent, destination)
        self.peers = []
        self.abort = False
        self.task = None

        def download_complete():
            self.stop()
            total_time = asyncio.get_event_loop().time() - self.stats['started']
            log = logging.getLogger("opalescence")
            old_level = log.getEffectiveLevel()
            logger.setLevel(logging.INFO)
            logger.info(f"Download stopped! Took {round(total_time, 5)}s")
            logger.info(f"Downloaded: {self.stats['downloaded']} Uploaded: {self.stats['uploaded']}")
            logger.info(f"Est download speed: "
                        f"{round((self.stats['downloaded'] / total_time) / 2 ** 20, 2)} MB/s")
            log.setLevel(old_level)

            if self.writer:
                self.writer.close_files()

        self.download_complete_cb = download_complete
        self.requester = PieceRequester(torrent, self.writer, self.download_complete_cb, self.stats)

    def stop(self):
        if self.task:
            self.task.cancel()

    def download(self):
        self.present = []
        self.missing = []
        self.check_pieces()
        logger.info(f"We have: {self.present}")
        logger.info(f"We need: {self.missing}")
        if len(self.present) == self.torrent.num_pieces:
            raise Complete
        self.stats["started"] = asyncio.get_event_loop().time()
        self.task = asyncio.create_task(self.download_coro(), name=f"Download for {self.torrent}")
        return self.task

    def _file_for_offset(self, offset: int) -> tuple[int, FileItem, int]:
        """
        :param offset: the contiguous offset of the piece (as if all files were concatenated together)
        :return: (file_num, FileItem, file_offset)
        """
        size_sum = 0
        for i, file in self.torrent.files.items():
            if offset - size_sum < file.size:
                file_offset = offset - size_sum
                return i, file, file_offset
            size_sum += file.size

    def _create_shell_pieces(self):
        for pc in range(self.torrent.num_pieces):
            piece_length = self.torrent.piece_length
            if pc == self.torrent.num_pieces - 1:
                piece_length = self.torrent.total_size - (pc * piece_length)

            self.all_pieces.append(Piece(pc, piece_length))

    def _load_single_piece(self, piece: Piece, fps: dict[int, IO]) -> Piece:
        p = Piece(piece.index, piece.length)
        file_index, _, offset = self._file_for_offset(p.index * self.torrent.piece_length)
        fp = fps[file_index]
        if fp is None:
            return p
        fp.seek(offset)
        piece_data = fp.read(p.length)
        if len(piece_data) == piece.length:
            p.data = piece_data
            return p
        fp = fps[file_index + 1]
        if fp is None:
            return p
        fp.seek(0)
        piece_data += fp.read(p.length - len(piece_data))
        if len(piece_data) == piece.length:
            p.data = piece_data
            return p
        return p

    def _verify_pieces(self, fps: dict[int, IO]):
        for i, piece in enumerate(self.all_pieces):
            p = self._load_single_piece(piece, fps)
            if not p.complete:
                self.missing.append(piece)
            else:
                if p.hash() == self.torrent.piece_hashes[i]:
                    self.present.append(piece)
                else:
                    self.missing.append(piece)

    def check_pieces(self):
        """
        Checks which pieces already exist on disk and which need to be downloaded.
        :return:
        """
        fps = {}
        try:
            for i, file in self.torrent.files.items():
                filepath = self.destination / file.path
                if not filepath.exists():
                    fps[i] = None
                else:
                    fps[i] = open(filepath, 'rb')
        except:
            raise DownloadError

        self._create_shell_pieces()
        self._verify_pieces(fps)

        for _, fp in fps.items():
            if fp is not None:
                fp.close()

    async def download_coro(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        TODO: needs work
        """
        previous = None
        interval = self.tracker.DEFAULT_INTERVAL
        self.peers = [PeerConnection(self.client_info, self.torrent.info_hash, self.requester, self.peer_q)
                      for _ in range(MAX_PEER_CONNECTIONS)]

        try:
            while True:
                if self.requester.complete:
                    await self.tracker.completed()
                    self.download_complete_cb()
                    break

                if self.abort:
                    logger.info(f"Aborting download of {self.torrent.name}. Downloaded {self.stats['downloaded']} "
                                f"bytes")
                    await self.tracker.cancel()
                    self.download_complete_cb()
                    break

                current = asyncio.get_running_loop().time()
                if (not previous) or (previous + interval < current):
                    try:
                        response = await self.tracker.announce()
                    except TrackerConnectionError:
                        self.abort = True
                        continue

                    if response:
                        previous = current
                        if response.interval:
                            interval = response.interval

                        while not self.peer_q.empty():
                            self.peer_q.get_nowait()

                        for peer in response.get_peers():
                            if peer[0] == self.client_info.ip:
                                if peer[1] == self.client_info.port:
                                    logger.info(f"Ignoring peer. It's us...")
                                    continue
                            self.peer_q.put_nowait(PeerInfo(peer[0], peer[1]))
                else:
                    await asyncio.sleep(interval)
        except (asyncio.CancelledError, Exception) as e:
            if not isinstance(e, asyncio.CancelledError):
                logger.debug(f"{type(e).__name__} exception received in client.download.")
                logger.exception(e, exc_info=True)
                logger.info(f"Downloaded: {self.stats['downloaded']} Uploaded: {self.stats['uploaded']}")
            else:
                self.download_complete_cb()
                await self.tracker.cancel()
        finally:
            logger.debug(f"Ending download loop. Cleaning up.")
            for peer in self.peers:
                peer.stop_forever()
