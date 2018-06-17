# Philosophy of Opalescence
1. Variable names should be complete.
2. Classes should provide a clean API.
3. Don't hide functionality.
4. Don't store state for one object in another object.
5. Log events before they occur so failueres are more easily debugged.
6. Only catch the most relevant Exceptions.

## Philosophy of Architecture
1. Each object should have one responsibility to fulfill.
2. `opalescence.btlib.tracker.Tracker` is responsible for announcing our current state to the tracker.
3. `opalescence.btlib.protocol.peer.Peer` is responsible for communicating with a peer. It exchanges ``Message``s, asking the ``Requester`` for help when necessary.
4. `opalescence.btlib.protocol.piece_handler.Requester` is responsible for keeping track of pieces and requesting.
5. `opalescence.btlib.protocol.piece_handler.Writer` is responsible for writing pieces to disk.
6. `opalescence.btlib.client.Client` is responsible for downloading a torrent. It handles communication between the torrent's tracker, local peers, and remote peers.

