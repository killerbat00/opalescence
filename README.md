# :gem: opalescence :gem:

Opalescence is a torrent client written in Python with asyncio.

It was originally started to explore new features in Python 3.6+ and learn more about asyncio, unittests, and more
complex system architecture.

Current capabilities:

1. Download a specified .torrent file, piece by piece employing a naive sequential, tit-for-tat piece requesting
   strategy without unchoking remote peers. Opalescence checks for existing files in the given destination and will only
   download what's necessary.

## Installing Opalescence

clone this repository

`$ git clone https://github.com/killerbat00/opalescence.git`

install using pip

`$ pip install -e <path-to-opalescence>`

install using poetry
`$ poetry install`

## Using Opalescence

download a torrent

`$ python -m opalescence download <.torrent-file> <destination>`

## Testing Opalescence

`$ python -m opalescence test`

[The philosophy of Opalescence](philosophy.md)

