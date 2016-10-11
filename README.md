# opalescence

One day this project will grow to be a humble, yet useful torrent client.
A torrent client that strives not to impress, but rather to just...exist.

Currently, it's a glorified bencoder and torrent creation machine. (with tests!)

#TODO
- [x] refactor torrent creation from path
- [x] simplify torrent translation lifecycle (textfile -> pyobject -> Torrent)
- [x] more effective torrent dictionary verification
- [x] better logging
- [ ] get rid of dependency on weird config.py file
- [ ] better tests


### add functionality for:
- [x] specifying path/dir from which to create .torrent from cli
- [x] specifying path to which to save .torrent
- [x] specifying .torrent name
- [x] specifying optional .torrent options (piece_size, etc)


#### far in the future functionality:
- [ ] diffing between Torrents?
- [ ] tracker comm
- [ ] ui?
